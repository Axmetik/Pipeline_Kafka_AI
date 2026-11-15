"""Standalone sustained-low v1. Experimental context deviation, never a diagnosis.

No changes to energy_rules v2, ML, calendar/occupancy inference or runtime IO.
"""
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import math
from statistics import median

from processing.energy_schema import parse_timestamp, validate_energy
from processing.message_schema import InvalidMessage


@dataclass(frozen=True)
class LowRuleConfig:
    low_intervals: int = 6
    context_days: int = 7
    minimum_context_days: int = 3
    minimum_context_points: int = 18
    mad_multiplier: float = 3.0
    minimum_drop_wh: float = 10.0
    minimum_relative_drop: float = 0.5
    minimum_reference_wh: float = 20.0

    def __post_init__(self):
        for name in ('low_intervals','context_days','minimum_context_days','minimum_context_points'):
            v=getattr(self,name)
            if type(v) is not int or v<1:raise ValueError(name+' must be a positive integer')
        if self.low_intervals<2 or self.context_days>31:raise ValueError('Invalid duration/history budget')
        if self.minimum_context_days>self.context_days or self.minimum_context_points>self.context_days*6:
            raise ValueError('Impossible context requirements')
        for name in ('mad_multiplier','minimum_drop_wh','minimum_relative_drop','minimum_reference_wh'):
            v=getattr(self,name)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:
                raise ValueError(name+' must be finite nonnegative')
        if not 0<self.minimum_relative_drop<1 or self.minimum_drop_wh<=0 or self.minimum_reference_wh<=0:
            raise ValueError('Require positive absolute/reference floors and relative drop in (0,1)')

    @property
    def version(self):
        text=json.dumps(asdict(self),sort_keys=True,separators=(',',':'),allow_nan=False)
        return 'sustained-low-v1-'+hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class _State:
    binding: tuple
    history: deque = field(default_factory=deque)
    last_timestamp: object = None
    last_event_id: str | None = None
    last_fingerprint: str | None = None
    last_result: dict | None = None
    count: int = 0
    start: str | None = None
    references: dict | None = None


