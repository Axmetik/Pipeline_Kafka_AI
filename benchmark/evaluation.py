"""Metrics, training-only peak threshold and isolated prediction timing."""
from time import perf_counter_ns
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error


def error_metrics(actual, predicted):
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    if not len(actual):
        return {'count': 0, 'mae_wh': None, 'rmse_wh': None,
                'mean_signed_error_wh': None, 'underprediction_fraction': None}
    error = predicted - actual
    return {'count': len(actual), 'mae_wh': float(mean_absolute_error(actual, predicted)),
            'rmse_wh': float(np.sqrt(mean_squared_error(actual, predicted))),
            'mean_signed_error_wh': float(error.mean()),
            'underprediction_fraction': float((error < 0).mean())}


def relative_improvement(baseline_error, model_error):
    if baseline_error is None or baseline_error == 0 or model_error is None:
        return None
    return 100 * (baseline_error - model_error) / baseline_error


def peak_threshold(train_targets, quantile=0.9):
    return float(np.quantile(np.asarray(train_targets), quantile, method='linear'))


def evaluate_predictions(actual, predictions, threshold):
    actual = np.asarray(actual)
    peak = actual > threshold
    overall, peaks = {}, {}
    for name, predicted in predictions.items():
        overall[name] = error_metrics(actual, predicted)
        peaks[name] = error_metrics(actual[peak], np.asarray(predicted)[peak])
    for table in (overall, peaks):
        for row in table.values():
            for metric in ('mae_wh', 'rmse_wh'):
                row[f'{metric}_improvement_pct'] = relative_improvement(table['persistence'][metric], row[metric])
    return overall, peaks


def measure_prediction_time(model, features, config):
    from benchmark.models import predict
    indices = np.linspace(0, len(features) - 1, min(config['sample_count'], len(features)), dtype=int)
    rows = [features[index:index + 1] for index in indices]
    for i in range(config['warmup_calls']):
        predict(model, rows[i % len(rows)])
    observations = []
    for repeat in range(config['repeats']):
        for index, row in zip(indices, rows):
            start = perf_counter_ns()
            predict(model, row)
            elapsed = perf_counter_ns() - start
            observations.append({'repeat': repeat, 'test_row_index': int(index), 'microseconds': elapsed / 1000})
    durations = [row['microseconds'] for row in observations]
    return {'median_us': float(np.median(durations)), 'p95_us': float(np.percentile(durations, 95)),
            'calls': len(durations)}, observations
