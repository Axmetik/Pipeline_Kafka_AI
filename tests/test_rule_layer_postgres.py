"""Isolated PostgreSQL transaction tests with deterministic model doubles, no training/Kafka."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone
import json,os,unittest
from unittest.mock import patch
from uuid import uuid4
import numpy as np
from sqlalchemy import create_engine,select,func,text,delete,update
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command
from integration.settings import Settings,ROOT
from integration.processor import Processor
from integration.runtime import RecoveryError
from storage.postgres.repository import Repository,RepositoryError
from storage.postgres import schema as s
from storage.postgres import rules_schema as rs
from processing.message_schema import InvalidMessage
from processing.energy_rules import RuleConfig
from test_energy_rules import record

FIXED=datetime(2026,11,9,tzinfo=timezone.utc)
class FrozenDateTime(datetime):
    @classmethod
    def now(cls,tz=None):return FIXED if tz else FIXED.replace(tzinfo=None)

class Primary:
    def validate_source(self,r):
        if r['source_id']!='meter':raise InvalidMessage('fixture incompatible')
    def predict(self,f):return float(f['energy_wh']) if f else None

class Bundle:
    thresholds={'0.99':{'isolation_forest':.5,'autoencoder':.5,'residual':50.}}
    metadata={'model_version':'fixture-anomaly','feature_version':'energy-anomaly-20-v1','rf_feature_version':'benchmark-energy-v1','threshold_version':'fixture-q99'}
    def validate_source(self,r):return Primary().validate_source(r)
    def current_scores(self,x):return {'isolation_forest':np.zeros(len(x)),'autoencoder':np.zeros(len(x))}
    def forecast(self,x):return x[:,0].copy()

class Artifacts:
    primary=Primary();anomaly=Bundle();manifest_sha256='a'*64
    def registry(self):
        return [dict(model_id='fixture:'+role,artifact_sha256='a'*64,role=role,model_version='fixture-primary' if role=='primary_forecast' else 'fixture-anomaly',feature_version='benchmark-energy-v1' if role in ('residual','residual_reference') else 'energy-anomaly-20-v1',threshold_version=None if role=='primary_forecast' else 'fixture-q99',maturity='existing' if role=='primary_forecast' else 'experimental',details={}) for role in ('primary_forecast','residual_reference','isolation_forest','autoencoder','residual')]

@unittest.skipUnless(os.getenv('RUN_API_INTEGRATION')=='1','Requires isolated PostgreSQL')
class RuleLayerPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url=os.environ.get('MVP_TEST_DATABASE_URL') or Settings.from_env().database_url;cls.admin=create_engine(cls.url);cls.artifacts=Artifacts()
    @classmethod
    def tearDownClass(cls):cls.admin.dispose()
    def setUp(self):
        self.name='rules_test_'+uuid4().hex
        with self.admin.begin() as c:c.execute(text(f'CREATE SCHEMA "{self.name}"'))
        url=make_url(self.url).update_query_dict({'options':'-csearch_path='+self.name}).render_as_string(hide_password=False)
        self.settings=Settings(url,run_id=uuid4().hex,group_id=uuid4().hex,topic='fixture')
        self.engine=create_engine(url)
        self.base=Config(str(ROOT/'alembic.ini'));self.optional=Config(str(ROOT/'alembic-rules.ini'))
        self.migrate(self.base,'upgrade','head')
        self.patches=[patch('integration.runtime.now',return_value=FIXED),patch('anomaly.residual.datetime',FrozenDateTime)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.engine.dispose()
        with self.admin.begin() as c:c.execute(text(f'DROP SCHEMA "{self.name}" CASCADE'))
    def migrate(self,config,direction,version):
        with self.engine.begin() as c:config.attributes['connection']=c;getattr(command,direction)(config,version)
    def repo(self,enabled=True,new_run=False):
        settings=replace(self.settings,energy_rules_enabled=enabled)
        if new_run:settings=replace(settings,run_id=uuid4().hex,group_id=uuid4().hex)
        r=Repository(self.engine,settings);r.initialize(self.artifacts,'fixture-cluster');r.create_checkpoint();return r
    def send(self,p,offset,r=None):
        r=r if r is not None else record(offset)
        return p.process(offset,json.dumps([r['building_id'],r['source_id']]).encode(),json.dumps(r).encode())
    def count(self,table):
        with self.engine.connect() as c:return c.execute(select(func.count()).select_from(table)).scalar_one()
    def domain(self,run):
        result={}
        with self.engine.connect() as c:
            for table in (s.forecasts,s.scores,s.combined_decisions):
                rows=c.execute(select(table).join(s.measurements,table.c.measurement_id==s.measurements.c.measurement_id).where(table.c.run_id==run).order_by(s.measurements.c.kafka_offset)).mappings().all()
                # Ignore only run-derived relational IDs; all values, times and versions stay exact.
                omit={'run_id','measurement_id','forecast_id','score_id','decision_id','reference_forecast_id','scored_at','decided_at'}
                result[table.name]=sorted([json.dumps({k:str(v) for k,v in r.items() if k not in omit},sort_keys=True) for r in rows])
        return result
    def snapshot(self):
        with self.engine.connect() as c:return dict(c.execute(select(rs.states)).mappings().one())

    def test_default_off_old_schema_optional_migration_and_parity(self):
        off=self.repo(False);p=Processor(off,self.artifacts)
        for i in range(8):self.send(p,i)
        with self.assertRaisesRegex(RepositoryError,'optional schema missing'):self.repo(True)
        self.migrate(self.optional,'upgrade','head')
        self.assertEqual(self.count(rs.assessments),0) # no backfill
        with self.engine.connect() as c:self.assertEqual(c.execute(text('select version_num from alembic_version')).scalar_one(),'0003_email')
        before=self.domain(off.settings.run_id)
        on=self.repo(True,new_run=True);q=Processor(on,self.artifacts)
        for i in range(8):self.send(q,i)
        self.assertEqual(before,self.domain(on.settings.run_id))
        self.assertEqual(self.count(rs.assessments),24);self.assertEqual(self.count(rs.decisions),8)
        self.assertEqual(self.count(s.forecasts),32);self.assertEqual(self.count(s.scores),48);self.assertEqual(self.count(s.combined_decisions),16)
        self.migrate(self.optional,'downgrade','base');self.migrate(self.optional,'upgrade','head')
        self.assertEqual(self.count(rs.assessments),0)
        self.assertEqual(before,self.domain(off.settings.run_id))

    def test_seven_day_candidate_rollback_duplicates_and_restart(self):
        self.migrate(self.optional,'upgrade','head');repo=self.repo();p=Processor(repo,self.artifacts)
        start=7*144+47
        for i in range(start+5):self.send(p,i,record(i,100 if i<start else 200))
        saved=self.snapshot();blob=saved['state']['source']
        self.assertGreater(len(blob['history']),144);self.assertEqual(blob['high_count'],5);self.assertEqual(len(blob['high_references']),24)
        olddomain=self.domain(repo.settings.run_id)
        def fail(stage):
            if stage=='before_db_commit':raise RuntimeError('rollback')
        p.failpoint=fail
        with self.assertRaisesRegex(RuntimeError,'rollback'):self.send(p,start+5,record(start+5,200))
        self.assertEqual(self.snapshot(),saved);self.assertEqual(repo.checkpoint()['next_offset'],start+5)
        self.assertEqual(self.domain(repo.settings.run_id),olddomain)
        with self.assertRaises(RepositoryError):self.send(p,start+5,record(start+5,200))
        p=Processor(repo,self.artifacts);self.assertEqual(p.rule_layer.engine._sources[('house','meter')].high_count,5)
        self.send(p,start+5,record(start+5,200))
        with self.engine.connect() as c:
            episode=dict(c.execute(select(rs.episodes).where(rs.episodes.c.status=='open')).mappings().one());self.assertEqual(episode['flagged_points'],1)
            prior_rows={t.name:[dict(r) for r in c.execute(select(t)).mappings()] for t in (s.forecasts,s.scores,s.combined_decisions)}
        def after(stage):
            if stage=='after_db_commit':raise RuntimeError('committed crash')
        p.failpoint=after
        with self.assertRaises(RuntimeError):self.send(p,start+6,record(start+6,200))
        p=Processor(repo,self.artifacts);before=self.snapshot()
        self.assertEqual(self.send(p,start+6,record(start+6,200))['outcome'],'offset_duplicate')
        self.assertEqual(self.send(p,start+7,record(start+6,200))['outcome'],'message_duplicate')
        self.assertEqual(before,self.snapshot())
        p=Processor(repo,self.artifacts);self.send(p,start+8,record(start+7,200))
        with self.engine.connect() as c:
            now=dict(c.execute(select(rs.episodes).where(rs.episodes.c.status=='open')).mappings().one());self.assertEqual(now['episode_id'],episode['episode_id']);self.assertEqual(now['flagged_points'],3)
            for table in (s.forecasts,s.scores,s.combined_decisions):
                pk=list(table.primary_key.columns)[0]
                for old in prior_rows[table.name]:self.assertEqual(dict(c.execute(select(table).where(pk==old[pk.name])).mappings().one()),old)
        changed=Processor(repo,self.artifacts,rule_config=RuleConfig(high_intervals=7))
        self.send(changed,start+9,record(start+8,200))
        with self.engine.connect() as c:
            closed=c.execute(select(rs.episodes).where(rs.episodes.c.episode_id==episode['episode_id'])).mappings().one()
            self.assertEqual(closed['closed_reason'],'configuration_changed')

    def test_partial_positive_null_false_gap_and_no_notification_integration(self):
        from integration.rule_layer import hybrid_or
        self.migrate(self.optional,'upgrade','head');repo=self.repo();p=Processor(repo,self.artifacts)
        original=p.rule_layer.compute
        # Storage lifecycle contract uses controlled decisions; state still from real v2.
        flags=iter([(True,None),(True,None),(False,None),(True,False),(False,False),(True,False),(True,False)])
        def decisions(raw,result):
            out=original(raw,result);a,b=next(flags);out['decision']=hybrid_or(a,b);return out
        p.rule_layer.compute=decisions
        for i in range(6):self.send(p,i)
        self.send(p,6,record(8)) # timestamp gap: close/reopen true episode
        with self.engine.connect() as c:
            episodes=list(c.execute(select(rs.episodes).order_by(rs.episodes.c.start_timestamp)).mappings())
            self.assertEqual([e['closed_reason'] for e in episodes],['unknown','negative','gap',None])
            self.assertEqual([e['flagged_points'] for e in episodes],[2,1,1,1])
            self.assertEqual(c.execute(select(func.count()).select_from(s.notifications)).scalar_one(),0)
            d=c.execute(select(rs.decisions).order_by(rs.decisions.c.measurement_id)).mappings().all()
            self.assertTrue(any(x['flag'] is True and x['coverage_count']==1 and x['status']=='partial_positive' for x in d))
            self.assertTrue(any(x['flag'] is None for x in d))
            gap=c.execute(select(rs.assessments).where(rs.assessments.c.rule=='interval_gap',rs.assessments.c.flag.is_(True))).mappings().one()
            self.assertEqual(gap['evidence']['missing_intervals'],2)
            self.assertEqual(gap['evidence']['detection'],'on_next_received_measurement')

    def test_missing_corrupt_snapshot_rejected_and_reactivation_explicit(self):
        self.migrate(self.optional,'upgrade','head');repo=self.repo();p=Processor(repo,self.artifacts);self.send(p,0)
        saved=self.snapshot()
        with self.engine.begin() as c:c.execute(update(rs.states).values(state_sha256='0'*64))
        with self.assertRaisesRegex(RecoveryError,'checksum'):Processor(repo,self.artifacts)
        with self.engine.begin() as c:c.execute(update(rs.states).values(state_sha256=saved['state_sha256']))
        off=self.repo(False);self.send(Processor(off,self.artifacts),1)
        restored=Processor(repo,self.artifacts);self.send(restored,2)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(select(rs.assessments.c.activation).where(rs.assessments.c.measurement_id==self.snapshot()['measurement_id']).limit(1)).scalar_one(),'activation_gap')
        with self.engine.begin() as c:c.execute(delete(rs.states))
        with self.assertRaisesRegex(RecoveryError,'Missing committed'):Processor(repo,self.artifacts)
