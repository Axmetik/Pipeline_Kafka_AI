"""Real PostgreSQL plus actual Kafka, isolated schemas/topics for every test."""
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import uuid4

import numpy as np
from sqlalchemy import create_engine,select,func,text,delete,update
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
from kafka.structs import OffsetAndMetadata
from threadpoolctl import threadpool_limits
from integration.settings import Settings,ROOT
from integration.artifacts import load_manifest,ArtifactError
from integration.runtime import Runtime,RecoveryError
from integration.processor import Processor
from integration.energy_worker import run_worker
from integration.checkpoints import CheckpointError
from storage.postgres.repository import Repository,RepositoryError
from storage.postgres import schema as s
from mvp_helpers import artifact_fixture


@unittest.skipUnless(os.getenv('RUN_MVP_INTEGRATION')=='1','Select --suite mvp with real PostgreSQL and Kafka')
class MVPIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.threads=threadpool_limits(1)
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.records,cls.manifest,cls.artifacts=artifact_fixture(cls.root/'ordinary')
        _,cls.open_manifest,cls.open_artifacts=artifact_fixture(cls.root/'open',always_flag=True)
        cls.base=Settings.from_env()
        cls.base_engine=create_engine(os.getenv('MVP_TEST_DATABASE_URL',cls.base.database_url))

    @classmethod
    def tearDownClass(cls):
        cls.base_engine.dispose();cls.temp.cleanup();cls.threads.restore_original_limits()

    def setUp(self):
        self.namespace='mvp_test_'+uuid4().hex
        with self.base_engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{self.namespace}"'))
        url=make_url(os.getenv('MVP_TEST_DATABASE_URL',self.base.database_url)).update_query_dict({'options':'-csearch_path='+self.namespace})
        self.settings=replace(self.base,database_url=url.render_as_string(hide_password=False),
                              run_id=uuid4().hex,group_id='mvp-test-'+uuid4().hex,topic='mvp-test-'+uuid4().hex,
                              artifact_manifest=self.manifest)
        self.engine=create_engine(self.settings.database_url)
        self.alembic=Config(str(ROOT/'alembic.ini'))
        with self.engine.begin() as c:
            self.alembic.attributes['connection']=c;command.upgrade(self.alembic,'head')
        self.topics=[]

    def tearDown(self):
        self.engine.dispose()
        if self.topics:
            admin=KafkaAdminClient(bootstrap_servers=self.base.bootstrap_servers)
            admin.delete_topics(self.topics);admin.close()
        with self.base_engine.begin() as c:
            c.execute(text(f'DROP SCHEMA "{self.namespace}" CASCADE'))

    def repo(self,artifacts=None):
        repo=Repository(self.engine,self.settings);repo.initialize(artifacts or self.artifacts,'test-cluster');repo.create_checkpoint()
        return repo

    def send_direct(self,processor,index,record=None):
        row=record or self.records[index]
        key=json.dumps([row['building_id'],row['source_id']]).encode()
        return processor.process(index,key,json.dumps(row,allow_nan=False).encode())

    def count(self,table):
        with self.engine.connect() as c:
            return c.execute(select(func.count()).select_from(table)).scalar_one()

    def publish(self,records):
        admin=KafkaAdminClient(bootstrap_servers=self.base.bootstrap_servers)
        admin.create_topics([NewTopic(self.settings.topic,num_partitions=1,replication_factor=1)]);admin.close()
        self.topics.append(self.settings.topic)
        producer=KafkaProducer(bootstrap_servers=self.base.bootstrap_servers)
        try:
            for row in records:
                producer.send(self.settings.topic,json.dumps(row).encode(),key=json.dumps([row['building_id'],row['source_id']]).encode()).get(timeout=30)
        finally:
            producer.close(timeout=30)

    def kafka_committed(self):
        consumer=KafkaConsumer(bootstrap_servers=self.base.bootstrap_servers,group_id=self.settings.group_id,enable_auto_commit=False)
        try:
            return consumer.committed(TopicPartition(self.settings.topic,0))
        finally:
            consumer.close(autocommit=False)

    def test_migrations_match_metadata_and_roundtrip(self):
        with self.engine.connect() as c:
            differences=compare_metadata(MigrationContext.configure(c),s.metadata)
            self.assertEqual(differences,[])
        with self.engine.begin() as c:
            self.alembic.attributes['connection']=c;command.downgrade(self.alembic,'base');command.upgrade(self.alembic,'head')
        self.assertEqual(self.count(s.measurements),0)

    def test_duplicate_delivery_event_conflict_and_history_parity(self):
        repo=self.repo();processor=Processor(repo,self.artifacts)
        for i in range(150): self.send_direct(processor,i)
        self.assertEqual(self.send_direct(processor,100)['outcome'],'offset_duplicate')
        self.assertEqual(self.send_direct(processor,150,self.records[100])['outcome'],'message_duplicate')
        conflict=copy.deepcopy(self.records[100]);conflict['energy']['value']+=10
        self.assertEqual(self.send_direct(processor,151,conflict)['outcome'],'event_conflict')
        self.send_direct(processor,152,self.records[150])
        self.assertEqual(self.count(s.measurements),151);self.assertEqual(self.count(s.forecasts),302)
        self.assertEqual(self.count(s.scores),453);self.assertEqual(self.count(s.receipts),153);self.assertEqual(self.count(s.errors),1)
        expected=Runtime(self.artifacts)
        for row in self.records[:151]: latest=expected.compute(row)
        with self.engine.connect() as c:
            mid=c.execute(select(s.measurements.c.measurement_id).where(s.measurements.c.event_id==self.records[150]['event_id'])).scalar_one()
            saved=c.execute(select(s.scores).where(s.scores.c.measurement_id==mid,s.scores.c.detector=='residual')).mappings().one()
        self.assertEqual(saved['prediction_wh'],latest['scores'][2]['prediction_wh'])
        self.assertEqual(repo.checkpoint()['next_offset'],153)

    def test_failure_before_commit_rolls_back_and_requires_recovery(self):
        repo=self.repo();processor=Processor(repo,self.artifacts)
        for i in range(40): self.send_direct(processor,i)
        def crash(stage):
            if stage=='before_db_commit': raise RuntimeError('test crash before commit')
        processor.failpoint=crash
        with self.assertRaisesRegex(RuntimeError,'test crash'): self.send_direct(processor,40)
        self.assertEqual(self.count(s.measurements),40);self.assertEqual(repo.checkpoint()['next_offset'],40)
        with self.assertRaisesRegex(RepositoryError,'restart/recover'): self.send_direct(processor,40)
        recovered=Processor(repo,self.artifacts)
        for i in range(40,150): self.send_direct(recovered,i)
        self.assertEqual(self.count(s.measurements),150)
        with self.engine.connect() as c:
            rows=c.execute(select(s.scores).where(s.scores.c.detector=='residual').order_by(s.scores.c.measurement_id)).mappings().all()
        self.assertEqual(sum(r['status']=='ready' for r in rows),6)

    def test_after_commit_restart_preserves_forecasts_and_open_episodes(self):
        repo=self.repo(self.open_artifacts);processor=Processor(repo,self.open_artifacts)
        for i in range(150): self.send_direct(processor,i)
        with self.engine.connect() as c:
            old_forecasts=list(c.execute(select(s.forecasts).order_by(s.forecasts.c.forecast_id)).mappings())
            old_episodes={r['detector']:dict(r) for r in c.execute(select(s.episodes).where(s.episodes.c.status=='open')).mappings()}
        self.assertEqual(set(old_episodes),{'isolation_forest','autoencoder','residual'})
        def crash(stage):
            if stage=='after_db_commit': raise RuntimeError('test crash after commit')
        processor.failpoint=crash
        with self.assertRaisesRegex(RuntimeError,'test crash'): self.send_direct(processor,150)
        self.assertEqual(repo.checkpoint()['next_offset'],151)
        recovered=Processor(repo,self.open_artifacts)
        self.send_direct(recovered,151)
        with self.engine.connect() as c:
            for old in old_forecasts:
                saved=c.execute(select(s.forecasts).where(s.forecasts.c.forecast_id==old['forecast_id'])).mappings().one()
                self.assertEqual(dict(saved),dict(old))
            for old in old_episodes.values():
                saved=c.execute(select(s.episodes).where(s.episodes.c.episode_id==old['episode_id'])).mappings().one()
                self.assertEqual(saved['status'],'open');self.assertEqual(saved['flagged_points'],old['flagged_points']+2)
            mid=c.execute(select(s.measurements.c.measurement_id).where(s.measurements.c.event_id==self.records[151]['event_id'])).scalar_one()
            score=c.execute(select(s.scores).where(s.scores.c.measurement_id==mid,s.scores.c.detector=='residual')).mappings().one()
            reference=c.execute(select(s.forecasts).where(s.forecasts.c.forecast_id==score['reference_forecast_id'])).mappings().one()
            self.assertEqual(reference['generated_at'],score['reference_generated_at'])
        self.assertEqual(self.count(s.episodes),3)

    def test_gap_closes_episode_and_incompatible_source_stores_null_scores(self):
        repo=self.repo(self.open_artifacts);processor=Processor(repo,self.open_artifacts)
        for i in range(20): self.send_direct(processor,i)
        self.send_direct(processor,20,self.records[21])
        unknown=copy.deepcopy(self.records[22]);unknown['source_id']='other';unknown['timestamp']='2016-01-01T03:40:00+00:00';unknown['timezone']='UTC'
        self.send_direct(processor,21,unknown)
        with self.engine.connect() as c:
            closed=c.execute(select(s.episodes).where(s.episodes.c.status=='closed')).mappings().all()
            self.assertTrue(closed);self.assertTrue(all(r['closed_reason']=='gap' for r in closed))
            m=c.execute(select(s.measurements).where(s.measurements.c.source_id=='other')).mappings().one()
            self.assertEqual(m['feature_status'],'incompatible');self.assertEqual(m['measurement_time_utc'].hour,3)
            self.assertTrue(all(r['score'] is None and r['flag'] is None for r in c.execute(select(s.scores).where(s.scores.c.measurement_id==m['measurement_id'])).mappings()))
            naive=c.execute(select(s.measurements).where(s.measurements.c.source_id=='meter').limit(1)).mappings().one()
            self.assertIsNone(naive['measurement_time_utc']);self.assertIsNone(naive['measurement_time_local'].tzinfo)

    def test_model_context_change_missing_checkpoint_and_exclusive_ownership(self):
        repo=self.repo();processor=Processor(repo,self.artifacts);self.send_direct(processor,0)
        with self.assertRaisesRegex(RepositoryError,'artifact context changed'):
            repo.initialize(self.open_artifacts,'test-cluster')
        with repo.worker_lock():
            other=Repository(self.engine,self.settings)
            with self.assertRaisesRegex(RepositoryError,'Another worker'):
                with other.worker_lock(): pass
        with self.engine.begin() as c: c.execute(delete(s.checkpoints))
        with self.assertRaisesRegex(RepositoryError,'ledger exists without checkpoint'): repo.create_checkpoint()

    def test_kafka_hard_process_crashes_before_after_commit_and_recovery(self):
        import sys
        self.publish(self.records[:170])
        child = """
import os
from integration.settings import Settings
from integration.energy_worker import run_worker
counter=0
stage_to_crash=os.environ['MVP_TEST_CRASH_STAGE']
def crash(stage):
    global counter
    if stage==stage_to_crash:
        counter+=1
        if counter==int(os.environ['MVP_TEST_CRASH_AT']):
            os._exit(91)
run_worker(Settings.from_env(),max_messages=170,idle_timeout=5,failpoint=crash)
"""
        environment={**os.environ,'MVP_DATABASE_URL':self.settings.database_url,
                     'MVP_ARTIFACT_MANIFEST':str(self.settings.artifact_manifest),
                     'MVP_RUN_ID':self.settings.run_id,'MVP_GROUP_ID':self.settings.group_id,
                     'MVP_TOPIC':self.settings.topic,'MVP_BOOTSTRAP_SERVERS':self.settings.bootstrap_servers,
                     'OMP_NUM_THREADS':'1'}
        for stage,count in [('before_db_commit',1),('after_db_commit',150)]:
            result=subprocess.run([sys.executable,'-c',child],cwd=ROOT,
                                  env=environment|{'MVP_TEST_CRASH_STAGE':stage,'MVP_TEST_CRASH_AT':str(count)},
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
            self.assertEqual(result.returncode,91,result.stdout.decode())
            if stage=='before_db_commit':
                self.assertEqual(self.count(s.measurements),0);self.assertEqual(self.kafka_committed(),0)
            else:
                self.assertEqual(self.count(s.measurements),150);self.assertEqual(self.kafka_committed(),149)
        report=run_worker(self.settings,max_messages=20,idle_timeout=5)
        self.assertEqual(report['db_next_offset'],170);self.assertEqual(self.kafka_committed(),170)
        self.assertEqual(self.count(s.measurements),170);self.assertEqual(self.count(s.forecasts),340);self.assertEqual(self.count(s.scores),510)
        self.assertEqual(report['verified_journal_records'],150)

    def test_kafka_ahead_checkpoint_missing_or_outside_log_are_rejected(self):
        self.publish(self.records[:3])
        run_worker(self.settings,max_messages=1,idle_timeout=5)
        consumer=KafkaConsumer(bootstrap_servers=self.base.bootstrap_servers,group_id=self.settings.group_id,enable_auto_commit=False)
        tp=TopicPartition(self.settings.topic,0)
        consumer.assign([tp]);consumer.commit({tp:OffsetAndMetadata(2,'test',-1)});consumer.close(autocommit=False)
        with self.assertRaisesRegex(CheckpointError,'ahead of DB'):
            run_worker(self.settings,max_messages=1,idle_timeout=5)
        with self.engine.begin() as c: c.execute(update(s.checkpoints).values(next_offset=100))
        with self.assertRaisesRegex(CheckpointError,'outside available'):
            run_worker(self.settings,max_messages=1,idle_timeout=5)
        with self.engine.begin() as c: c.execute(delete(s.checkpoints))
        with self.assertRaisesRegex(CheckpointError,'without a DB checkpoint'):
            run_worker(self.settings,max_messages=1,idle_timeout=5)

    def test_full_retained_log_validation_detects_changed_earlier_ledger(self):
        self.publish(self.records[:3])
        run_worker(self.settings,max_messages=2,idle_timeout=5)
        with self.engine.begin() as c:
            c.execute(update(s.receipts).where(s.receipts.c.offset==0).values(payload_sha256='0'*64))
        with self.assertRaisesRegex(CheckpointError,'journal differs'):
            run_worker(self.settings,max_messages=1,idle_timeout=5)
        self.assertEqual(self.count(s.measurements),2)
        self.assertEqual(self.kafka_committed(),2)

    def test_recreated_topic_changed_prefix_rejected_even_when_anchor_matches(self):
        import time
        self.publish(self.records[:3])
        run_worker(self.settings,max_messages=2,idle_timeout=5)
        admin=KafkaAdminClient(bootstrap_servers=self.base.bootstrap_servers)
        try:
            admin.delete_topics([self.settings.topic])
            deadline=time.monotonic()+30
            while self.settings.topic in admin.list_topics():
                if time.monotonic()>deadline: self.fail('Test topic deletion did not finish')
                time.sleep(.2)
            admin.create_topics([NewTopic(self.settings.topic,num_partitions=1,replication_factor=1)])
        finally:
            admin.close()
        changed=copy.deepcopy(self.records[:3]);changed[0]['energy']['value']+=77
        producer=KafkaProducer(bootstrap_servers=self.base.bootstrap_servers)
        try:
            for row in changed:
                producer.send(self.settings.topic,json.dumps(row).encode(),key=json.dumps([row['building_id'],row['source_id']]).encode()).get(timeout=30)
        finally: producer.close(timeout=30)
        with self.assertRaisesRegex(CheckpointError,'journal differs'):
            run_worker(self.settings,max_messages=1,idle_timeout=5)
        self.assertEqual(self.count(s.measurements),2)

    def test_committed_history_fingerprint_and_checkpoint_digest_are_verified(self):
        self.publish(self.records[:3])
        run_worker(self.settings,max_messages=2,idle_timeout=5)
        with self.engine.begin() as c:
            old=c.execute(select(s.checkpoints.c.last_payload_sha256)).scalar_one()
            c.execute(update(s.checkpoints).values(last_payload_sha256='0'*64))
        with self.assertRaisesRegex(CheckpointError,'checkpoint digest'):
            run_worker(self.settings,max_messages=1,idle_timeout=5)
        with self.engine.begin() as c:
            c.execute(update(s.checkpoints).values(last_payload_sha256=old))
            corrupted=copy.deepcopy(self.records[1]);corrupted['energy']['value']+=99
            c.execute(update(s.measurements).where(s.measurements.c.event_id==corrupted['event_id']).values(wire_record=corrupted))
        repo=Repository(self.engine,self.settings);repo.initialize(self.artifacts,self._cluster_id())
        with self.assertRaisesRegex(RecoveryError,'history fingerprint'):
            Processor(repo,self.artifacts)

    def _cluster_id(self):
        admin=KafkaAdminClient(bootstrap_servers=self.base.bootstrap_servers)
        try: return admin.describe_cluster()['cluster_id']
        finally: admin.close()

    def test_external_checkpoint_advance_fences_stale_in_memory_worker(self):
        repo=self.repo()
        first=Processor(repo,self.artifacts);stale=Processor(repo,self.artifacts)
        self.send_direct(first,0)
        with self.assertRaisesRegex(CheckpointError,'outside this worker'):
            self.send_direct(stale,0)
        self.assertTrue(stale.poisoned)
        recovered=Processor(repo,self.artifacts)
        self.send_direct(recovered,1)
        self.assertEqual(self.count(s.measurements),2)
        self.assertEqual(repo.checkpoint()['next_offset'],2)
