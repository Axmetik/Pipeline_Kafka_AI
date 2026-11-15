"""Matching/manifest regressions only; never fit or run a real-data experiment."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import unittest
from diagnostics.rule_comparison import intervals,onset_match,transform,describe,check_gap,METHODS
from processing.energy_rules import EnergyRules

START=datetime(2016,1,1)
STEP=timedelta(minutes=10)

def wire(i):
    return {'schema_version':'1.0','building_id':'house','source_id':'meter','source_type':'dataset',
            'event_id':str(i),'timestamp':(START+i*STEP).isoformat(),'timezone':None,
            'timestamp_reference':'dataset_label','interval_seconds':600,
            'energy':{'value':float(i+1),'unit':'Wh','scope':'appliances','measurement_type':'interval_energy'},
            'environment':{},'additional_parameters':{}}

def rows(count=8):
    return [{'timestamp':(START+i*STEP).isoformat(),**{name+'_flag':False for name in METHODS}} for i in range(count)]

def case(**kwargs):
    return {'scenario_id':'fixture','start':(START+2*STEP).isoformat(),'intervals':3,
            'family':'flatline','category':'telemetry_quality','target':True,
            'operation':'hold_previous_energy',**kwargs}

class MatchingTests(unittest.TestCase):
    def test_preexisting_overlap_is_not_a_detection(self):
        stamps=[START+i*STEP for i in range(5)]
        alarms=intervals(stamps,[True,True,True,True,False])
        self.assertIsNone(onset_match(alarms,stamps[1],stamps[3]))

    def test_inclusive_end_and_no_tail_grace(self):
        stamps=[START+i*STEP for i in range(5)]
        alarms=intervals(stamps,[False,False,False,True,True])
        self.assertIsNotNone(onset_match(alarms,stamps[1],stamps[3]))
        self.assertIsNone(onset_match(alarms,stamps[1],stamps[2]))

    def test_null_false_and_timestamp_gap_break_episodes(self):
        stamps=[START+i*STEP for i in (0,1,2,3,4,6,7)]
        alarms=intervals(stamps,[True,None,True,False,True,True,True])
        self.assertEqual([a['points'] for a in alarms],[1,1,1,2])

    def test_common_mask_cannot_fabricate_onset(self):
        modified=rows();original=rows()
        for i in range(5): modified[i]['flatline_flag']=True
        modified[0]['residual_flag']=None
        details=describe(case(),modified,original)
        flat=next(r for r in details if r['method']=='flatline')
        self.assertFalse(flat['detected_common'])
        self.assertEqual(flat['preexisting_overlap'],1)
        self.assertIsNone(flat['delay_minutes'])

    def test_match_delay_and_pair_crossing_are_separate(self):
        modified=rows();original=rows()
        modified[3]['flatline_flag']=True
        original[3]['flatline_flag']=True
        flat=next(r for r in describe(case(),modified,original) if r['method']=='flatline')
        self.assertTrue(flat['detected_common'])
        self.assertEqual(flat['delay_minutes'],10)
        self.assertFalse(flat['new_paired_crossing'])

    def test_insufficient_common_coverage_keeps_missed_target(self):
        modified=rows();original=rows()
        modified[2]['flatline_flag']=True
        modified[2]['residual_flag']=None
        flat=next(r for r in describe(case(),modified,original) if r['method']=='flatline')
        self.assertTrue(flat['target'])
        self.assertTrue(flat['detected_own'])
        self.assertFalse(flat['detected_common'])
        self.assertAlmostEqual(flat['common_event_coverage'],2/3)

    def test_controls_have_no_target_true_positive(self):
        modified=rows();original=rows()
        modified[3]['flatline_flag']=True
        result=describe(case(family='control',target=False),modified,original)
        self.assertTrue(all(not r['target'] and r['detected_common'] is None for r in result))
        self.assertEqual(next(r for r in result if r['method']=='flatline')['modified_event_onsets'],1)

class ScenarioTests(unittest.TestCase):
    def test_hold_previous_uses_exact_registered_window_and_preserves_raw(self):
        original=[wire(i) for i in range(8)];before=deepcopy(original)
        changed=transform(original,case())
        self.assertEqual(original,before)
        self.assertEqual([r['energy']['value'] for r in changed],[1,2,2,2,2,6,7,8])

    def test_gap_is_removed_not_zero_filled_and_detected_only_at_return(self):
        original=[wire(i) for i in range(8)]
        scenario=case(family='interval_gap',operation='remove_records')
        changed=transform(original,scenario);engine=EnergyRules();scored=[]
        for r in changed:
            scored.append({'timestamp':r['timestamp'],'rule_evidence_json':json.dumps(engine.process(r)['signals'])})
        gap=check_gap(scenario,scored)
        self.assertEqual(len(changed),5)
        self.assertTrue(gap['correct'])
        self.assertEqual(gap['detected_missing_intervals'],3)
        self.assertEqual(gap['actual_detection_timestamp'],(START+5*STEP).isoformat())
        self.assertEqual(gap['delay_from_first_missing_minutes'],30)

    def test_missing_registered_timestamp_refuses_scenario(self):
        with self.assertRaises(ValueError): transform([wire(i) for i in (0,1,3,4,5,6)],case())

    def test_addition_and_zero_do_not_change_other_fields(self):
        original=[wire(i) for i in range(8)]
        changed=transform(original,case(operation='add_energy_wh',amplitude_wh=300))
        self.assertEqual(changed[2]['energy']['value'],303)
        self.assertEqual(changed[2]['environment'],original[2]['environment'])
        zero=transform(original,case(operation='set_energy_wh',value_wh=0))
        self.assertEqual([r['energy']['value'] for r in zero[2:5]],[0,0,0])

    def test_manifest_retains_all_registered_families_and_short_cases(self):
        path=Path(__file__).resolve().parents[1]/'docs/energy-rules/controlled-20261108/scenarios.json'
        manifest=json.loads(path.read_text());cases=manifest['scenarios']
        self.assertEqual(len(cases),24)
        self.assertEqual(len({s['scenario_id'] for s in cases}),24)
        for family,count in (('flatline',6),('sustained_high',12),('interval_gap',3),('control',3)):
            self.assertEqual(sum(s['family']==family for s in cases),count)
        self.assertEqual({s['intervals'] for s in cases if s['family']=='flatline'},{3,6,12})
