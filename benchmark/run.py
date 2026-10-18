"""Run the frozen Stage 3 protocol, without changing production inference."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import joblib
import pandas as pd
from threadpoolctl import threadpool_info, threadpool_limits
from producer.appliances_dataset import dataset_sha256, iter_appliances
from benchmark.config import load_protocol
from benchmark.features import BENCHMARK_FEATURES, FEATURE_VERSION, build_samples, split_samples
from benchmark.selection import tune_on_validation, refit_selected
from benchmark.models import predict
from benchmark.evaluation import peak_threshold, evaluate_predictions, measure_prediction_time
from benchmark.plots import save_plots

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def table(rows, timing=None):
    result = '| Model | MAE (Wh) | RMSE (Wh) | MAE improvement vs persistence | Median inference (µs) |\n|---|---:|---:|---:|---:|\n'
    for name, metrics in rows.items():
        latency = f"{timing[name]['median_us']:.2f}" if timing else '—'
        improvement = metrics.get('mae_wh_improvement_pct')
        improvement = f'{improvement:.2f}%' if improvement is not None else '—'
        mae = f"{metrics['mae_wh']:.4f}" if metrics['mae_wh'] is not None else '—'
        rmse = f"{metrics['rmse_wh']:.4f}" if metrics['rmse_wh'] is not None else '—'
        result += f'| {name} | {mae} | {rmse} | {improvement} | {latency} |\n'
    return result


def run(dataset, output, models_output):
    protocol, protocol_hash = load_protocol()
    if dataset_sha256(dataset) != protocol['dataset_sha256']:
        raise ValueError('Dataset checksum differs from the frozen protocol')
    if output.exists() or models_output.exists():
        raise ValueError('Output paths must be new; existing experiments are never overwritten')
    output.mkdir(parents=True)
    models_output.mkdir(parents=True)
    write_json(output / 'protocol.json', protocol)
    source_files = sorted([* (ROOT / 'benchmark').glob('*.py'), ROOT / 'producer/appliances_dataset.py', ROOT / 'processing/energy_processor.py', ROOT / 'processing/energy_schema.py'])
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    metadata = {
        'protocol_sha256': protocol_hash, 'dataset_sha256': dataset_sha256(dataset),
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'git_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip()),
        'source_hashes': source_hashes, 'seed': protocol['seed'], 'feature_version': FEATURE_VERSION,
        'features': BENCHMARK_FEATURES, 'python': sys.version, 'platform': platform.platform(),
        'machine': platform.machine(), 'processor': platform.processor(), 'logical_cpu_count': os.cpu_count(),
        'libraries': {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scikit-learn', 'scipy', 'joblib', 'threadpoolctl', 'matplotlib', 'pyarrow']},
        'test_previously_viewed': True,
    }
    start = perf_counter()
    frame, quality = build_samples(iter_appliances(dataset))
    parts = split_samples(frame, protocol)
    write_json(output / 'data_quality.json', quality)
    splits = {name: {'count': len(part), 'first_target': part.forecast_target_timestamp.iloc[0], 'last_target': part.forecast_target_timestamp.iloc[-1]} for name, part in parts.items()}
    write_json(output / 'splits.json', splits)
    pd.concat([part[['building_id', 'source_id', 'forecast_origin', 'forecast_target_timestamp']].assign(split=name) for name, part in parts.items()]).to_csv(output / 'split_membership.csv', index=False)
    threshold = peak_threshold(parts['train'].actual_energy_wh, protocol['peak_quantile'])
    with threadpool_limits(limits=protocol['threads']):
        metadata['threadpools'] = threadpool_info()
        selection, trials = tune_on_validation(parts['train'], parts['validation'], protocol)
        # Persist the decision before refitting or predicting any test target.
        write_json(output / 'selection.json', selection)
        write_json(output / 'validation_trials.json', trials)
        models = refit_selected(pd.concat([parts['train'], parts['validation']]), selection, protocol['seed'])
        metadata['estimator_parameters'] = {name: model.named_steps['regressor'].get_params()
                                            for name, model in models.items() if hasattr(model, 'named_steps')}
        metadata['imputation'] = {'strategy': 'median', 'keep_empty_features': True,
                                  'selection_fit': 'train', 'final_fit': 'train+validation'}
        for name, model in models.items():
            joblib.dump(model, models_output / f'{name}.joblib')
        xtest = parts['test'][BENCHMARK_FEATURES].to_numpy(dtype=float)
        forecasts = {name: predict(model, xtest) for name, model in models.items()}
        overall, peaks = evaluate_predictions(parts['test'].actual_energy_wh, forecasts, threshold)
        timing, observations = {}, []
        for name, model in models.items():
            timing[name], samples = measure_prediction_time(model, xtest, protocol['timing'])
            observations.extend({'model': name, **sample} for sample in samples)
    predictions = parts['test'][['building_id', 'source_id', 'forecast_origin', 'forecast_target_timestamp', 'actual_energy_wh']].reset_index(drop=True)
    predictions['is_peak'] = predictions.actual_energy_wh > threshold
    for name, values in forecasts.items():
        predictions[name] = values
    predictions.to_csv(output / 'test_predictions.csv', index=False)
    for name, values in [('metrics', overall), ('peak_metrics', peaks), ('timing', timing)]:
        write_json(output / f'{name}.json', values)
        pd.DataFrame.from_dict(values, orient='index').rename_axis('model').to_csv(output / f'{name}.csv')
    pd.DataFrame(observations).to_csv(output / 'timing_observations.csv', index=False)
    save_plots(predictions, overall, timing, protocol['plots'], output / 'plots')
    metadata.update(peak_threshold_wh=threshold, elapsed_seconds=perf_counter() - start,
                    model_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(models_output.glob('*.joblib'))})
    write_json(output / 'metadata.json', metadata)
    write_json(models_output / 'metadata.json', metadata)
    report = f'''# Stage 3 — Forecasting Model Benchmark

Protocol: [frozen protocol](../protocol.md), SHA-256 `{protocol_hash}`.
Implementation commit: `{metadata['git_commit']}`. Seed: {protocol['seed']}.
Dataset SHA-256: `{metadata['dataset_sha256']}`. Target: appliances energy in Wh per 10-minute interval.
Original timezone-naive timestamps are preserved. Horizon: 10 minutes.

## Evaluation protocol

**The test window was already inspected in Stage 2. It is not an unseen independent holdout.**
Model/hyperparameter choices use validation MAE, then RMSE only. Test results are descriptive confirmation, not a selection criterion.
Each test forecast uses observations available at its origin, including earlier observed test values; this is rolling one-step evaluation, not a multi-step forecast from one fixed origin.
All four models use the same target rows; 144 uninterrupted historical measurements are required.
Seasonal Naive uses exactly target time minus 24 hours. Both ML models use the same 21 causal features and median imputation fitted on train during selection, then train+validation during final refit.

Splits (target timestamps):

'''
    for name, bounds in splits.items():
        report += f"- {name}: {bounds['count']} targets, {bounds['first_target']} through {bounds['last_target']}.\n"
    report += '\n## Validation selection\n\n' + table(selection['validation_metrics'])
    report += f"\nRecommended by validation: **{selection['recommended_by_validation']}**. This decision was saved before test evaluation.\n\n"
    report += 'Selected parameters (RF also random_state=42, n_jobs=1; HGB also random_state=42, early_stopping=False, loss=squared_error):\n\n'
    for name in ('random_forest', 'hist_gradient_boosting'):
        report += f"- {name}: `{json.dumps(selection['parameters'][name], sort_keys=True)}`.\n"
    report += '\n## Common test observations\n\n' + table(overall, timing)
    report += '\nPositive improvement means lower error than persistence; negative means worse. RMSE improvements are included in metrics.csv.\n'
    report += f"\n## High-load observations\n\nThreshold: actual > **{threshold:.4f} Wh**, the train-only 90th percentile (linear interpolation). Count: **{int(predictions.is_peak.sum())}**. High loads are not automatically anomalies.\n\n" + table(peaks)
    report += '\nSigned errors are prediction minus actual; negative values indicate underprediction.\n\n| Model | Mean signed error (Wh) | Underprediction fraction |\n|---|---:|---:|\n'
    for name, row in peaks.items():
        report += f"| {name} | {row['mean_signed_error_wh']:.4f} | {row['underprediction_fraction']:.2%} |\n"
    report += '''
## Figures

![First seven test days](plots/forecast_overview.png)
![High-load episodes](plots/peak_episodes.png)
![Errors](plots/errors.png)
![Model comparison](plots/comparison.png)

## Reproducibility and limitations

All test predictions are in `test_predictions.csv`; every split membership is in `split_membership.csv`.
`selection.json`, `validation_trials.json`, `protocol.json`, and `metadata.json` record choices, all candidates, checksums, features, versions and runtime environment. Models are stored separately under ignored artifacts/; their hashes are recorded.
Inference timing includes imputation and a single-row predict call, excludes feature construction, storage and loading; 256 evenly spaced test rows, five passes after ten warmup calls, one thread. Raw timings and p95 are saved. Timing varies across hardware/runs and does not determine the winner.
This is a single household, a single chronological split, and an already-viewed test window. It is not evidence of generalization to arbitrary buildings. No statistical significance claim is made.
The Stage 2 metric comparison is not controlled: Stage 3 adds a daily feature and a longer shared warmup. Production Kafka inference remains unchanged. Integration of any selected model is a separate task.
'''
    (output / 'report.md').write_text(report)
    print(json.dumps({'selection': selection, 'test': overall, 'peaks': peaks, 'output': str(output)}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/forecast-benchmark/results')
    parser.add_argument('--models-output', type=Path, default=ROOT / 'artifacts/forecast-benchmark/v1')
    args = parser.parse_args()
    run(args.dataset, args.output, args.models_output)


if __name__ == '__main__':
    main()
