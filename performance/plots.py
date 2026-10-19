"""Scientific static plots from retained run summaries; never imputes failures."""
import json
from pathlib import Path
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/energy-stage6-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]/'docs/stage6'


def main():
    rows=[]
    for path in sorted((ROOT/'raw').glob('*/run.json')):
        run=json.loads(path.read_text())
        summary=path.parent/'summary.json'
        if run['status']=='complete' and summary.exists():rows.append((run,json.loads(summary.read_text())))
    output=ROOT/'plots';output.mkdir(exist_ok=True)
    for series in ('pilot','main'):
        selected=[(r,s) for r,s in rows if r['label']==series or r['label'].startswith(series+'-') and series=='main']
        if not selected:continue
        fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
        labels=[r['label']+' / '+r['mode'] for r,s in selected]
        for metric in ('p50','p95','p99'):
            axes[0].plot(range(len(selected)),[s['latency_ms']['process'][metric] for r,s in selected],marker='o',label=metric)
        axes[0].set(ylabel='Worker processing latency (ms)',title=series+' — per independent run')
        axes[0].legend();axes[0].set_xticks(range(len(labels)),labels,rotation=65,ha='right')
        axes[1].bar(range(len(selected)),[s.get('completion_throughput_per_second',0) for r,s in selected])
        axes[1].set(ylabel='Committed messages / second',title='Completion throughput, includes draining')
        axes[1].set_xticks(range(len(labels)),labels,rotation=65,ha='right')
        fig.savefig(output/(series+'-latency-throughput.png'),dpi=180);plt.close(fig)
        fig,axis=plt.subplots(figsize=(8,4),layout='constrained')
        for r,s in selected:
            dashboard=s['dashboard']
            label=r['label']+' / '+r['mode']
            mid=dashboard['availability_to_dom_midpoint_ms']['p95']
            lo=dashboard['availability_to_dom_lower_ms']['p95'];hi=dashboard['availability_to_dom_upper_ms']['p95']
            if mid is not None:
                axis.errorbar(label,mid,yerr=[[mid-lo],[hi-mid]],fmt='o',capsize=4,label=label)
        axis.set(ylabel='Availability→DOM p95 midpoint estimate (ms)',title=series+' — interval-censored availability; observed DOM IDs only')
        axis.tick_params(axis='x',rotation=65)
        fig.savefig(output/(series+'-dashboard-freshness.png'),dpi=180);plt.close(fig)
        fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
        for index,(run,summary) in enumerate(selected):
            worker=next((v for k,v in summary.get('resources',{}).items() if '-worker-' in k),None)
            if worker:
                axes[0].bar(index,worker['cpu_mean_percent'])
                axes[1].bar(index,worker['ram_peak_bytes']/1024**2)
        axes[0].set(ylabel='Mean Docker CPU (% of one CPU)',title=series+' — worker, measured window')
        axes[1].set(ylabel='Peak Docker memory (MiB)',title='Observed samples; see actual sampling cadence')
        for axis in axes:axis.set_xticks(range(len(labels)),labels,rotation=65,ha='right')
        fig.savefig(output/(series+'-worker-resources.png'),dpi=180);plt.close(fig)
    recoveries=[r for r,s in rows if r['label'].startswith('recovery-')]
    if recoveries:
        fig,axis=plt.subplots(figsize=(8,4),layout='constrained')
        axis.scatter([r['label'] for r in recoveries],[r['recovery_resumed_observed_ns']/1e9 for r in recoveries])
        axis.set(ylabel='Observed functional recovery (seconds)',title='All independent recovery trials; includes observation delay')
        fig.savefig(output/'recovery.png',dpi=180);plt.close(fig)
    http=[(r,s['http']) for r,s in rows if r['label'].startswith('api-') and 'http' in s]
    if http:
        fig,axis=plt.subplots(figsize=(12,4),layout='constrained')
        for q in ('p50','p95','p99'):
            axis.plot(range(len(http)),[s['latency_ms'][q] for r,s in http],marker='o',label=q)
        axis.set(ylabel='HTTP complete-response latency (ms)',title='Separate API series, per-run quantiles, all attempts')
        axis.set_xticks(range(len(http)),[r['label'] for r,s in http],rotation=65,ha='right');axis.legend()
        fig.savefig(output/'api-latency.png',dpi=180);plt.close(fig)


if __name__=='__main__':main()
