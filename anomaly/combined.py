"""Versioned current-record voting; no model/threshold mutation or history access."""
from functools import lru_cache
import json
import math
from pathlib import Path

NAMES = ('isolation_forest', 'autoencoder', 'residual')
RULES = {'or': 1, 'majority': 2, 'unanimous': 3}

@lru_cache(maxsize=1)
def selected_rule():
    config = json.loads((Path(__file__).resolve().parents[1] / 'configs/combined-rule-v1.json').read_text())
    if config['rule_version'] != 'combined-q99-v1-' + config['rule'] or config['rule'] not in RULES:
        raise ValueError('Unsupported combined rule configuration')
    return config['rule']

def combine(scores, rule=None):
    rule = rule or selected_rule()
    if rule not in RULES: raise ValueError('Unknown combined rule')
    by_name = {s['detector']: s for s in scores}
    if len(by_name) != len(scores) or set(by_name) - set(NAMES):
        raise ValueError('Exactly one original result per detector is required')
    ready, reasons, versions = [], [], {}
    for name in NAMES:
        s = by_name.get(name, {})
        versions[name] = {k:s.get(k) for k in ('model_id','model_version','feature_version','threshold_version')}
        valid = (s.get('status') == 'ready' and type(s.get('flag')) is bool and
                 all(type(s.get(k)) in (float,int) and math.isfinite(s[k]) for k in ('score','threshold')))
        if valid: ready.append(name)
        else: reasons.append(s.get('status') if s.get('status') in ('warmup','gap','incompatible') else 'partial')
    triggered = [name for name in ready if by_name[name]['flag']]
    status = next((s for s in ('incompatible','gap','warmup','partial') if s in reasons), 'ready')
    count = len(triggered) if status == 'ready' else None
    return {'rule':rule,'rule_version':'combined-q99-v1-'+rule,'maturity':'experimental',
            'coverage_count':len(ready),'available_detectors':ready,'triggered_methods':triggered,
            'available_trigger_count':len(triggered),'trigger_count':count,
            'flag':count >= RULES[rule] if count is not None else None,
            'agreement':('none','one','two','three')[count] if count is not None else None,
            'status':status,'input_versions':versions}
