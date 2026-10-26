"""Agreement is not probability; unavailable votes never become false."""
import copy
import unittest
from anomaly.combined import combine,NAMES
from anomaly.combined_benchmark import choose

class CombinedTests(unittest.TestCase):
    def scores(self,n=0):
        return [dict(detector=name,status='ready',score=2. if i<n else 0.,threshold=1.,flag=i<n,
                     model_id=name,model_version='v1',feature_version='f1',threshold_version='q99') for i,name in enumerate(NAMES)]

    def test_zero_to_three_votes_and_all_rules(self):
        for count in range(4):
            for rule,minimum in [('or',1),('majority',2),('unanimous',3)]:
                scores=self.scores(count);before=copy.deepcopy(scores);r=combine(scores,rule)
                self.assertEqual(r['trigger_count'],count);self.assertEqual(r['coverage_count'],3)
                self.assertEqual(r['flag'],count>=minimum);self.assertEqual(scores,before)
                self.assertEqual(r['triggered_methods'],list(NAMES[:count]))
                self.assertEqual(r,combine(scores,rule))

    def test_missing_warmup_gap_incompatible_and_invalid_never_zero_of_three(self):
        for status in ['warmup','gap','incompatible','partial']:
            for value in [None,float('nan'),float('inf')]:
                scores=self.scores();scores[0].update(status=status,flag=None,score=value)
                result=combine(scores,'or')
                self.assertIsNone(result['flag']);self.assertIsNone(result['trigger_count'])
                self.assertIsNone(result['agreement']);self.assertEqual(result['coverage_count'],2)
        self.assertEqual(combine([],'or')['status'],'partial')
        self.assertEqual(combine(self.scores()[:1],'or')['coverage_count'],1)

    def test_future_or_other_source_results_are_not_read(self):
        scores=self.scores(2)
        self.assertEqual(combine(scores,'or'),combine(copy.deepcopy(scores),'or'))
        with self.assertRaises(ValueError): combine(scores+[scores[0]],'or')
        with self.assertRaises(ValueError): combine(scores,'unknown')

    def test_validation_selection_is_frozen_and_budget_is_explicit(self):
        rows=[];controls=[]
        for rule in ['or','majority','unanimous']:
            rows.append(dict(method=rule,scenario='mixed-seed101',event_f1=.9 if rule=='or' else 0.,delay_median_minutes=None))
            controls.append(dict(method=rule,background_alarm_rate=.02 if rule=='or' else .001 if rule=='majority' else 0.))
        selected=choose(rows,controls)
        self.assertEqual(selected['rule'],'unanimous');self.assertFalse(selected['uses_test'])
        self.assertEqual(selected['rule_version'],'combined-q99-v1-unanimous')
        # No test table is accepted by the selection function.
        self.assertEqual(selected,choose(copy.deepcopy(rows),copy.deepcopy(controls)))

    def test_no_rule_is_selected_when_all_exceed_background_budget(self):
        rows=[];controls=[]
        for rule in ['or','majority','unanimous']:
            rows.append(dict(method=rule,scenario='mixed-seed101',event_f1=.9,delay_median_minutes=0.))
            controls.append(dict(method=rule,background_alarm_rate=.02))
        selected=choose(rows,controls)
        self.assertIsNone(selected['rule'])
        self.assertIsNone(selected['rule_version'])
        self.assertFalse(selected['eligible'])
        self.assertFalse(selected['uses_test'])
        self.assertEqual(set(selected['candidates']),{'or','majority','unanimous'})

    def test_test_rows_cannot_enter_selection(self):
        with self.assertRaisesRegex(ValueError,'validation only'):
            choose([{'split':'test'}],[])

    def test_saved_single_detector_metrics_match_stage4(self):
        from pathlib import Path
        import pandas as pd
        root=Path(__file__).resolve().parents[1]
        old=pd.read_csv(root/'docs/energy-anomaly/results/metrics.csv')
        old=old[old['quantile']==.99]
        for split in ['validation','test']:
            path=root/f'docs/stage7b/results/{split}-metrics.csv'
            if not path.exists(): continue
            new=pd.read_csv(path);new=new[new.method.isin(NAMES)]
            original=old[old.split==split].rename(columns={'detector':'method'})
            joined=new.merge(original,on=['scenario','method'],suffixes=('_new','_old'),validate='one_to_one')
            self.assertEqual(len(joined),len(new))
            for field in ['precision','recall','f1','event_recall','event_f1','alarm_episodes','delay_median_minutes']:
                import numpy as np
                np.testing.assert_allclose(joined[field+'_new'],joined[field+'_old'],equal_nan=True,atol=1e-14)
