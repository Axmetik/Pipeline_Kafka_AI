"""Read-only Stage3 analysis. Default: saved gzip API export only.
--capture reads existing persisted results over GET once; no model imports/writes to DB.
"""
import argparse
import ast
import csv
import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

OUT = Path(__file__).resolve().parent
PREV = OUT.parent/'stage2'
PLAN = json.loads((PREV/'plan.json').read_text())
ENV = json.loads((PREV/'environment.json').read_text())
METHODS = ('residual','autoencoder','isolation_forest','unanimous','sustained_high','hybrid','flatline','interval_gap')
MAIN = METHODS[:6]
START, END, RETURN = (PLAN[k] for k in ('intervention_start','intervention_end','return_to_original'))
CACHE = OUT/'source-api.json.gz'


def dump(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def csv_file(name, rows):
    assert rows
    with (OUT/name).open('w') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False,separators=(',',':')) if v is None or isinstance(v,(bool,list,dict)) else v for k,v in row.items()})


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def dt(value):
    return datetime.fromisoformat(value)


def minutes(a,b):
    return (dt(b)-dt(a)).total_seconds()/60


def period(timestamp):
    return 'before' if timestamp < START else 'intervention' if timestamp <= END else 'after'


def capture():
    assert not CACHE.exists(), 'Saved input already exists: use offline analysis; never overwrite source evidence'
    resources = ('measurements','anomaly-scores','combined-decisions','rule-assessments','hybrid-decisions',
                 'events','combined-events','hybrid-events')
    cache = {'base_url':ENV['base_url'],'source_code_sha':PLAN['code_sha'],'scenarios':{},'requests':{}}
    for label,ids in ENV['scenarios'].items():
        data, counts = {}, {}
        for endpoint in resources:
            params = dict(run_id=ids['run_id'],building_id='appliances-house-1',source_id='uci-appliances',limit=1000)
            rows, pages = [],0
            while True:
                with urlopen(ENV['base_url']+'/api/'+endpoint+'?'+urlencode(params),timeout=20) as response:
                    assert response.status == 200
                    page = json.load(response)
                pages += 1
                rows.extend(page['items'])
                if not page['next_cursor']: break
                params['cursor'] = page['next_cursor']
            data[endpoint] = rows
            counts[endpoint] = dict(rows=len(rows),pages=pages,canonical_sha256=digest(rows))
        cache['scenarios'][label] = data
        cache['requests'][label] = counts
        print('Read persisted API rows:',label,{k:v['rows'] for k,v in counts.items()},flush=True)
    CACHE.write_bytes(gzip.compress(json.dumps(cache,sort_keys=True,separators=(',',':')).encode(),mtime=0))


