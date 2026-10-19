"""Validate pilot correctness and overhead before releasing the full series."""
import json
from pathlib import Path
import statistics
import hashlib
from performance.analysis import read,summarize,read_json

ROOT=Path(__file__).resolve().parents[1]/'docs/stage6'


def check(directory):
    run=json.loads((directory/'run.json').read_text())
    integrity=read_json(directory/'integrity.json')
    summary=summarize(directory)
    expected=run['warmup']+run['measured']
    issues=list(integrity['failures'])
    publications=[r for r in read(directory/'producer.jsonl') if r['kind']=='publication']
    workers=[r for r in read(directory/'worker.jsonl') if r['kind']=='message']
    db={r['kafka_offset']:r for r in integrity['rows']}
    if len(publications)!=expected or len(db)!=expected:issues.append('Publication/DB coverage incomplete')
    for row in publications:
        if db.get(row['offset'],{}).get('event_id')!=row['event_id']:issues.append('Publication/DB correlation failed')
    if run['instrumented']:
        if {r['offset'] for r in workers}!=set(range(expected)):issues.append('Worker telemetry coverage incomplete')
        for row in workers:
            if row.get('db_commit_ack_calls')!=1 or row.get('sql_calls',0)==0:issues.append('Missing SQL/commit spans')
        for metric in ('hgb','rf','if','ae','db_commit_ack','kafka_commit_ack'):
            if summary['latency_ms'][metric]['n']!=run['measured']:issues.append('Measured span incomplete: '+metric)
        if not summary['cross_process_clock_valid']:issues.append('Clock step exceeds budget')
        if (directory/'clock-domains.json').exists() and summary['clock_method']!='verified_shared_vm_CLOCK_MONOTONIC':
            issues.append('Unverified monotonic endpoints/domain')
        if (directory/'clock-domains.json').exists() and summary['dashboard']['clock_method']!='verified_vm_monotonic_bridge':
            issues.append('Unverified browser monotonic bridge')
        if not summary['dashboard']['observed_measured_ids']:issues.append('No measured data reached browser DOM')
        if summary['dashboard']['invalid_clock_observations']:issues.append('Browser clock uncertainty exceeds budget')
        if summary['telemetry_errors']:issues.append('Telemetry loss/error')
        pub_by_offset={r['offset']:r for r in publications}
        if any('db_ack_mono_ns' in r and r['db_ack_mono_ns']<pub_by_offset[r['offset']]['send_mono_ns'] for r in workers):
            issues.append('Negative verified-monotonic end-to-end latency')
        for filename in ('producer','worker','visibility'):
            end=[r for r in read(directory/(filename+'.jsonl')) if r['kind']=='telemetry_end']
            if not end or end[-1]['dropped']:issues.append('Unclean telemetry shutdown: '+filename)
    for row in read(directory/'browser.jsonl'):
        if row['kind'] in ('fatal','browser_error'):issues.append('Browser error')
    return dict(run_id=run['run_id'],issues=sorted(set(issues)))


def main():
    config=json.loads((ROOT.parent.parent/'configs/system-performance-v1.json').read_text())
    runs=[]
    for path in sorted((ROOT/'raw').glob('*/run.json')):
        run=json.loads(path.read_text())
        if run['status']=='complete':runs.append((path.parent,run))
    pilots=[(p,r) for p,r in runs if r['label']=='pilot-'+config['pilot']['campaign']]
    if {r['mode'] for p,r in pilots}!={'slow','demo','max'}:raise SystemExit('Three completed pilot modes required')
    checks=[check(p) for p,r in pilots]
    pairs=[]
    for label in ['overhead-'+config['overhead']['campaign']+'-'+str(i) for i in range(1,4)]:
        trials=[(p,r) for p,r in runs if r['label']==label and not r.get('excluded_from_overhead_pairs')]
        if len(trials)!=2 or {r['instrumented'] for p,r in trials}!={True,False}:
            raise SystemExit('Exactly one on/off pair required: '+label)
        on=next(p for p,r in trials if r['instrumented']);off=next(p for p,r in trials if not r['instrumented'])
        checks.extend(check(p) for p,r in trials)
        original=read_json(off/'integrity.json');instrumented=read_json(on/'integrity.json')
        parity=all(original[key]==instrumented[key] for key in ('outputs','score_outputs'))
        if not parity:raise SystemExit('Model output parity failed')
        def throughput(path):
            run=json.loads((path/'run.json').read_text())
            return run['measured']/(run['observed_completion_duration_ns']/1e9)
        enabled,disabled=throughput(on),throughput(off)
        pairs.append(dict(pair=label,on_run=on.name,off_run=off.name,on_per_second=enabled,off_per_second=disabled,
                          throughput_overhead_percent=100*(disabled-enabled)/disabled,model_output_parity=parity))
    median=statistics.median(r['throughput_overhead_percent'] for r in pairs)
    result={'checks':checks,'pairs':pairs,'median_throughput_overhead_percent':median,
            'correctness_passed':not any(r['issues'] for r in checks),'overhead_under_investigation':median>5}
    from performance.run import instrumentation_digest,CONFIG
    result.update(config_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
                  instrumentation_sha256=instrumentation_digest(),
                  manifest_sha256=hashlib.sha256((ROOT.parent.parent/config['manifest']).read_bytes()).hexdigest(),
                  environment_sha256=hashlib.sha256((ROOT/'environment.json').read_bytes()).hexdigest())
    (ROOT/'pilot-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['correctness_passed'] or result['overhead_under_investigation']:
        raise SystemExit('Pilot gate not passed; see pilot-validation.json')
    # Recovery pilot is independently required before publishing the release marker.
    recovery=[(p,r) for p,r in runs if r['label']=='pilot-recovery-'+config['pilot']['campaign'] and r.get('recovery_forecasts_unchanged') and r.get('recovery_resumed_observed_ns')]
    if not recovery:raise SystemExit('Successful recovery pilot required')
    for p,r in recovery:
        failures=check(p)['issues']
        if failures:raise SystemExit('Recovery pilot telemetry validation failed: '+str(failures))
    (ROOT/'pilot-approved.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
