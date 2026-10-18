"""Shared causal state for batch evaluation and streaming detection."""
import numpy as np
import pandas as pd
from benchmark.features import BenchmarkFeatures, BENCHMARK_FEATURES
from processing.energy_processor import FEATURE_NAMES, EnergyProcessor
from processing.energy_schema import validate_energy

FEATURE_VERSION = 'energy-anomaly-20-v1'
RF_FEATURE_VERSION = 'benchmark-energy-v1'
NAMES = ('isolation_forest', 'autoencoder', 'residual')


class CapturingProcessor(EnergyProcessor):
    def process(self, record):
        result = super().process(record)
        self.last_features = ([result['features'][n] for n in FEATURE_NAMES]
                              if result['features'] is not None else None)
        return result


class CapturingBenchmark(BenchmarkFeatures):
    def __init__(self):
        super().__init__()
        self.base = CapturingProcessor()


class FeatureStream:
    def __init__(self):
        self.processor = CapturingBenchmark()

    def step(self, raw):
        result = self.processor.process(raw)
        return result['record'], result, self.processor.base.last_features


def collect(records, validate_source=None):
    stream = FeatureStream()
    pending = {}
    rows, current, previous = [], [], []
    for raw in records:
        record = validate_energy(raw)
        if validate_source:
            validate_source(record)
        record, result, x = stream.step(raw)
        key = (record['building_id'], record['source_id'])
        prev = pending.get(key)
        ready_rf = prev is not None and prev[0] == record['timestamp']
        rows.append({'event_id': record['event_id'], 'building_id': key[0], 'source_id': key[1],
                     'measurement_timestamp': record['timestamp'], 'actual_energy_wh': record['energy']['value'],
                     'feature_ready': x is not None, 'residual_ready': ready_rf,
                     'forecast_origin': prev[2] if ready_rf else None,
                     'forecast_target_timestamp': record['timestamp'] if ready_rf else None,
                     'gap_detected': result['gap_detected']})
        current.append(x if x is not None else [np.nan] * len(FEATURE_NAMES))
        previous.append(prev[1] if ready_rf else [np.nan] * len(BENCHMARK_FEATURES))
        pending[key] = ((result['forecast_target_timestamp'],
                         [result['features'][n] for n in BENCHMARK_FEATURES], result['forecast_origin'])
                        if result['features'] is not None else None)
    return pd.DataFrame(rows), np.asarray(current, dtype=float), np.asarray(previous, dtype=float)
