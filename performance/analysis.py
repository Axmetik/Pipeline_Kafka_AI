"""Deterministic per-run summaries; no pooled pseudo-replication."""
import json
from pathlib import Path
import statistics
import re
import gzip


def quantiles(values):
    values=sorted(values)
    if not values:return {'n':0,'p50':None,'p95':None,'p99':None}
    def at(p):
        index=(len(values)-1)*p;lo=int(index);hi=min(lo+1,len(values)-1)
        return values[lo]+(values[hi]-values[lo])*(index-lo)
    return dict(n=len(values),p50=at(.5),p95=at(.95),p99=at(.99))


def read(path):
    path=Path(path)
    if path.exists():value=path.read_text()
    elif Path(str(path)+'.gz').exists():
        with gzip.open(str(path)+'.gz','rt') as stream:value=stream.read()
    else:return []
    return [json.loads(line) for line in value.splitlines() if line.strip()]


def read_json(path):
    path=Path(path)
    if path.exists():return json.loads(path.read_text())
    with gzip.open(str(path)+'.gz','rt') as stream:return json.load(stream)


def clock_steps(rows):
    points=[r for r in rows if 'epoch_ns' in r and 'mono_ns' in r]
    return [max(0,abs((b['epoch_ns']-a['epoch_ns'])-(b['mono_ns']-a['mono_ns']))
                -a.get('clock_read_uncertainty_ns',0)-b.get('clock_read_uncertainty_ns',0))/1e6
            for a,b in zip(points,points[1:])]