class SustainedLow:
    def __init__(self,config=None):
        self._config=config if config is not None else LowRuleConfig()
        if not isinstance(self._config,LowRuleConfig):raise TypeError('Expected LowRuleConfig')
        self._sources={}

    @property
    def config(self):return self._config

    def metadata(self):
        return dict(schema_version='sustained-low-assessment-v1',algorithm_version='sustained-low-v1',
                    rule_version=self.config.version,configuration=asdict(self.config),interval_seconds=600,
                    energy_unit='Wh',maturity='experimental',persistence='in_memory_only',
                    calibration='unvalidated_engineering_defaults',calendar_model=False)

    def _context(self,state,timestamp):
        selected=[(t,v) for t,v,eligible in state.history if eligible and
                  1<=(timestamp.date()-t.date()).days<=self.config.context_days and t.hour==timestamp.hour]
        dates={t.date() for t,_ in selected}
        details=dict(context_hour=timestamp.hour,context_clock='source_timestamp_label',
                     context_points=len(selected),context_days=len(dates),
                     required_context_points=self.config.minimum_context_points,
                     required_context_days=self.config.minimum_context_days)
        if len(dates)<self.config.minimum_context_days or len(selected)<self.config.minimum_context_points:
            return {**details,'unavailable_reason':'insufficient_hourly_context'}
        center=median(v for _,v in selected);mad=median(abs(v-center) for _,v in selected)
        if not math.isfinite(center) or not math.isfinite(mad):
            return {**details,'unavailable_reason':'nonfinite_context_threshold'}
        details.update(reference_median_wh=center,reference_mad_wh=mad)
        if center<self.config.minimum_reference_wh:
            return {**details,'unavailable_reason':'low_reference_energy'}
        threshold=center-max(self.config.mad_multiplier*1.4826*mad,self.config.minimum_drop_wh,
                             self.config.minimum_relative_drop*center)
        if not math.isfinite(threshold):return {**details,'unavailable_reason':'nonfinite_context_threshold'}
        if threshold<=0:return {**details,'unavailable_reason':'no_positive_lower_threshold'}
        return {**details,'threshold_wh':threshold}

    def process(self,message):
        record=validate_energy(message)
        if record['interval_seconds']!=600:raise InvalidMessage('Sustained low supports 600-second interval energy only')
        stamp=parse_timestamp(record['timestamp']);label=stamp.isoformat();key=(record['building_id'],record['source_id'])
        binding=(record['source_type'],record['energy']['scope'],record['interval_seconds'],record['timestamp_reference'],record['timezone'],stamp.tzinfo is not None)
        fingerprint=hashlib.sha256(json.dumps(record,sort_keys=True,allow_nan=False).encode()).hexdigest()
        old=self._sources.get(key)
        if old:
            if old.binding!=binding:raise InvalidMessage('Source measurement/time semantics changed')
            if record['event_id']==old.last_event_id:
                if fingerprint!=old.last_fingerprint:raise InvalidMessage('Conflicting retry')
                return deepcopy(old.last_result)
            if stamp<=old.last_timestamp:raise InvalidMessage('Duplicate-time or out-of-order input')
        # History tuples are immutable, frozen reference dicts never mutated.
        # Copy the deque only, avoiding a recursive clone of all prior timestamps.
        state=replace(old,history=deque(old.history)) if old else _State(binding)
        broken=state.last_timestamp is not None and (stamp-state.last_timestamp).total_seconds()!=600
        if broken:state.count=0;state.start=state.references=None
        ref=state.references[stamp.hour] if state.references is not None else self._context(state,stamp)
        threshold=ref.get('threshold_wh');value=record['energy']['value']
        if threshold is None:
            flag=None;status='unavailable';state.count=0;state.start=state.references=None
        elif value<threshold:
            if state.count==0:
                state.references={hour:{**self._context(state,stamp.replace(hour=hour)),
                                       'reference_cutoff_timestamp':label} for hour in range(24)}
                ref=state.references[stamp.hour];state.start=label
            state.count+=1;flag=state.count>=self.config.low_intervals;status='ready' if flag else 'observing'
        else:
            state.count=0;state.start=state.references=None;flag=False;status='ready'
        signal=dict(rule='sustained_low',category='consumption_pattern',maturity='experimental',
                    semantics='review_signal_not_confirmed_fault',flag=flag,status=status,
                    evidence={**ref,'energy_wh':value,'consecutive_intervals':state.count,
                              'required_intervals':self.config.low_intervals,'candidate_start_timestamp':state.start,
                              'reference_frozen':state.references is not None,'cadence_broken':broken,
                              'minimum_reference_wh':self.config.minimum_reference_wh,
                              'interpretation':'Low contextual consumption may be legitimate; no work-calendar or fault diagnosis'})
        result=dict(schema_version='sustained-low-assessment-v1',rule_version=self.config.version,
                    building_id=key[0],source_id=key[1],event_id=record['event_id'],measurement_timestamp=label,
                    time_basis='offset_aware' if stamp.tzinfo is not None else 'dataset_naive',
                    timestamp_reference=record['timestamp_reference'],timezone=record['timezone'],
                    interval_seconds=600,energy_unit='Wh',signal=signal)
        state.history.append((stamp,value,not broken))
        while state.history and (stamp.date()-state.history[0][0].date()).days>self.config.context_days:state.history.popleft()
        while len(state.history)>(self.config.context_days+1)*144:state.history.popleft()
        state.last_timestamp=stamp;state.last_event_id=record['event_id'];state.last_fingerprint=fingerprint
        state.last_result=deepcopy(result);self._sources[key]=state
        return result


def evaluate_low(records,config=None):
    engine=SustainedLow(config)
    return [engine.process(record) for record in records]
