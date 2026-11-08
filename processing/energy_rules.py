"""Causal, in-memory review signals; independent of ML scores and runtime storage.

Consume the existing energy-message-v1 wire contract. No wall-clock, model,
network, database, filesystem writes, or implicit timezone assignment is used.
"""
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import timedelta
import hashlib
import json
import math
from statistics import median

from processing.energy_schema import parse_timestamp, validate_energy
from processing.message_schema import InvalidMessage


@dataclass(frozen=True)
class RuleConfig:
    """Engineering defaults, not fitted parameters or a validated alarm policy."""
    plateau_intervals: int = 6
    plateau_tolerance_wh: float = 0.0
    high_intervals: int = 6
    context_days: int = 7
    minimum_context_days: int = 3
    minimum_context_points: int = 18
    mad_multiplier: float = 3.0
    minimum_excess_wh: float = 50.0
    minimum_relative_excess: float = 0.5

    def __post_init__(self):
        for name in ('plateau_intervals', 'high_intervals', 'context_days',
                     'minimum_context_days', 'minimum_context_points'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f'{name} must be a positive integer')
        if self.plateau_intervals < 2 or self.high_intervals < 2:
            raise ValueError('Duration rules require at least two intervals')
        if self.context_days > 31:
            raise ValueError('context_days must not exceed the 31-day memory budget')
        if self.minimum_context_days > self.context_days:
            raise ValueError('Minimum context days exceeds the history window')
        if self.minimum_context_points > self.context_days * 6:
            raise ValueError('Minimum points exceeds six ten-minute samples per hour/day')
        for name in ('plateau_tolerance_wh', 'mad_multiplier', 'minimum_excess_wh',
                     'minimum_relative_excess'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if self.minimum_excess_wh == self.minimum_relative_excess == self.mad_multiplier == 0:
            raise ValueError('At least one high-consumption margin must be positive')

    @property
    def version(self):
        content = json.dumps(asdict(self), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return 'energy-rules-v1-' + hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class _SourceState:
    binding: tuple
    history: deque = field(default_factory=deque)
    last_timestamp: object = None
    last_event_id: str | None = None
    last_fingerprint: str | None = None
    last_result: dict | None = None
    contiguous: int = 0
    plateau_count: int = 0
    plateau_min: float = 0.0
    plateau_max: float = 0.0
    plateau_start: str | None = None
    high_count: int = 0
    high_start: str | None = None
    high_reference: dict | None = None


def _signal(rule, category, status, flag, **evidence):
    return {'rule': rule, 'category': category, 'status': status, 'flag': flag,
            'maturity': 'experimental', 'semantics': 'review_signal_not_confirmed_fault',
            'evidence': evidence}


class EnergyRules:
    """Independent state for each building/source; call once per ordered record.

    Exact last-message retries are idempotent; older/out-of-order deliveries and
    conflicting retries fail explicitly. Durable deduplication belongs to the
    existing worker ledger, which this module does not modify or bypass.
    """
    def __init__(self, config=None):
        self._config = config if config is not None else RuleConfig()
        if not isinstance(self._config, RuleConfig):
            raise TypeError('config must be a RuleConfig')
        self._sources = {}

    @property
    def config(self):
        return self._config

    def metadata(self):
        return {'schema_version': 'energy-rule-assessment-v1',
                'rule_version': self.config.version, 'configuration': asdict(self.config),
                'interval_seconds': 600, 'energy_unit': 'Wh',
                'calibration': 'unvalidated_engineering_defaults',
                'persistence': 'in_memory_only'}

    def _context(self, state, timestamp):
        # Only previous labelled dates in the same labelled hour. No interpolation
        # and no current-day/self inclusion, even in batch evaluation.
        days = self.config.context_days
        selected = [(stamp, value) for stamp, value, eligible in state.history
                    if eligible and 1 <= (timestamp.date() - stamp.date()).days <= days
                    and stamp.hour == timestamp.hour]
        dates = {stamp.date() for stamp, _ in selected}
        details = {'context_points': len(selected), 'context_days': len(dates),
                   'context_hour': timestamp.hour,
                   'context_clock': 'source_timestamp_label',
                   'required_context_points': self.config.minimum_context_points,
                   'required_context_days': self.config.minimum_context_days}
        if (len(dates) < self.config.minimum_context_days or
                len(selected) < self.config.minimum_context_points):
            return details
        center = median(value for _, value in selected)
        mad = median(abs(value - center) for _, value in selected)
        threshold = center + max(self.config.mad_multiplier * 1.4826 * mad,
                                 self.config.minimum_excess_wh,
                                 self.config.minimum_relative_excess * center)
        if not math.isfinite(threshold):
            # Valid but extremely large readings must not yield an Infinity signal.
            return {**details, 'unavailable_reason': 'nonfinite_context_threshold'}
        return {**details, 'reference_median_wh': center, 'reference_mad_wh': mad,
                'threshold_wh': threshold}

    def process(self, message):
        record = validate_energy(message)
        if record['interval_seconds'] != 600:
            raise InvalidMessage('Energy rules v1 support 600-second interval energy only')
        timestamp = parse_timestamp(record['timestamp'])
        timestamp_label = timestamp.isoformat()
        key = record['building_id'], record['source_id']
        binding = (record['source_type'], record['energy']['scope'], record['interval_seconds'],
                   record['timestamp_reference'], record['timezone'], timestamp.tzinfo is not None)
        fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False).encode()).hexdigest()
        previous = self._sources.get(key)
        if previous:
            if previous.binding != binding:
                raise InvalidMessage('Source measurement/time semantics changed; use a different source identity')
            if record['event_id'] == previous.last_event_id:
                if fingerprint != previous.last_fingerprint:
                    raise InvalidMessage('Conflicting retry for the same event_id')
                return deepcopy(previous.last_result)
            if timestamp <= previous.last_timestamp:
                raise InvalidMessage('Duplicate-time or out-of-order rule input')
        state = deepcopy(previous) if previous else _SourceState(binding=binding)
        delta = ((timestamp - state.last_timestamp).total_seconds()
                 if state.last_timestamp is not None else None)
        cadence_broken = delta is not None and delta != 600
        if cadence_broken:
            state.contiguous = state.plateau_count = state.high_count = 0
            state.high_reference = state.high_start = None
        state.contiguous += 1
        value = record['energy']['value']

        if delta is None:
            gap = _signal('interval_gap', 'telemetry_quality', 'warmup', None,
                          elapsed_seconds=None, missing_intervals=None, detection='on_next_received_measurement')
        else:
            aligned = delta > 600 and delta % 600 == 0
            gap = _signal('interval_gap', 'telemetry_quality', 'ready', cadence_broken,
                          elapsed_seconds=delta,
                          missing_intervals=int(delta / 600) - 1 if aligned else (0 if delta == 600 else None),
                          reason='missing_intervals' if aligned else ('irregular_cadence' if cadence_broken else 'continuous'),
                          expected_timestamp=(state.last_timestamp + timedelta(seconds=600)).isoformat(),
                          detection='on_next_received_measurement')

        low = min(state.plateau_min, value) if state.plateau_count else value
        high = max(state.plateau_max, value) if state.plateau_count else value
        if state.plateau_count and high - low <= self.config.plateau_tolerance_wh:
            state.plateau_count += 1
            state.plateau_min, state.plateau_max = low, high
        else:
            state.plateau_count = 1
            state.plateau_min = state.plateau_max = value
            state.plateau_start = timestamp_label
        plateau_ready = state.contiguous >= self.config.plateau_intervals
        plateau = _signal('flatline', 'telemetry_quality', 'ready' if plateau_ready else 'warmup',
                          state.plateau_count >= self.config.plateau_intervals if plateau_ready else None,
                          consecutive_intervals=state.plateau_count,
                          required_intervals=self.config.plateau_intervals,
                          tolerance_wh=self.config.plateau_tolerance_wh,
                          range_wh=state.plateau_max - state.plateau_min,
                          evidence_start_timestamp=state.plateau_start,
                          observed_label_span_seconds=(state.plateau_count - 1) * 600,
                          represented_interval_seconds=state.plateau_count * 600,
                          interpretation='Repeated values can also be normal, zero load, or meter rounding')

        reference = state.high_reference or self._context(state, timestamp)
        threshold = reference.get('threshold_wh')
        if threshold is None:
            elevated_status, elevated_flag = 'warmup', None
        elif value > threshold:
            if state.high_count == 0:
                state.high_reference = deepcopy(reference)
                state.high_start = timestamp_label
            state.high_count += 1
            elevated_flag = state.high_count >= self.config.high_intervals
            elevated_status = 'ready' if elevated_flag else 'observing'
        else:
            state.high_count = 0
            state.high_reference = state.high_start = None
            elevated_status, elevated_flag = 'ready', False
        elevated = _signal('sustained_high', 'consumption_pattern', elevated_status, elevated_flag,
                           **reference, energy_wh=value, consecutive_intervals=state.high_count,
                           required_intervals=self.config.high_intervals,
                           candidate_start_timestamp=state.high_start,
                           reference_frozen=state.high_reference is not None,
                           interpretation='High consumption relative to historical context, not a diagnosed fault')

        result = {'schema_version': 'energy-rule-assessment-v1', 'rule_version': self.config.version,
                  'building_id': key[0], 'source_id': key[1], 'event_id': record['event_id'],
                  'measurement_timestamp': timestamp_label,
                  'time_basis': 'offset_aware' if timestamp.tzinfo is not None else 'dataset_naive',
                  'timestamp_reference': record['timestamp_reference'], 'timezone': record['timezone'],
                  'interval_seconds': 600, 'energy_unit': 'Wh',
                  'signals': [gap, plateau, elevated]}
        # Do not allow cadence-violating samples to inflate reference coverage.
        state.history.append((timestamp, value, not cadence_broken))
        # Calendar-date window includes all six samples of the oldest same-hour
        # bin. There is also a fixed bound for pathological high-frequency input.
        while state.history and (timestamp.date() - state.history[0][0].date()).days > self.config.context_days:
            state.history.popleft()
        while len(state.history) > (self.config.context_days + 1) * 144:
            state.history.popleft()
        state.last_timestamp, state.last_event_id = timestamp, record['event_id']
        state.last_fingerprint, state.last_result = fingerprint, deepcopy(result)
        self._sources[key] = state
        return result


def evaluate(records, config=None):
    """Batch wrapper around the very same causal streaming implementation."""
    engine = EnergyRules(config)
    return [engine.process(record) for record in records]
