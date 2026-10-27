"""Read-only audit of saved results. No model loading, inference, replay or DB writes.
Usage: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python docs/stage8a/verify_evidence.py --stage6 /path/to/archive/docs/stage6
JSON goes to stdout; redirect only into the CURRENT checkout, never the archive.
"""
import argparse,csv,gzip,hashlib,json,math,re,statistics,subprocess,sys
import importlib.metadata
from datetime import datetime,timedelta
from pathlib import Path
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[2]
SOURCES={}
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
def remember(p):
    key=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
    SOURCES[key]=sha(p)
    return p

def js(p): return json.loads(remember(p).read_text())
def csvrows(p):
    with remember(p).open(newline='') as f: return list(csv.DictReader(f))
def gzjs(p):
    with gzip.open(remember(p),'rt') as f: return json.load(f)
def lines(p):
    with gzip.open(remember(p),'rt') as f: return [json.loads(l) for l in f if l.strip()]
def close(a,b):
    assert math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-10),(a,b)
def errors(actual,pred):
    e=[p-a for a,p in zip(actual,pred)]
    return {'count':len(e),'mae_wh':statistics.mean(map(abs,e)),'rmse_wh':math.sqrt(statistics.mean(x*x for x in e))}
def quantile(v,q):
    v=sorted(v);i=(len(v)-1)*q;a=math.floor(i);b=math.ceil(i)
    return v[a]+(v[b]-v[a])*(i-a)
def groups(flags):
    result=[];start=None
    for i,flag in enumerate([*flags,False]):
        if flag and start is None:start=i
        if not flag and start is not None:result.append((start,i-1));start=None
    return result

def detection(flags,labels,events):
    tp=sum(f and l for f,l in zip(flags,labels));fp=sum(f and not l for f,l in zip(flags,labels))
    pos=sum(labels);p=tp/(tp+fp) if tp+fp else 0;r=tp/pos if pos else 0
    alarms=groups(flags);matched={}
    for a,b in alarms:
        available=[e for e in events if e['event_id'] not in matched and e['start']<=b and e['end']>=a]
        if available:
            e=min(available,key=lambda e:e['start']);matched[e['event_id']]=max(a,e['start'])
    ep=len(matched)/len(alarms) if alarms else 0;er=len(matched)/len(events) if events else 0
    return dict(precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0,event_recall=er,event_f1=2*ep*er/(ep+er) if ep+er else 0,
        alarm_episodes=len(alarms),matched_events=len(matched),alarms=sum(flags))

