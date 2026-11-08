"""Frozen standalone sustained-low experiment and local compute-cost comparison."""
import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timedelta
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess
import time

import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits

from anomaly.residual import StreamDetector
from diagnostics.rule_comparison import ROOT,STEP,infer,intervals,onset_match,check_gap,write_json
from diagnostics.rule_complementarity import tri_or,transform as previous_transform
from integration.artifacts import load_manifest,sha256
from processing.energy_low_rule import LowRuleConfig,SustainedLow,evaluate_low
from processing.energy_rules import EnergyRules
from producer.appliances_dataset import iter_appliances

PLAN=ROOT/'docs/energy-rules/sustained-low-20261108'
PRIMARY=('residual','sustained_high','sustained_low','residual_high_or','residual_high_low_or')
METHODS=(*PRIMARY,'flatline','interval_gap')
UNIONS={'residual_high_or':('residual','sustained_high'),'residual_high_low_or':('residual','sustained_high','sustained_low')}


def transform(raw,case):
    op=case['operation']
    if op not in ('constant_profile','day_night_profile','workweek_profile'):return previous_transform(raw,case)
    # Validate exact registered event/return timestamps before modifying a profile.
    previous_transform(raw,{**case,'operation':'identity'})
    changed=deepcopy(raw)
    for r in changed:
        stamp=datetime.fromisoformat(r['timestamp'])
        if op=='constant_profile':value=case['value_wh']
        elif op=='day_night_profile':value=case['day_wh'] if case['day_start']<=stamp.hour<case['day_end'] else case['night_wh']
        else:value=case['work_wh'] if stamp.weekday()<5 and case['day_start']<=stamp.hour<case['day_end'] else case['off_wh']
        r['energy']['value']=value
    return changed


def add_low(raw,base):
    batch=evaluate_low(raw);stream=SustainedLow();rows=[]
    if len(base)!=len(raw):raise ValueError('Inference row count differs')
    for r,prior,expected in zip(raw,base,batch):
        actual=stream.process(r)
        if actual!=expected:raise ValueError('Low offline/streaming mismatch')
        low=actual['signal'];row=dict(prior)
        row.update(sustained_low_flag=low['flag'],sustained_low_status=low['status'],
                   sustained_low_threshold=low['evidence'].get('threshold_wh'),
                   sustained_low_evidence_json=json.dumps(low['evidence'],sort_keys=True,allow_nan=False))
        for name,names in UNIONS.items():
            vote=tri_or({n:row[n+'_flag'] for n in names})
            row[name+'_flag']=vote['flag'];row[name+'_provenance_json']=json.dumps(vote,sort_keys=True,allow_nan=False)
        rows.append(row)
    return rows


