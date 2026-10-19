"""Reproducible figures and transparent reporting of synthetic-label metrics."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from anomaly.features import NAMES


def plots_and_report(output, aggregates, controls, selection, thresholds):
    directory = output / 'plots'; directory.mkdir()
    def save(fig, name):
        fig.tight_layout()
        for ext in ('png', 'svg'):
            fig.savefig(directory / f'{name}.{ext}', dpi=150)
        plt.close(fig)
    main = aggregates[(aggregates.split == 'test') & (aggregates.type == 'mixed') & (aggregates['quantile'] == .99)].set_index('detector').reindex(NAMES)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, column in zip(axes, ['f1', 'event_f1', 'fpr_synthetic']):
        ax.bar(NAMES, main[column]); ax.set_title(column); ax.tick_params(axis='x', rotation=20)
    save(fig, 'comparison')
    by_type = aggregates[(aggregates.split == 'test') & (aggregates['quantile'] == .99)]
    matrix = by_type.pivot(index='type', columns='detector', values='event_f1').reindex(columns=NAMES)
    fig, ax = plt.subplots(figsize=(8, 6))
    plot = ax.imshow(matrix.to_numpy(), vmin=0, vmax=1, cmap='viridis')
    ax.set_xticks(range(3), NAMES, rotation=20); ax.set_yticks(range(len(matrix)), matrix.index)
    for y in range(len(matrix)):
        for x in range(3):
            ax.text(x, y, f'{matrix.iloc[y, x]:.2f}', ha='center', va='center', color='white' if matrix.iloc[y,x] < .5 else 'black')
    fig.colorbar(plot, ax=ax, label='Mean synthetic event F1')
    save(fig, 'by_type')
    paths = sorted((output / 'scores').glob('test-mixed-*.parquet'))
    first = paths[0]
    scores = pd.read_parquet(first)
    times = pd.to_datetime(scores.measurement_timestamp)
    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    axes[0].plot(times, scores.actual_energy_wh, lw=.7, label='Modified stream')
    axes[0].scatter(times[scores.synthetic_label], scores.loc[scores.synthetic_label, 'actual_energy_wh'], s=7, color='red', label='Injected event')
    axes[0].set_ylabel('Wh / 10min'); axes[0].legend()
    for ax, name in zip(axes[1:], NAMES):
        ax.plot(times, scores[name], lw=.7); ax.axhline(thresholds['0.99'][name], color='red', ls='--')
        ax.set_ylabel(name)
    fig.suptitle(f'Fixed first mixed test seed: {first.stem}')
    save(fig, 'score_timeline')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    control = controls[(controls.split == 'test') & (controls['quantile'] == .99)].set_index('detector').reindex(NAMES)
    axes[0].bar(NAMES, control.background_alarms); axes[0].set_title('Unchanged UCI alarms (not verified false positives)')
    axes[1].bar(NAMES, main.post_event_alarms); axes[1].set_title('Mean post-event alarms, mixed seeds')
    for ax in axes:
        ax.tick_params(axis='x', rotation=20)
    save(fig, 'background_and_recovery')
    report = '# Stage 4 — Energy Anomaly Detection\n\n'
    report += 'Frozen protocol: [protocol.md](../protocol.md). All thresholds/models/scenarios were fixed before test evaluation.\n\n'
    report += '**This is a synthetic-intervention benchmark on an already-viewed UCI series, not an unseen holdout or verified real fault dataset.**\n\n'
    report += f"Validation-selected detector: **{selection['recommended'] or 'none meets the background alarm budget'}**. Selection is saved in selection.json before test scoring. No test-based switch is made.\n\n"
    report += '## Test mixed scenarios, primary 99th-percentile thresholds\n\nMetrics below are macro means over five seeds; the actual injection prevalence is recorded in injections.csv. Synthetic FPR/precision assume the unlabeled background is negative.\n\n'
    report += '| Detector | Precision | Recall | F1 | Synthetic FPR | Event F1 | Alarms/day | Mean matched-event median delay (min) |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    for name, r in main.iterrows():
        delay = f'{r.delay_median_minutes:.2f}' if pd.notna(r.delay_median_minutes) else 'undefined'
        report += f'| {name} | {r.precision:.4f} | {r.recall:.4f} | {r.f1:.4f} | {r.fpr_synthetic:.4f} | {r.event_f1:.4f} | {r.alarms_per_day:.2f} | {delay} |\n'
    report += '\n## Unchanged test control\n\nThese alarms are not confirmed false positives. Original UCI data have no trustworthy anomaly labels.\n\n| Detector | Alarms | Alarm rate | Alarms/day |\n|---|---:|---:|---:|\n'
    for name, r in control.iterrows():
        report += f'| {name} | {r.background_alarms:.0f} | {r.background_alarm_rate:.4%} | {r.alarms_per_day:.2f} |\n'
    report += '\n## Readiness, events and recovery\n\n'
    coverage = pd.read_csv(output / 'coverage.csv')
    for name in NAMES:
        r = coverage[(coverage.split == 'test') & (coverage.scenario == 'clean') & (coverage.detector == name)].iloc[0]
        report += f'- {name}: partition coverage {r.coverage:.2%}; full replay unready rows {int(r.replay_unready)} including 144 context records.\n'
    report += '\nDetection window is strictly event start through end; contiguous alarm episodes are matched one-to-one, without point adjustment. Missed events remain missed and have no artificial zero delay. event_outcomes.csv preserves individual detections/delays. Post-event tail is 144 intervals; its alarms remain included in background errors.\n\n'
    report += '| Detector | Mean alarms during events | Mean post-event alarms | Mean missed fraction |\n|---|---:|---:|---:|\n'
    for name, r in main.iterrows():
        report += f'| {name} | {r.during_event_alarms:.2f} | {r.post_event_alarms:.2f} | {r.missed_fraction:.4f} |\n'
    report += '\n## Figures\n\n![Comparison](plots/comparison.png)\n![By type](plots/by_type.png)\n![Timeline](plots/score_timeline.png)\n![Background and recovery](plots/background_and_recovery.png)\n\n'
    report += '## Artifacts and limits\n\nby_type.csv and by_severity.csv stratify all types/strengths and all three thresholds. metrics.csv preserves each scenario/seed; no favorable seed is selected. scores/ stores every score, forecast, actual and intervention label; manifests/ records exact original/modified values and placement. thresholds.json, model_metadata.json, metadata.json and checksums.json record provenance.\n\n'
    report += 'IF/AE use the shared 20-feature contract; the dedicated residual RF uses the unchanged 21-feature contract and prior-interval predictions. RF is newly fitted on Stage 4 train only, but its hyperparameters were historically selected using Stage 3 validation. That prior exposure cannot be undone. No model fits calibration, validation or test during Stage 4.\n\n'
    report += 'High loads are not automatically anomalies. Synthetic faults do not establish operational precision. Large amplitudes can be easier than realistic faults; slow drift or stuck readings can become part of history and cease triggering residuals. Repeated seeds share the same household and timeline and are not independent households. Production Energy forecasting, IoT and Stage 2/3 results remain unchanged.\n'
    (output / 'report.md').write_text(report)
