"""Source identity and catalog SQL tested on isolated migrated PostgreSQL."""
import os, unittest
from sqlalchemy import select, event
from storage.postgres import schema as s
import test_api_integration as base

@unittest.skipUnless(os.getenv('RUN_API_INTEGRATION')=='1','Requires isolated PostgreSQL')
class SourceCatalogAPI(unittest.TestCase):
    setUpClass=classmethod(base.APIIntegration.setUpClass.__func__)
    tearDownClass=classmethod(base.APIIntegration.tearDownClass.__func__)
    setUp=base.APIIntegration.setUp
    tearDown=base.APIIntegration.tearDown
    get=base.APIIntegration.get
    def seed(self):
        base.APIIntegration.seed(self)
        with self.engine.begin() as c:
            binding=c.execute(select(s.sources.c.binding).where(s.sources.c.source_id=='dataset')).scalar_one()
            c.execute(s.sources.insert().values(building_id='other-house',source_id='dataset',binding=binding))
            original=dict(c.execute(select(s.measurements).where(s.measurements.c.measurement_id=='run-a-dataset-7')).mappings().one())
            original.update(measurement_id='other-id',building_id='other-house',energy_wh=999)
            c.execute(s.measurements.insert().values(**original))
            c.execute(s.sources.insert().values(building_id='house',source_id='unmeasured',binding=binding))
    def test_identity_latest_and_scope(self):
        result=self.get('/api/source-summaries',run_id='run-a')
        self.assertEqual(len(result['items']),3)
        by={(x['building_id'],x['source_id']):x for x in result['items']}
        self.assertEqual(by['house','dataset']['latest_energy_wh'],80)
        self.assertEqual(by['other-house','dataset']['latest_energy_wh'],999)
        row=by['house','dataset']
        self.assertEqual(row['measurement_timestamp'],'2016-01-01T01:10:00')
        self.assertEqual(row['time_basis'],'dataset_naive');self.assertEqual(row['activity_status'],'unknown')
        self.assertNotIn('binding',row);self.assertNotIn('wire_record',row)
        self.assertEqual(len(self.get('/api/source-summaries',run_id='run-b')['items']),2)
        self.assertEqual(len(self.get('/api/source-summaries',run_id='run-a',building_id='other-house')['items']),1)
        self.assertEqual(result['building_ids'],['house','other-house'])
    def test_cursor_search_and_limits(self):
        params=dict(run_id='run-a',limit=1);seen=[]
        while True:
            result=self.get('/api/source-summaries',**params)
            seen += [(x['building_id'],x['source_id']) for x in result['items']]
            if not result['next_cursor']:break
            params['cursor']=result['next_cursor']
        self.assertEqual(len(seen),len(set(seen)));self.assertEqual(len(seen),3)
        self.assertEqual(len(self.get('/api/source-summaries',run_id='run-a',search='DATA')['items']),2)
        self.assertEqual(self.get('/api/source-summaries',run_id='run-a',search='%')['items'],[])
        cursor=self.get('/api/source-summaries',run_id='run-a',limit=1)['next_cursor']
        self.assertEqual(self.client.get('/api/source-summaries',params=dict(run_id='run-b',cursor=cursor)).status_code,422)
        for q in ['','run_id=run-a&limit=1001','run_id=run-a&start=2016-01-01','run_id=run-a&unknown=1']:
            self.assertEqual(self.client.get('/api/source-summaries?'+q).status_code,422)
    def test_empty_and_constant_query_count(self):
        self.assertEqual(self.get('/api/source-summaries',run_id='absent')['items'],[])
        queries=[]
        def observe(c,cursor,statement,*args):
            if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
        event.listen(self.engine,'before_cursor_execute',observe)
        try:self.get('/api/source-summaries',run_id='run-a')
        finally:event.remove(self.engine,'before_cursor_execute',observe)
        self.assertEqual(len(queries),2) # bounded catalog + building options, not per-card queries
