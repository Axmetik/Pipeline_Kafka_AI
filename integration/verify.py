"""Full-artifact Stage 5A demonstration with restart and duplicate deliveries."""
import argparse
from dataclasses import replace
import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import numpy as np
from sqlalchemy import create_engine,select,func,text
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
from threadpoolctl import threadpool_limits
from producer.appliances_dataset import iter_appliances,dataset_sha256
from integration.settings import Settings
from integration.artifacts import load_manifest
from integration.energy_worker import run_worker
from integration.runtime import Runtime
from storage.postgres import schema as s


def verify(dataset,output,count=300):
    if count<300:
        raise ValueError('Verification requires at least 300 original measurements')
    output=Path(output)
    if output.exists():
        raise ValueError('Verification output already exists')
    base=Settings.from_env();artifacts=load_manifest(base.artifact_manifest)
    token=uuid4().hex
    settings=replace(base,run_id='verification-'+token,group_id='mvp-verification-'+token,topic='mvp-verification-'+token)
    records=list(iter_appliances(dataset,limit=count))
    if len(records)!=count: raise ValueError('Dataset shorter than requested verification')
    duplicates=[records[25],records[100]]
    admin=KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
    admin.create_topics([NewTopic(settings.topic,num_partitions=1,replication_factor=1)]);admin.close()
    producer=KafkaProducer(bootstrap_servers=settings.bootstrap_servers)
    try:
        for row in records+duplicates:
            producer.send(settings.topic,json.dumps(row,allow_nan=False).encode(),key=json.dumps([row['building_id'],row['source_id']]).encode()).get(timeout=30)
    finally: producer.close(timeout=30)
    engine=create_engine(settings.database_url)
    first=run_worker(settings,max_messages=150,idle_timeout=5)
    with engine.connect() as c:
        before=list(c.execute(select(s.forecasts).where(s.forecasts.c.run_id==settings.run_id)).mappings())
    second=run_worker(settings,max_messages=count+2-150,idle_timeout=5)
    with threadpool_limits(1):
        reference=Runtime(artifacts)
        expected=[reference.compute(row) for row in records]
    with engine.connect() as c:
        saved=list(c.execute(select(s.measurements).where(s.measurements.c.run_id==settings.run_id).order_by(s.measurements.c.kafka_offset)).mappings())
        assert len(saved)==count and all(row['measurement_time_utc'] is None and row['time_basis']=='dataset_naive' for row in saved)
        forecast_rows=list(c.execute(select(s.forecasts).where(s.forecasts.c.run_id==settings.run_id)).mappings())
        score_rows=list(c.execute(select(s.scores).where(s.scores.c.run_id==settings.run_id)).mappings())
        forecasts={(r['measurement_id'],r['purpose']):r for r in forecast_rows}
        scores={(r['measurement_id'],r['detector']):r for r in score_rows}
        for row in before:
            after=next(r for r in forecast_rows if r['forecast_id']==row['forecast_id'])
            assert dict(after)==dict(row)
        for row,computed in zip(saved,expected):
            for f in computed['forecasts']:
                stored=forecasts[(row['measurement_id'],f['purpose'])]
                assert stored['status']==f['status']
                assert stored['forecast_origin']==f['forecast_origin'] and stored['forecast_target_timestamp']==f['forecast_target_timestamp']
                if f['predicted_energy_wh'] is None: assert stored['predicted_energy_wh'] is None
                else: np.testing.assert_allclose(stored['predicted_energy_wh'],f['predicted_energy_wh'],rtol=1e-12,atol=1e-12)
            for score in computed['scores']:
                stored=scores[(row['measurement_id'],score['detector'])]
                assert stored['flag']==score['flag'] and stored['status']==score['status']
                assert stored['maturity']=='experimental'
                if score['score'] is None: assert stored['score'] is None
                else: np.testing.assert_allclose(stored['score'],score['score'],rtol=1e-5,atol=1e-6)
        checkpoint=c.execute(select(s.checkpoints.c.next_offset).where(s.checkpoints.c.group_id==settings.group_id)).scalar_one()
        receipts=c.execute(select(func.count()).select_from(s.receipts).where(s.receipts.c.run_id==settings.run_id)).scalar_one()
        events=c.execute(select(func.count()).select_from(s.episodes).where(s.episodes.c.run_id==settings.run_id)).scalar_one()
        database_version=c.execute(text('SHOW server_version')).scalar_one()
    consumer=KafkaConsumer(bootstrap_servers=settings.bootstrap_servers,group_id=settings.group_id,enable_auto_commit=False)
    committed=consumer.committed(TopicPartition(settings.topic,0));consumer.close(autocommit=False)
    assert checkpoint==committed==count+2 and receipts==count+2
    assert len(forecasts)==2*count and len(scores)==3*count
    report={'implementation_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('integration').glob('*.py'))},
            'run_id':settings.run_id,'topic':settings.topic,'postgres_version':database_version,
            'dataset_sha256':dataset_sha256(dataset),'manifest_sha256':artifacts.manifest_sha256,
            'unique_measurements':count,'forecasts':len(forecasts),'anomaly_score_rows':len(scores),
            'duplicate_deliveries':second['message_duplicate'],'delivery_receipts':receipts,
            'db_next_offset':checkpoint,'kafka_committed_offset':committed,
            'experimental_episodes':events,'restart_reconciled_journal_records':second['verified_journal_records'],
            'previous_forecasts_and_generated_times_preserved':True,'offline_inference_matches':True,
            'naive_dataset_time_preserved':True,
            'ready_scores':{name:sum(r['detector']==name and r['status']=='ready' for r in score_rows)
                            for name in ('isolation_forest','autoencoder','residual')},
            'model_registry':[{k:r[k] for k in ('role','model_version','feature_version','threshold_version','maturity')} for r in artifacts.registry()]}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    engine.dispose()
    # Keep this demonstration run/topic for inspection; only tests delete their owned topics.
    print(json.dumps(report,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();verify(args.dataset,args.output)


if __name__=='__main__': main()
