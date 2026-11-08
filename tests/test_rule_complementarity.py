"""Small deterministic regressions; no real-data scoring or training."""
from copy import deepcopy
from datetime import datetime
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from diagnostics.rule_complementarity import (tri_or,augment,measure,contributions,summary_rows,
                                             transform,run,METHODS,CONSUMPTION,STEP)

START=datetime(2016,1,1)
def rows(n=8):
    return [{'timestamp':(START+i*STEP).isoformat(),**{m+'_flag':False for m in METHODS}} for i in range(n)]
def case(**changes):
    return dict(scenario_id='fixture',family='sustained_high',category='consumption_pattern',target=True,
                start=(START+2*STEP).isoformat(),intervals=3,operation='add_energy_wh',amplitude_wh=200,**changes)
def wire(n=8):
    return [{'timestamp':(START+i*STEP).isoformat(),'energy':{'value':float(i+10),'unit':'Wh'},'environment':{'T':20}} for i in range(n)]

class UnionTests(unittest.TestCase):
    def test_exhaustive_three_and_four_input_truth_tables(self):
        for n in (3,4):
            for values in itertools.product([True,False,None],repeat=n):
                inputs=dict(zip('abcd',values));out=tri_or(inputs)
                expected=True if True in values else None if None in values else False
                self.assertIs(out['flag'],expected)
                self.assertEqual(out['positive'],[k for k,v in inputs.items() if v is True])
                self.assertEqual(out['missing'],[k for k,v in inputs.items() if v is None])
                self.assertEqual(out['available'],[k for k,v in inputs.items() if v is not None])
                self.assertEqual(out['required'],list(inputs))

    def test_rejects_empty_and_non_boolean_decisions(self):
        for inputs in ({},{'x':0},{'x':'true'},{'x':1}):
            with self.assertRaises(ValueError):tri_or(inputs)

    def test_positive_with_missing_is_available_but_records_missing(self):
        inp=rows(1);inp[0]['residual_flag']=None;inp[0]['isolation_forest_flag']=True
        out=augment(inp)[0]
        self.assertIs(out['ml_or_flag'],True)
        self.assertEqual(json.loads(out['ml_or_provenance_json'])['missing'],['residual'])

    def test_augment_is_repeatable_non_mutating_and_excludes_telemetry(self):
        inp=rows(1);inp[0]['flatline_flag']=True;inp[0]['interval_gap_flag']=True
        before=deepcopy(inp);a=augment(inp);b=augment(inp)
        self.assertEqual(inp,before);self.assertEqual(a,b)
        self.assertIs(a[0]['ml_or_flag'],False);self.assertIs(a[0]['ml_high_or_flag'],False)

