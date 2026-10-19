"""Real SQL against isolated migrated PostgreSQL; no repository mocks or ML fitting."""
from datetime import datetime,timedelta,timezone
import json
import os
import unittest
from uuid import uuid4
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func,text,update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from api.main import create_app,read_connection
from integration.settings import Settings,ROOT
from storage.postgres import schema as s


@unittest.skipUnless(os.getenv('RUN_API_INTEGRATION')=='1','Select --suite api with real PostgreSQL')
class APIIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url=os.getenv('MVP_TEST_DATABASE_URL') or Settings.from_env().database_url
        cls.base=create_engine(cls.url)

    @classmethod
    def tearDownClass(cls): cls.base.dispose()

    def setUp(self):
        self.namespace='api_test_'+uuid4().hex
        with self.base.begin() as c: c.execute(text(f'CREATE SCHEMA "{self.namespace}"'))
        url=make_url(self.url).update_query_dict({'options':'-csearch_path='+self.namespace})
        self.engine=create_engine(url)
        config=Config(str(ROOT/'alembic.ini'))
        with self.engine.begin() as c:
            config.attributes['connection']=c;command.upgrade(config,'head')
        self.seed()
        self.client=TestClient(create_app(self.engine));self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None);self.engine.dispose()
        with self.base.begin() as c: c.execute(text(f'DROP SCHEMA "{self.namespace}" CASCADE'))

    def seed(self):
        self.start=datetime(2016,1,1)
        self.now=datetime(2026,10,19,tzinfo=timezone.utc)
        with self.engine.begin() as c:
            for role in ['primary_forecast','residual_reference','isolation_forest','autoencoder','residual']:
                c.execute(s.models.insert().values(model_id=role,artifact_sha256=role,role=role,model_version=role+'-v1',
                    feature_version='energy-20' if role=='primary_forecast' else 'energy-21',threshold_version='q99' if role in ['isolation_forest','autoencoder','residual'] else None,
                    maturity='experimental' if role!='primary_forecast' else 'existing',details={'feature_names':['energy_wh'],'horizon_seconds':600,'private':'password-not-public'}))
            for run in ['run-a','run-b']:
                c.execute(s.runs.insert().values(run_id=run,group_id=run,topic=run,cluster_id='private',manifest_sha256='a'*64,config={'private':'password-not-public'},created_at=self.now))
            for source,aware in [('dataset',False),('meter',True)]:
                binding=dict(source_type='smart_meter' if aware else 'dataset',energy_scope='appliances',interval_seconds=600,
                    timestamp_reference='interval_end' if aware else 'dataset_label',timezone=None,timestamp_has_offset=aware)
                c.execute(s.sources.insert().values(building_id='house',source_id=source,binding=binding))
                for run in ['run-a','run-b']:
                    for i in range(8):
                        mid=f'{run}-{source}-{i}'
                        local=self.start+timedelta(minutes=i*10)
                        dt=local.replace(tzinfo=timezone(timedelta(hours=2))) if aware else local
                        c.execute(s.measurements.insert().values(measurement_id=mid,run_id=run,building_id='house',source_id=source,
                            event_id=str(i),kafka_offset=i,measurement_timestamp=dt.isoformat(),measurement_time_local=local,
                            measurement_time_utc=dt.astimezone(timezone.utc) if aware else None,time_basis='offset_aware' if aware else 'dataset_naive',
                            timezone=None,timestamp_reference=binding['timestamp_reference'],interval_seconds=600,energy_wh=10*(i+1),
                            environment={'temperature_c':20,'relative_humidity_pct':None},wire_record={'secret':'password-not-public'},
                            normalized_sha256='b'*64,compatible=True,feature_status='warmup' if i==0 else 'ready',gap_detected=False,received_at=self.now))
                        for purpose in ['primary_forecast','residual_reference']:
                            target=dt+timedelta(minutes=10)
                            c.execute(s.forecasts.insert().values(forecast_id=mid+'-'+purpose,run_id=run,measurement_id=mid,model_id=purpose,purpose=purpose,
                                model_version=purpose+'-v1',feature_version='energy-20' if purpose=='primary_forecast' else 'energy-21',
                                forecast_origin=dt.isoformat(),forecast_target_timestamp=target.isoformat(),target_time_local=target.replace(tzinfo=None),
                                target_time_utc=target.astimezone(timezone.utc) if aware else None,generated_at=self.now,predicted_energy_wh=None if i==0 else 42,
                                status='warmup' if i==0 else 'ready',horizon_seconds=600))
                        for detector in ['isolation_forest','autoencoder','residual']:
                            c.execute(s.scores.insert().values(score_id=mid+'-'+detector,run_id=run,measurement_id=mid,model_id=detector,detector=detector,
                                model_version=detector+'-v1',feature_version='energy-21',threshold_version='q99',maturity='experimental',
                                score=None if i==0 else 1.5,threshold=1,flag=None if i==0 else True,status='warmup' if i==0 else 'ready',scored_at=self.now,
                                reference_forecast_id=f'{run}-{source}-{i-1}-residual_reference' if i>0 and detector=='residual' else None,
                                prediction_wh=42 if i>0 and detector=='residual' else None,signed_residual_wh=10*(i+1)-42 if i>0 and detector=='residual' else None,
                                forecast_origin=(dt-timedelta(minutes=10)).isoformat() if i>0 and detector=='residual' else None,
                                forecast_target_timestamp=dt.isoformat() if i>0 and detector=='residual' else None,
                                reference_generated_at=self.now if i>0 and detector=='residual' else None))
            for detector,status,i in [('autoencoder','open',1),('residual','closed',2)]:
                c.execute(s.episodes.insert().values(episode_id=detector,run_id='run-a',building_id='house',source_id='dataset',model_id=detector,
                    detector=detector,model_version=detector+'-v1',feature_version='energy-21',threshold_version='q99',maturity='experimental',
                    start_measurement_id=f'run-a-dataset-{i}',end_measurement_id=f'run-a-dataset-{i+1}',start_timestamp=(self.start+timedelta(minutes=i*10)).isoformat(),
                    end_timestamp=(self.start+timedelta(minutes=(i+1)*10)).isoformat(),flagged_points=2,status=status,closed_reason=None if status=='open' else 'below_threshold'))
            c.execute(s.checkpoints.insert().values(group_id='run-a',topic='run-a',partition=0,run_id='run-a',next_offset=11,updated_at=self.now))
            for i,outcome in enumerate(['accepted','message_duplicate','invalid_message']):
                c.execute(s.receipts.insert().values(group_id='run-a',topic='run-a',partition=0,offset=i,run_id='run-a',payload_sha256='c'*64,outcome=outcome))
            c.execute(s.errors.insert().values(error_id='bad',run_id='run-a',topic='run-a',partition=0,offset=2,kind='invalid_message',reason='password-not-public',payload_base64={'secret':'password-not-public'}))

    def get(self,path,**params):
        r=self.client.get(path,params=params);self.assertEqual(r.status_code,200,r.text);return r.json()

    def test_filters_and_stable_cursor_no_duplicates(self):
        params={'run_id':'run-a','source_id':'dataset','building_id':'house','limit':3}
        ids=[];timestamps=[]
        while True:
            data=self.get('/api/measurements',**params)
            ids += [r['measurement_id'] for r in data['items']]
            timestamps += [r['measurement_timestamp'] for r in data['items']]
            if not data['next_cursor']: break
            params['cursor']=data['next_cursor']
        self.assertEqual(len(ids),8);self.assertEqual(len(set(ids)),8)
        self.assertEqual(timestamps,sorted(timestamps,reverse=True))
        self.assertEqual(self.get('/api/measurements',run_id='absent')['items'],[])
        self.assertEqual(len(self.get('/api/measurements',run_id='run-a',start='2016-01-01T00:20:00',end='2016-01-01T00:50:00')['items']),3)
        self.assertEqual(len(self.get('/api/measurements',run_id='run-a',status='warmup')['items']),1)

    def test_tied_timestamps_and_cursor_filter_mismatch(self):
        params={'limit':1};ids=[]
        while True:
            result=self.get('/api/measurements',**params);ids += [r['measurement_id'] for r in result['items']]
            if not result['next_cursor']: break
            params['cursor']=result['next_cursor']
        self.assertEqual(len(ids),16);self.assertEqual(len(set(ids)),16)
        cursor=self.get('/api/measurements',limit=1)['next_cursor']
        self.assertEqual(self.client.get('/api/measurements',params={'cursor':cursor,'run_id':'run-a'}).status_code,422)
        self.assertEqual(self.client.get('/api/forecasts',params={'cursor':cursor}).status_code,422)

    def test_nullable_forecasts_and_target_alignment(self):
        result=self.get('/api/forecasts',run_id='run-a',status='warmup',purpose='primary_forecast')['items'][0]
        self.assertIsNone(result['predicted_energy_wh'])
        self.assertEqual(result['forecast_origin'],'2016-01-01T00:00:00')
        self.assertEqual(result['forecast_target_timestamp'],'2016-01-01T00:10:00')
        self.assertEqual(datetime.fromisoformat(result['generated_at'].replace('Z','+00:00')),self.now)
        rows=self.get('/api/forecasts',run_id='run-a',start='2016-01-01T00:10:00',end='2016-01-01T00:20:00',model_id='primary_forecast')['items']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['forecast_origin'],'2016-01-01T00:00:00')

    def test_experimental_scores_and_events(self):
        row=self.get('/api/anomaly-scores',run_id='run-a',detector='residual',status='warmup')['items'][0]
        for field in ['score','flag','prediction_wh']: self.assertIsNone(row[field])
        self.assertEqual(row['maturity'],'experimental');self.assertEqual(row['threshold_version'],'q99')
        rows=self.get('/api/anomaly-scores',run_id='run-a',detector='residual',status='ready')['items']
        for row in rows:
            self.assertEqual(row['forecast_target_timestamp'],row['measurement_timestamp'])
            self.assertEqual(datetime.fromisoformat(row['measurement_timestamp'])-datetime.fromisoformat(row['forecast_origin']),timedelta(minutes=10))
            self.assertTrue(row['reference_forecast_id'].endswith('residual_reference'))
        row=self.get('/api/events',status='open',detector='autoencoder')['items'][0]
        self.assertEqual(row['event_type'],'experimental_threshold_exceedance');self.assertEqual(row['flagged_points'],2)
        self.assertEqual(len(self.get('/api/events',status='closed')['items']),1)

    def test_naive_utc_and_offset_preservation(self):
        row=self.get('/api/measurements',run_id='run-a',source_id='dataset',limit=1)['items'][0]
        self.assertTrue(row['measurement_timestamp'].startswith('2016-'));self.assertIsNone(row['timezone'])
        self.assertIsNone(datetime.fromisoformat(row['measurement_timestamp']).tzinfo)
        rows=self.get('/api/measurements',run_id='run-a',source_id='meter',time_basis='offset_aware',start='2015-12-31T22:00:00Z',end='2015-12-31T22:20:00Z')['items']
        self.assertEqual(len(rows),2);self.assertTrue(rows[0]['measurement_timestamp'].endswith('+02:00'))
        self.assertEqual(self.client.get('/api/measurements?start=2016-01-01T00:00:00Z').status_code,422)
        self.assertEqual(self.client.get('/api/measurements?time_basis=offset_aware&start=2016-01-01').status_code,422)

    def test_aggregation_sums_wh_and_marks_partial_buckets(self):
        rows=self.get('/api/measurements/aggregate',run_id='run-a',source_id='dataset',bucket_minutes=60)['items']
        self.assertEqual(len(rows),2)
        self.assertFalse(rows[0]['complete']);self.assertIsNone(rows[0]['energy_wh'])
        self.assertEqual(rows[1]['energy_wh'],210);self.assertTrue(rows[1]['complete'])
        self.assertEqual(rows[1]['expected_intervals'],6);self.assertEqual(rows[1]['energy_unit'],'Wh')
        rows=self.get('/api/measurements/aggregate',run_id='run-a',source_id='dataset',start='2016-01-01T00:10:00',end='2016-01-01T01:00:00')['items']
        self.assertFalse(rows[0]['complete']);self.assertIsNone(rows[0]['energy_wh'])
        rows=self.get('/api/measurements/aggregate',time_basis='offset_aware',run_id='run-a')['items']
        self.assertEqual(rows[1]['energy_wh'],210);self.assertTrue(rows[1]['bucket_start'].endswith('+00:00'))

    def test_aggregation_cursor_and_source_run_separation(self):
        params={'limit':1};rows=[]
        while True:
            data=self.get('/api/measurements/aggregate',**params);rows+=data['items']
            if not data['next_cursor']: break
            params['cursor']=data['next_cursor']
        self.assertEqual(len(rows),4)
        self.assertEqual(sorted(r['energy_wh'] for r in rows if r['complete']),[210,210])
        with self.engine.begin() as c: c.execute(update(s.measurements).where(s.measurements.c.measurement_id=='run-a-dataset-1').values(interval_seconds=300))
        self.assertEqual(self.client.get('/api/measurements/aggregate?run_id=run-a').status_code,422)

    def test_empty_lists_and_limits(self):
        for resource in ['runs','sources','measurements','forecasts','anomaly-scores','events','models','measurements/aggregate']:
            with self.subTest(resource=resource):
                value=self.get('/api/'+resource,run_id='missing')
                self.assertEqual(value['items'],[]);self.assertIsNone(value['next_cursor'])
        for query in ['limit=0','limit=1001','limit=no','cursor=garbage','unknown=1']:
            self.assertEqual(self.client.get('/api/measurements?'+query).status_code,422)
        self.assertEqual(self.client.get('/api/measurements/aggregate?bucket_minutes=15').status_code,422)

    def test_metadata_and_status_do_not_expose_secrets(self):
        self.assertEqual(len(self.get('/api/sources',run_id='run-a')['items']),2)
        models=self.get('/api/models',run_id='run-a',model_version='residual-v1')['items'];self.assertEqual(len(models),1)
        status=self.get('/api/pipeline-status',run_id='run-a')
        self.assertEqual(status['worker_status'],'unknown');self.assertEqual(status['unique_measurements'],16)
        self.assertEqual(status['forecasts'],32);self.assertEqual(status['anomaly_scores'],48)
        self.assertEqual(status['duplicate_deliveries'],1);self.assertEqual(status['rejected_messages'],1)
        self.assertEqual(status['checkpoints'][0]['next_offset'],11)
        for path in ['/api/runs','/api/sources','/api/measurements','/api/forecasts','/api/anomaly-scores','/api/events','/api/models','/api/pipeline-status']:
            body=self.client.get(path).text
            for secret in ['password-not-public','wire_record','payload_base64','database_url','manifest_sha256']:
                self.assertNotIn(secret,body)
        self.assertEqual(self.get('/api/pipeline-status',run_id='missing')['checkpoints'],[])

    def test_read_only_sql_and_http(self):
        with self.assertRaises(DBAPIError),read_connection(self.engine) as c: c.execute(s.runs.delete())
        self.assertEqual(self.client.post('/api/runs',json={}).status_code,405)
        self.assertEqual(self.get('/health/live')['status'],'live')
        self.assertEqual(self.get('/health/ready')['status'],'ready')
        before=self.get('/api/pipeline-status')
        for path in ['/api/forecasts','/api/anomaly-scores','/api/events']: self.get(path)
        self.assertEqual(before,self.get('/api/pipeline-status'))

    def test_database_failure_is_503_without_credentials(self):
        broken=create_engine('postgresql+psycopg://secret:password-not-public@127.0.0.1:1/secret',connect_args={'connect_timeout':1})
        try:
            with TestClient(create_app(broken)) as c:
                self.assertEqual(c.get('/health/live').status_code,200)
                for path in ['/health/ready','/api/measurements','/api/pipeline-status']:
                    r=c.get(path);self.assertEqual(r.status_code,503);self.assertNotIn('password',r.text);self.assertNotIn('secret',r.text)
        finally: broken.dispose()

    def test_cors_and_local_access(self):
        allowed=self.client.options('/api/runs',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET'})
        self.assertEqual(allowed.status_code,200);self.assertEqual(allowed.headers['access-control-allow-origin'],'http://localhost:5173')
        self.assertEqual(self.client.options('/api/runs',headers={'Origin':'https://external.example','Access-Control-Request-Method':'GET'}).status_code,400)
        with TestClient(create_app(self.engine),client=('192.0.2.10',5000)) as c: self.assertEqual(c.get('/health/live').status_code,403)

    def test_pagination_for_every_resource(self):
        for resource,key,count in [('runs','run_id',2),('sources','source_id',2),('models','model_id',5),
                                   ('forecasts','forecast_id',32),('anomaly-scores','score_id',48),('events','episode_id',2)]:
            with self.subTest(resource=resource):
                params={'limit':1};ids=[]
                while True:
                    value=self.get('/api/'+resource,**params);ids += [r[key] for r in value['items']]
                    if not value['next_cursor']: break
                    params['cursor']=value['next_cursor']
                self.assertEqual(len(ids),count);self.assertEqual(len(set(ids)),count)
        self.assertEqual(len(self.get('/api/forecasts',run_id='run-a',model_version='primary_forecast-v1')['items']),8)
        self.assertEqual(self.client.get('/api/measurements?model_id=primary_forecast').status_code,422)
        self.assertEqual(self.client.get('/api/runs?detector=residual').status_code,422)
        self.assertEqual(self.client.get('/api/events?status=ready').status_code,422)

    def test_utc_label_and_off_grid_aggregation(self):
        with self.engine.begin() as c:
            c.execute(update(s.measurements).where(s.measurements.c.measurement_id=='run-a-meter-0').values(
                measurement_timestamp='2015-12-31T22:00:00+00:00',measurement_time_local=datetime(2015,12,31,22)))
            c.execute(update(s.measurements).where(s.measurements.c.measurement_id=='run-a-dataset-1').values(
                measurement_time_local=self.start+timedelta(minutes=11)))
        row=self.get('/api/measurements',time_basis='offset_aware',run_id='run-a',source_id='meter',
                     start='2015-12-31T22:00:00Z',end='2015-12-31T22:10:00Z')['items'][0]
        self.assertEqual(row['measurement_timestamp'],'2015-12-31T22:00:00+00:00')
        rows=self.get('/api/measurements/aggregate',run_id='run-a',source_id='dataset')['items']
        self.assertEqual(rows[1]['observed_intervals'],6)
        self.assertFalse(rows[1]['complete']);self.assertIsNone(rows[1]['energy_wh'])
