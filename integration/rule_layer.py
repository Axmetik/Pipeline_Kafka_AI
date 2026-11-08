"""Optional frozen-v2 rule adapter with explicit JSON recovery (never pickle)."""
from collections import deque
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json

from processing.energy_rules import EnergyRules,RuleConfig,_SourceState
from processing.energy_schema import parse_timestamp,validate_energy
from integration.runtime import RecoveryError

SNAPSHOT_VERSION='energy-rules-state-v1'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def hybrid_or(residual,high):
    inputs={'residual':residual,'sustained_high':high}
    if any(v is not None and type(v) is not bool for v in inputs.values()):raise ValueError('Expected bool or null')
    available=[k for k,v in inputs.items() if v is not None]
    triggered=[k for k,v in inputs.items() if v is True]
    flag=True if triggered else False if len(available)==2 else None
    return dict(flag=flag,status='ready' if len(available)==2 else 'partial_positive' if flag else 'unavailable',
                coverage_count=len(available),available_inputs=available,triggered_inputs=triggered)


class RuleLayer:
    def __init__(self,residual_model,config=None):
        self.engine=EnergyRules(config or RuleConfig())
        self.residual_version={k:residual_model[k] for k in ('model_id','model_version','feature_version','threshold_version')}
        self.configuration={'algorithm':'residual-high-layer-v1','rule_version':self.engine.config.version,
                            'rules':asdict(self.engine.config),'inputs':{'residual':self.residual_version},
                            'hybrid':'residual OR sustained_high','low_enabled':False}
        self.version='residual-high-v1-'+digest(self.configuration)[:24]
        self.activation={}

    def restore(self,row):
        key=(row['building_id'],row['source_id'])
        blob=row['state']
        if digest(blob)!=row['state_sha256']:raise RecoveryError('Rule snapshot checksum mismatch')
        if row['layer_version']!=self.version:
            self.activation[key]='configuration_changed';return
        if blob.get('schema_version')!=SNAPSHOT_VERSION or blob.get('rule_version')!=self.engine.config.version:
            raise RecoveryError('Unsupported rule snapshot version')
        if row.get('stale'):
            self.activation[key]='activation_gap';return
        data=blob['source']
        if data is None:return
        state=_SourceState(binding=tuple(data['binding']))
        state.history=deque((parse_timestamp(t),v,eligible) for t,v,eligible in data['history'])
        state.last_timestamp=parse_timestamp(data['last_timestamp'])
        fingerprint=hashlib.sha256(json.dumps(validate_energy(row['wire_record']),sort_keys=True,allow_nan=False).encode()).hexdigest()
        if data['last_fingerprint']!=fingerprint:
            raise RecoveryError('Rule snapshot fingerprint differs from measurement')
        if state.last_timestamp!=parse_timestamp(row['last_timestamp']) or data['last_event_id']!=row['event_id']:
            raise RecoveryError('Rule snapshot anchor differs from measurement')
        for field in ('last_event_id','last_fingerprint','last_result','high_count','high_start'):
            setattr(state,field,deepcopy(data[field]))
        state.plateau_window=deque(tuple(p) for p in data['plateau_window'])
        state.high_references=({int(k):v for k,v in data['high_references'].items()} if data['high_references'] is not None else None)
        self.engine._sources[key]=state
        self.activation[key]='restored'

    def snapshot(self,key):
        state=self.engine._sources.get(key);data=None
        if state is not None:
            data={field:deepcopy(getattr(state,field)) for field in ('binding','last_event_id','last_fingerprint','last_result','high_count','high_start')}
            data.update(binding=list(state.binding),last_timestamp=state.last_timestamp.isoformat(),
                        history=[[t.isoformat(),v,eligible] for t,v,eligible in state.history],
                        plateau_window=[list(p) for p in state.plateau_window],
                        high_references={str(k):deepcopy(v) for k,v in state.high_references.items()} if state.high_references is not None else None)
        return {'schema_version':SNAPSHOT_VERSION,'rule_version':self.engine.config.version,'source':data}

    def compute(self,raw,result):
        record=validate_energy(raw);key=(record['building_id'],record['source_id'])
        existed=key in self.engine._sources
        if record['interval_seconds']==600:
            assessment=self.engine.process(raw);signals=assessment['signals']
        else:
            signals=[dict(rule=n,category='consumption_pattern' if n=='sustained_high' else 'telemetry_quality',
                          status='incompatible',flag=None,evidence={'unavailable_reason':'unsupported_interval_seconds'},
                          maturity='experimental',semantics='review_signal_not_confirmed_fault') for n in ('flatline','interval_gap','sustained_high')]
        high=next(s['flag'] for s in signals if s['rule']=='sustained_high')
        residual=next(s['flag'] for s in result['scores'] if s['detector']=='residual')
        decision=hybrid_or(residual,high)
        activation=self.activation.pop(key,'continuing' if existed else 'new_activation')
        snapshot=self.snapshot(key)
        return dict(signals=signals,decision=decision,configuration=self.configuration,layer_version=self.version,
                    rule_version=self.engine.config.version,activation=activation,state=snapshot,state_sha256=digest(snapshot))
