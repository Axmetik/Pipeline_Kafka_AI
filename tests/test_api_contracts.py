"""API validation and contracts, independent of PostgreSQL/Kafka."""
import base64
from datetime import datetime
import json
import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from api.main import create_app
from api.query import Filters,decode_cursor,fingerprint
from api.schemas import Forecast,Score


class APIContracts(unittest.TestCase):
    def test_timestamp_validation_and_request_bounds(self):
        for kwargs in [{'limit':0},{'limit':1001},{'cursor':'x'*4097},
                       {'start':'2016-01-01T00:00:00Z'},
                       {'time_basis':'offset_aware','end':'2016-01-01'},
                       {'start':'2016-01-02','end':'2016-01-01'}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValidationError): Filters(**kwargs)
        self.assertIsNone(Filters(start='2016-01-01').start.tzinfo)
        self.assertIsNotNone(Filters(time_basis='offset_aware',start='2016-01-01T00:00:00Z').start.tzinfo)

    def test_cursor_rejects_malformed_foreign_or_wrong_time_basis(self):
        f=Filters()
        for value in ['!','W10',base64.urlsafe_b64encode(json.dumps({'v':1,'q':fingerprint('measurements',f),'k':['2016-01-01T00:00:00Z','id']}).encode()).decode()]:
            with self.subTest(value=value),self.assertRaises(HTTPException): decode_cursor(value,'measurements',f,['time','str'])

    def test_openapi_exposes_all_read_only_contracts(self):
        spec=create_app(object()).openapi()
        self.assertEqual(len(spec['paths']),11)
        for value in spec['paths'].values(): self.assertEqual(set(value),{'get'})
        schemas=spec['components']['schemas']
        self.assertEqual(schemas['Score']['properties']['maturity']['const'],'experimental')
        self.assertEqual(schemas['PipelineStatus']['properties']['worker_status']['const'],'unknown')
        self.assertEqual(set(schemas['Forecast']['required']),{'run_id','building_id','source_id','time_basis','timezone','timestamp_reference',
            'forecast_id','measurement_id','model_id','model_version','feature_version','purpose','forecast_origin',
            'forecast_target_timestamp','generated_at','predicted_energy_wh','horizon_seconds','status'})
        for model,field in [(Forecast,'predicted_energy_wh'),(Score,'score'),(Score,'flag')]:
            self.assertIn({'type':'null'},model.model_json_schema()['properties'][field]['anyOf'])

    def test_api_imports_no_inference_modules(self):
        import subprocess,sys
        code="from api.main import create_app; import sys; assert not any(x in sys.modules for x in ['torch','sklearn','integration.runtime','anomaly.residual'])"
        subprocess.run([sys.executable,'-c',code],check=True)