def assemble(label, data):
    report = json.loads((PREV/(label+'-summary.json')).read_text())
    run = ENV['scenarios'][label]['run_id']
    mapping = {'measurements':'measurements','anomaly-scores':'scores','combined-decisions':'combined_decisions',
               'rule-assessments':'rule_assessments','hybrid-decisions':'hybrid_decisions','events':'episodes',
               'combined-events':'combined_episodes','hybrid-events':'hybrid_episodes'}
    for endpoint,key in mapping.items():
        assert len(data[endpoint]) == report['counts'][key]
        assert all(x['run_id']==run and x['building_id']=='appliances-house-1' and x['source_id']=='uci-appliances' for x in data[endpoint])
    scores = {(x['measurement_id'],x['detector']):x for x in data['anomaly-scores']}
    rules = {(x['measurement_id'],x['rule']):x for x in data['rule-assessments']}
    hybrid = {x['measurement_id']:x for x in data['hybrid-decisions']}
    unanimous = {x['measurement_id']:x for x in data['combined-decisions']}
    points,versions = [],{m:set() for m in METHODS}
    for measurement in sorted(data['measurements'],key=lambda x:x['measurement_timestamp']):
        mid = measurement['measurement_id']
        p = {k:measurement[k] for k in ('measurement_timestamp','measurement_id','building_id','source_id','energy_wh','received_at')}
        p['timestamp'] = p.pop('measurement_timestamp')
        p['period'] = period(p['timestamp'])
        assert measurement['time_basis']=='dataset_naive' and measurement['timezone'] is None
        assert measurement['interval_seconds']==600 and not measurement['gap_detected']
        entries = {m:scores[mid,m] for m in METHODS[:3]}
        entries.update({m:rules[mid,m] for m in ('sustained_high','flatline','interval_gap')})
        entries.update(hybrid=hybrid[mid],unanimous=unanimous[mid])
        for method,entry in entries.items():
            assert entry['flag'] is None or type(entry['flag']) is bool
            p[method+'_flag'],p[method+'_status'] = entry['flag'],entry['status']
            signature = {k:entry[k] for k in ('model_id','model_version','feature_version','threshold_version','threshold',
                'rule_version','layer_version','configuration','input_versions') if k in entry}
            versions[method].add(json.dumps(signature,sort_keys=True))
        a,b = p['residual_flag'],p['sustained_high_flag']
        expected = True if a is True or b is True else False if a is False and b is False else None
        assert p['hybrid_flag'] is expected
        available = [m for m in ('residual','sustained_high') if p[m+'_flag'] is not None]
        triggered = [m for m in ('residual','sustained_high') if p[m+'_flag'] is True]
        assert hybrid[mid]['available_inputs']==available and hybrid[mid]['triggered_inputs']==triggered
        assert hybrid[mid]['coverage_count']==len(available)
        p['hybrid_triggered_inputs'] = triggered
        points.append(p)
    assert len(points)==1308 and len({p['timestamp'] for p in points})==1308
    assert all(dt(b['timestamp'])-dt(a['timestamp'])==timedelta(seconds=600) for a,b in zip(points,points[1:]))
    # Cross-check every exported Stage2 flag/value, not just aggregate totals.
    by_stamp = {p['timestamp']:p for p in points}
    for row in csv.DictReader((PREV/(label+'-points.csv')).open()):
        p = by_stamp[row['timestamp']]
        assert p['energy_wh']==float(row['energy_wh']) and p['measurement_id']==row['measurement_id']
        for method in METHODS:
            expected = None if row[method+'_flag']=='' else {'True':True,'False':False}[row[method+'_flag']]
            assert p[method+'_flag'] is expected and p[method+'_status']==row[method+'_status']
    for endpoint,key in [('events','episodes'),('combined-events','combined_episodes'),('hybrid-events','hybrid_episodes')]:
        old = {x['episode_id']:x for x in report[key]}
        assert {x['episode_id'] for x in data[endpoint]}==set(old)
        for e in data[endpoint]:
            assert all(e[k]==old[e['episode_id']][k] for k in ('start_timestamp','end_timestamp','flagged_points','status','closed_reason'))
            assert dt(e['updated_at'])==dt(old[e['episode_id']]['updated_at'])
    return points,versions