def run(stage6):
    remember(Path(__file__))
    result={'verifier_sha256':sha(Path(__file__)),'python':sys.version.split()[0],'pyarrow':importlib.metadata.version('pyarrow'),'base_commit':'c156668a1bc41e20eb7c3c175eb5da1afd9037d7','audit_date':'2026-10-27','new_experiments':False}
    dataset=ROOT/'data/energy/raw/energydata_complete.csv';raw=csvrows(dataset)
    actual={r['date'].replace(' ','T'):float(r['Appliances']) for r in raw}
    result['dataset']={'count':len(raw),'sha256':sha(dataset),'first':min(actual),'last':max(actual)}
    assert result['dataset']['sha256']=='2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d'
    b=ROOT/'docs/forecast-benchmark/results';pred=csvrows(b/'test_predictions.csv');saved={r['model']:r for r in csvrows(b/'metrics.csv')}
    metrics={};y=[float(r['actual_energy_wh']) for r in pred]
    for r in pred:
        origin=datetime.fromisoformat(r['forecast_origin']);target=datetime.fromisoformat(r['forecast_target_timestamp'])
        assert target-origin==timedelta(minutes=10)
        close(float(r['actual_energy_wh']),actual[target.isoformat()]);close(float(r['persistence']),actual[origin.isoformat()])
        close(float(r['seasonal_naive']),actual[(target-timedelta(days=1)).isoformat()])
    for model in saved:
        metrics[model]=errors(y,[float(r[model]) for r in pred])
        for key in ('mae_wh','rmse_wh'):close(metrics[model][key],saved[model][key])
    split=csvrows(b/'split_membership.csv');targets=[r['forecast_target_timestamp'] for r in split]
    assert len(targets)==len(set(targets)) and targets==sorted(targets)
    train_y=[actual[r['forecast_target_timestamp']] for r in split if r['split']=='train']
    peak=quantile(train_y,.9);close(peak,210)
    peak_rows=[r for r in pred if float(r['actual_energy_wh'])>peak]
    for expected in csvrows(b/'peak_metrics.csv'):
        computed=errors([float(r['actual_energy_wh']) for r in peak_rows],[float(r[expected['model']]) for r in peak_rows])
        assert computed['count']==int(expected['count'])
        for k in ('mae_wh','rmse_wh'):close(computed[k],expected[k])
    result['forecast_stage3']={'peak_threshold_wh':peak,'peak_count':len(peak_rows),'test_metrics':metrics,'selection':js(b/'selection.json'),'splits':js(b/'splits.json'),
        'peaks':csvrows(b/'peak_metrics.csv'),'same_target_count':len(pred),'seasonal_exact_target_minus_day':True}
    p=ROOT/'artifacts/mvp/docker/hgb/test_predictions.parquet';rows=pq.read_table(remember(p)).to_pylist();saved2=js(p.parent/'metrics.json')
    result['forecast_stage2_local_docker']={}
    for name,col,expected in [('hgb20','predicted_energy_wh','ml'),('persistence','baseline_energy_wh','persistence')]:
        m=errors([r['actual_energy_wh'] for r in rows],[r[col] for r in rows]);result['forecast_stage2_local_docker'][name]=m
        for key in ('mae_wh','rmse_wh'):close(m[key],saved2[expected][key])
    manifest=ROOT/'artifacts/mvp/docker/manifest.json';m=js(manifest)
    result['trusted_local_artifacts']={name:sha(remember(manifest.parent/v['path']))==v['sha256'] for name,v in m['artifacts'].items()}
    assert all(result['trusted_local_artifacts'].values())
    archive_root=stage6.parents[1] if stage6 else None
    if archive_root:
        metadata=js(b/'metadata.json')
        original3={name:sha(remember(archive_root/'artifacts/forecast-benchmark/v1'/name))==digest for name,digest in metadata['model_sha256'].items()}
        original4=sha(remember(archive_root/'artifacts/energy-anomaly/v1/bundle.joblib'))==js(ROOT/'docs/energy-anomaly/results/metadata.json')['model_sha256']
        assert all(original3.values()) and original4
        result['original_archived_weights']={'stage3':original3,'stage4':original4}

    s4=ROOT/'docs/energy-anomaly/results';checks=js(s4/'checksums.json')
    failures=[n for n,h in checks.items() if sha(s4/n)!=h];assert not failures,failures
    result['stage4_original_checksums']={'verified':len(checks),'mismatches':failures}
    thresholds=js(s4/'thresholds.json');result['thresholds']=thresholds
    s7=ROOT/'docs/stage7b/results';summary={r['method']:r for r in csvrows(s7/'test-summary.csv')};summaryval=csvrows(s7/'validation-summary.csv')
    per_method={n:[] for n in summary}
    saved4=csvrows(s4/'metrics.csv')
    for seed in range(201,206):
        scenario=f'mixed-seed{seed}';rr=pq.read_table(remember(s4/f'scores/test-{scenario}.parquet')).to_pylist()
        events=js(s4/f'manifests/test-{scenario}.json')['events'];labels=[r['synthetic_label'] for r in rr]
        flags={n:[r[n]>thresholds['0.99'][n] for r in rr] for n in ('isolation_forest','autoencoder','residual')}
        votes=[sum(v) for v in zip(*flags.values())]
        flags.update({'or':[v>=1 for v in votes],'majority':[v>=2 for v in votes],'unanimous':[v==3 for v in votes]})
        for n,ff in flags.items():
            val=detection(ff,labels,events);per_method[n].append(val)
            if n in thresholds['0.99']:
                old=next(r for r in saved4 if r['split']=='test' and r['scenario']==scenario and r['detector']==n and r['quantile']=='0.99')
                for k in ('precision','recall','f1','event_recall','event_f1','alarm_episodes'):close(val[k],old[k])
    calculated={n:{k:statistics.mean(r[k] for r in vals) for k in vals[0]} for n,vals in per_method.items()}
    for n,values in calculated.items():
        for k in ('precision','recall','f1','event_recall','event_f1','alarm_episodes'):close(values[k],summary[n][k])
    result['anomaly_mixed_test_recomputed']=calculated
    result['combined_selection']=js(s7/'selection.json');result['combined_test_summary']=list(summary.values());result['combined_validation_summary']=summaryval
    by_type=csvrows(s7/'test-by_type.csv');result['combined_unanimous_by_type']=[r for r in by_type if r['method']=='unanimous']
    result['stage4_mixed_q99_fpr']={n:statistics.mean(float(r['fpr_synthetic']) for r in saved4 if r['split']=='test' and r['scenario'].startswith('mixed-') and r['quantile']=='0.99' and r['detector']==n) for n in thresholds['0.99']}
    result['sole_residual_hit']=csvrows(ROOT/'docs/energy-anomaly/diagnostics/sole_residual_hit.csv')
    if stage6:
        checks6=js(stage6/'raw-checksums.json');bad=[]
        for name,h in checks6.items():
            p=stage6/name
            with gzip.open(p,'rb') as f: original=hashlib.sha256(f.read()).hexdigest()
            if sha(p)!=h['compressed_sha256'] or original!=h['original_sha256']:bad.append(name)
        assert not bad,bad
        result['stage6_archive_checksums']={'verified':len(checks6),'mismatches':bad}
        pilots=[];table=csvrows(stage6/'pilot-latencies.csv')
        throughput=csvrows(stage6/'throughput.csv')
        for entry in js(stage6/'evidence-index.json')['runs']:
            if entry['evidence_group']!='completed_final_pilot':continue
            base=stage6/'raw'/entry['run_id'];run=js(base/'run.json');summ=js(base/'summary.json');integrity=gzjs(base/'integrity.json.gz')
            pub=[r for r in lines(base/'producer.jsonl.gz') if r['kind']=='publication' and r['phase']=='measured']
            workers={r['offset']:r for r in lines(base/'worker.jsonl.gz') if r['kind']=='message'}
            durations=[(workers[r['offset']]['db_ack_mono_ns']-r['send_mono_ns'])/1e6 for r in pub]
            savedq=next(r for r in table if r['run_id']==entry['run_id'] and r['metric']=='send_to_db_ack')
            q={k:quantile(durations,v) for k,v in [('p50',.5),('p95',.95),('p99',.99)]}
            for k in q:close(q[k],savedq[k]);close(q[k],summ['latency_ms']['send_to_db_ack'][k])
            assert integrity['failures']==[] and integrity['measurements']==210 and integrity['event_ids']==210
            assert integrity['forecasts']==420 and integrity['scores']==630
            assert integrity['next_offset']==integrity['broker_next_offset']==integrity['kafka_end_offset']==210
            db={r['kafka_offset']:r for r in integrity['rows']}
            assert len(pub)==60 and len(workers)==210 and len({r['event_id'] for r in pub})==60
            assert all(r['event_id']==db[r['offset']]['event_id'] and workers[r['offset']]['outcome']=='accepted' for r in pub)

            measured_workers=[workers[r['offset']] for r in pub]
            rates={'publication_per_second':(len(pub)-1)/((pub[-1]['send_mono_ns']-pub[0]['send_mono_ns'])/1e9),
                   'commit_per_second':(len(pub)-1)/((measured_workers[-1]['db_ack_mono_ns']-measured_workers[0]['db_ack_mono_ns'])/1e9),
                   'completion_per_second':len(pub)/((measured_workers[-1]['db_ack_mono_ns']-pub[0]['send_mono_ns'])/1e9)}
            saved_rate=next(r for r in throughput if r['run_id']==entry['run_id'])
            for k,value in rates.items():close(value,saved_rate[k])
            pilots.append({'run_id':entry['run_id'],'mode':entry['mode'],'warmup':run['warmup'],'measured':run['measured'],
                'send_to_db_ack_ms':q,'clocks_valid':summ['cross_process_clock_valid'],
                'integrity':{k:integrity[k] for k in ('measurements','forecasts','scores','event_ids','receipts','duplicate_deliveries','errors','next_offset','broker_next_offset','kafka_end_offset')},
                'throughput':next(r for r in throughput if r['run_id']==entry['run_id']),
                'dashboard':summ['dashboard']})
        rec=js(stage6/'raw/s6-pilot-recovery-v7-demo-20261019t175618-a15932/run.json')
        result['stage6']={'location':str(stage6),'pilots':pilots,'closure':js(stage6/'closure-status.json'),
            'recovery':{k:v for k,v in rec.items() if k.startswith('recovery_')},'overhead':js(stage6/'pilot-validation.json')}
    result['email']=js(ROOT/'docs/stage7c/verification.json')
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}',r'AKIA[0-9A-Z]{16}']
    suspect=[]
    for file in tracked:
        p=ROOT/file
        if p.stat().st_size>2_000_000:continue
        try:t=p.read_text()
        except UnicodeError:continue
        if any(re.search(pattern,t) for pattern in patterns):suspect.append(file)
    result['tracked_secret_pattern_scan']={'scope':'current tracked text <=2MB; selected private-key/GitHub/AWS patterns; not full history or secret-scanner guarantee',
        'suspect_paths':suspect,'tracked_env_files':[p for p in tracked if Path(p).name.startswith('.env')]}
    # Record the manifest itself and rehash every explicitly-read source (no writes to archive).
    result['sources_sha256']=dict(sorted(SOURCES.items()))
    assert all(sha(ROOT/k if not Path(k).is_absolute() else Path(k))==v for k,v in SOURCES.items())
    result['read_sources_unchanged_at_end']=True
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage6',type=Path);a=parser.parse_args();run(a.stage6)
