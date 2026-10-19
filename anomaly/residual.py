"""Single shared scoring contract with strictly previous-interval forecasts."""
from datetime import datetime, timezone
import numpy as np
from processing.energy_schema import validate_energy
from benchmark.features import BENCHMARK_FEATURES
from anomaly.features import FeatureStream, NAMES


def score_batch(bundle, frame, x, rf_x):
    result = frame.copy()
    for name in NAMES:
        result[name] = np.nan
    mask = frame.feature_ready.to_numpy()
    if mask.any():
        for name, values in bundle.current_scores(x[mask]).items():
            result.loc[mask, name] = values
    mask = frame.residual_ready.to_numpy()
    result['prediction_wh'] = np.nan
    if mask.any():
        result.loc[mask, 'prediction_wh'] = bundle.forecast(rf_x[mask])
    result['signed_residual_wh'] = result.actual_energy_wh - result.prediction_wh
    result['residual'] = result.signed_residual_wh.abs()
    return result


class StreamDetector:
    def __init__(self, bundle):
        self.bundle = bundle
        if '0.99' not in bundle.thresholds:
            raise ValueError('Streaming requires calibrated thresholds')
        self.features = FeatureStream()
        self.pending = {}

    def process(self, raw):
        record = validate_energy(raw)
        self.bundle.validate_source(record)
        key = (record['building_id'], record['source_id'])
        # The stored prediction was calculated during the previous call.
        previous = self.pending.get(key)
        record, result, current = self.features.step(raw)
        ready = previous is not None and previous['target'] == record['timestamp']
        output = {'event_id': record['event_id'], 'building_id': key[0], 'source_id': key[1],
                  'measurement_timestamp': record['timestamp'], 'actual_energy_wh': record['energy']['value'],
                  'detected_at_utc': datetime.now(timezone.utc).isoformat(),
                  'feature_ready': current is not None, 'residual_ready': ready,
                  'gap_detected': result['gap_detected'], 'prediction_wh': previous['value'] if ready else None,
                  'forecast_origin': previous['origin'] if ready else None,
                  'forecast_target_timestamp': previous['target'] if ready else None,
                  'forecast_generated_at_utc': previous['generated_at'] if ready else None,
                  'model_version': self.bundle.metadata['model_version'],
                  'feature_version': self.bundle.metadata['feature_version'],
                  'rf_feature_version': self.bundle.metadata['rf_feature_version'],
                  'threshold_version': self.bundle.metadata.get('threshold_version', 'fixture')} 
        for name in NAMES:
            output[name] = None
        if current is not None:
            output.update({name: float(value[0]) for name, value in self.bundle.current_scores(np.asarray([current])).items()})
        output['signed_residual_wh'] = record['energy']['value'] - previous['value'] if ready else None
        output['residual'] = abs(output['signed_residual_wh']) if ready else None
        for name in NAMES:
            output[name + '_threshold'] = self.bundle.thresholds['0.99'][name]
            output[name + '_flag'] = output[name] > output[name + '_threshold'] if output[name] is not None else None
            output[name + '_status'] = 'ok' if output[name] is not None else ('gap' if result['gap_detected'] else 'warmup')
        features = result['features']
        self.pending[key] = ({'origin': result['forecast_origin'], 'target': result['forecast_target_timestamp'],
                              'value': float(self.bundle.forecast(np.asarray([[features[n] for n in BENCHMARK_FEATURES]]))[0]),
                              'generated_at': datetime.now(timezone.utc).isoformat()}
                             if features is not None else None)
        return output
