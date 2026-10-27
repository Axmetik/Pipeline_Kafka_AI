"""Local-only delivery proof, separate from real-model replay. Never uses real SMTP."""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from uuid import uuid4
from sqlalchemy import create_engine,select,func,text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from integration.settings import Settings,ROOT
from storage.postgres import schema as s
from storage.postgres.repository import Repository,identity
from notifications.config import EmailConfig


def local_config():
    cfg=EmailConfig.from_env()
    if not cfg.enabled or cfg.host not in ('mailpit','127.0.0.1','localhost') or cfg.real_delivery or not cfg.recipient.endswith('@example.test'):
        raise ValueError('Demo requires enabled local Mailpit, real delivery disabled and @example.test recipient')
    return cfg


def synthetic(settings,cfg):
    if not cfg.run_id.startswith('email-delivery-test-'): raise ValueError('Use an isolated email-delivery-test-* run')
    if cfg.mode not in ('individual','both'): raise ValueError('Synthetic delivery demo requires individual or both mode')
    repo=Repository(create_engine(settings.database_url),settings)
    try:
        row={'schema_version':'1.0','event_id':'delivery-test-001','building_id':cfg.building_id,'source_id':cfg.source_id,
            'source_type':'dataset','timestamp':'2016-05-26T14:00:00','timezone':None,'timestamp_reference':'dataset_label',
            'interval_seconds':600,'energy':{'value':380.,'unit':'Wh','scope':'appliances','measurement_type':'interval_energy'},
            'environment':{},'additional_parameters':{'delivery_test':True}}
        model='email-delivery-test-fixture'
        with repo.engine.begin() as c:
            c.execute(pg_insert(s.runs).values(run_id=settings.run_id,group_id=settings.group_id,topic=settings.topic,
                cluster_id='synthetic-delivery-no-kafka',manifest_sha256='0'*64,config={'delivery_test':True}).on_conflict_do_nothing())
            c.execute(pg_insert(s.models).values(model_id=model,artifact_sha256='0'*64,role=model,model_version=model,
                feature_version='delivery-test',threshold_version='delivery-test',maturity='experimental',details={'delivery_test':True}).on_conflict_do_nothing())
            if not repo.existing_event(c,row):
                problem=repo.source_problem(c,row)
                if problem: raise ValueError('Demo source conflict')
                mid=repo.persist(c,0,row,row,identity(row),dict(compatible=False,feature_status='incompatible',gap_detected=False,forecasts=[],scores=[]))
                repo.update_episode(c,mid,row,dict(detector='isolation_forest',model_id=model,model_version=model,
                    feature_version='delivery-test',threshold_version='delivery-test',score=2.,threshold=1.,flag=True),False)
                # Explicit test marker in the same transaction as the synthetic episode.
                notification=c.execute(select(s.notifications).where(s.notifications.c.run_id==cfg.run_id)).mappings().one()
                c.execute(s.notifications.update().where(s.notifications.c.notification_id==notification['notification_id']).values(payload={**notification['payload'],'delivery_test':True}))
        return repo.engine
    except Exception:
        repo.engine.dispose();raise


