"""Document original matching edge cases without changing frozen metrics."""
import unittest
import numpy as np
import pandas as pd
from anomaly.evaluate import metrics
from diagnostics.energy_anomaly_audit import event_matches, paired_summary


class DiagnosticEdgeTests(unittest.TestCase):
    def event(self, start=3, end=4, identity=0):
        return {'event_id':identity,'type':'spike','severity':0,'start':start,'end':end}

    def test_preexisting_alarm_episode_can_count_under_original_rule(self):
        flags=[False,True,True,True,True,False]
        labels=[False,False,False,True,True,False]
        times=pd.date_range('2016-01-01',periods=6,freq='10min')
        matched=event_matches(flags,times,[self.event()])
        self.assertEqual(matched[0]['episode_start'],1)
        self.assertEqual(matched[0]['first_overlap'],3)
        result,outcomes=metrics(flags,labels,times,[self.event()])
        self.assertEqual(result['matched_events'],1)
        self.assertEqual(outcomes[0]['delay_minutes'],0)
        # A clean counterpart with the same alarm cannot be evidence of a new response.
        clean_flags=np.asarray(flags)
        self.assertFalse((np.asarray(flags)[3:5]&~clean_flags[3:5]).any())

    def test_detection_window_includes_end_but_not_following_interval(self):
        times=pd.date_range('2016-01-01',periods=6,freq='10min')
        self.assertFalse(event_matches([False,False,True,False,False,True],times,[self.event()]))
        matched=event_matches([False,False,False,False,True,False],times,[self.event()])
        self.assertEqual(matched[0]['first_overlap'],4)

    def test_timestamp_gap_breaks_alarm_episode(self):
        times=pd.to_datetime(['2016-01-01T00:00','2016-01-01T00:10','2016-01-01T00:40','2016-01-01T00:50'])
        events=[self.event(0,0,0),self.event(2,2,1)]
        matched=event_matches([True]*4,times,events)
        self.assertEqual(len(matched),2)
        self.assertEqual(matched[1]['episode_start'],2)

    def test_multiple_alarm_episodes_cannot_match_same_event_twice(self):
        times=pd.date_range('2016-01-01',periods=6,freq='10min')
        matched=event_matches([False,True,False,True,False,False],times,[self.event(1,3)])
        self.assertEqual(len(matched),1)
        self.assertEqual(matched[0]['episode_start'],1)

    def test_paired_crossings_are_strict_and_distinguish_new_lost(self):
        frame=pd.DataFrame({'clean_score':[0.,3.,1.,2.],'modified_score':[3.,1.,2.,2.],'threshold':[2.]*4})
        result=paired_summary(frame)
        self.assertEqual(result['clean_crossings'],1)
        self.assertEqual(result['modified_crossings'],1)
        self.assertEqual(result['new_crossings'],1)
        self.assertEqual(result['lost_crossings'],1)
        self.assertEqual(result['modified_crossing_rate'],.25)
