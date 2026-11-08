"""Controlled examples only; these checks are not detection-quality estimates."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
import json
import unittest

from processing.energy_rules import EnergyRules, RuleConfig, evaluate
from processing.message_schema import InvalidMessage


START = datetime(2016, 1, 1)


def record(index, value=100.0, building='house', source='meter', start=START):
    return {
        'schema_version': '1.0', 'event_id': f'event-{index}',
        'building_id': building, 'source_id': source, 'source_type': 'dataset',
        'timestamp': (start + timedelta(minutes=10 * index)).isoformat(),
        'timezone': None, 'timestamp_reference': 'dataset_label', 'interval_seconds': 600,
        'energy': {'value': value, 'unit': 'Wh', 'scope': 'appliances',
                   'measurement_type': 'interval_energy'},
        'environment': {}, 'additional_parameters': {},
    }


def signal(result, name):
    return next(row for row in result['signals'] if row['rule'] == name)


def context_config(**kwargs):
    return RuleConfig(minimum_context_days=1, minimum_context_points=6, **kwargs)


def primed_context(config=None):
    # Synthetic constant prior day. Does not read or train on the Appliances data.
    engine = EnergyRules(config or context_config())
    for i in range(144):
        engine.process(record(i))
    return engine


class RuleConfigurationTests(unittest.TestCase):
    def test_defaults_and_configuration_are_versioned(self):
        self.assertEqual(RuleConfig().version, RuleConfig().version)
        self.assertNotEqual(RuleConfig().version, RuleConfig(high_intervals=3).version)
        self.assertEqual(EnergyRules().metadata()['calibration'], 'unvalidated_engineering_defaults')
        with self.assertRaises(FrozenInstanceError):
            RuleConfig().high_intervals = 1
        with self.assertRaises(AttributeError):
            EnergyRules().config = RuleConfig(high_intervals=3)

    def test_invalid_configuration_fails_before_processing(self):
        cases = [{'plateau_intervals': 1}, {'high_intervals': True}, {'context_days': 0},
                 {'context_days': 32}, {'minimum_context_days': 8},
                 {'minimum_context_points': 43}, {'minimum_excess_wh': -1},
                 {'mad_multiplier': float('nan')}, {'plateau_tolerance_wh': float('inf')},
                 {'minimum_relative_excess': True},
                 {'minimum_excess_wh': 0, 'minimum_relative_excess': 0, 'mad_multiplier': 0}]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                RuleConfig(**values)
        with self.assertRaises(TypeError):
            EnergyRules({})


class FlatlineTests(unittest.TestCase):
    def test_exact_six_intervals_and_no_retroactive_flag(self):
        results = evaluate([record(i) for i in range(7)])
        self.assertIsNone(signal(results[4], 'flatline')['flag'])
        found = signal(results[5], 'flatline')
        self.assertIs(found['flag'], True)
        self.assertEqual(found['evidence']['consecutive_intervals'], 6)
        self.assertEqual(found['evidence']['observed_label_span_seconds'], 3000)
        self.assertEqual(found['evidence']['represented_interval_seconds'], 3600)
        self.assertEqual(results[5]['measurement_timestamp'], '2016-01-01T00:50:00')
        self.assertEqual(signal(results[6], 'flatline')['evidence']['consecutive_intervals'], 7)

    def test_variation_and_return_to_normal_clear_flag(self):
        engine = EnergyRules()
        results = [engine.process(record(i, 100+i)) for i in range(6)]
        self.assertIs(signal(results[-1], 'flatline')['flag'], False)
        for i in range(6, 12):
            result = engine.process(record(i, 200))
        self.assertIs(signal(result, 'flatline')['flag'], True)
        result = engine.process(record(12, 201))
        self.assertIs(signal(result, 'flatline')['flag'], False)

    def test_zero_load_is_only_a_review_candidate(self):
        found = signal(evaluate([record(i, 0) for i in range(6)])[-1], 'flatline')
        self.assertTrue(found['flag'])
        self.assertEqual(found['semantics'], 'review_signal_not_confirmed_fault')
        self.assertIn('zero load', found['evidence']['interpretation'])

    def test_tolerance_uses_entire_range_not_transitive_neighbor_differences(self):
        config = RuleConfig(plateau_intervals=3, plateau_tolerance_wh=1)
        result = evaluate([record(i, value) for i, value in enumerate([10, 10.75, 11.5])], config)[-1]
        self.assertFalse(signal(result, 'flatline')['flag'])
        result = evaluate([record(i, value) for i, value in enumerate([10, 10.5, 11])], config)[-1]
        self.assertTrue(signal(result, 'flatline')['flag'])

    def test_gap_resets_duration(self):
        engine = EnergyRules()
        for i in range(6):
            engine.process(record(i))
        result = engine.process(record(8))
        self.assertIsNone(signal(result, 'flatline')['flag'])
        self.assertEqual(signal(result, 'flatline')['evidence']['consecutive_intervals'], 1)


class GapTests(unittest.TestCase):
    def test_first_point_is_unknown_not_a_gap_and_no_wall_clock_assumption(self):
        result = EnergyRules().process(record(0))
        self.assertIsNone(signal(result, 'interval_gap')['flag'])
        self.assertEqual(result['measurement_timestamp'], '2016-01-01T00:00:00')
        self.assertEqual(result['time_basis'], 'dataset_naive')

    def test_contiguous_then_two_missing_intervals(self):
        engine = EnergyRules()
        engine.process(record(0))
        self.assertFalse(signal(engine.process(record(1)), 'interval_gap')['flag'])
        result = signal(engine.process(record(4)), 'interval_gap')
        self.assertTrue(result['flag'])
        self.assertEqual(result['evidence']['missing_intervals'], 2)
        self.assertEqual(result['evidence']['expected_timestamp'], '2016-01-01T00:20:00')
        self.assertFalse(signal(engine.process(record(5)), 'interval_gap')['flag'])

    def test_nonintegral_gap_and_early_arrival_do_not_invent_missing_count(self):
        for minutes in (5, 15, 25):
            with self.subTest(minutes=minutes):
                engine = EnergyRules()
                engine.process(record(0))
                changed = record(1)
                changed['timestamp'] = (START + timedelta(minutes=minutes)).isoformat()
                found = signal(engine.process(changed), 'interval_gap')
                self.assertTrue(found['flag'])
                self.assertIsNone(found['evidence']['missing_intervals'])
                self.assertEqual(found['evidence']['reason'], 'irregular_cadence')


class SustainedHighTests(unittest.TestCase):
    def test_missing_context_is_null_not_false(self):
        found = signal(EnergyRules().process(record(0, 999)), 'sustained_high')
        self.assertEqual(found['status'], 'warmup')
        self.assertIsNone(found['flag'])
        self.assertNotIn('threshold_wh', found['evidence'])

    def test_default_three_day_requirement_and_same_hour_reference(self):
        engine = EnergyRules()
        # Different hours have legitimately different normal levels.
        for i in range(432):
            result = engine.process(record(i, 100 + 10*((i//6) % 24)))
        self.assertIsNone(signal(result, 'sustained_high')['flag'])
        result = signal(engine.process(record(432, 100)), 'sustained_high')
        self.assertFalse(result['flag'])
        self.assertEqual(result['evidence']['context_days'], 3)
        self.assertEqual(result['evidence']['context_points'], 18)
        self.assertEqual(result['evidence']['reference_median_wh'], 100)

    def test_strict_threshold_and_single_peak_are_not_sustained(self):
        engine = primed_context()
        equal = signal(engine.process(record(144, 150)), 'sustained_high')
        self.assertFalse(equal['flag'])
        peak = signal(engine.process(record(145, 200)), 'sustained_high')
        self.assertFalse(peak['flag'])
        self.assertEqual(peak['status'], 'observing')
        normal = signal(engine.process(record(146)), 'sustained_high')
        self.assertFalse(normal['flag'])
        self.assertEqual(normal['evidence']['consecutive_intervals'], 0)

    def test_six_high_intervals_and_frozen_reference_across_hour_boundary(self):
        engine = primed_context()
        found = None
        for i in range(144, 156):
            found = signal(engine.process(record(i, 200)), 'sustained_high')
            self.assertEqual(found['evidence']['threshold_wh'], 150)
            self.assertEqual(found['flag'], i >= 149)
        self.assertTrue(found['evidence']['reference_frozen'])
        self.assertEqual(found['evidence']['consecutive_intervals'], 12)
        self.assertEqual(found['evidence']['candidate_start_timestamp'], '2016-01-02T00:00:00')
        self.assertEqual(found['evidence']['context_hour'], 0)

    def test_gap_clears_high_candidate_and_requires_duration_again(self):
        engine = primed_context()
        for i in range(144, 150):
            engine.process(record(i, 200))
        found = signal(engine.process(record(152, 200)), 'sustained_high')
        self.assertFalse(found['flag'])
        self.assertEqual(found['evidence']['consecutive_intervals'], 1)

    def test_zero_reference_uses_absolute_margin(self):
        engine = EnergyRules(context_config())
        for i in range(144):
            engine.process(record(i, 0))
        found = signal(engine.process(record(144, 100)), 'sustained_high')
        self.assertEqual(found['evidence']['threshold_wh'], 50)
        self.assertFalse(found['flag'])

    def test_mad_margin_for_variable_context(self):
        engine = EnergyRules(context_config())
        for i in range(144):
            engine.process(record(i, 100 if i % 2 == 0 else 200))
        found = signal(engine.process(record(144, 300)), 'sustained_high')
        self.assertEqual(found['evidence']['reference_median_wh'], 150)
        self.assertEqual(found['evidence']['reference_mad_wh'], 50)
        self.assertAlmostEqual(found['evidence']['threshold_wh'], 150 + 3*1.4826*50)
        self.assertFalse(found['flag'])

    def test_different_hour_does_not_borrow_inappropriate_context(self):
        engine = EnergyRules(context_config())
        for i in range(6):
            engine.process(record(i))
        found = signal(engine.process(record(150, 1000)), 'sustained_high')
        self.assertIsNone(found['flag'])
        self.assertEqual(found['evidence']['context_points'], 0)

    def test_normal_high_usage_in_another_hour_is_not_compared_to_low_hour(self):
        engine = EnergyRules(context_config())
        for i in range(144):
            engine.process(record(i, 100 if i < 6 else 1000))
        result = signal(engine.process(record(150, 1000)), 'sustained_high')
        self.assertEqual(result['evidence']['reference_median_wh'], 1000)
        self.assertFalse(result['flag'])

    def test_irregular_samples_do_not_inflate_reference_coverage(self):
        engine = EnergyRules(context_config())
        for i in range(6):
            row = record(i)
            row['timestamp'] = (START + timedelta(minutes=5*i)).isoformat()
            engine.process(row)
        result = signal(engine.process(record(144, 200)), 'sustained_high')
        self.assertIsNone(result['flag'])
        self.assertEqual(result['evidence']['context_points'], 1)

    def test_context_is_not_shared_with_another_source(self):
        engine = primed_context()
        result = signal(engine.process(record(144, 9999, source='other')), 'sustained_high')
        self.assertIsNone(result['flag'])
        self.assertEqual(result['evidence']['context_points'], 0)

    def test_history_window_does_not_use_old_dates(self):
        engine = EnergyRules(context_config(context_days=1))
        for i in range(144):
            engine.process(record(i))
        found = signal(engine.process(record(432, 200)), 'sustained_high')
        self.assertIsNone(found['flag'])
        self.assertEqual(found['evidence']['context_points'], 0)


class IntegrityTests(unittest.TestCase):
    def test_future_changes_do_not_change_past_assessments(self):
        original = [record(i, 100+i%6) for i in range(160)]
        changed = deepcopy(original)
        for item in changed[150:]:
            item['energy']['value'] = 100000
        self.assertEqual(evaluate(original, context_config())[:150],
                         evaluate(changed, context_config())[:150])

    def test_batch_and_incremental_outputs_match(self):
        rows = [record(i, 100+i%7) for i in range(150)]
        engine = EnergyRules()
        self.assertEqual(evaluate(rows), [engine.process(item) for item in rows])

    def test_same_last_message_retry_does_not_advance_state(self):
        engine = EnergyRules()
        for i in range(5):
            engine.process(record(i))
        original = engine.process(record(5))
        retry = engine.process(record(5))
        self.assertEqual(original, retry)
        retry['signals'][1]['evidence']['consecutive_intervals'] = 999
        result = signal(engine.process(record(6)), 'flatline')
        self.assertEqual(result['evidence']['consecutive_intervals'], 7)

    def test_conflicting_retries_duplicate_time_and_old_records_fail_without_mutation(self):
        engine = EnergyRules()
        engine.process(record(0))
        engine.process(record(1))
        collision = record(1)
        collision['event_id'] = 'different-event'
        for invalid in (record(0), record(1, 200), collision):
            with self.assertRaises(InvalidMessage):
                engine.process(invalid)
        self.assertEqual(signal(engine.process(record(2)), 'flatline')['evidence']['consecutive_intervals'], 3)

    def test_sources_and_buildings_do_not_share_state(self):
        engine = EnergyRules()
        for i in range(6):
            engine.process(record(i))
        for building, source in [('other', 'meter'), ('house', 'other')]:
            result = engine.process(record(0, building=building, source=source))
            self.assertIsNone(signal(result, 'flatline')['flag'])
            self.assertIsNone(signal(result, 'interval_gap')['flag'])
            self.assertIsNone(signal(result, 'sustained_high')['flag'])

    def test_naive_and_offset_aware_labels_keep_their_semantics(self):
        row = record(0)
        row['timestamp'] += '+02:00'
        result = EnergyRules().process(row)
        self.assertEqual(result['measurement_timestamp'], '2016-01-01T00:00:00+02:00')
        self.assertEqual(result['time_basis'], 'offset_aware')
        self.assertIsNone(result['timezone'])
        self.assertEqual(EnergyRules().process(record(0))['measurement_timestamp'], '2016-01-01T00:00:00')

    def test_source_semantics_cannot_change_midstream(self):
        for field in ('timezone_kind', 'scope', 'source_type', 'timestamp_reference'):
            with self.subTest(field=field):
                engine = EnergyRules()
                engine.process(record(0))
                row = record(1)
                if field == 'timezone_kind':
                    row['timestamp'] += '+00:00'
                elif field == 'scope':
                    row['energy']['scope'] = 'whole_building'
                elif field == 'source_type':
                    row['source_type'] = 'smart_meter'
                else:
                    row['timestamp_reference'] = 'interval_end'
                with self.assertRaises(InvalidMessage):
                    engine.process(row)

    def test_unit_conversion_does_not_mutate_input(self):
        row = record(0, 0.1)
        row['energy']['unit'] = 'kWh'
        before = deepcopy(row)
        result = EnergyRules().process(row)
        self.assertEqual(row, before)
        self.assertEqual(signal(result, 'sustained_high')['evidence']['energy_wh'], 100)
        self.assertEqual(result['energy_unit'], 'Wh')

    def test_invalid_input_and_unsupported_interval_do_not_change_state(self):
        engine = EnergyRules()
        engine.process(record(0))
        for value in (-1, float('nan'), float('inf')):
            with self.assertRaises((InvalidMessage, ValueError)):
                engine.process(record(1, value))
        row = record(1)
        row['interval_seconds'] = 900
        with self.assertRaises(InvalidMessage):
            engine.process(row)
        self.assertFalse(signal(engine.process(record(1)), 'interval_gap')['flag'])

    def test_outputs_are_json_serializable_and_experimental_not_probabilities(self):
        result = EnergyRules().process(record(0))
        json.dumps(result, allow_nan=False)
        for item in result['signals']:
            self.assertEqual(item['maturity'], 'experimental')
            self.assertNotIn('probability', item)
            self.assertEqual(item['semantics'], 'review_signal_not_confirmed_fault')

    def test_infinite_computed_threshold_is_unavailable_not_an_infinite_alarm(self):
        engine = EnergyRules(context_config())
        for i in range(144):
            engine.process(record(i, 1e308))
        result = engine.process(record(144, 1e308))
        found = signal(result, 'sustained_high')
        self.assertIsNone(found['flag'])
        json.dumps(result, allow_nan=False)

    def test_current_point_is_not_in_its_own_reference(self):
        a, b = primed_context(), primed_context()
        left = signal(a.process(record(144, 100)), 'sustained_high')['evidence']
        right = signal(b.process(record(144, 9999)), 'sustained_high')['evidence']
        self.assertEqual(left['threshold_wh'], right['threshold_wh'])
        self.assertEqual(left['context_points'], 6)


if __name__ == '__main__':
    unittest.main()
