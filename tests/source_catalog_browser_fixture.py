"""Isolated UI fixture; imports saved values, never loads or predicts a model."""
import hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pyarrow.parquet as pq
from sqlalchemy import create_engine,select,update
from alembic import command
from alembic.config import Config
from storage.postgres import schema as s
from test_source_catalog_api import SourceCatalogAPI

engine=create_engine(os.environ['MVP_DATABASE_URL'])
config=Config('alembic.ini')
with engine.begin() as c:
 config.attributes['connection']=c;command.upgrade(config,'head')
fixture=SourceCatalogAPI('test_identity_latest_and_scope');fixture.engine=engine;fixture.seed()
root=Path.cwd()
hgb_file=root/'artifacts/mvp/docker/hgb/test_predictions.parquet'
score_file=root/'docs/energy-anomaly/results/scores/test-clean.parquet'
meta=json.loads((root/'artifacts/mvp/docker/hgb/metadata.json').read_text())
ameta=json.loads((root/'docs/energy-anomaly/results/model_metadata.json').read_text())
thresholds=json.loads((root/'docs/energy-anomaly/results/thresholds.json').read_text())['0.99']
rows=pq.read_table(hgb_file).slice(1,144).to_pylist()
scores={r['measurement_timestamp']:r for r in pq.read_table(score_file).to_pylist()}
now=datetime(2026,11,15,tzinfo=timezone.utc) # Operational timestamps are fixture-only, not archived inference times.
run='source-saved-review';building='appliances-house-1';source='uci-appliances'
with engine.begin() as c:
 c.execute(s.runs.insert().values(run_id=run,group_id=run,topic=run,cluster_id='isolated',manifest_sha256='a'*64,config={'fixture':'saved UCI/HGB20/Stage4 values; no inference'},created_at=now))
 c.execute(s.sources.insert().values(building_id=building,source_id=source,binding=meta['allowed_sources'][0]))
 for role in ['primary_forecast','isolation_forest','autoencoder','residual']:
  primary=role=='primary_forecast'
  c.execute(s.models.insert().values(model_id='review-'+role,artifact_sha256='review-'+role,role=role,model_version=meta['model_version'] if primary else ameta['model_version'],feature_version='energy-features-v1' if primary else ('benchmark-energy-v1' if role=='residual' else 'energy-anomaly-20-v1'),threshold_version=None if primary else ameta['threshold_version'],maturity='existing' if primary else 'experimental',details={'saved_fixture':True}))
 for i,row in enumerate(rows):
  stamp=row['forecast_origin'];mid='review-'+str(i);dt=datetime.fromisoformat(stamp)
  c.execute(s.measurements.insert().values(measurement_id=mid,run_id=run,building_id=building,source_id=source,event_id=stamp,kafka_offset=i,measurement_timestamp=stamp,measurement_time_local=dt,measurement_time_utc=None,time_basis='dataset_naive',timezone=None,timestamp_reference='dataset_label',interval_seconds=600,energy_wh=row['baseline_energy_wh'],environment={},wire_record={},normalized_sha256='a'*64,compatible=True,feature_status='ready',gap_detected=False,received_at=now))
  c.execute(s.forecasts.insert().values(forecast_id=mid+'-hgb',measurement_id=mid,run_id=run,model_id='review-primary_forecast',purpose='primary_forecast',model_version=meta['model_version'],feature_version='energy-features-v1',forecast_origin=stamp,forecast_target_timestamp=row['forecast_target_timestamp'],target_time_local=datetime.fromisoformat(row['forecast_target_timestamp']),target_time_utc=None,generated_at=now,predicted_energy_wh=row['predicted_energy_wh'],status='ready',horizon_seconds=600))
  score=scores[stamp]
  assert score['actual_energy_wh']==row['baseline_energy_wh']
  for detector in ['isolation_forest','autoencoder','residual']:
   c.execute(s.scores.insert().values(score_id=mid+'-'+detector,measurement_id=mid,run_id=run,model_id='review-'+detector,detector=detector,model_version=ameta['model_version'],feature_version='benchmark-energy-v1' if detector=='residual' else 'energy-anomaly-20-v1',threshold_version=ameta['threshold_version'],maturity='experimental',score=score[detector],threshold=thresholds[detector],flag=score[detector]>thresholds[detector],status='ready',scored_at=now,prediction_wh=score['prediction_wh'] if detector=='residual' else None,signed_residual_wh=score['signed_residual_wh'] if detector=='residual' else None,forecast_origin=score['forecast_origin'] if detector=='residual' else None,forecast_target_timestamp=score['forecast_target_timestamp'] if detector=='residual' else None))
 # A deliberately labeled functional episode/outbox fixture; no delivery process is started.
 stamp=rows[0]['forecast_origin']
 c.execute(s.episodes.insert().values(episode_id='review-functional-episode',run_id=run,building_id=building,source_id=source,model_id='review-residual',detector='residual',model_version=ameta['model_version'],feature_version='benchmark-energy-v1',threshold_version=ameta['threshold_version'],maturity='experimental',start_measurement_id='review-0',end_measurement_id='review-0',start_timestamp=stamp,end_timestamp=stamp,flagged_points=1,status='closed',closed_reason='fixture'))
 c.execute(s.notifications.insert().values(notification_id='review-functional-mail',episode_id='review-functional-episode',run_id=run,building_id=building,source_id=source,kind='individual',method='residual',recipient='fixture@example.invalid',config_fingerprint='a'*64,payload={},status='suppressed',attempt_count=0,suppression_reason='notifications_disabled'))
 c.execute(update(s.measurements).where(s.measurements.c.measurement_id=='other-id').values(feature_status='incompatible',compatible=False))
 binding=c.execute(select(s.sources.c.binding).where(s.sources.c.building_id=='house',s.sources.c.source_id=='dataset')).scalar_one()
 c.execute(s.sources.insert().values(building_id='house',source_id='warmup-fixture',binding=binding))
 measurement=dict(c.execute(select(s.measurements).where(s.measurements.c.measurement_id=='run-a-dataset-0')).mappings().one())
 measurement.update(measurement_id='warmup-fixture',source_id='warmup-fixture',energy_wh=0)
 c.execute(s.measurements.insert().values(**measurement))
 forecast=dict(c.execute(select(s.forecasts).where(s.forecasts.c.forecast_id=='run-a-dataset-0-primary_forecast')).mappings().one())
 forecast.update(forecast_id='warmup-fixture',measurement_id='warmup-fixture')
 c.execute(s.forecasts.insert().values(**forecast))
# Long composite identifiers are confined to this disposable fixture.
with engine.begin() as c:
 long_source='source-'+('long-identifier-'*8)
 long_building='building-'+('wide-context-'*7)
 c.execute(s.sources.insert().values(building_id=long_building,source_id=long_source,binding=binding))
 measurement.update(measurement_id='long-identifiers-fixture',source_id=long_source,building_id=long_building)
 c.execute(s.measurements.insert().values(**measurement))
print(json.dumps({'saved_points':len(rows),'hgb_sha256':hashlib.sha256(hgb_file.read_bytes()).hexdigest(),'score_sha256':hashlib.sha256(score_file.read_bytes()).hexdigest(),'no_inference':True,'isolated_only':True,'operational_timestamps':'fixture only; not archived generation/receipt times','episode_and_outbox':'synthetic functional fixtures; no sending'},indent=2))
engine.dispose()
