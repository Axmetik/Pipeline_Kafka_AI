"""Causal seasonal extension of unchanged Stage 2 features."""
from collections import deque
from datetime import timedelta

import pandas as pd
from processing.energy_processor import EnergyProcessor, FEATURE_NAMES
from processing.energy_schema import validate_energy, parse_timestamp
from processing.message_schema import InvalidMessage

BENCHMARK_FEATURES = [*FEATURE_NAMES, 'seasonal_energy_wh']
FEATURE_VERSION = 'benchmark-energy-v1'


class BenchmarkFeatures:
    def __init__(self):
        self.base = EnergyProcessor()
        self.histories = {}

    def process(self, raw):
        record = validate_energy(raw)
        result = self.base.process(record)
        key = (record['building_id'], record['source_id'])
        history = self.histories.setdefault(key, deque(maxlen=144))
        if result['gap_detected']:
            history.clear()
        timestamp = parse_timestamp(record['timestamp'])
        history.append((timestamp, record['energy']['value']))
        seasonal_time = parse_timestamp(result['forecast_target_timestamp']) - timedelta(days=1)
        if len(history) != 144 or history[0][0] != seasonal_time:
            result['features'] = None
        elif result['features'] is not None:
            result['features'] = {**result['features'], 'seasonal_energy_wh': history[0][1]}
        return result


def build_samples(records):
    processor = BenchmarkFeatures()
    pending = {}
    rows, rejected = [], []
    received = warmup = 0
    for raw in records:
        received += 1
        try:
            result = processor.process(raw)
        except InvalidMessage as exc:
            rejected.append({'event_id': raw.get('event_id'), 'reason': str(exc)})
            continue
        record = result['record']
        key = (record['building_id'], record['source_id'])
        previous = pending.get(key)
        if previous is not None and previous['features'] is not None and previous['forecast_target_timestamp'] == result['forecast_origin']:
            rows.append({**previous['features'], 'building_id': key[0], 'source_id': key[1],
                         'forecast_origin': previous['forecast_origin'],
                         'forecast_target_timestamp': previous['forecast_target_timestamp'],
                         'actual_energy_wh': record['energy']['value']})
        warmup += int(result['features'] is None)
        pending[key] = result
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values(['forecast_target_timestamp', 'building_id', 'source_id']).reset_index(drop=True)
    return frame, {'received': received, 'eligible': len(frame), 'warmup': warmup, 'rejected': rejected}


def split_samples(frame, protocol):
    if frame.empty:
        raise ValueError('No eligible samples')
    target = pd.to_datetime(frame.forecast_target_timestamp)
    validation_start = pd.Timestamp(protocol['validation_start'])
    test_start = pd.Timestamp(protocol['test_start'])
    test_end = pd.Timestamp(protocol['test_end'])
    if not validation_start < test_start <= test_end:
        raise ValueError('Invalid chronological boundaries')
    parts = {
        'train': frame[target < validation_start].copy(),
        'validation': frame[(target >= validation_start) & (target < test_start)].copy(),
        'test': frame[(target >= test_start) & (target <= test_end)].copy(),
    }
    if any(part.empty for part in parts.values()):
        raise ValueError('Each split must contain samples')
    return parts