def summarize(directory):
    directory=Path(directory)
    publications=[r for r in read(directory/'producer.jsonl') if r['kind']=='publication' and r['phase']=='measured']
    offsets={r['offset']:r for r in publications}
    workers=[r for r in read(directory/'worker.jsonl') if r['kind']=='message' and r['offset'] in offsets]
    result={'publications':len(publications),'processed':len(workers),'latency_ms':{}}
    for metric in ('process','poll_to_db','hgb','rf','if','ae','runtime','energy_features','anomaly_features',
                   'transaction','sql','db_commit_ack','kafka_commit_ack'):
        result['latency_ms'][metric]=quantiles([r[metric+'_ns']/1e6 for r in workers if metric+'_ns' in r])
    result['latency_ms']['ml_inference']=quantiles([sum(r.get(name+'_ns',0) for name in ('hgb','rf','if','ae'))/1e6
        for r in workers if all(name+'_ns' in r for name in ('hgb','rf','if','ae'))])
    result['latency_ms']['publication_ack']=quantiles([r['ack_ns']/1e6 for r in publications])
    from performance.clock_domain import compatible
    domains=read_json(directory/'clock-domains.json') if (directory/'clock-domains.json').exists() else {}
    verified=compatible(list(domains.values()))
    if verified:
        reference=next(iter(domains.values()))
        actual=[r for name in ('producer','worker','visibility','http') for r in read(directory/(name+'.jsonl')) if r['kind']=='clock_domain']
        verified=bool(actual) and all({k:r.get(k) for k in reference}==reference for r in actual)
    shared=verified and all('send_mono_ns' in r for r in publications) and all('db_ack_mono_ns' in r for r in workers)
    result['clock_method']='verified_shared_vm_CLOCK_MONOTONIC' if shared else 'legacy_epoch'
    send_key='send_mono_ns' if shared else 'send_epoch_ns'
    end_key='db_ack_mono_ns' if shared else 'db_ack_epoch_ns'
    result['latency_ms']['send_to_db_ack']=quantiles([(r[end_key]-offsets[r['offset']][send_key])/1e6 for r in workers])
    result['clock_step_ms']={name:quantiles(clock_steps(read(directory/(name+'.jsonl')))) for name in ('producer','worker')}
    result['epoch_clock_valid']=all(max(clock_steps(read(directory/(name+'.jsonl'))),default=0)<=10 and
        max([r.get('clock_read_uncertainty_ns',0)/1e6 for r in read(directory/(name+'.jsonl'))],default=0)<=10
        for name in ('producer','worker'))
    result['cross_process_clock_valid']=shared if domains else result['epoch_clock_valid']
    if not result['cross_process_clock_valid']:
        result['latency_ms']['send_to_db_ack']['valid']=False
    if len(publications)>1:
        result['publication_rate_per_second']=(len(publications)-1)/((publications[-1][send_key]-publications[0][send_key])/1e9)
    if len(workers)>1:
        result['commit_rate_per_second']=(len(workers)-1)/((workers[-1][end_key]-workers[0][end_key])/1e9)
    if publications and workers:
        result['completion_throughput_per_second']=len(workers)/((workers[-1][end_key]-publications[0][send_key])/1e9)
    visibility={r['measurement_id']:r for r in read(directory/'visibility.jsonl') if r['kind']=='visible'}
    browser=read(directory/'browser.jsonl')
    clocks=[r for r in browser if r['kind']=='clock']
    mono_visibility=verified and bool(visibility) and all('available_lower_mono_ns' in v for v in visibility.values()) and all('serverMonoNs' in r and r.get('clockDomain')==next(iter(domains.values())) for r in clocks)
    upper_key='available_upper_mono_ns' if mono_visibility else 'available_upper_ns'
    lower_key='available_lower_mono_ns' if mono_visibility else 'available_lower_ns'
    # Use the nearest clock exchange in time, minimum RTT of its ten-sample batch.
    samples=[]
    for i in range(0,len(clocks),10):
        group=clocks[i:i+10]
        best=min(group,key=lambda r:r['endEpochMs']-r['startEpochMs'])
        samples.append(((best['startEpochMs']+best['endEpochMs'])/2,
                        best['serverMonoNs' if mono_visibility else 'serverEpochNs']/1e6-(best['startEpochMs']+best['endEpochMs'])/2,
                        (best['endEpochMs']-best['startEpochMs'])/2))
    lower=[];upper=[];middle=[];fetch=[];seen=set();invalid=0
    latest_lower=[];latest_upper=[];head_gaps=[];dom_times=[]
    measured_ids={v['measurement_id'] for v in visibility.values() if v['kafka_offset'] in offsets}
    for row in browser:
        if row['kind']!='dom':continue
        dom_times.append(row['domEpochMs'])
        fetch.append(row['domEpochMs']-row['fetchedEpochMs'])
        if not samples:continue
        _,delta,error=min(samples,key=lambda s:abs(s[0]-row['domEpochMs']))
        if row['ids'] and row['ids'][0] in visibility and error<=10:
            latest=visibility[row['ids'][0]];dom=row['domEpochMs']+delta
            latest_lower.append(dom-latest[upper_key]/1e6-error)
            latest_upper.append(dom-latest[lower_key]/1e6+error)
            known=max([v['kafka_offset'] for v in visibility.values() if v[upper_key]/1e6<=dom-error]+[latest['kafka_offset']])
            head_gaps.append(known-latest['kafka_offset'])
        for mid in row['firstIds']:
            if mid not in measured_ids:continue
            seen.add(mid)
            if error>10:invalid+=1;continue
            v=visibility[mid];dom=row['domEpochMs']+delta
            lo=dom-v[upper_key]/1e6-error
            hi=dom-v[lower_key]/1e6+error
            lower.append(lo);upper.append(hi);middle.append((lo+hi)/2)
    result['dashboard']={'committed_measured_ids':len(measured_ids),'observed_measured_ids':len(seen),
                         'censored':len(measured_ids-seen),'invalid_clock_observations':invalid,
                         'availability_to_dom_lower_ms':quantiles(lower),'availability_to_dom_upper_ms':quantiles(upper),
                         'availability_to_dom_midpoint_ms':quantiles(middle),'fetch_to_dom_ms':quantiles(fetch),
                         'clock_uncertainty_ms':quantiles([s[2] for s in samples])}
    result['dashboard'].update(latest_displayed_availability_age_lower_ms=quantiles(latest_lower),
        latest_displayed_availability_age_upper_ms=quantiles(latest_upper),known_db_head_gap_records=quantiles(head_gaps),
        actual_poll_interval_ms=quantiles([b-a for a,b in zip(dom_times,dom_times[1:])]))
    result['dashboard']['cross_process_clock_valid']=result['cross_process_clock_valid']
    result['dashboard']['clock_method']='verified_vm_monotonic_bridge' if mono_visibility else 'legacy_epoch_bridge'
    result['telemetry_errors']=[r for r in read(directory/'worker.jsonl') if r['kind']=='process_error' or (r['kind']=='telemetry_end' and r['dropped'])]
    http=[r for r in read(directory/'http.jsonl') if r['kind']=='http' and r['phase']=='measured']
    if http:
        result['http']={'attempts':len(http),'errors':sum(r['error'] is not None for r in http),
                        'timeouts':sum(r.get('timeout',False) or r['error'] in ('TimeoutError','socket.timeout') for r in http),
                        'latency_ms':quantiles([r['duration_ns']/1e6 for r in http]),
                        'success_latency_ms':quantiles([r['duration_ns']/1e6 for r in http if r['status']==200 and r['error'] is None]),
                        'by_endpoint':{key:quantiles([r['duration_ns']/1e6 for r in http if r['endpoint']==key]) for key in sorted({r['endpoint'] for r in http})}}
        if publications:
            lo=publications[0][send_key];hi=publications[-1]['mono_ns' if shared else 'epoch_ns']
            result['http']['requests_during_replay']=sum(lo<=r['start_mono_ns' if shared else 'start_epoch_ns']<=hi for r in http)
        if all('start_mono_ns' in r for r in http):
            duration=(max(r['start_mono_ns']+r['duration_ns'] for r in http)-min(r['start_mono_ns'] for r in http))/1e9
            result['http']['attempts_per_second']=len(http)/duration
    resource_rows=read(directory/'resources.jsonl')
    result['resource_sampling_errors']=sum(r['kind']=='resource_error' for r in resource_rows)
    resources=[r for r in resource_rows if r['kind']=='resource']
    run_path=directory/'run.json'
    if run_path.exists():
        run=json.loads(run_path.read_text())
        resources=[r for r in resources if run.get('measured_start_epoch_ns',0)<=r['epoch_ns']<=run.get('measured_end_epoch_ns',2**63)]
    result['resource_scope']='measured controller epoch window; Docker CPU samples have their own averaging interval'
    result['resources']={}
    for container in sorted({r['Name'] for r in resources}):
        samples=[r for r in resources if r['Name']==container]
        def memory(value):
            number,unit=re.fullmatch(r'([\d.]+)\s*([A-Za-z]+)',value.split(' / ')[0]).groups()
            return float(number)*{'B':1,'kB':1000,'MB':1000**2,'GB':1000**3,'KiB':1024,'MiB':1024**2,'GiB':1024**3}[unit]
        cpu=[float(r['CPUPerc'].rstrip('%')) for r in samples]
        result['resources'][container]={'samples':len(samples),'cpu_percent':quantiles(cpu),
            'cpu_mean_percent':statistics.mean(cpu),'cpu_peak_percent':max(cpu),
            'ram_peak_bytes':max(memory(r['MemUsage']) for r in samples),
            'sampling_interval_ms':quantiles([(b['epoch_ns']-a['epoch_ns'])/1e6 for a,b in zip(samples,samples[1:])])}
    (directory/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
