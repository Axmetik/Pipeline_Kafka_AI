"""Validate compact saved Stage8B evidence; optional local hashes, no ML loading."""
import argparse,hashlib,json
from pathlib import Path


def verify(directory,check_local=False):
    d=Path(directory);load=lambda name:json.loads((d/name).read_text())
    v=load('verification.json');r=load('runtime-verification.json');a=load('api-verification.json');b=load('browser-verification.json');e=load('email-delivery-verification.json');i=load('image-artifact-verification.json');o=load('operational-final.json')
    assert v['decision']=='GO' and v['runtime_source_commit']==i['source_commit']=='51e4b94635ec775a6ab2111b894b8cc8034fd45b'
    assert v['run_id']==r['run_id']==a['run_id']==b['run_id']==v['topic']==v['group_id']
    assert e['run_id']!=v['run_id'] and e['project']!=v['project']
    counts=r['counts']
    for name,expected in [('measurements',300),('forecasts',600),('scores',900),('combined_decisions',300),('receipts',300),('errors',0),('notifications',0)]:assert counts[name]==expected
    assert a['counts']['measurements']==counts['measurements'] and a['counts']['forecasts']==counts['forecasts'] and a['counts']['anomaly-scores']==counts['scores']
    assert sum(s['ready'] for s in r['forecast_states'])==451 and sum(s['null_values'] for s in r['forecast_states'])==149
    assert sum(s['ready'] for s in r['score_states'])==744 and sum(s['null_values'] for s in r['score_states'])==156
    assert r['combined_states']=={'warmup':144,'ready':156} and r['combined_flags']==0
    assert r['kafka']['begin_offset']==0 and r['kafka']['end_offset']==r['kafka']['committed_offset']==r['kafka']['journal_payloads_verified']==300
    assert all(r['checks'].values()) and b['console_errors']==[] and b['reload_preserved_count'] and b['observed_intermediate_live_update']
    assert b['counts_observed'][-1]['count']==300 and len(b['counts_observed'])==23
    assert len(e['notifications'])==len(e['mailpit_messages'])==e['observed_message_total']==1
    assert e['notifications'][0]['status']=='sent' and e['notifications'][0]['attempt_count']==1
    assert e['duplicate_event_and_notifier_restart_checked'] and not e['real_smtp']
    assert {'multipart/alternative','text/html','text/plain'}<=set(e['mime_parts'])
    assert i['all_runtime_files_match_checkout'] and i['runtime_file_count']==89 and i['graphite_tokens_present']
    assert o['all_artifacts_and_dataset_unchanged'] and o['all_preexisting_volumes_preserved'] and o['published_ports_localhost_only'] and o['worker_cannot_connect_api_8000']
    before=load('history-before.json');after=load('history-after.json')
    assert before['revision']==after['revision']=='0003_email'
    for table,rows in before['tables'].items():
        current={x['run_id']:x for x in after['tables'][table]}
        assert all(current[row['run_id']]==row for row in rows)
    ci=load('base-ci-evidence.json');assert len(ci['checks'])==6 and all(c['conclusion']=='success' for c in ci['checks'])
    for screenshot in load('screenshots/manifest.json')['screenshots']:
        p=d/screenshot['path'];assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==screenshot['sha256']
        assert screenshot['run_id'] in (v['run_id'],e['run_id'])
        assert screenshot['category'] in ('real_pipeline','synthetic_delivery_test')
    for rel,h in load('checksums.json').items():assert hashlib.sha256((d/rel).read_bytes()).hexdigest()==h,rel
    if check_local:
        root=d.resolve().parents[1]
        for rel,h in v['protected_files_sha256'].items():
            p=root/rel
            assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==h,rel
    return {'decision':v['decision'],'saved_evidence_valid':True,'local_hashes_verified':check_local,'run_id':v['run_id']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-local',action='store_true');a=p.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parent,a.check_local),indent=2))