def deliver_and_report(engine,cfg,mailpit_url):
    # Fresh processes prove persisted pending state and no resend after a restart.
    for _ in range(100):
        subprocess.run([sys.executable,'-m','notifications.notifier','--once'],check=True,cwd=ROOT)
        with engine.connect() as c:
            due=c.execute(select(func.count()).select_from(s.notifications).where(s.notifications.c.run_id==cfg.run_id,
                s.notifications.c.status.in_(['pending','retrying']),s.notifications.c.next_retry_at<=func.now())).scalar_one()
        if not due: break
    subprocess.run([sys.executable,'-m','notifications.notifier','--once'],check=True,cwd=ROOT)
    with engine.connect() as c:
        rows=[dict(r) for r in c.execute(select(s.notifications.c.notification_id,s.notifications.c.status,s.notifications.c.attempt_count,
            s.notifications.c.suppression_reason).where(s.notifications.c.run_id==cfg.run_id)).mappings()]
        individual=c.execute(select(func.count()).select_from(s.episodes).where(s.episodes.c.run_id==cfg.run_id)).scalar_one()
        combined=c.execute(select(func.count()).select_from(s.combined_episodes).where(s.combined_episodes.c.run_id==cfg.run_id)).scalar_one()
    # Only local Mailpit URLs are accepted; no external delivery/readback endpoint.
    if not mailpit_url.startswith(('http://mailpit:8025','http://127.0.0.1:','http://localhost:')): raise ValueError('Local Mailpit URL required')
    with urllib.request.urlopen(mailpit_url+'/api/v1/messages',timeout=10) as response: messages=json.load(response)
    matching=[]
    for item in messages['messages']:
        with urllib.request.urlopen(mailpit_url+'/api/v1/message/'+item['ID'],timeout=10) as response: msg=json.load(response)
        if cfg.run_id in msg.get('Text',''):
            matching.append({'id':item['ID'],'html':bool(msg.get('HTML')),'plain_text':bool(msg.get('Text'))})
    result={'run_id':cfg.run_id,'mode':cfg.mode,'individual_episodes':individual,'combined_episodes':combined,
        'notifications':rows,'mailpit_messages':matching,'models_or_thresholds_modified':False}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('scenario',choices=['synthetic','replay'])
    p.add_argument('--mailpit-url',default='http://mailpit:8025');p.add_argument('--output',type=Path);a=p.parse_args()
    cfg=local_config();settings=Settings.from_env()
    if settings.run_id!=cfg.run_id: raise ValueError('MVP_RUN_ID must match EMAIL_RUN_ID')
    if a.scenario=='synthetic':
        engine=synthetic(settings,cfg)
        # Repeat event creation as well as notifier invocation.
        another=synthetic(settings,cfg);another.dispose()
    else:
        if not cfg.run_id.startswith('email-ml-'): raise ValueError('Use an isolated email-ml-* run')
        from producer.appliances_dataset import iter_appliances
        from kafka import KafkaProducer
        from kafka.admin import KafkaAdminClient,NewTopic
        from integration.energy_worker import run_worker
        dataset=ROOT/'data/energy/raw/energydata_complete.csv'
        before=hashlib.sha256(dataset.read_bytes()).hexdigest()
        admin=KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
        try:
            if settings.topic in admin.list_topics(): raise ValueError('Use a fresh demo topic/run/group')
            admin.create_topics([NewTopic(settings.topic,1,1)])
        finally: admin.close()
        producer=KafkaProducer(bootstrap_servers=settings.bootstrap_servers)
        try:
            for row in iter_appliances(dataset,cfg.building_id,cfg.source_id,start='2016-04-30T07:20:00',limit=300):
                producer.send(settings.topic,json.dumps(row).encode(),key=json.dumps([row['building_id'],row['source_id']]).encode()).get(timeout=30)
        finally: producer.close(timeout=30)
        worker=run_worker(settings,max_messages=300,idle_timeout=5)
        if worker['accepted']!=300: raise ValueError('Incomplete real-model replay')
        if hashlib.sha256(dataset.read_bytes()).hexdigest()!=before: raise ValueError('Dataset changed')
        engine=create_engine(settings.database_url)
    try:
        report=deliver_and_report(engine,cfg,a.mailpit_url)
        if a.scenario=='synthetic':
            if len(report['notifications'])!=1 or report['notifications'][0]['status']!='sent' or len(report['mailpit_messages'])!=1 or not all(report['mailpit_messages'][0][x] for x in ('html','plain_text')):
                raise ValueError('Delivery proof failed')
        else:
            with engine.connect() as c:
                report['counts']={name:c.execute(select(func.count()).select_from(table).where(table.c.run_id==cfg.run_id)).scalar_one()
                    for name,table in [('measurements',s.measurements),('forecasts',s.forecasts),('scores',s.scores)]}
            report['worker']=worker
        if a.output:
            a.output.parent.mkdir(exist_ok=True,parents=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally: engine.dispose()

if __name__=='__main__': main()