def describe(case,modified,paired):
    start=datetime.fromisoformat(case['start']);end=start+STEP*(case['intervals']-1)
    ts=[datetime.fromisoformat(r['timestamp']) for r in modified];ps=[datetime.fromisoformat(r['timestamp']) for r in paired]
    pair=dict(zip(ps,paired));wanted={start+i*STEP for i in range(case['intervals'])}
    common={t for t,r in zip(ts,modified) if all(r[n+'_flag'] is not None for n in PRIMARY)}
    event=[r for t,r in zip(ts,modified) if t in wanted];details=[];episodes=[]
    for name in METHODS:
        alarms=intervals(ts,[r[name+'_flag'] for r in modified]);rawalarms=intervals(ps,[r[name+'_flag'] for r in paired])
        hit=onset_match(alarms,start,end);commonhit=onset_match(alarms,start,end,common)
        target=bool(case['target'] and ((case['category']=='consumption_pattern' and name in PRIMARY) or (case['family']=='flatline' and name=='flatline')))
        rawflag=pair[hit['start']][name+'_flag'] if hit else None
        details.append(dict(scenario_id=case['scenario_id'],cohort=case['cohort'],family=case['family'],method=name,target=target,
                            start=start.isoformat(),end=end.isoformat(),intervals=case['intervals'],factor=case.get('factor'),
                            detected=bool(hit) if target else None,detected_common_onset=bool(commonhit) if target else None,
                            alarm_start=hit['start'].isoformat() if target and hit else None,
                            delay_minutes=(hit['start']-start).total_seconds()/60 if target and hit else None,
                            new_paired_crossing=(rawflag is False) if target and hit else None,
                            paired_unknown_at_match=(rawflag is None) if target and hit else None,
                            paired_flag_at_match=rawflag if target and hit else None,
                            event_coverage=sum(r[name+'_flag'] is not None for r in event)/len(wanted),
                            unavailable_event_points=len(wanted)-sum(r[name+'_flag'] is not None for r in event),
                            stream_coverage=sum(r[name+'_flag'] is not None for r in modified)/len(modified),
                            unavailable_stream_points=sum(r[name+'_flag'] is None for r in modified),
                            common_event_coverage=len(common&wanted)/len(wanted),
                            modified_episode_onsets=len(alarms),paired_episode_onsets=len(rawalarms),
                            modified_event_onsets=sum(start<=a['start']<=end for a in alarms),
                            paired_event_onsets=sum(start<=a['start']<=end for a in rawalarms),
                            modified_tail_onsets=sum(a['start']>end for a in alarms),
                            paired_tail_onsets=sum(a['start']>end for a in rawalarms),
                            modified_event_flagged_points=sum(r[name+'_flag'] is True for r in event),
                            paired_event_flagged_points=sum(r[name+'_flag'] is True for t,r in zip(ps,paired) if t in wanted),
                            preexisting_overlap=sum(a['start']<start<=a['end'] for a in alarms)))
        for arm,alist in [('modified',alarms),('paired',rawalarms)]:
            episodes.extend(dict(scenario_id=case['scenario_id'],method=name,arm=arm,start=a['start'].isoformat(),end=a['end'].isoformat(),points=a['points'],onset_inside_event=start<=a['start']<=end) for a in alist)
    return details,episodes


def contributions(details):
    df=pd.DataFrame(details);rows=[]
    for sid,g in df[df.target & df.method.isin(PRIMARY)].groupby('scenario_id',sort=True):
        m=g.set_index('method').to_dict('index');hits={n:bool(m[n]['detected']) for n in PRIMARY}
        base=hits['residual_high_or'];plus=hits['residual_high_low_or']
        rows.append(dict(scenario_id=sid,cohort=m['residual']['cohort'],family=m['residual']['family'],
                         **{n+'_detected':v for n,v in hits.items()},
                         component_set='+'.join(n for n in PRIMARY[:3] if hits[n]) or 'none',
                         added_vs_baseline=plus and not base,lost_vs_baseline=base and not plus,
                         added_vs_residual=plus and not hits['residual'],lost_vs_residual=hits['residual'] and not plus,
                         low_only=hits['sustained_low'] and not (hits['residual'] or hits['sustained_high']),
                         union_differs_from_component_set=plus!=any(hits[n] for n in PRIMARY[:3])))
    return rows


def aggregate(details):
    df=pd.DataFrame(details);rows=[]
    for (cohort,family,name),g in df[df.target].groupby(['cohort','family','method'],sort=True):
        rows.append(summary(g,cohort,family,name))
    for (cohort,name),g in df[df.target & df.method.isin(PRIMARY)].groupby(['cohort','method'],sort=True):
        rows.append(summary(g,cohort,'all_consumption',name))
    return rows


def summary(g,cohort,family,name):
    delays=g.delay_minutes.dropna()
    return dict(cohort=cohort,family=family,method=name,target_events=len(g),detected_events=int(g.detected.sum()),missed_events=int((~g.detected.astype(bool)).sum()),
                common_onset_detected_events=int(g.detected_common_onset.sum()),event_coverage_percent=100*float(g.event_coverage.mean()),
                stream_coverage_percent=100*float(g.stream_coverage.mean()),common_event_coverage_percent=100*float(g.common_event_coverage.mean()),
                unavailable_event_points=int(g.unavailable_event_points.sum()),unavailable_stream_points=int(g.unavailable_stream_points.sum()),
                delay_median_minutes=float(delays.median()) if len(delays) else None,delay_values_minutes=json.dumps(delays.tolist()),
                new_paired_crossings=int(g.new_paired_crossing.fillna(False).sum()),paired_unknown_matches=int(g.paired_unknown_at_match.fillna(False).sum()),
                paired_episode_onsets=int(g.paired_episode_onsets.sum()),modified_episode_onsets=int(g.modified_episode_onsets.sum()),
                paired_event_onsets=int(g.paired_event_onsets.sum()),modified_tail_onsets=int(g.modified_tail_onsets.sum()))


