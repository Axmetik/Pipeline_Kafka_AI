"""Narrow real PostgreSQL tests. SMTP mocked; no broker or model fitting required."""
import copy
from dataclasses import replace
from datetime import timedelta
import json
import os
import smtplib
import unittest
from unittest.mock import patch
from uuid import uuid4
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine,select,func,text,update
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient
from api.main import create_app
from integration.settings import Settings,ROOT
from integration.processor import Processor
from storage.postgres.repository import Repository
from storage.postgres import schema as s
from notifications.notifier import claim,deliver,tick
from test_email import config
from energy_helpers import energy_records


@unittest.skipUnless(os.getenv('RUN_API_INTEGRATION')=='1','Real PostgreSQL required')
class EmailPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url=os.environ.get('MVP_TEST_DATABASE_URL') or Settings.from_env().database_url
        cls.base=create_engine(cls.url)

    @classmethod
    def tearDownClass(cls): cls.base.dispose()

    def setUp(self):
        self.namespace='email_test_'+uuid4().hex
        with self.base.begin() as c: c.execute(text(f'CREATE SCHEMA "{self.namespace}"'))
        self.engine=create_engine(make_url(self.url).update_query_dict({'options':'-csearch_path='+self.namespace}))
        self.alembic=Config(str(ROOT/'alembic.ini'))
        with self.engine.begin() as c:
            self.alembic.attributes['connection']=c;command.upgrade(self.alembic,'head')
        self.cfg=config(mode='both');self.records=list(energy_records(180))
        self.settings=Settings(self.engine.url.render_as_string(hide_password=False),run_id='email-test',group_id='email-test',topic='email-test')
        self.repo=Repository(self.engine,self.settings);self.repo.email_config=self.cfg
        with self.engine.begin() as c:
            c.execute(s.runs.insert().values(run_id='email-test',group_id='email-test',topic='email-test',cluster_id='test',manifest_sha256='a'*64,config={}))
            c.execute(s.models.insert().values(model_id='if-test',artifact_sha256='a'*64,role='isolation_forest',model_version='test',feature_version='test',threshold_version='q99',maturity='experimental',details={}))
        self.repo.create_checkpoint()

    def tearDown(self):
        self.engine.dispose()
        with self.base.begin() as c: c.execute(text(f'DROP SCHEMA "{self.namespace}" CASCADE'))

    def rows(self):
        with self.engine.connect() as c: return [dict(r) for r in c.execute(select(s.notifications).order_by(s.notifications.c.created_at)).mappings()]

    def process(self,i,flag=True,record=None):
        row=record or self.records[i]
        class FakeRuntime:
            def __init__(self,*args): pass
            def restore(self,*args): pass
            def compute(self,raw):
                return dict(compatible=True,feature_status='ready',gap_detected=False,forecasts=[],scores=[dict(model_id='if-test',
                    detector='isolation_forest',model_version='test',feature_version='test',threshold_version='q99',maturity='experimental',
                    score=2 if flag else 0,threshold=1,flag=flag,status='ready')])
        with patch('integration.processor.Runtime',FakeRuntime):
            processor=Processor(self.repo,None)
        return processor.process(i,json.dumps([row['building_id'],row['source_id']]).encode(),json.dumps(row).encode())

    def test_episode_outbox_rollback_duplicates_continuation_and_cooldown(self):
        self.process(0)
        self.assertEqual(len(self.rows()),1)
        self.process(0)  # exact Kafka coordinate redelivery
        self.process(1,record=self.records[0])  # duplicate event at next offset
        self.process(2,record=self.records[1])  # same episode continuation
        self.assertEqual(len(self.rows()),1)
        self.process(3,False,record=self.records[2]);self.process(4,record=self.records[3])
        self.assertEqual([r['status'] for r in self.rows()],['pending','suppressed'])
        self.assertEqual(self.rows()[1]['suppression_reason'],'cooldown')
        before=len(self.rows())
        from notifications.outbox import enqueue
        with self.assertRaises(RuntimeError):
            with self.engine.begin() as c:
                enqueue(c,'combined',dict(episode_id='rollback',run_id='email-test',rule_version='unanimous'),self._mid(),self.records[0],{'trigger_count':3},self.cfg)
                raise RuntimeError('rollback')
        self.assertEqual(len(self.rows()),before)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(select(s.checkpoints.c.next_offset)).scalar_one(),5)
            self.assertEqual(c.execute(select(func.count()).select_from(s.episodes)).scalar_one(),2)

    def _mid(self):
        with self.engine.connect() as c: return c.execute(select(s.measurements.c.measurement_id).limit(1)).scalar_one()

    def test_disabled_filters_no_backfill_and_mode_changes(self):
        self.repo.email_config=replace(self.cfg,enabled=False);self.process(0)
        self.repo.email_config=self.cfg;self.process(1)
        self.assertEqual(self.rows(),[]) # enabling doesn't notify already-open episode
        self.process(2,False);self.repo.email_config=replace(self.cfg,source_id='other');self.process(3)
        self.assertEqual(self.rows(),[])
        self.process(4,False);self.repo.email_config=replace(self.cfg,mode='combined');self.process(5)
        self.assertEqual(self.rows(),[])
        self.process(6,False);self.repo.email_config=self.cfg;self.process(7)
        self.assertEqual(len(self.rows()),1)
        result=tick(self.engine,replace(self.cfg,mode='individual'),lambda *a:self.fail('changed policy sent'))
        self.assertEqual(result['status'],'suppressed');self.assertEqual(self.rows()[0]['suppression_reason'],'configuration_changed')

    def test_retry_permanent_failure_success_and_restart(self):
        self.process(0)
        def temporary(*args): raise smtplib.SMTPDataError(451,b'private server info')
        self.assertEqual(tick(self.engine,self.cfg,temporary)['status'],'retrying')
        self.assertIsNone(tick(self.engine,self.cfg,temporary))
        with self.engine.begin() as c: c.execute(update(s.notifications).values(next_retry_at=text("clock_timestamp()-interval '1 second'")))
        calls=[];self.assertEqual(tick(self.engine,self.cfg,lambda msg,cfg:calls.append(msg))['status'],'sent')
        self.assertEqual(len(calls),1);self.assertEqual(self.rows()[0]['attempt_count'],2)
        self.assertIsNone(tick(self.engine,self.cfg,lambda *a:self.fail('duplicate send')))
        self.process(1,False);self.repo.email_config=replace(self.cfg,cooldown_minutes=0);self.process(2)
        def permanent(*args): raise smtplib.SMTPAuthenticationError(535,b'secret')
        self.assertEqual(tick(self.engine,self.repo.email_config,permanent)['status'],'failed')
        self.assertIsNone(tick(self.engine,self.repo.email_config,permanent))
        self.assertEqual(self.rows()[1]['error_category'],'smtp_authentication')

    def test_concurrent_claim_skip_locked_stale_recovery_and_attempt_bound(self):
        self.process(0);first=claim(self.engine,self.cfg)
        self.assertIsNone(claim(self.engine,self.cfg))
        with self.engine.begin() as c: c.execute(update(s.notifications).values(claimed_until=text("clock_timestamp()-interval '1 second'")))
        with self.engine.begin() as locked:
            locked.execute(select(s.notifications).with_for_update()).all()
            self.assertIsNone(claim(self.engine,self.cfg))
        second=claim(self.engine,self.cfg)
        self.assertNotEqual(first['claim_token'],second['claim_token'])
        self.assertEqual(deliver(self.engine,self.cfg,first,lambda *a:self.fail('stale sender'))['status'],'claim_lost')
        self.assertEqual(deliver(self.engine,self.cfg,second,lambda *a:None)['status'],'sent')
        with self.engine.begin() as c:
            c.execute(update(s.notifications).values(status='sending',attempt_count=5,claimed_until=text("clock_timestamp()-interval '1 second'")))
        self.assertEqual(claim(self.engine,self.cfg)['status'],'failed')

    def test_ambiguous_smtp_acceptance_may_repeat_after_crash(self):
        self.process(0)
        accepted=[]
        task=claim(self.engine,self.cfg)
        def crash_after_accept(message,cfg):
            accepted.append(message['Message-ID'])
            raise SystemExit('simulate process death after SMTP acceptance')
        with self.assertRaises(SystemExit): deliver(self.engine,self.cfg,task,crash_after_accept)
        self.assertEqual(self.rows()[0]['status'],'sending')
        with self.engine.begin() as c:
            c.execute(update(s.notifications).values(claimed_until=text("clock_timestamp()-interval '1 second'")))
        self.assertEqual(tick(self.engine,self.cfg,lambda message,cfg:accepted.append(message['Message-ID']))['status'],'sent')
        self.assertEqual(len(accepted),2)
        self.assertEqual(accepted[0],accepted[1]) # stable ID does not guarantee SMTP deduplication

    def test_atomic_combined_episode_and_deduplication(self):
        self.process(0,False)
        from storage.postgres.combined import persist_combined
        from anomaly.combined import NAMES
        scores=[dict(detector=n,status='ready',score=2.,threshold=1.,flag=True,model_id=n,model_version='v1',feature_version='f1',threshold_version='q99') for n in NAMES]
        # Remove the existing partial decision only in this isolated test fixture.
        with self.engine.begin() as c:
            c.execute(s.combined_decisions.delete())
            persist_combined(self.repo,c,self._mid(),self.records[0],scores,False)
        self.assertEqual(len(self.rows()),1);self.assertEqual(self.rows()[0]['kind'],'combined')
        self.assertEqual(self.rows()[0]['payload']['trigger_count'],3)
        from notifications.outbox import enqueue
        with self.engine.begin() as c:
            enqueue(c,'combined',dict(episode_id=self.rows()[0]['episode_id'],run_id='email-test',rule_version='combined-q99-v1-unanimous'),self._mid(),self.records[0],{'trigger_count':3},self.cfg)
        self.assertEqual(len(self.rows()),1)

    def test_worker_transaction_failure_and_post_commit_redelivery(self):
        self.process(0,False)
        class FailAfterInsert:
            def __init__(self,original): self.original=original
            def __call__(self,*args):
                result=self.original(*args)
                raise RuntimeError('abort worker transaction')
        original=self.repo.persist
        self.repo.persist=FailAfterInsert(original)
        with self.assertRaises(RuntimeError): self.process(1)
        self.assertEqual(self.rows(),[])
        self.repo.persist=original;self.process(1)
        self.assertEqual(len(self.rows()),1)
        self.process(1);self.assertEqual(len(self.rows()),1)

    def test_additive_migration_roundtrip_metadata_and_safe_read_api(self):
        with self.engine.connect() as c: self.assertEqual(compare_metadata(MigrationContext.configure(c),s.metadata),[])
        self.process(0);self.process(1,False);self.process(2)
        with TestClient(create_app(self.engine)) as client:
            response=client.get('/api/notifications?run_id=email-test&limit=1')
            self.assertEqual(response.status_code,200)
            data=response.json();self.assertEqual(len(data['items']),1)
            self.assertNotIn('recipient',data['items'][0]);self.assertNotIn('payload',data['items'][0])
            self.assertIsNotNone(data['next_cursor'])
            second=client.get('/api/notifications',params={'run_id':'email-test','limit':1,'cursor':data['next_cursor']})
            self.assertEqual(second.status_code,200)
            self.assertNotEqual(second.json()['items'][0]['notification_id'],data['items'][0]['notification_id'])
            self.assertEqual(client.get('/api/notifications?source_id=other').json()['items'],[])
            self.assertEqual(client.get('/api/notifications?limit=1001').status_code,422)
        with self.engine.begin() as c:
            self.alembic.attributes['connection']=c;command.downgrade(self.alembic,'0002_combined');command.upgrade(self.alembic,'head')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(select(func.count()).select_from(s.measurements)).scalar_one(),3)
            self.assertEqual(compare_metadata(MigrationContext.configure(c),s.metadata),[])
