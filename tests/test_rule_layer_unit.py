"""Targeted optional-layer contracts; no model training or external services."""
from copy import deepcopy
from datetime import datetime
import itertools,json,os,unittest
from unittest.mock import patch
from integration.rule_layer import RuleLayer,hybrid_or,digest
from integration.runtime import RecoveryError
from integration.settings import Settings
from processing.energy_rules import RuleConfig
from test_energy_rules import record

MODEL=dict(model_id='fixture-residual',model_version='fixture-v1',feature_version='rf21-v1',threshold_version='q99-v1')
SCORES={'scores':[{'detector':'residual','flag':None}]}

def anchor(layer,raw):
    key=(raw['building_id'],raw['source_id']);blob=layer.snapshot(key)
    return dict(building_id=key[0],source_id=key[1],layer_version=layer.version,state=blob,state_sha256=digest(blob),
                last_timestamp=raw['timestamp'],event_id=raw['event_id'],wire_record=raw,stale=False)

class RuleLayerUnitTests(unittest.TestCase):
    def test_or_all_null_combinations_and_provenance(self):
        for a,b in itertools.product((True,False,None),repeat=2):
            d=hybrid_or(a,b);expected=True if a is True or b is True else False if a is False and b is False else None
            self.assertIs(d['flag'],expected)
            self.assertEqual(d['coverage_count'],sum(v is not None for v in (a,b)))
            self.assertEqual(d['triggered_inputs'],[k for k,v in zip(('residual','sustained_high'),(a,b)) if v is True])
        with self.assertRaises(ValueError):hybrid_or(1,False)

    def test_switch_default_off_and_strict_environment(self):
        with patch('integration.settings.env_file',return_value={}),patch.dict(os.environ,{'MVP_DATABASE_URL':'postgresql://unused'},clear=True):
            self.assertFalse(Settings.from_env().energy_rules_enabled)
            os.environ['MVP_ENERGY_RULES_ENABLED']='true';self.assertTrue(Settings.from_env().energy_rules_enabled)
            os.environ['MVP_ENERGY_RULES_ENABLED']='typo'
            with self.assertRaises(ValueError):Settings.from_env()

    def test_json_roundtrip_preserves_seven_days_frozen_profile_and_retry(self):
        layer=RuleLayer(MODEL)
        for i in range(7*144+47):layer.compute(record(i,100),SCORES)
        for i in range(7*144+47,7*144+52):last=record(i,200);layer.compute(last,SCORES)
        saved=json.loads(json.dumps(anchor(layer,last)))
        self.assertGreater(len(saved['state']['source']['history']),144)
        self.assertEqual(saved['state']['source']['high_count'],5)
        self.assertEqual(len(saved['state']['source']['high_references']),24)
        restored=RuleLayer(MODEL);restored.restore(saved)
        self.assertEqual(restored.snapshot(('house','meter')),layer.snapshot(('house','meter')))
        # Exact retry has the same assessment, without advancing rule counters.
        before=restored.snapshot(('house','meter'));restored.compute(last,SCORES)
        self.assertEqual(before,restored.snapshot(('house','meter')))
        nextrow=record(7*144+52,200)
        a=layer.compute(nextrow,SCORES);b=restored.compute(nextrow,SCORES)
        self.assertEqual(a['signals'],b['signals']);self.assertTrue(b['decision']['flag'])

    def test_tamper_anchor_stale_and_configuration_change(self):
        l=RuleLayer(MODEL);r=record(0);l.compute(r,SCORES);saved=anchor(l,r)
        bad=deepcopy(saved);bad['state']['source']['high_count']=99
        with self.assertRaises(RecoveryError):RuleLayer(MODEL).restore(bad)
        bad=deepcopy(saved);bad['wire_record']['energy']['value']=42
        with self.assertRaises(RecoveryError):RuleLayer(MODEL).restore(bad)
        changed=RuleLayer(MODEL,RuleConfig(high_intervals=7));changed.restore(saved)
        self.assertEqual(changed.activation[('house','meter')],'configuration_changed')
        stale=deepcopy(saved);stale['stale']=True;new=RuleLayer(MODEL);new.restore(stale)
        self.assertEqual(new.activation[('house','meter')],'activation_gap')
        self.assertEqual(new.engine._sources,{})

    def test_categories_unsupported_interval_and_no_low(self):
        layer=RuleLayer(MODEL);r=record(0);r['interval_seconds']=1200
        out=layer.compute(r,SCORES)
        self.assertEqual({s['rule'] for s in out['signals']},{'flatline','interval_gap','sustained_high'})
        self.assertTrue(all(s['flag'] is None for s in out['signals']))
        self.assertIsNone(out['decision']['flag']);self.assertFalse(out['configuration']['low_enabled'])
        self.assertIsNone(out['state']['source'])
