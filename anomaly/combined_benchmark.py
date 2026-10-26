"""Reuse frozen Stage 4 outputs only. Validation selection is persisted before test."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from anomaly.combined import NAMES, RULES
from anomaly.evaluate import metrics, runs

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'docs/energy-anomaly/results'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def evaluate(split, source=SOURCE):
    thresholds=json.loads((source/'thresholds.json').read_text())['0.99']
    rows,controls,coverage,outcomes=[],[],[],[]
    for path in sorted((source/'scores').glob(split+'-*.parquet')):
        scenario=path.stem[len(split)+1:]
        f=pd.read_parquet(path)
        times=pd.to_datetime(f.measurement_timestamp)
        if times.duplicated().any() or not times.is_monotonic_increasing or not times.diff().iloc[1:].eq(pd.Timedelta(minutes=10)).all():
            raise ValueError('Stored timeline is not unique and contiguous')
        ready=np.column_stack([np.isfinite(f[n]) for n in NAMES]);common=ready.all(axis=1)
        # Stage 4 saved partitions have complete common coverage; fail rather than
        # compress event indices or silently count unready intervals as false.
        if not common.all(): raise ValueError('Incomplete common timeline requires explicit segmentation')
        votes=np.column_stack([(f[n]>thresholds[n]).to_numpy() for n in NAMES])
        flags={n:votes[:,i] for i,n in enumerate(NAMES)}
        flags.update({name:votes.sum(axis=1)>=minimum for name,minimum in RULES.items()})
        for name in flags:
            coverage.append(dict(split=split,scenario=scenario,method=name,count=len(f),ready=int(common.sum()),coverage=float(common.mean()),saved_partition_unready=int((~common).sum()),history_prefix=144))
        if scenario=='clean':
            for name,alarm in flags.items():
                controls.append(dict(split=split,method=name,count=len(f),alarms=int(alarm.sum()),background_alarm_rate=float(alarm.mean()),alarms_per_day=float(alarm.sum()/(len(f)/144)),alarm_episodes=len(runs(alarm,times))))
            continue
        manifest=json.loads((source/f'manifests/{split}-{scenario}.json').read_text())
        labels=np.zeros(len(f),dtype=bool)
        for e in manifest['events']:
            if str(f.measurement_timestamp.iloc[e['start']])!=e['start_timestamp'] or str(f.measurement_timestamp.iloc[e['end']])!=e['end_timestamp']:
                raise ValueError('Manifest timestamp alignment differs')
            labels[e['start']:e['end']+1]=True
        np.testing.assert_array_equal(labels,f.synthetic_label.to_numpy(bool))
        for name,alarm in flags.items():
            result,events=metrics(alarm,labels,times,manifest['events'])
            fresh=sum(any(e['start']<=start<=e['end'] for start,_ in runs(alarm,times)) for e in manifest['events'])
            key=dict(split=split,scenario=scenario,type=manifest['type'],method=name)
            rows.append(key|result|{'onset_in_event_diagnostic_recall':fresh/len(events) if events else None})
            outcomes.extend(key|e for e in events)
    return rows,controls,coverage,outcomes

def persist(split,data,output):
    for name,rows in zip(('metrics','controls','coverage','event_outcomes'),data): pd.DataFrame(rows).to_csv(output/f'{split}-{name}.csv',index=False)
    frame=pd.DataFrame(data[0]);numeric=['precision','recall','f1','event_recall','event_f1','alarm_episodes','delay_median_minutes','post_event_alarms','onset_in_event_diagnostic_recall']
    frame.groupby(['split','type','method'])[numeric].mean().reset_index().to_csv(output/f'{split}-by_type.csv',index=False)
    summary=frame[frame.scenario.str.startswith('mixed-')].groupby('method')[numeric].mean()
    summary.join(pd.DataFrame(data[1]).set_index('method')[['background_alarm_rate','alarms_per_day']]).to_csv(output/f'{split}-summary.csv')

def choose(rows,controls):
    if any(r.get('split','validation')!='validation' for r in [*rows,*controls]): raise ValueError('Selection accepts validation only')
    f=pd.DataFrame(rows);c=pd.DataFrame(controls).set_index('method');values={}
    for name in RULES:
        r=f[(f.method==name)&f.scenario.str.startswith('mixed-')]
        delay=r.delay_median_minutes.mean()
        values[name]={'event_f1':float(r.event_f1.mean()),'background_alarm_rate':float(c.loc[name,'background_alarm_rate']),
                      'delay_minutes':float(delay) if pd.notna(delay) else None}
    eligible=[n for n in RULES if values[n]['background_alarm_rate']<=.01]
    selected=min(eligible,key=lambda n:(-values[n]['event_f1'],values[n]['delay_minutes'] if values[n]['delay_minutes'] is not None else float('inf'),values[n]['background_alarm_rate'],list(RULES).index(n))) if eligible else None
    return {'rule':selected,'rule_version':'combined-q99-v1-'+selected if selected is not None else None,'uses_test':False,'eligible':bool(eligible),'candidates':values,'maturity':'experimental','test_previously_viewed':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['validation','test']);p.add_argument('--output',type=Path,default=ROOT/'docs/stage7b/results');a=p.parse_args()
    output=a.output;output.mkdir(exist_ok=True,parents=True)
    checks=json.loads((SOURCE/'checksums.json').read_text())
    for path,digest in checks.items():
        if sha(SOURCE/path)!=digest: raise ValueError('Original Stage 4 input changed: '+path)
    if (output/f'{a.phase}-metrics.csv').exists(): raise ValueError('Do not overwrite results')
    if a.phase=='test' and not (output/'selection.json').exists(): raise ValueError('Freeze validation selection first')
    result=evaluate(a.phase);persist(a.phase,result,output)
    if a.phase=='validation':
        selection=choose(result[0],result[1]);write(output/'selection.json',selection)
        frozen=ROOT/'configs/combined-rule-v1.json'
        if frozen.exists() and json.loads(frozen.read_text())!=selection: raise ValueError('Frozen rule differs; do not overwrite')
        if not frozen.exists(): write(frozen,selection)
        print(json.dumps(selection,indent=2))
    write(output/f'{a.phase}-provenance.json',{'source_checksums_sha256':sha(SOURCE/'checksums.json'),'protocol_sha256':sha(ROOT/'docs/stage7b/protocol.md'),'selection_sha256':sha(output/'selection.json'),'input_sha256':checks,'new_training':False})
if __name__=='__main__': main()