def clone_stream(original):
    # Immutable loaded model bundle is shared; only causal histories/pending are cloned.
    other=StreamDetector(original.bundle);other.features=deepcopy(original.features);other.pending=deepcopy(original.pending)
    return other


def timed_loop(records,v2,low,ml,cached_flags,scope,include_low):
    samples=[];outputs=[];low_samples=[]
    total_start=time.perf_counter_ns()
    for i,raw in enumerate(records):
        t0=time.perf_counter_ns()
        result=v2.process(raw);high=next(s['flag'] for s in result['signals'] if s['rule']=='sustained_high')
        residual=ml.process(raw)['residual_flag'] if scope=='full_scoring' else cached_flags[i]
        baseline=tri_or(dict(residual=residual,sustained_high=high))['flag']
        low_flag=None;combined=None;low_ns=None
        if include_low:
            lt=time.perf_counter_ns();low_flag=low.process(raw)['signal']['flag'];low_ns=time.perf_counter_ns()-lt
            combined=tri_or(dict(residual=residual,sustained_high=high,sustained_low=low_flag))['flag']
        elapsed=time.perf_counter_ns()-t0
        samples.append(elapsed);outputs.append((residual,high,baseline,low_flag,combined))
        if low_ns is not None:low_samples.append(low_ns)
    total=time.perf_counter_ns()-total_start
    return samples,total,low_samples,outputs


def timing(output,records,artifacts,plan):
    spec=plan['timing'];start=datetime.fromisoformat(spec['measurement_start']);left=start.replace(hour=0,minute=0,second=0)-timedelta(days=7)
    warm=[r for r in records if left<=datetime.fromisoformat(r['timestamp'])<start]
    measured=[r for r in records if start<=datetime.fromisoformat(r['timestamp'])<start+spec['measured_records']*STEP]
    if len(measured)!=spec['measured_records']:raise ValueError('Timing stream incomplete')
    v2=EnergyRules();low=SustainedLow();ml=StreamDetector(artifacts.anomaly)
    print(json.dumps(dict(phase='timing_prime',records=len(warm))),flush=True)
    for r in warm:v2.process(r);low.process(r);ml.process(r)
    cache_ml=clone_stream(ml);flags=[cache_ml.process(r)['residual_flag'] for r in measured]
    rows=[];summaries=[];delta=[]
    for scope in ['rules_only','full_scoring']:
        for repeat,order in enumerate(spec['order'],1):
            reference=None;totals={}
            for variant in order.split(','):
                plus=variant=='plus_low';a=deepcopy(v2);b=deepcopy(low) if plus else None;c=clone_stream(ml) if scope=='full_scoring' else None
                samples,total,low_samples,answers=timed_loop(measured,a,b,c,flags,scope,plus)
                unchanged=[v[:3] for v in answers]
                if reference is not None and unchanged!=reference:raise ValueError('Timing treatment changed baseline decisions')
                reference=unchanged;totals[variant]=total
                for i,value in enumerate(samples):rows.append(dict(scope=scope,repeat=repeat,variant=variant,record_index=i,timestamp=measured[i]['timestamp'],elapsed_ns=value,low_compute_ns=low_samples[i] if plus else None))
                summaries.append(dict(scope=scope,repeat=repeat,variant=variant,records=len(samples),record_p50_ms=float(np.percentile(samples,50)/1e6),record_p95_ms=float(np.percentile(samples,95)/1e6),total_ms=total/1e6,low_p50_ms=float(np.percentile(low_samples,50)/1e6) if plus else None,low_p95_ms=float(np.percentile(low_samples,95)/1e6) if plus else None))
                print(json.dumps(dict(phase='timing',scope=scope,repeat=repeat,variant=variant,total_ms=total/1e6)),flush=True)
            delta.append(dict(scope=scope,repeat=repeat,baseline_total_ms=totals['baseline']/1e6,plus_total_ms=totals['plus_low']/1e6,delta_ms=(totals['plus_low']-totals['baseline'])/1e6,delta_percent=100*(totals['plus_low']/totals['baseline']-1)))
    pd.DataFrame(rows).to_csv(output/'timing-records.csv',index=False);pd.DataFrame(summaries).to_csv(output/'timing-summary.csv',index=False);pd.DataFrame(delta).to_csv(output/'timing-paired-deltas.csv',index=False)
    env=dict(platform=platform.platform(),machine=platform.machine(),processor=platform.processor(),clock=time.get_clock_info('perf_counter')._asdict() if hasattr(time.get_clock_info('perf_counter'),'_asdict') else vars(time.get_clock_info('perf_counter')),image_id=plan['docker_image_id'],limits=dict(cpus=1,memory='2g',threads=1),warmup_records=len(warm),measured_records=len(measured),repeats=5,instrumentation='Outer per-record/loop timers both variants; two extra monotonic reads around low in treatment, included in treatment totals; no synchronous logging/IO inside loop.',libraries={n:importlib.metadata.version(n) for n in ['numpy','pandas','scikit-learn','torch','joblib']})
    for path in ['/proc/cpuinfo','/sys/fs/cgroup/cpu.max','/sys/fs/cgroup/memory.max']:
        p=Path(path)
        if p.exists():env[path]=p.read_text()
    write_json(output/'timing-environment.json',env)
    return summaries


