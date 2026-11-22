"""Regression boundaries for the preregistered low experiment, without inference."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from diagnostics.sustained_low_comparison import (PRIMARY,METHODS,STEP,transform,describe,contributions,timed_loop,run)
from diagnostics.rule_complementarity import tri_or
from test_energy_rules import record

START=datetime(2016,1,1)
def rows():return [{'timestamp':(START+i*STEP).isoformat(),**{n+'_flag':False for n in METHODS}} for i in range(8)]
def case():return dict(scenario_id='fixture',cohort='new',family='drop',category='consumption_pattern',target=True,start=(START+2*STEP).isoformat(),intervals=3,operation='scale_energy',factor=.2)
def combine(rows):
    result=deepcopy(rows)
    for r in result:
        r['residual_high_or_flag']=tri_or({n:r[n+'_flag'] for n in ['residual','sustained_high']})['flag']
        r['residual_high_low_or_flag']=tri_or({n:r[n+'_flag'] for n in ['residual','sustained_high','sustained_low']})['flag']
    return result

class LowComparisonTests(unittest.TestCase):
    def test_later_low_component_does_not_create_union_credit(self):
        mod=rows()
        for i in range(1,5):mod[i]['sustained_high_flag']=True
        mod[3]['sustained_low_flag']=True
        d,_=describe(case(),combine(mod),combine(rows()));c=contributions(d)[0]
        self.assertTrue(c['sustained_low_detected']);self.assertFalse(c['residual_high_low_or_detected'])
        self.assertTrue(c['union_differs_from_component_set'])

    def test_low_preexisting_episode_can_lose_baseline_match(self):
        mod=rows()
        for i in range(1,4):mod[i]['sustained_low_flag']=True
        mod[3]['residual_flag']=True
        d,_=describe(case(),combine(mod),combine(rows()));c=contributions(d)[0]
        self.assertTrue(c['lost_vs_baseline']);self.assertFalse(c['added_vs_baseline'])

    def test_new_low_event_credit_and_null_coverage(self):
        mod=rows();mod[3]['sustained_low_flag']=True;mod[2]['sustained_low_flag']=None
        d,_=describe(case(),combine(mod),combine(rows()));c=contributions(d)[0]
        self.assertTrue(c['added_vs_baseline']);self.assertTrue(c['low_only'])
        low=next(r for r in d if r['method']=='sustained_low')
        self.assertEqual(low['unavailable_event_points'],1);self.assertEqual(low['delay_minutes'],10)

    def test_profile_transforms_preserve_source_and_use_explicit_calendar(self):
        raw=[record(i) for i in range(144*7)];before=deepcopy(raw);c=case();c.update(operation='workweek_profile',work_wh=200,off_wh=20,day_start=8,day_end=18)
        changed=transform(raw,c)
        # Jan01 Friday daytime200; Jan02 Saturday daytime20; nighttime20.
        self.assertEqual(changed[10*6]['energy']['value'],200)
        self.assertEqual(changed[144+10*6]['energy']['value'],20)
        self.assertEqual(changed[0]['energy']['value'],20);self.assertEqual(raw,before)
        c.update(operation='constant_profile',value_wh=0)
        self.assertTrue(all(r['energy']['value']==0 for r in transform(raw,c)))

    def test_manifest_separates_known_six_and_new_eighteen(self):
        base=Path(__file__).resolve().parents[1]/'docs/energy-rules/sustained-low-20261108'
        cases=json.loads((base/'scenarios.json').read_text())['scenarios']
        self.assertEqual(len(cases),32);self.assertEqual(len({c['scenario_id'] for c in cases}),32)
        self.assertEqual(sum(c['cohort']=='known_regression' for c in cases),6)
        self.assertEqual(sum(c['cohort']=='new' for c in cases),18)
        self.assertEqual({c['factor'] for c in cases if c['cohort']=='new' and c['family']=='drop'},{.2,.6})
        self.assertEqual({c['intervals'] for c in cases if c['cohort']=='new' and c['family']=='drop'},{3,6,12})

    def test_timed_loop_keeps_identical_baseline_decisions_and_sample_count(self):
        class V2:
            def process(self,r):return {'signals':[{'rule':'sustained_high','flag':False}]}
        class Low:
            def process(self,r):return {'signal':{'flag':True}}
        raw=[record(i) for i in range(4)];flags=[False]*4
        a,total,low,aout=timed_loop(raw,V2(),None,None,flags,'rules_only',False)
        b,total2,low2,bout=timed_loop(raw,V2(),Low(),None,flags,'rules_only',True)
        self.assertEqual(len(a),4);self.assertEqual(len(b),4);self.assertEqual(len(low2),4)
        self.assertEqual([v[:3] for v in aout],[v[:3] for v in bout]);self.assertEqual(low,[])
        self.assertTrue(all(v[-1] is True for v in bout));self.assertGreater(total,0);self.assertGreater(total2,0)

    def test_existing_output_refused_before_loading(self):
        with tempfile.TemporaryDirectory() as p:
            with self.assertRaises(FileExistsError):run(Path('/missing'),Path(p))
