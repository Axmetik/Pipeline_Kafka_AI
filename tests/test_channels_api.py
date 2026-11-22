"""Actual SQL for logical channel identity, nulls, windows and pagination."""
import os,unittest
from sqlalchemy import select,update,event
from storage.postgres import schema as s
import test_source_catalog_api as base

@unittest.skipUnless(os.getenv('RUN_API_INTEGRATION')=='1','Requires isolated PostgreSQL')
class ChannelsAPI(unittest.TestCase):
    setUpClass=classmethod(base.SourceCatalogAPI.setUpClass.__func__)
    tearDownClass=classmethod(base.SourceCatalogAPI.tearDownClass.__func__)
    setUp=base.SourceCatalogAPI.setUp
    tearDown=base.SourceCatalogAPI.tearDown
    get=base.SourceCatalogAPI.get
    def seed(self):
        base.SourceCatalogAPI.seed(self)
        with self.engine.begin() as c:
            for i in range(8):
                extras={'lights':i*2 if i!=7 else None}
                for z in range(2,10):extras.update({f'T{z}':z+i/10,f'RH_{z}':40+z+i/10})
                wire={'source_type':'dataset','energy':{'scope':'appliances'},'environment':{'temperature_c':20+i/10,'relative_humidity_pct':None},'additional_parameters':extras}
                c.execute(update(s.measurements).where(s.measurements.c.measurement_id==f'run-a-dataset-{i}').values(wire_record=wire))
    def test_columns_units_and_null_are_not_appliances(self):
        rows=self.get('/api/channels',run_id='run-a',building_id='house',source_id='dataset')['items']
        self.assertEqual(len(rows),11)
        by={r['channel_id']:r for r in rows}
        self.assertEqual(by['appliances']['value'],80)
        self.assertIsNone(by['lights']['value'])
        self.assertEqual(by['lights']['columns'],['lights']);self.assertEqual(by['lights']['units'],['Wh'])
        self.assertEqual(by['zone-1']['value'],20.7);self.assertIsNone(by['zone-1']['secondary_value'])
        for i in range(2,10):
            row=by[f'zone-{i}'];self.assertEqual(row['columns'],[f'T{i}',f'RH_{i}'])
            self.assertEqual(row['value'],i+.7);self.assertEqual(row['secondary_value'],40+i+.7)
            self.assertEqual(row['units'],['°C','%']);self.assertEqual(row['capabilities'],['statistics'])
        self.assertIn('північна',by['zone-6']['name'])
        self.assertNotIn('wire_record',by['lights']);self.assertNotIn('predicted_energy_wh',by['lights'])
    def test_context_categories_search_and_cursor(self):
        self.assertEqual(len(self.get('/api/channels',run_id='run-b')['items']),2)
        self.assertEqual(len(self.get('/api/channels',run_id='run-a',building_id='other-house')['items']),1)
        self.assertEqual(len(self.get('/api/channels',run_id='run-a',category='zones')['items']),9)
        self.assertEqual(self.get('/api/channels',run_id='run-a',search='кухня')['items'][0]['channel_id'],'zone-1')
        self.assertEqual(self.get('/api/channels',run_id='run-a',search='RH_6')['items'][0]['channel_id'],'zone-6')
        self.assertEqual(self.get('/api/channels',run_id='run-a',search='%')['items'],[])
        params={'run_id':'run-a','limit':3};keys=[]
        while True:
            result=self.get('/api/channels',**params)
            keys.extend((r['building_id'],r['source_id'],r['channel_id']) for r in result['items'])
            if not result['next_cursor']:break
            params['cursor']=result['next_cursor']
        self.assertEqual(len(keys),13);self.assertEqual(len(set(keys)),13)
        self.assertEqual(self.client.get('/api/channels',params={**params,'category':'zones'}).status_code,422)
    def test_series_window_missing_and_timestamps(self):
        params=dict(run_id='run-a',building_id='house',source_id='dataset',channel_id='lights',limit=3)
        result=self.get('/api/channel-series',**params)
        self.assertEqual([r['value'] for r in result['items']],[None,12,10])
        self.assertEqual(result['statistics'],[dict(count=2,minimum=10,maximum=12,mean=11)])
        self.assertEqual(result['items'][0]['measurement_timestamp'],'2016-01-01T01:10:00')
        self.assertEqual(result['items'][0]['time_basis'],'dataset_naive')
        self.assertEqual(result['statistics_scope'],'returned_window')
        self.assertEqual(self.get('/api/channel-series',**{**params,'building_id':'other-house'})['items'],[])
        window=self.get('/api/channel-series',**{**params,'limit':100,'start':'2016-01-01T00:20:00','end':'2016-01-01T00:50:00'})
        self.assertEqual([r['value'] for r in window['items']],[8,6,4])
        cursor=result['next_cursor']
        self.assertEqual(self.client.get('/api/channel-series',params={**params,'channel_id':'zone-1','cursor':cursor}).status_code,422)
        self.assertEqual(self.client.get('/api/channel-series',params={**params,'start':'2016-01-01T00:00:00Z'}).status_code,422)
        for extra in [{'model_id':'primary_forecast'},{'channel_id':'fridge'},{'limit':1001}]:
            self.assertEqual(self.client.get('/api/channel-series',params={**params,**extra}).status_code,422)
    def test_bounded_queries_no_models_and_no_invented_channels(self):
        queries=[]
        def observe(c,cursor,stmt,*a):
            if stmt.lstrip().upper().startswith(('SELECT','WITH')):queries.append(stmt)
        event.listen(self.engine,'before_cursor_execute',observe)
        try:self.get('/api/channels',run_id='run-a')
        finally:event.remove(self.engine,'before_cursor_execute',observe)
        self.assertEqual(len(queries),2)
        self.assertFalse(any('energy_forecasts' in q or 'anomaly_scores' in q for q in queries))
        self.assertEqual(self.get('/api/channels',run_id='absent')['items'],[])