def plots(output,all_points,cases,plan):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    (output/'plots').mkdir();lookup={c['scenario_id']:c for c in cases}
    for sid in plan['plots']:
        c=lookup[sid];start=datetime.fromisoformat(c['start']);end=start+STEP*(c['intervals']-1);left=start-6*STEP;right=end+12*STEP
        mod,raw=all_points[sid];a=[r for r in mod if left<=datetime.fromisoformat(r['timestamp'])<=right];b=[r for r in raw if left<=datetime.fromisoformat(r['timestamp'])<=right]
        fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True)
        for data,label,style in [(b,'Untouched pair','--'),(a,'Modified/control','-')]:axes[0].plot([datetime.fromisoformat(r['timestamp']) for r in data],[r['energy_wh'] for r in data],style,label=label)
        axes[0].plot([datetime.fromisoformat(r['timestamp']) for r in a],[r['sustained_low_threshold'] if r['sustained_low_threshold'] is not None else np.nan for r in a],':',label='Frozen hourly low threshold')
        axes[0].legend(fontsize=8);axes[0].set_ylabel('Interval energy, Wh')
        for lane,name in enumerate(PRIMARY):
            for flag,marker,color in [(True,'|','tab:blue'),(None,'x','gray')]:
                hits=[datetime.fromisoformat(r['timestamp']) for r in a if r[name+'_flag'] is flag]
                axes[1].scatter(hits,[lane]*len(hits),marker=marker,color=color,s=40)
        axes[1].set_yticks(range(len(PRIMARY)),PRIMARY,fontsize=8);axes[1].set_ylim(-.7,len(PRIMARY)-.3)
        for ax in axes:ax.axvspan(start,end+STEP,color='orange',alpha=.12);ax.grid(alpha=.2)
        axes[1].set_xlabel('Naive dataset time; blue=true; gray x=unavailable; blank at observation=false')
        fig.suptitle(sid+' — controlled historical scenario, not confirmed fault');fig.autofmt_xdate();fig.tight_layout();fig.savefig(output/'plots'/f'{sid}.png',dpi=140);plt.close(fig)


