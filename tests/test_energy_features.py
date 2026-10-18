import copy
import unittest

from energy_helpers import energy_records
from processing.energy_schema import validate_energy
from processing.energy_processor import EnergyProcessor
from processing.message_schema import InvalidMessage
from ai.train_energy_forecaster import build_samples, chronological_split


class EnergyFeatureTests(unittest.TestCase):
    def test_exact_lags_rolling_and_target(self):
        processor = EnergyProcessor()
        results = [processor.process(validate_energy(record)) for record in energy_records(7)]
        self.assertTrue(all(row['features'] is None for row in results[:6]))
        last = results[-1]
        self.assertEqual(last['features']['energy_wh'], 7)
        self.assertEqual(last['features']['lag_1_wh'], 6)
        self.assertEqual(last['features']['lag_6_wh'], 1)
        self.assertEqual(last['features']['rolling_3_mean'], 6)
        self.assertEqual(last['features']['rolling_6_mean'], 4.5)
        self.assertEqual(last['forecast_origin'], '2016-01-01T01:00:00')
        self.assertEqual(last['forecast_target_timestamp'], '2016-01-01T01:10:00')

    def test_future_changes_do_not_change_features(self):
        original = list(energy_records(30))
        changed = copy.deepcopy(original)
        for record in changed[20:]:
            record['energy']['value'] = 100000
        before, _ = build_samples(original)
        after, _ = build_samples(changed)
        # Earlier targets and their features are completely unchanged.
        self.assertTrue(before.iloc[:13].equals(after.iloc[:13]))
        # The row targeting changed t=20 has unchanged features but changed label.
        self.assertEqual(before.iloc[13]['energy_wh'], after.iloc[13]['energy_wh'])
        self.assertNotEqual(before.iloc[13]['actual_energy_wh'], after.iloc[13]['actual_energy_wh'])

    def test_gap_duplicate_and_source_isolation(self):
        records = list(energy_records(20))
        processor = EnergyProcessor()
        for record in records[:7]:
            processor.process(validate_energy(record))
        with self.assertRaises(InvalidMessage):
            processor.process(validate_energy(records[6]))
        with self.assertRaises(InvalidMessage):
            processor.process(validate_energy(records[1]))
        other = copy.deepcopy(records[7])
        other['building_id'] = 'other'
        self.assertIsNone(processor.process(validate_energy(other))['features'])
        result = processor.process(validate_energy(records[9]))
        self.assertTrue(result['gap_detected'])
        self.assertIsNone(result['features'])
        frame, _ = build_samples(records[:9] + records[10:])
        self.assertNotIn(records[10]['timestamp'], frame.forecast_target_timestamp.tolist())

    def test_interval_and_semantics_changes_rejected(self):
        records = list(energy_records(3))
        processor = EnergyProcessor()
        processor.process(validate_energy(records[0]))
        records[1]['interval_seconds'] = 300
        with self.assertRaises(InvalidMessage):
            processor.process(validate_energy(records[1]))
        records[2]['timestamp'] += '+00:00'
        with self.assertRaises(InvalidMessage):
            processor.process(validate_energy(records[2]))

    def test_target_based_chronological_split(self):
        frame, _ = build_samples(energy_records(100))
        train, test = chronological_split(frame)
        self.assertLess(train.forecast_target_timestamp.max(), test.forecast_target_timestamp.min())
        self.assertEqual(train.forecast_target_timestamp.max(), test.forecast_origin.min())
        self.assertEqual(test.iloc[0].actual_energy_wh, test.iloc[0].energy_wh + 1)