def episodes_for(label,method,points,data):
    # Reconstruct consecutive true episodes; verify persisted episode identity/bounds separately.
    episodes,current = [],[]
    def finish(closure):
        if not current: return
        start,last = current[0],current[-1]
        flag = closure[method+'_flag'] if closure else None
        reason = ('below_threshold' if flag is False else 'unknown') if method in METHODS[:3] else ('negative' if flag is False else 'unknown')
        if method=='unanimous': reason = 'below_rule' if flag is False else 'unavailable'
        episodes.append(dict(scenario=label,method=method,start_timestamp=start['timestamp'],last_positive_timestamp=last['timestamp'],
            positive_points=len(current),closed_on_measurement_timestamp=closure['timestamp'] if closure else None,
            closing_flag=flag,closed_reason=reason if closure else None,status='closed' if closure else 'open',
            represented_positive_minutes=len(current)*10,positive_label_span_minutes=minutes(start['timestamp'],last['timestamp']),
            overlaps_intervention=start['timestamp']<=END and last['timestamp']>=START,
            post_return_positive_points=sum(p['timestamp']>=RETURN for p in current),
            post_return_represented_minutes=10*sum(p['timestamp']>=RETURN for p in current),
            episode_storage='derived_from_saved_flags',episode_id=None,closed_updated_at_utc=None,
            closure_wall_timestamp_within_next_measurement_transaction=None))
    for p in points:
        if p[method+'_flag'] is True: current.append(p)
        else:
            finish(p)
            current=[]
    finish(None)
    if method in METHODS[:3]: existing=[e for e in data['events'] if e['detector']==method]
    elif method=='unanimous': existing=data['combined-events']
    elif method=='hybrid': existing=data['hybrid-events']
    else: existing=None
    if existing is not None:
        stored = {(e['start_timestamp'],e['end_timestamp']):e for e in existing}
        assert len(stored)==len(episodes)
        by_stamp={p['timestamp']:i for i,p in enumerate(points)}
        for e in episodes:
            old=stored[e['start_timestamp'],e['last_positive_timestamp']]
            assert (e['positive_points'],e['status'],e['closed_reason'])==(old['flagged_points'],old['status'],old['closed_reason'])
            e.update(episode_storage='persisted',episode_id=old['episode_id'],closed_updated_at_utc=old['updated_at'] if old['status']=='closed' else None)
            if e['status']=='closed':
                index=by_stamp[e['closed_on_measurement_timestamp']]
                lower=dt(points[index]['received_at'])
                upper=dt(points[index+1]['received_at']) if index+1<len(points) else None
                valid=lower<=dt(old['updated_at']) and (upper is None or dt(old['updated_at'])<upper)
                assert valid, (method,old['episode_id'],'wall timestamp does not match closing measurement')
                e['closure_wall_timestamp_within_next_measurement_transaction']=True
    return episodes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',action='store_true')
    args=parser.parse_args()
    if args.capture: capture()
    cache=json.loads(gzip.decompress(CACHE.read_bytes()))
    streams,versions={},{}
    for label,data in cache['scenarios'].items(): streams[label],versions[label]=assemble(label,data)
    assert versions['control']==versions['plus-450'], 'Paired method configurations differ'
    assert all(len(v)==1 for v in versions['control'].values())
    control,modified=streams['control'],streams['plus-450']
    assert [(p['timestamp'],p['building_id'],p['source_id']) for p in control]==[(p['timestamp'],p['building_id'],p['source_id']) for p in modified]
    for a,b in zip(control,modified): assert b['energy_wh']-a['energy_wh']==(450 if period(a['timestamp'])=='intervention' else 0)
    all_episodes=[]
    for label,points in streams.items():
        for method in METHODS: all_episodes.extend(episodes_for(label,method,points,cache['scenarios'][label]))
    csv_file('all-episodes.csv',all_episodes)
    intersecting=[e for e in all_episodes if e['overlaps_intervention']]
    dump('intervention-episodes.json',intersecting)
    summary=[]
    for label,points in streams.items():
        for method in MAIN:
            window=[p for p in points if p['period']=='intervention']
            positives=[p for p in window if p[method+'_flag'] is True]
            ep=[e for e in intersecting if e['scenario']==label and e['method']==method]
            summary.append(dict(scenario=label,method=method,total=12,positive=len(positives),
                negative=sum(p[method+'_flag'] is False for p in window),unavailable=sum(p[method+'_flag'] is None for p in window),
                first_positive=positives[0]['timestamp'] if positives else None,
                first_delay_event_minutes=minutes(START,positives[0]['timestamp']) if positives else None,
                overlapping_episodes=len(ep),episode_bounds=[f"{e['start_timestamp']}..{e['last_positive_timestamp']}" for e in ep],
                post_return_positive_points_in_overlapping_episodes=sum(e['post_return_positive_points'] for e in ep),
                post_return_represented_minutes_in_overlapping_episodes=sum(e['post_return_represented_minutes'] for e in ep)))
    csv_file('method-summary.csv',summary);dump('method-summary.json',summary)
    hybrid_table=[]
    for a,b in zip(control,modified):
        if a['period']!='intervention': continue
        row=dict(timestamp=a['timestamp'],control_energy_wh=a['energy_wh'],modified_energy_wh=b['energy_wh'])
        for label,p in [('control',a),('modified',b)]:
            row.update({label+'_'+m:p[m+'_flag'] for m in ('residual','sustained_high','hybrid')})
            row[label+'_positive_sources']=p['hybrid_triggered_inputs']
        hybrid_table.append(row)
    csv_file('hybrid-12-points.csv',hybrid_table);dump('hybrid-12-points.json',hybrid_table)
    contribution={}
    for label,points in streams.items():
        window=[p for p in points if p['period']=='intervention']
        residual=sum(p['residual_flag'] is True for p in window)
        high_only=sum(p['sustained_high_flag'] is True and p['residual_flag'] is not True for p in window)
        both=sum(p['sustained_high_flag'] is True and p['residual_flag'] is True for p in window)
        total=sum(p['hybrid_flag'] is True for p in window)
        assert total==residual+high_only
        contribution[label]=dict(residual_including_both=residual,residual_only=residual-both,high_only=high_only,both=both,hybrid_total=total,
            residual_point_coverage_fraction=residual/12,hybrid_point_coverage_fraction=total/12,
            additional_points=total-residual,additional_coverage_percentage_points=100*(total-residual)/12,
            intervening_false_timestamps=[p['timestamp'] for p in window if p['hybrid_flag'] is False],
            unknown_timestamps=[p['timestamp'] for p in window if p['hybrid_flag'] is None])
    dump('hybrid-contribution.json',contribution)
    comparison=[]
    for phase in ('before','intervention','after'):
        pairs=[(a,b) for a,b in zip(control,modified) if a['period']==phase]
        for method in METHODS:
            af,bf=method+'_flag',method+'_flag'
            available=[(a,b) for a,b in pairs if a[af] is not None and b[bf] is not None]
            extra=[a['timestamp'] for a,b in available if a[af] is False and b[bf] is True]
            lost=[a['timestamp'] for a,b in available if a[af] is True and b[bf] is False]
            common=[a['timestamp'] for a,b in available if a[af] is True and b[bf] is True]
            transitions=Counter(f'{a[af]}->{b[bf]}' for a,b in pairs)
            comparison.append(dict(period=phase,method=method,all_points=len(pairs),paired_available=len(available),
                excluded_unavailable=len(pairs)-len(available),control_null=sum(a[af] is None for a,b in pairs),modified_null=sum(b[bf] is None for a,b in pairs),
                control_positive=sum(a[af] is True for a,b in pairs),modified_positive=sum(b[bf] is True for a,b in pairs),
                common_positive=len(common),additional_positive=len(extra),lost_positive=len(lost),
                became_unavailable=sum(a[af] is not None and b[bf] is None for a,b in pairs),became_available=sum(a[af] is None and b[bf] is not None for a,b in pairs),
                additional_timestamps=extra,lost_timestamps=lost,common_positive_timestamps=common,transitions=dict(transitions)))
    csv_file('paired-periods.csv',comparison);dump('paired-periods.json',comparison)
    post_details=[]
    for method in METHODS:
        pairs=[(a,b) for a,b in zip(control,modified) if a['period']=='after']
        extra=[a['timestamp'] for a,b in pairs if a[method+'_flag'] is False and b[method+'_flag'] is True]
        affected_episodes=[e for e in all_episodes if e['scenario']=='plus-450' and e['method']==method
                           and any(e['start_timestamp']<=stamp<=e['last_positive_timestamp'] for stamp in extra)]
        post_details.append(dict(method=method,post_period_points=108,additional_positive_timestamps=extra,
            additional_positive_points=len(extra),additional_represented_interval_minutes=len(extra)*10,
            additional_label_span_minutes=minutes(extra[0],extra[-1]) if extra else None,
            affected_episodes=affected_episodes))
    dump('post-return-signals.json',post_details)
    csv_file('post-return-signals.csv',[{k:v for k,v in x.items() if k!='affected_episodes'} for x in post_details])
    background_episodes=[]
    for phase in ('before','intervention','after'):
        for method in METHODS:
            phase_stamps={p['timestamp'] for p in control if p['period']==phase}
            # Count episodes having a positive point in this phase, not simply bounding-box overlap.
            paired={}
            for label in streams:
                paired[label]={(e['start_timestamp'],e['last_positive_timestamp']) for e in all_episodes
                    if e['scenario']==label and e['method']==method and
                    any(e['start_timestamp']<=t<=e['last_positive_timestamp'] for t in phase_stamps)}
            a,b=paired['control'],paired['plus-450']
            background_episodes.append(dict(period=phase,method=method,control_episodes=len(a),modified_episodes=len(b),
                same_bounds_episodes=len(a&b),modified_only_bounds=sorted(b-a),control_only_bounds=sorted(a-b),
                note='Bounds changes are not automatically new physical events; one episode can intersect two periods'))
    dump('paired-episode-bounds.json',background_episodes)
    shared_availability=[]
    for phase in ('before','intervention','after'):
        pairs=[(a,b) for a,b in zip(control,modified) if a['period']==phase and
               all(a[m+'_flag'] is not None and b[m+'_flag'] is not None for m in MAIN)]
        shared_availability.append(dict(period=phase,all_six_methods_paired_available_points=len(pairs),
            positive_counts={label:{m:sum(p[m+'_flag'] is True for p in [pair[i] for pair in pairs]) for m in MAIN}
                             for i,label in enumerate(('control','plus-450'))}))
    dump('common-availability.json',shared_availability)
    source_flags=[]
    for label,points in streams.items(): source_flags.extend(dict(scenario=label,**p) for p in points)
    csv_file('source-flags.csv',source_flags)
    truth=Counter(f"{p['residual_flag']},{p['sustained_high_flag']}->{p['hybrid_flag']}" for points in streams.values() for p in points)
    telemetry=[x for x in comparison if x['method'] in ('flatline','interval_gap')]
    dump('telemetry-quality.json',dict(paired_periods=telemetry,episodes=[x for x in all_episodes if x['method'] in ('flatline','interval_gap')],
                                     semantics='Separate telemetry review signals, not confirmed faults; gap observed on next received record, not silence watchdog'))
    sources={str(p.relative_to(OUT.parent.parent.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in [PREV/'plan.json',PREV/'environment.json',PREV/'control-summary.json',PREV/'plus-450-summary.json',PREV/'control-points.csv',PREV/'plus-450-points.csv']}
    ast.parse(Path(__file__).read_text())
    verification=dict(source_stage2_commit='f9d518531c2be1fd8b75c77d64a4e10ce7b43303',application_code_sha=PLAN['code_sha'],
        source_files_sha256=sources,api_cache_sha256=hashlib.sha256(CACHE.read_bytes()).hexdigest(),api_exports=cache['requests'],
        paired_by=['measurement_timestamp','building_id','source_id','method','compatible_configuration'],paired_by_internal_ids=False,
        rows_per_run=1308,stage2_csv_rows_crosschecked_per_run=300,stage2_flag_cells_crosschecked_per_run=2400,
        all_2616_hybrid_flags_availability_provenance_match_OR=True,observed_OR_truth_cases=dict(truth),
        identical_model_rule_threshold_signatures=True,signatures={m:json.loads(next(iter(v))) for m,v in versions['control'].items()},
        all_persisted_ML_Unanimous_hybrid_episodes_match_recomputed_runs=True,
        closure_evidence='Persisted updated_at and first subsequent non-true measurement; updated_at verified between that measurement received_at and the next one. Not a measured DB commit acknowledgement.',
        sustained_high_episode_storage='Only assessments persisted; high/flatline/gap episodes derived from saved flags, no invented DB episode IDs',
        phase_denominators={'before':1188,'intervention':12,'after':108},
        new_replay_inference_training_tests_screenshots=False,email_enabled=False,analysis_script_AST_syntax=True)
    dump('verification.json',verification)
    print('Analysis complete. Intervention:',json.dumps(summary,ensure_ascii=False))
    print('Contribution:',json.dumps(contribution,ensure_ascii=False))
    print('After:',json.dumps([x for x in comparison if x['period']=='after'],ensure_ascii=False))


if __name__=='__main__': main()
