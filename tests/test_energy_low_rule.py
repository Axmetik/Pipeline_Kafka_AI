"""Controlled low-rule semantics; no training or real-data experiments."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime
import hashlib
from pathlib import Path
import unittest
from processing.energy_low_rule import SustainedLow,LowRuleConfig,evaluate_low
from processing.energy_rules import EnergyRules,RuleConfig
from processing.message_schema import InvalidMessage
from test_energy_rules import record

def prime(profile=lambda h:100,days=3,skip_hour=None):
    e=SustainedLow()
    for i in range(days*144):
        r=record(i,profile((i//6)%24))
        if (i//6)%24!=skip_hour:e.process(r)
    return e

def s(result):return result['signal']

class LowRuleTests(unittest.TestCase):
    def test_frozen_formula_config_and_invalid_settings(self):
        c=LowRuleConfig();self.assertEqual(c.low_intervals,6)
        self.assertEqual((c.minimum_context_days,c.minimum_context_points),(3,18))
        self.assertNotEqual(c.version,LowRuleConfig(low_intervals=3).version)
        with self.assertRaises(FrozenInstanceError):c.low_intervals=2
        for kwargs in [dict(low_intervals=True),dict(low_intervals=1),dict(context_days=32),dict(minimum_context_points=43),dict(minimum_context_days=8),dict(minimum_drop_wh=0),dict(minimum_reference_wh=float('nan')),dict(minimum_relative_drop=1)]:
            with self.assertRaises(ValueError):LowRuleConfig(**kwargs)
        with self.assertRaises(TypeError):SustainedLow({})

    def test_short_drop_not_confirmed_and_long_drop_sixth_point(self):
        e=prime();out=[s(e.process(record(432+i,10))) for i in range(6)]
        self.assertEqual([r['flag'] for r in out],[False]*5+[True])
        self.assertEqual(out[-1]['evidence']['threshold_wh'],50)
        self.assertEqual(out[-1]['evidence']['consecutive_intervals'],6)
        self.assertEqual(out[-1]['category'],'consumption_pattern')
        self.assertEqual(out[-1]['semantics'],'review_signal_not_confirmed_fault')
        self.assertIs(s(e.process(record(438,100)))['flag'],False)

    def test_threshold_strict_equality_is_not_low(self):
        e=prime();self.assertIs(s(e.process(record(432,50)))['flag'],False)

    def test_normal_hour_transition_does_not_borrow_night_threshold(self):
        e=prime(lambda h:100 if h<8 else 20)
        for i in range(432,479):e.process(record(i,100))
        self.assertFalse(s(e.process(record(479,10)))['flag']) #07:50
        result=s(e.process(record(480,20))) #08:00
        self.assertFalse(result['flag']);self.assertEqual(result['evidence']['threshold_wh'],10)
        self.assertEqual(result['evidence']['consecutive_intervals'],0)

    def test_midnight_uses_frozen_next_hour_context(self):
        e=prime(lambda h:200 if h==0 else 100)
        for i in range(432,575):e.process(record(i,200 if (i//6)%24==0 else 100))
        e.process(record(575,10)) #23:50, L=50
        results=[s(e.process(record(i,70))) for i in range(576,581)] #next00 L=100
        self.assertTrue(results[-1]['flag']);self.assertEqual(results[-1]['evidence']['threshold_wh'],100)
        self.assertEqual(results[-1]['evidence']['reference_cutoff_timestamp'],'2016-01-04T23:50:00')

    def test_missing_next_hour_context_is_null_and_resets(self):
        e=prime(skip_hour=8)
        for i in range(432,479):
            if (i//6)%24!=8:e.process(record(i,100))
        e.process(record(479,10))
        out=s(e.process(record(480,1)))
        self.assertIsNone(out['flag']);self.assertEqual(out['evidence']['unavailable_reason'],'insufficient_hourly_context')
        self.assertEqual(out['evidence']['consecutive_intervals'],0)

    def test_insufficient_history_and_same_day_exclusion(self):
        e=SustainedLow()
        for i in range(144):out=e.process(record(i))
        out=s(e.process(record(144,10)))
        self.assertIsNone(out['flag']);self.assertEqual(out['evidence']['context_days'],1)
        self.assertEqual(out['evidence']['context_points'],6)

    def test_gap_breaks_candidate_and_return_starts_new_one(self):
        e=prime()
        for i in range(432,437):e.process(record(i,10))
        out=s(e.process(record(438,10)))
        self.assertFalse(out['flag']);self.assertTrue(out['evidence']['cadence_broken'])
        self.assertEqual(out['evidence']['consecutive_intervals'],1)
        for i in range(439,444):out=s(e.process(record(i,10)))
        self.assertTrue(out['flag'])

    def test_retry_is_idempotent_defensive_and_conflict_rejected(self):
        e=prime();r=record(432,10);a=e.process(r);b=e.process(r)
        self.assertEqual(a,b);a['signal']['evidence']['threshold_wh']=-1
        self.assertEqual(e.process(r),b)
        bad=deepcopy(r);bad['energy']['value']=20
        with self.assertRaises(InvalidMessage):e.process(bad)
        self.assertEqual(s(e.process(record(433,10)))['evidence']['consecutive_intervals'],2)

    def test_out_of_order_and_source_binding_fail_without_mutation(self):
        e=prime();e.process(record(432,10))
        with self.assertRaises(InvalidMessage):e.process(record(431,10))
        r=record(433,10);r['timestamp_reference']='interval_end'
        with self.assertRaises(InvalidMessage):e.process(r)
        self.assertEqual(s(e.process(record(433,10)))['evidence']['consecutive_intervals'],2)

    def test_sources_and_buildings_are_isolated(self):
        e=prime()
        for i in range(432,438):out=e.process(record(i,10))
        self.assertTrue(s(out)['flag'])
        for kwargs in [dict(source='other'),dict(building='other')]:
            other=s(e.process(record(438,10,**kwargs)))
            self.assertIsNone(other['flag']);self.assertEqual(other['evidence']['context_points'],0)

    def test_low_and_zero_background_unavailable_not_false(self):
        for value in [0,5,19]:
            e=prime(lambda h:value);out=s(e.process(record(432,0)))
            self.assertIsNone(out['flag']);self.assertEqual(out['evidence']['unavailable_reason'],'low_reference_energy')

    def test_variable_context_without_positive_lower_threshold_unavailable(self):
        e=SustainedLow()
        for i in range(432):e.process(record(i,0 if i%2==0 else 200))
        out=s(e.process(record(432,0)))
        self.assertIsNone(out['flag']);self.assertEqual(out['evidence']['unavailable_reason'],'no_positive_lower_threshold')

    def test_normal_night_decline_follows_hour_profile(self):
        e=prime(lambda h:200 if 8<=h<18 else 20)
        for i in range(432,576):
            out=s(e.process(record(i,200 if 8<=(i//6)%24<18 else 20)))
            self.assertIs(out['flag'],False)

    def test_regular_nonwork_is_not_calendar_adjusted(self):
        # Jan04 Monday through Jan10 Sunday, 5 workdays dominate same-hour median.
        start=datetime(2016,1,4);e=SustainedLow()
        for i in range(6*144):
            r=record(i,start=start);dt=datetime.fromisoformat(r['timestamp'])
            r['energy']['value']=200 if dt.weekday()<5 and 8<=dt.hour<18 else 20;e.process(r)
        for i in range(6*144,6*144+8*6+6):
            out=e.process(record(i,20,start=start))
        self.assertTrue(s(out)['flag'])
        self.assertFalse(e.metadata()['calendar_model'])

    def test_zero_after_nonzero_context_is_review_not_fault(self):
        e=prime()
        for i in range(432,438):out=e.process(record(i,0))
        self.assertTrue(s(out)['flag']);self.assertIn('legitimate',s(out)['evidence']['interpretation'])

    def test_offline_stream_equal_and_future_suffix_cannot_change_prefix(self):
        raw=[record(i,100 if i<432 else 10) for i in range(444)]
        a=evaluate_low(raw);e=SustainedLow();b=[e.process(r) for r in raw]
        self.assertEqual(a,b)
        changed=deepcopy(raw)
        for r in changed[438:]:r['energy']['value']=999
        self.assertEqual(a[:438],evaluate_low(changed)[:438])

    def test_input_immutable_and_kwh_normalized(self):
        e=prime();r=record(432,0.01);r['energy']['unit']='kWh';before=deepcopy(r)
        out=e.process(r);self.assertEqual(r,before);self.assertEqual(s(out)['evidence']['energy_wh'],10)

    def test_reference_frozen_and_current_day_cannot_adapt(self):
        e=prime()
        for i in range(432,450):out=e.process(record(i,0))
        self.assertEqual(s(out)['evidence']['reference_median_wh'],100)
        self.assertEqual(s(out)['evidence']['reference_cutoff_timestamp'],'2016-01-04T00:00:00')

    def test_v2_unchanged_by_parallel_new_rule(self):
        p=Path(__file__).resolve().parents[1]/'processing/energy_rules.py'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),'4fd53075e7f784056656dcc283047c69a307c01816f71a27948a69f43a80a91f')
        a=EnergyRules();b=EnergyRules();low=SustainedLow()
        for i in range(438):
            r=record(i,100 if i<432 else 10)
            before=a.process(r);low.process(r);after=b.process(r)
            self.assertEqual(before,after)
        self.assertEqual(RuleConfig().version,'energy-rules-v2-a83ff8cf889d4981')

    def test_extreme_finite_readings_do_not_leak_nonfinite_evidence(self):
        import json
        e=prime(lambda h:1.7e308)
        result=e.process(record(432,0))
        json.dumps(result,allow_nan=False)
        self.assertIsNone(s(result)['flag'])
        self.assertEqual(s(result)['evidence']['unavailable_reason'],'nonfinite_context_threshold')
