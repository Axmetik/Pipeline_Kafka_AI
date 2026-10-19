"""Read-only HTTP verification against an existing replay (no fitting or writes)."""
import argparse
from datetime import datetime,timedelta
import json
from pathlib import Path
from urllib.parse import urlencode,urlparse
from urllib.request import urlopen


def verify(base_url,run_id,minimum_measurements=300):
    url=urlparse(base_url)
    if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.username or url.password:
        raise ValueError('Use a local HTTP API URL without credentials')
    def get(path,**params):
        with urlopen(base_url.rstrip('/')+path+'?'+urlencode(params),timeout=15) as r: return json.load(r)
    def rows(resource,**params):
        result=[]
        params={'run_id':run_id,'limit':127,**params}
        while True:
            value=get('/api/'+resource,**params)
            result.extend(value['items'])
            if not value['next_cursor']: return result
            params['cursor']=value['next_cursor']
    assert get('/health/live')['status']=='live'
    assert get('/health/ready')['status']=='ready'
    before=get('/api/pipeline-status',run_id=run_id)
    measurements=rows('measurements');forecasts=rows('forecasts');scores=rows('anomaly-scores');events=rows('events')
    assert len(measurements)>=minimum_measurements
    assert len({r['measurement_id'] for r in measurements})==len(measurements)
    by_id={r['measurement_id']:r for r in measurements}
    for f in forecasts:
        assert f['forecast_origin']==by_id[f['measurement_id']]['measurement_timestamp']
        assert datetime.fromisoformat(f['forecast_target_timestamp'])-datetime.fromisoformat(f['forecast_origin'])==timedelta(seconds=f['horizon_seconds'])
    for row in scores:
        assert row['maturity']=='experimental' and row['score_semantics']=='detector_score_not_probability'
        if row['status']=='warmup': assert row['score'] is None and row['flag'] is None
        if row['detector']=='residual' and row['status']=='ready':
            assert row['forecast_target_timestamp']==by_id[row['measurement_id']]['measurement_timestamp']
    assert {r['detector'] for r in scores}=={'isolation_forest','autoencoder','residual'}
    assert all(e['maturity']=='experimental' for e in events)
    after=get('/api/pipeline-status',run_id=run_id)
    assert before==after,'Run must be idle during verification'
    return {'run_id':run_id,'measurements':len(measurements),'forecasts':len(forecasts),'anomaly_scores':len(scores),
        'events':len(events),'status_unchanged':before==after,'pipeline_status':after,
        'latest_measurement':measurements[0],
        'warmup_forecast':next((f for f in forecasts if f['status']=='warmup'),None),
        'warmup_score':next((s for s in scores if s['status']=='warmup'),None),
        'hourly_example':get('/api/measurements/aggregate',run_id=run_id,limit=1)['items'],
        'runs':rows('runs'),'sources':rows('sources'),'models':rows('models')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--minimum-measurements',type=int,default=300)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=verify(args.base_url,args.run_id,args.minimum_measurements)
    if args.output: args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:result[k] for k in ['run_id','measurements','forecasts','anomaly_scores','events','status_unchanged']}))


if __name__=='__main__': main()