def report(output,summaries,contrib,gaps):
    lines=['# Sustained-low: preregistered controlled experiment','',
           'All32 cases retained. New18 consumption events and known-six regression drops are separate. No fitting/calibration/parameter selection. Same historical house/previously viewed period, synthetic labels, not real fault validation.','',
           '| Cohort | Method | Detected / target | Event coverage | Stream availability | Median delay,min | Paired episodes: full / event | New paired crossings |',
           '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summaries:
        if r['family']!='all_consumption':continue
        d='—' if r['delay_median_minutes'] is None else f"{r['delay_median_minutes']:g}"
        lines.append(f"| {r['cohort']} | {r['method']} | {r['detected_events']}/{r['target_events']} | {r['event_coverage_percent']:.1f}% | {r['stream_coverage_percent']:.1f}% | {d} | {r['paired_episode_onsets']} / {r['paired_event_onsets']} | {r['new_paired_crossings']} |")
    for cohort in ['new','known_regression']:
        subset=[r for r in contrib if r['cohort']==cohort]
        lines+=['',f"{cohort}: actual combined added vs residual|high={sum(r['added_vs_baseline'] for r in subset)}, lost={sum(r['lost_vs_baseline'] for r in subset)}; low-only component matches={sum(r['low_only'] for r in subset)}. Episodes reconstructed, not component totals summed."]
    lines+=['','## Controls (onsets / flagged points in control window)','',
            '| Case | Method | Modified | Raw pair | Event coverage |','|---|---|---:|---:|---:|']
    for r in pd.read_csv(output/'controls.csv').to_dict('records'):
        if r['method'] not in PRIMARY:continue
        lines.append(f"| {r['scenario_id']} | {r['method']} | {r['modified_event_onsets']} / {r['modified_event_flagged_points']} | {r['paired_event_onsets']} / {r['paired_event_flagged_points']} | {100*r['event_coverage']:.1f}% |")
    lines+=['','## Gaps: separate telemetry task','',json.dumps(gaps,indent=2),'',
            'See cases.csv for every target/miss and unavailable count; contributions.csv for each component/union overlap; unavailable-reasons.csv for reasons; episodes.csv for exact onsets and tails. Flatline and gaps are never consumption events. Paired UCI episodes are not confirmed false positives, and repeated context is not independent physical exposure.',
            'Low has no work calendar: legitimate scheduled closures and benign zeros can trigger. Background below20Wh or nonpositive computed lower threshold yields null, not a negative decision. Union true/false/null preserves provenance and can be less available when low is unknown; positives from other methods remain positive.',
            'Delay is dataset-time minutes for detected events only. Six observations represent60min of interval energy and50min between labels, distinct from compute milliseconds. Timing CSV contains five paired repetitions, record p50/p95 and loop totals; model loading, warmup, clone and file IO are outside timers. See timing-environment.json and parent report for interpretation.',
            'Existing V2/ML/Unanimous sources and artifacts are checksum-protected; known-six previous scores are read solely AFTER fresh inference for exact regression verification, never substitution. Low batch and streaming results compared exactly on every record of every pair.']
    (output/'report.md').write_text('\n'.join(lines)+'\n')


def run(plan_dir,output):
    if output.exists():raise FileExistsError('Never overwrite results')
    plan=json.loads((plan_dir/'plan.json').read_text());manifest=json.loads((plan_dir/'scenarios.json').read_text())
    if sha256(plan_dir/'scenarios.json')!=plan['manifest_sha256'] or asdict(LowRuleConfig())!=plan['low_config']:raise ValueError('Frozen plan/config differs')
    if plan['union_inputs']!={k:list(v) for k,v in UNIONS.items()}:raise ValueError('Union differs')
    for p,h in plan['input_sha256'].items():
        if sha256(ROOT/p)!=h:raise ValueError('Protected input differs: '+p)
    artifacts=load_manifest(ROOT/'artifacts/mvp/docker/manifest.json');records=list(iter_appliances(ROOT/'data/energy/raw/energydata_complete.csv'))
    output.mkdir(parents=True);(output/'points').mkdir();details=[];episodes=[];gaps=[];executed=[];all_points={};parity_count=0;regressions=[];reasons=[]
    for c in manifest['scenarios']:
        start=datetime.fromisoformat(c['start']);end=start+STEP*(c['intervals']-1);left=start.replace(hour=0,minute=0,second=0)-timedelta(days=7);right=end+144*STEP
        raw=[deepcopy(r) for r in records if left<=datetime.fromisoformat(r['timestamp'])<=right]
        if [r['timestamp'] for r in raw]!=[(left+i*STEP).isoformat() for i in range(int((right-left)/STEP)+1)]:raise ValueError('Incomplete planned slice')
        changed=transform(raw,c);print(json.dumps(dict(case=c['scenario_id'],phase='fresh_paired_inference')),flush=True)
        mod=add_low(changed,infer(changed,artifacts));pair=add_low(raw,infer(raw,artifacts));parity_count+=len(mod)+len(pair)
        for arm,rows in [('modified',mod),('paired',pair)]:
            df=pd.DataFrame(rows)
            for n in (*METHODS,'isolation_forest','autoencoder','unanimous'):df[n+'_flag']=pd.array(df[n+'_flag'],dtype='boolean')
            df.to_parquet(output/'points'/f"{c['scenario_id']}-{arm}.parquet",index=False)
            if c['cohort']=='known_regression':
                oldpath=ROOT/'docs/energy-rules/complementarity-20261108/results/run1/points'/f"{c['historical_id']}-{arm}.parquet"
                old=pd.read_parquet(oldpath)
                cols=[n for n in old if not n.startswith(('ml_or_','ml_high_or_'))]
                pd.testing.assert_frame_equal(df[cols],old[cols],check_dtype=False,check_exact=True)
                regressions.append(dict(scenario_id=c['scenario_id'],arm=arm,old_sha256=sha256(oldpath),old_columns_compared=cols,rows=len(df),all_exact=True))
            for phase,section in [('stream',rows),('event',[r for r in rows if c['start']<=r['timestamp']<=end.isoformat()])]:
                counts={}
                for r in section:
                    if r['sustained_low_flag'] is None:
                        why=json.loads(r['sustained_low_evidence_json'])['unavailable_reason'];counts[why]=counts.get(why,0)+1
                reasons.extend(dict(scenario_id=c['scenario_id'],cohort=c['cohort'],arm=arm,phase=phase,reason=why,points=n) for why,n in counts.items())
        d,e=describe(c,mod,pair);details+=d;episodes+=e;all_points[c['scenario_id']]=(mod,pair)
        if c['family']=='interval_gap':gaps.append(check_gap(c,mod))
        executed.append({**c,'raw_points':len(raw),'modified_points':len(changed),'slice_start':left.isoformat(),'slice_end':right.isoformat()})
    if len(executed)!=plan['scenarios']:raise ValueError('Incomplete campaign')
    df=pd.DataFrame(details);df.to_csv(output/'cases.csv',index=False);df[df.family=='control'].to_csv(output/'controls.csv',index=False)
    pd.DataFrame(episodes).to_csv(output/'episodes.csv',index=False);pd.DataFrame(gaps).to_csv(output/'gaps.csv',index=False);pd.DataFrame(reasons).to_csv(output/'unavailable-reasons.csv',index=False)
    contrib=contributions(details);summaries=aggregate(details);pd.DataFrame(contrib).to_csv(output/'contributions.csv',index=False);pd.DataFrame(summaries).to_csv(output/'summary.csv',index=False)
    timing(output,records,artifacts,plan);report(output,summaries,contrib,gaps);plots(output,all_points,manifest['scenarios'],plan)
    write_json(output/'executed-manifest.json',executed);write_json(output/'v2-regression.json',regressions)
    for p,h in plan['input_sha256'].items():
        if sha256(ROOT/p)!=h:raise ValueError('Protected input changed')
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    except (FileNotFoundError,subprocess.CalledProcessError):commit=None
    provenance=dict(plan_sha256=sha256(plan_dir/'plan.json'),manifest_sha256=plan['manifest_sha256'],runner_sha256=sha256(Path(__file__)),low_module_sha256=sha256(ROOT/'processing/energy_low_rule.py'),git_commit=commit,
                    low_metadata=SustainedLow().metadata(),v2_metadata=EnergyRules().metadata(),registry=artifacts.registry(),thresholds=artifacts.anomaly.thresholds['0.99'],
                    protected_inputs_preserved=True,input_sha256=plan['input_sha256'],scenarios_completed=len(executed),low_exact_offline_streaming_records=parity_count,
                    old_scores_substituted=False,old_scores_read_for_exact_post_inference_regression=True,trained=False,
                    image_id=plan['docker_image_id'],libraries={n:importlib.metadata.version(n) for n in ['numpy','pandas','scikit-learn','torch','joblib','pyarrow']},
                    output_sha256={str(p.relative_to(output)):sha256(p) for p in sorted(output.rglob('*')) if p.is_file()})
    write_json(output/'provenance.json',provenance);print(json.dumps(dict(complete=True,scenarios=len(executed),low_parity_records=parity_count,v2_exact_regression_pairs=len(regressions))),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,default=PLAN);p.add_argument('--output',type=Path,required=True);args=p.parse_args();torch.set_num_threads(1)
    with threadpool_limits(1):run(args.plan,args.output)

if __name__=='__main__':main()
