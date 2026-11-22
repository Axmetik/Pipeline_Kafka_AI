"""Targeted read-only API contracts against isolated PostgreSQL; no inference."""
import os, unittest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, func
from integration.settings import ROOT
from storage.postgres import rules_schema as r
import test_api_integration as base


@unittest.skipUnless(os.getenv('RUN_API_INTEGRATION') == '1', 'Requires isolated PostgreSQL')
class RuleAPI(unittest.TestCase):
    setUpClass = classmethod(base.APIIntegration.setUpClass.__func__)
    tearDownClass = classmethod(base.APIIntegration.tearDownClass.__func__)
    setUp = base.APIIntegration.setUp
    tearDown = base.APIIntegration.tearDown
    seed = base.APIIntegration.seed
    get = base.APIIntegration.get

    def install(self):
        config = Config(str(ROOT/'alembic-rules.ini'))
        with self.engine.begin() as c:
            config.attributes['connection'] = c
            command.upgrade(config, 'head')

    def populate(self):
        self.install()
        with self.engine.begin() as c:
            for source in ['dataset', 'meter']:
                for i,flag in enumerate([None, False, True]):
                    mid = f'run-a-{source}-{i}'
                    c.execute(r.assessments.insert().values(assessment_id=mid, measurement_id=mid,run_id='run-a',rule='sustained_high',category='consumption_pattern',rule_version='v2',layer_version='fixture',configuration={},flag=flag,status='warmup' if flag is None else 'ready',evidence={'unavailable_reason':'insufficient_hourly_context'} if flag is None else {'threshold_wh':100},activation='new_activation',maturity='experimental'))
                    c.execute(r.decisions.insert().values(decision_id=mid,measurement_id=mid,run_id='run-a',channel='residual_or_sustained_high',layer_version='fixture',configuration={},input_versions={},flag=flag,status='unavailable' if flag is None else 'ready',coverage_count=0 if flag is None else 2,available_inputs=[] if flag is None else ['residual','sustained_high'],triggered_inputs=['residual','sustained_high'] if flag else [],maturity='experimental'))
            c.execute(r.episodes.insert().values(episode_id='fixture',run_id='run-a',building_id='house',source_id='dataset',layer_version='fixture',input_versions={},maturity='experimental',start_measurement_id='run-a-dataset-2',end_measurement_id='run-a-dataset-3',start_timestamp='2016-01-01T00:20:00',end_timestamp='2016-01-01T00:30:00',flagged_points=2,triggered_inputs=['residual','sustained_high'],status='closed',closed_reason='negative'))

    def test_without_tables_and_empty_installed_tables(self):
        for path in ['rule-assessments','hybrid-decisions','hybrid-events']:
            result=self.get('/api/'+path)
            self.assertEqual(result['channel_status'],'not_connected')
            self.assertEqual(result['items'],[])
        self.assertEqual(self.get('/health/ready')['status'],'ready')
        self.install()
        for path in ['rule-assessments','hybrid-decisions','hybrid-events']:
            self.assertEqual(self.get('/api/'+path)['channel_status'],'no_data')
        with self.engine.begin() as c: r.episodes.drop(c)
        self.assertEqual(self.get('/api/hybrid-decisions')['channel_status'],'not_connected')
        self.assertEqual(len(self.get('/api/measurements',run_id='run-a',source_id='dataset')['items']),8)

    def test_stored_flags_evidence_versions_no_writes(self):
        self.populate()
        params=dict(run_id='run-a',building_id='house',source_id='dataset')
        results=self.get('/api/hybrid-decisions',**params)
        self.assertEqual([x['flag'] for x in results['items']],[True,False,None])
        self.assertEqual(results['items'][0]['triggered_inputs'],['residual','sustained_high'])
        self.assertEqual(results['items'][2]['coverage_count'],0)
        rows=self.get('/api/rule-assessments',**params)['items']
        self.assertEqual(rows[-1]['evidence']['unavailable_reason'],'insufficient_hourly_context')
        self.assertEqual(rows[0]['rule_version'],'v2')
        self.assertEqual(self.get('/api/hybrid-events',**params)['items'][0]['maturity'],'experimental')
        with self.engine.connect() as c:self.assertEqual(c.execute(select(func.count()).select_from(r.decisions)).scalar_one(),6)
        self.assertEqual(self.get('/api/combined-decisions',**params)['items'][0]['rule'],'unanimous')

    def test_pagination_filter_and_naive_aware_contracts(self):
        self.populate()
        for path in ['rule-assessments','hybrid-decisions']:
            params=dict(run_id='run-a',building_id='house',source_id='dataset',limit=1)
            first=self.get('/api/'+path,**params)
            second=self.get('/api/'+path,**params,cursor=first['next_cursor'])
            self.assertNotEqual(first['items'][0]['measurement_id'],second['items'][0]['measurement_id'])
            self.assertEqual(first['items'][0]['time_basis'],'dataset_naive')
            self.assertEqual(self.client.get('/api/'+path,params={**params,'source_id':'meter','cursor':first['next_cursor']}).status_code,422)
            self.assertEqual(len(self.get('/api/'+path,**params,start='2016-01-01T00:10:00',end='2016-01-01T00:20:00')['items']),1)
            self.assertEqual(self.get('/api/'+path,run_id='run-b')['channel_status'],'no_data')
            self.assertEqual(self.get('/api/'+path,source_id='meter',time_basis='offset_aware',start='2015-12-31T22:00:00Z',end='2015-12-31T22:10:00Z')['items'][0]['measurement_timestamp'],'2016-01-01T00:00:00+02:00')
            for bad in ['limit=1001','start=2016-01-01T00:00:00Z','model_id=x']:
                self.assertEqual(self.client.get('/api/'+path+'?'+bad).status_code,422)
        self.assertEqual(self.get('/api/hybrid-events',source_id='dataset',start='2016-01-01T00:20:00',end='2016-01-01T00:30:00')['items'][0]['episode_id'],'fixture')
