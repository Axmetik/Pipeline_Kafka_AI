"""Real isolated Kafka/DB replay, unchanged scores and derived decisions parity.

Run inside the existing tools image; does not stop/reconfigure the live MVP worker.
Creates separate run/topic/group for clean and Stage 4 injected scenarios.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import numpy as np
from sqlalchemy import create_engine,select,func
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
from threadpoolctl import threadpool_limits
from integration.settings import Settings,ROOT
from integration.artifacts import load_manifest
from integration.runtime import Runtime
from integration.energy_worker import run_worker
from producer.appliances_dataset import iter_appliances,dataset_sha256
from anomaly.inject import inject
from anomaly.combined import combine


def verify(records,artifacts,kind,labels=None,injections=None,prefix=0):
    token='combined-'+kind+'-'+uuid4().hex
    settings=replace(Settings.from_env(),run_id=token,topic=token,group_id=token)
    admin=KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
    try: admin.create_topics([NewTopic(token,num_partitions=1,replication_factor=1)])
    finally: admin.close()
    producer=KafkaProducer(bootstrap_servers=settings.bootstrap_servers)
    try:
        for raw in records+[records[-1]]:
            producer.send(token,json.dumps(raw,allow_nan=False).encode(),key=json.dumps([raw['building_id'],raw['source_id']]).encode()).get(timeout=30)
    finally: producer.close(timeout=30)
    engine=create_engine(settings.database_url)
    run_worker(settings,max_messages=200,idle_timeout=10)
    from storage.postgres import schema as s
    def rows(c,table): return [dict(r) for r in c.execute(select(table).where(table.c.run_id==token)).mappings()]
    with engine.connect() as c:
        before=rows(c,s.forecasts);episodes_before=rows(c,s.combined_episodes)
    run_worker(settings,max_messages=len(records)+1-200,idle_timeout=10)
    with threadpool_limits(1):
        runtime=Runtime(artifacts);expected=[runtime.compute(raw) for raw in records]
    with engine.connect() as c:
        measured=sorted(rows(c,s.measurements),key=lambda r:r['kafka_offset'])
        forecasts=rows(c,s.forecasts);scores=rows(c,s.scores);decisions=rows(c,s.combined_decisions);events=rows(c,s.combined_episodes)
        saved={r['forecast_id']:r for r in forecasts}
        assert all(saved[r['forecast_id']]==r for r in before)
        dd={r['measurement_id']:r for r in decisions};ff={(r['measurement_id'],r['purpose']):r for r in forecasts};ss={(r['measurement_id'],r['detector']):r for r in scores}
        for m,reference in zip(measured,expected):
            mid=m['measurement_id'];derived=combine(reference['scores'])
            for key in derived: assert dd[mid][key]==derived[key],key
            for row in reference['forecasts']:
                stored=ff[mid,row['purpose']]
                for key in ('status','forecast_origin','forecast_target_timestamp'): assert stored[key]==row[key]
                np.testing.assert_allclose(stored['predicted_energy_wh'] if stored['predicted_energy_wh'] is not None else np.nan,row['predicted_energy_wh'] if row['predicted_energy_wh'] is not None else np.nan,equal_nan=True,rtol=1e-12)
            for row in reference['scores']:
                stored=ss[mid,row['detector']]
                assert stored['flag']==row['flag'] and stored['status']==row['status']
                np.testing.assert_allclose(stored['score'] if stored['score'] is not None else np.nan,row['score'] if row['score'] is not None else np.nan,equal_nan=True,rtol=1e-5,atol=1e-6)
        checkpoint=c.execute(select(s.checkpoints.c.next_offset).where(s.checkpoints.c.run_id==token)).scalar_one()
        duplicates=c.execute(select(func.count()).select_from(s.receipts).where(s.receipts.c.run_id==token,s.receipts.c.outcome=='message_duplicate')).scalar_one()
    consumer=KafkaConsumer(bootstrap_servers=settings.bootstrap_servers,group_id=token,enable_auto_commit=False)
    committed=consumer.committed(TopicPartition(token,0));consumer.close(autocommit=False)
    assert len(measured)==len(records) and len(forecasts)==2*len(records) and len(scores)==3*len(records) and len(decisions)==len(records)
    assert checkpoint==committed==len(records)+1 and duplicates==1
    assert len({e['episode_id'] for e in events})==len(events)
    from anomaly.evaluate import runs,metrics
    flags=np.array([dd[m['measurement_id']]['flag'] is True for m in measured])
    groups=runs(flags,[m['measurement_timestamp'] for m in measured])
    ordered=sorted(events,key=lambda e:e['start_timestamp'])
    assert len(groups)==len(ordered)
    for (start,end),episode in zip(groups,ordered):
        assert episode['start_timestamp']==measured[start]['measurement_timestamp']
        assert episode['end_timestamp']==measured[end]['measurement_timestamp']
        assert episode['flagged_points']==end-start+1
    extra={}
    if labels is not None:
        result,_=metrics(flags[prefix:],labels,[m['measurement_timestamp'] for m in measured[prefix:]],injections)
        extra={k:result[k] for k in ('events','matched_events','during_event_alarms','post_event_alarms','event_recall','event_f1','delay_median_minutes')}
    engine.dispose()
    return extra | {'run_id':token,'scenario':kind,'measurements':len(measured),'forecasts':len(forecasts),'original_scores':len(scores),'combined_decisions':len(decisions),
            'ready_combined':sum(d['status']=='ready' for d in decisions),'combined_flags':sum(d['flag'] is True for d in decisions),'combined_episodes':len(events),
            'episodes_before_restart':len(episodes_before),'duplicate_deliveries':duplicates,'next_offset':checkpoint,'kafka_committed':committed,
            'original_forecast_score_parity':True,'combined_offline_streaming_parity':True,'restart_forecasts_immutable':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists(): raise ValueError('Use a new output file; preserve prior verification')
    source=ROOT/'docs/energy-anomaly/results';config=json.loads((source/'protocol.json').read_text());stats=json.loads((source/'train_statistics.json').read_text())
    dataset=ROOT/'data/energy/raw/energydata_complete.csv';digest=dataset_sha256(dataset)
    if digest!=config['dataset_sha256']: raise ValueError('Dataset checksum differs')
    raw=list(iter_appliances(dataset));artifacts=load_manifest(Settings.from_env().artifact_manifest)
    first=next(i for i,r in enumerate(raw) if r['timestamp']>=config['test_start'])
    modified,labels,events,summary=inject(raw[first-144:first+500],144,config['injection'],stats,'spike',2,201)
    report={'rule':combine([])['rule_version'],'dataset_sha256':digest,'manifest_sha256':artifacts.manifest_sha256,'original_dataset_unchanged':True,
            'scenarios':[verify(raw[:300],artifacts,'clean'),verify(modified,artifacts,'spike-s2-seed201',labels,events,144)],
            'injection':{'events':events,'summary':summary,'labeled_points':int(labels.sum()),'prefix':144,'selection_uses_demo':False}}
    if dataset_sha256(dataset)!=digest: raise AssertionError('Original dataset changed')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print('COMBINED_VERIFIED '+json.dumps(report,separators=(',',':')))
if __name__=='__main__': main()
