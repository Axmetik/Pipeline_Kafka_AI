"""Execute the frozen Stage 4 protocol; test scores follow saved selection."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess
from time import perf_counter

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits, threadpool_info
from producer.appliances_dataset import iter_appliances, dataset_sha256
from anomaly.features import collect, NAMES
from anomaly.train import fit_models
from anomaly.calibrate import calibrate
from anomaly.residual import score_batch
from anomaly.inject import inject, scenarios, train_statistics
from anomaly.evaluate import metrics, choose_detector

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'configs/energy-anomaly-v1.json'


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def run(dataset, output, artifacts, protocol_path=PROTOCOL):
    config = json.loads(protocol_path.read_text())
    if dataset_sha256(dataset) != config['dataset_sha256']:
        raise ValueError('Dataset checksum does not match frozen protocol')
    if output.exists() or artifacts.exists():
        raise ValueError('Use new output/artifact directories; never overwrite experiments')
    output.mkdir(parents=True); artifacts.mkdir(parents=True)
    (output / 'scores').mkdir(); (output / 'manifests').mkdir()
    (output / 'protocol.json').write_bytes(protocol_path.read_bytes())
    records = list(iter_appliances(dataset))
    frame, x, rf_x = collect(records)
    times = frame.measurement_timestamp
    bounds = {
        'train': (times >= config['train_start']) & (times < config['calibration_start']),
        'calibration': (times >= config['calibration_start']) & (times < config['validation_start']),
        'validation': (times >= config['validation_start']) & (times < config['test_start']),
        'test': (times >= config['test_start']) & (times <= config['test_end'])}
    splits = {name: {'count': int(mask.sum()), 'first': times[mask].iloc[0], 'last': times[mask].iloc[-1]}
              for name, mask in bounds.items()}
    write_json(output / 'splits.json', splits)
    pd.concat([frame.loc[mask, ['event_id', 'measurement_timestamp']].assign(split=name)
               for name, mask in bounds.items()]).to_csv(output / 'split_membership.csv', index=False)
    started = perf_counter()
    print('Fitting train-only IF, AE and RF', flush=True)
    bundle = fit_models(frame, x, rf_x, bounds['train'], records[0], config)
    calibration_mask = bounds['calibration'].to_numpy()
    calibration_scores = score_batch(bundle, frame[calibration_mask].reset_index(drop=True), x[calibration_mask], rf_x[calibration_mask])
    bundle.thresholds = calibrate(calibration_scores, config['quantiles'])
    bundle.metadata.update(protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
                           dataset_sha256=config['dataset_sha256'], calibration=splits['calibration'],
                           configuration=config, threshold_version='quantiles-v1-' + hashlib.sha256(json.dumps(bundle.thresholds, sort_keys=True).encode()).hexdigest()[:16])
    bundle.save(artifacts / 'bundle.joblib')
    write_json(output / 'thresholds.json', bundle.thresholds)
    write_json(output / 'model_metadata.json', bundle.metadata)
    calibration_scores.to_parquet(output / 'scores/calibration.parquet', index=False)
    stats = train_statistics(frame[bounds['train']])
    write_json(output / 'train_statistics.json', stats)
    rows, controls, event_rows, coverage, injection_summary = [], [], [], [], []

    def evaluate_split(split):
        indices = np.flatnonzero(bounds[split])
        first, last = int(indices[0]), int(indices[-1])
        prefix = min(config['history_warmup_records'], first)
        source = records[first - prefix:last + 1]

        def score(raw, scenario):
            beginning = perf_counter()
            f, xx, rr = collect(raw, bundle.validate_source)
            scores = score_batch(bundle, f, xx, rr)
            for name in NAMES:
                ready = scores[name].notna()
                part_ready = ready.iloc[prefix:]
                coverage.append({'split': split, 'scenario': scenario, 'detector': name,
                                 'replay_count': len(scores), 'replay_unready': int((~ready).sum()),
                                 'partition_count': len(part_ready), 'partition_unready': int((~part_ready).sum()),
                                 'coverage': float(part_ready.mean()), 'elapsed_batch_seconds': perf_counter() - beginning})
            part = scores.iloc[prefix:].reset_index(drop=True)
            # The frozen dataset is uninterrupted. Fail rather than misalign event indices.
            if part[list(NAMES)].isna().any().any():
                raise ValueError('Partition has unready rows; common event timeline cannot be silently shortened')
            return part

        clean = score(source, 'clean')
        clean.to_parquet(output / f'scores/{split}-clean.parquet', index=False)
        for q in config['quantiles']:
            for name in NAMES:
                flags = clean[name] > bundle.thresholds[str(q)][name]
                high = clean.actual_energy_wh > stats['p90_wh']
                controls.append({'split': split, 'detector': name, 'quantile': q, 'count': len(clean),
                                 'background_alarms': int(flags.sum()), 'background_alarm_rate': float(flags.mean()),
                                 'alarms_per_day': float(flags.sum() / (len(clean) / 144)),
                                 'high_load_points': int(high.sum()), 'high_load_alarms': int((flags & high).sum())})
        for number, (scenario, kind, severity, seed) in enumerate(scenarios(config['injection'], split), 1):
            modified, labels, events, summary = inject(source, prefix, config['injection'], stats, kind, severity, seed)
            scores = score(modified, scenario)
            scores['synthetic_label'] = labels
            scores['original_energy_wh'] = [r['energy']['value'] for r in source[prefix:]]
            scores.to_parquet(output / f'scores/{split}-{scenario}.parquet', index=False)
            manifest = {'split': split, 'scenario': scenario, 'seed': seed, 'type': kind, 'severity': severity,
                        'prefix': prefix, **summary, 'events': events}
            write_json(output / f'manifests/{split}-{scenario}.json', manifest)
            injection_summary.append({k: v for k, v in manifest.items() if k != 'events'} | {'events': len(events)})
            for q in config['quantiles']:
                for name in NAMES:
                    flags = scores[name] > bundle.thresholds[str(q)][name]
                    result, outcomes = metrics(flags, labels, scores.measurement_timestamp, events, config['post_event_intervals'])
                    identity = {'split': split, 'scenario': scenario, 'type': kind, 'severity': severity,
                                'seed': seed, 'detector': name, 'quantile': q}
                    rows.append(identity | result)
                    event_rows.extend(identity | event for event in outcomes)
            if number % 10 == 0 or number == 95:
                print(f'{split}: {number} scenarios evaluated', flush=True)
        return clean

    evaluate_split('validation')
    selection = choose_detector(pd.DataFrame(rows), pd.DataFrame(controls), list(NAMES), config['selection_background_alarm_limit'])
    write_json(output / 'selection.json', selection)
    print('Validation choice saved; beginning test evaluation', flush=True)
    evaluate_split('test')
    tables = {'metrics': rows, 'clean_controls': controls, 'event_outcomes': event_rows,
              'coverage': coverage, 'injections': injection_summary}
    for name, values in tables.items():
        pd.DataFrame(values).to_csv(output / f'{name}.csv', index=False)
    metrics_frame = pd.DataFrame(rows)
    numeric = ['precision', 'recall', 'f1', 'fpr_synthetic', 'alarms_per_day', 'event_precision',
               'event_recall', 'event_f1', 'missed_fraction', 'delay_median_minutes', 'delay_p95_minutes',
               'during_event_alarms', 'post_event_alarms', 'other_background_alarms']
    aggregates = metrics_frame.groupby(['split', 'type', 'detector', 'quantile'])[numeric].mean().reset_index()
    aggregates.to_csv(output / 'by_type.csv', index=False)
    metrics_frame.groupby(['split', 'type', 'severity', 'detector', 'quantile'], dropna=False)[numeric].mean().reset_index().to_csv(output / 'by_severity.csv', index=False)
    metadata = {'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'tracked_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip()),
                'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted((ROOT / 'anomaly').glob('*.py'))},
                'protocol_sha256': hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
                'dataset_sha256': dataset_sha256(dataset), 'model_sha256': hashlib.sha256((artifacts / 'bundle.joblib').read_bytes()).hexdigest(),
                'elapsed_seconds': perf_counter() - started, 'platform': platform.platform(),
                'python': platform.python_version(), 'threadpools': threadpool_info(),
                'libraries': {n: importlib.metadata.version(n) for n in ['numpy', 'pandas', 'scikit-learn', 'torch', 'joblib', 'pyarrow', 'matplotlib', 'scipy', 'threadpoolctl']}}
    write_json(output / 'metadata.json', metadata)
    from anomaly.plots import plots_and_report
    plots_and_report(output, aggregates, pd.DataFrame(controls), selection, bundle.thresholds)
    hashes = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file()}
    write_json(output / 'checksums.json', hashes)
    print(json.dumps(selection, indent=2), flush=True)
    return selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/energy-anomaly/results')
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'artifacts/energy-anomaly/v1')
    args = parser.parse_args()
    with threadpool_limits(1):
        run(args.dataset, args.output, args.artifacts)


if __name__ == '__main__':
    main()