class EventTests(unittest.TestCase):
    def test_combination_rebuilds_episodes_can_lose_component_credit(self):
        mod=rows();raw=rows()
        # High begins before event and bridges to new ML onset inside it.
        for i in range(1,4):mod[i]['sustained_high_flag']=True
        mod[3]['isolation_forest_flag']=True
        details,_=measure(case(),augment(mod),augment(raw));c=contributions(details)[0]
        self.assertTrue(c['ml_detected']);self.assertFalse(c['rule_detected'])
        self.assertFalse(c['combined_detected']);self.assertTrue(c['combined_lost_vs_ml'])
        self.assertTrue(c['union_episode_differs_from_component_set'])

    def test_rule_only_adds_new_union_event(self):
        mod=rows();mod[4]['sustained_high_flag']=True
        details,_=measure(case(),augment(mod),augment(rows()));c=contributions(details)[0]
        self.assertEqual(c['component_group'],'rule_only');self.assertTrue(c['combined_added_vs_ml'])
        self.assertEqual(c['combined_delay'],20)

    def test_both_component_matches_count_one_event(self):
        mod=rows();mod[2]['isolation_forest_flag']=True;mod[3]['sustained_high_flag']=True
        details,_=measure(case(),augment(mod),augment(rows()));c=contributions(details)[0]
        self.assertEqual(c['component_group'],'both');self.assertTrue(c['combined_detected'])
        self.assertFalse(c['combined_added_vs_ml'])

    def test_null_breaks_episodes_without_inventing_mask_onset(self):
        mod=rows()
        for i in range(5):mod[i]['isolation_forest_flag']=True
        mod[2]['residual_flag']=None
        details,_=measure(case(),augment(mod),augment(rows()))
        union=next(r for r in details if r['method']=='ml_or')
        self.assertFalse(union['detected']);self.assertFalse(union['detected_common_onset'])
        self.assertEqual(union['preexisting_overlap'],1);self.assertEqual(union['event_coverage'],1)
        self.assertAlmostEqual(union['common_event_coverage'],2/3)

    def test_partial_availability_and_misses_are_retained(self):
        mod=rows();mod[2]['residual_flag']=None
        details,_=measure(case(),augment(mod),augment(rows()))
        union=next(r for r in details if r['method']=='ml_or')
        self.assertFalse(union['detected']);self.assertIsNone(union['delay_minutes'])
        self.assertEqual(union['unavailable_event_points'],1)
        self.assertAlmostEqual(union['event_coverage'],2/3)
        summary=next(r for r in summary_rows(details) if r['level']=='category' and r['method']=='ml_or')
        self.assertEqual(summary['target_events'],1);self.assertEqual(summary['missed_events'],1)

    def test_inclusive_last_label_and_no_tail_grace(self):
        mod=rows();mod[4]['isolation_forest_flag']=True
        details,_=measure(case(),augment(mod),augment(rows()))
        self.assertTrue(contributions(details)[0]['combined_detected'])
        mod=rows();mod[5]['isolation_forest_flag']=True
        details,_=measure(case(),augment(mod),augment(rows()))
        self.assertFalse(contributions(details)[0]['combined_detected'])

    def test_pair_coincidence_and_pair_unknown_are_not_new_crossings(self):
        for rawflag in (True,None,False):
            mod=rows();raw=rows();mod[3]['residual_flag']=True;raw[3]['residual_flag']=rawflag
            details,_=measure(case(),augment(mod),augment(raw))
            r=next(r for r in details if r['method']=='residual')
            self.assertTrue(r['detected']);self.assertIs(r['new_paired_crossing'],rawflag is False)
            self.assertIs(r['paired_unknown_at_match'],rawflag is None)

    def test_controls_gaps_flatline_excluded_from_consumption_contribution(self):
        all_details=[]
        for family,cat,target in [('control','normal_control',False),('interval_gap','telemetry_quality',True),('flatline','telemetry_quality',True)]:
            c=case();c.update(family=family,category=cat,target=target)
            mod=rows();mod[3]['flatline_flag']=True;mod[3]['isolation_forest_flag']=True
            d,_=measure(c,augment(mod),augment(rows()));all_details+=d
        self.assertEqual(contributions(all_details),[])
        self.assertTrue(all(r['group']!='consumption_pattern' for r in summary_rows(all_details)))

    def test_raw_pair_episode_count_is_reconstructed_not_flag_sum(self):
        raw=rows()
        for i in range(1,6):raw[i]['isolation_forest_flag']=True
        d,_=measure(case(),augment(rows()),augment(raw))
        r=next(r for r in d if r['method']=='ml_or')
        self.assertEqual(r['paired_episode_onsets'],1);self.assertEqual(r['paired_event_onsets'],0)
        self.assertEqual(r['paired_event_flagged_points'],3)

class ScenarioTests(unittest.TestCase):
    def test_drop_and_ramp_exact_formula_and_immutable_source(self):
        raw=wire();before=deepcopy(raw);c=case();c.update(operation='scale_energy',factor=.2)
        dropped=transform(raw,c);self.assertAlmostEqual(dropped[2]['energy']['value'],2.4)
        c.update(operation='ramp_add_energy',final_addition_wh=300)
        ramp=transform(raw,c)
        self.assertEqual([ramp[i]['energy']['value']-raw[i]['energy']['value'] for i in range(2,5)],[100,200,300])
        self.assertEqual(raw,before);self.assertEqual(ramp[5],raw[5]);self.assertEqual(ramp[2]['environment'],raw[2]['environment'])

    def test_identity_and_missing_timestamp_fail_closed(self):
        raw=wire();c=case();c.update(operation='identity')
        self.assertEqual(transform(raw,c),raw)
        with self.assertRaises(ValueError):transform(raw[:3]+raw[4:],c)

    def test_registered_33_cases_and_separate_target_denominators(self):
        base=Path(__file__).resolve().parents[1]/'docs/energy-rules/complementarity-20261108'
        manifest=json.loads((base/'scenarios.json').read_text());scenarios=manifest['scenarios']
        self.assertEqual(len(scenarios),33);self.assertEqual(len({c['scenario_id'] for c in scenarios}),33)
        self.assertEqual(sum(c['category']=='consumption_pattern' for c in scenarios),22)
        self.assertEqual(sum(c['family']=='flatline' for c in scenarios),6)
        self.assertEqual(sum(c['family']=='interval_gap' for c in scenarios),2)
        self.assertEqual(sum(c['family']=='control' for c in scenarios),3)
        self.assertEqual({c['intervals'] for c in scenarios if c['family']=='short_peak'},{1,2})

    def test_refuses_existing_output_before_loading_artifacts(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(FileExistsError):run(Path('/nonexistent'),Path(path))
