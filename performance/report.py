"""Build retained per-run CSV tables and a transparent progress report."""
import csv
import json
import statistics
from pathlib import Path
from performance.analysis import summarize,read,quantiles

ROOT=Path(__file__).resolve().parents[1]/'docs/stage6'


def main():
    rows=[];runs=[]
    for directory in sorted((ROOT/'raw').iterdir()):
        if not (directory/'run.json').exists():continue
        run=json.loads((directory/'run.json').read_text());runs.append(run)
        if run['status'] not in ('complete','failed'):continue
        result=summarize(directory)
        for metric,summary in result['latency_ms'].items():
            rows.append(dict(run_id=run['run_id'],label=run['label'],mode=run['mode'],
                             status=run['status'],metric=metric,unit='ms',valid=summary.get('valid',True),
                             **{key:summary[key] for key in ('n','p50','p95','p99')}))
    with (ROOT/'latencies.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['run_id','label','mode','status','metric','unit','valid','n','p50','p95','p99'])
        writer.writeheader();writer.writerows(rows)
    (ROOT/'runs.json').write_text(json.dumps(runs,indent=2)+'\n')
    lines=['# Stage 6 — execution status','','Protocol: [protocol.md](protocol.md).',
           '','Each row below is an independent run. Failed/preflight/pilot observations are retained and never pooled into the primary series.',
           '','| Run | Series | Mode | Status |','|---|---|---|---|']
    lines += [f"| {r['run_id']} | {r['label']} | {r['mode']} | {r['status']} |" for r in runs]
    lines+=['','This is an execution-progress artifact, not a claim that the registered full series has finished.',
            'No smart-meter hardware was measured. Historical timestamps were not used as system-latency clocks.']
    (ROOT/'execution-status.md').write_text('\n'.join(lines)+'\n')
    full_report(runs)


def full_report(runs):
    main=[r for r in runs if r['label'].startswith('main-') and r['status']=='complete']
    recovery=[r for r in runs if r['label'].startswith('recovery-') and r['status']=='complete']
    api=[r for r in runs if r['label'].startswith('api-') and r['status']=='complete']
    required={(f'main-{i}',mode) for i in range(1,6) for mode in ('slow','demo','max')}
    if len(main)!=15 or {(r['label'],r['mode']) for r in main}!=required or len(recovery)!=5 or len(api)!=20:
        return  # No "final" document based on an incomplete registered series.
    grouped=[]
    for mode in ('slow','demo','max'):
        selected=[r for r in main if r['mode']==mode]
        summaries=[json.loads((ROOT/'raw'/r['run_id']/'summary.json').read_text()) for r in selected]
        for metric in summaries[0]['latency_ms']:
            row={'mode':mode,'metric':metric,'independent_runs':5}
            for q in ('p50','p95','p99'):
                values=[s['latency_ms'][metric][q] for s in summaries if s['latency_ms'][metric][q] is not None]
                row[q+'_run_median']=statistics.median(values) if values else None
                row[q+'_run_min']=min(values) if values else None
                row[q+'_run_max']=max(values) if values else None
            grouped.append(row)
    with (ROOT/'between-runs.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(grouped[0]));writer.writeheader();writer.writerows(grouped)
    recovery_values=[r['recovery_resumed_observed_ns']/1e9 for r in recovery]
    report=['# Stage 6 — System Performance Evaluation','','Registered full series completed: 15 primary, 5 recovery and 20 separate API scenarios.',
        '','See [protocol](protocol.md), [amendments](protocol-amendments.md), [raw run manifests](runs.json), [per-run quantiles](latencies.csv) and [between-run summaries](between-runs.csv).',
        '','| Mode | Metric | Median of five run p50 (ms) | Median of five run p95 (ms) | Median of five run p99 (ms) |',
        '|---|---|---:|---:|---:|']
    for row in grouped:
        report.append(f"| {row['mode']} | {row['metric']} | {row['p50_run_median']} | {row['p95_run_median']} | {row['p99_run_median']} |")
    report+=['','Recovery readiness means restored history and a subsequent committed record observed in telemetry; durations include restart and observation delay.',
        '',f'All five values (seconds): {recovery_values}. Median {statistics.median(recovery_values):.3f}; min {min(recovery_values):.3f}; max {max(recovery_values):.3f}.',
        '','| API scenario | Measured attempts | Errors | Timeouts | p50 / p95 / p99 (ms) |','|---|---:|---:|---:|---|']
    for run in api:
        s=json.loads((ROOT/'raw'/run['run_id']/'summary.json').read_text())['http']
        report.append(f"| {run['label']} | {s['attempts']} | {s['errors']} | {s['timeouts']} | {s['latency_ms']['p50']} / {s['latency_ms']['p95']} / {s['latency_ms']['p99']} |")
    failures=[r for r in runs if r['status']=='failed']
    report+=['',f'Retained failed/preflight attempts: {len(failures)}. See individual manifests and amendments; none were silently deleted.',
        '','## Interpretation limits','',
        'Replay sleep settings are offered dataset-replay pacing, not measured system throughput or physical smart-meter sampling. Historical event time is never a latency clock. Maximum-rate end-to-end latency includes queue buildup; model-call latency alone is not pipeline latency.',
        '','Availability→DOM is interval-censored by independent database polling and clock error. Only observed DOM IDs have freshness values; skipped states are censored and coverage remains explicit in each run summary. CPU percentages use Docker sampling intervals, and very short-lived containers can be missed.',
        '','There are five independent primary repetitions per mode, not thousands of independent experiments. Per-run quantiles and between-run ranges are primary; no pooled pseudo-replication or claim of production SLA is made.',
        '','![Primary latency and throughput](plots/main-latency-throughput.png)','',
        '![Dashboard freshness](plots/main-dashboard-freshness.png)',
        '','HGB20 remains primary; RF21 remains the residual reference. IF/AE/residual remain experimental. No model training, threshold adjustment or prior experiment changes occurred.']
    (ROOT/'report.md').write_text('\n'.join(report)+'\n')


if __name__=='__main__':main()
