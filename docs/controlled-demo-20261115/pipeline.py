"""Container-side paired demo. Always real producer -> worker -> PostgreSQL.
No result inserts: only the unchanged worker writes domain rows.
"""
import argparse,copy,hashlib,json,os
from datetime import datetime,timedelta
from pathlib import Path
from sqlalchemy import create_engine,select,func
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
from alembic import command
from alembic.config import Config
from producer.appliances_dataset import iter_appliances
from processing.energy_schema import validate_energy
from integration.settings import Settings
from integration.energy_worker import run_worker
from integration.processor import payload_digest
from storage.postgres import schema as s
ROOT=Path('/work');PLAN=json.loads((ROOT/'docs/controlled-demo-20261115/plan.json').read_text())

def main():
 p=argparse.ArgumentParser();p.add_argument('--delta',type=int,default=0);a=p.parse_args()
 assert a.delta in [0,*PLAN['candidate_deltas_wh_in_order']]
 settings=Settings.from_env();assert settings.run_id.startswith('controlled-demo-')
 assert os.environ['EMAIL_NOTIFICATIONS_ENABLED']=='false'
 original=list(iter_appliances(ROOT/PLAN['dataset'],start=PLAN['start'],limit=PLAN['records']))
 records=copy.deepcopy(original);changes=[];lo=PLAN['injection_start_index_zero_based'];hi=lo+PLAN['injection_intervals']
 if a.delta:
  for i in range(lo,hi):
   records[i]['energy']['value']+=a.delta
   changes.append(dict(timestamp=records[i]['timestamp'],original_wh=original[i]['energy']['value'],modified_wh=records[i]['energy']['value']))
 assert len(records)==300
 for i,(before,after) in enumerate(zip(original,records)):
  validate_energy(after)
  check=copy.deepcopy(after);check['energy']['value']=before['energy']['value'];assert check==before
  if i:assert datetime.fromisoformat(after['timestamp'])-datetime.fromisoformat(records[i-1]['timestamp'])==timedelta(seconds=600)
 engine=create_engine(settings.database_url)
 config=Config('/work/alembic.ini')
 with engine.begin() as c:config.attributes['connection']=c;command.upgrade(config,'head')
 admin=KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
 assert settings.topic not in admin.list_topics();admin.create_topics([NewTopic(settings.topic,1,1)]);admin.close()
 producer=KafkaProducer(bootstrap_servers=settings.bootstrap_servers);digests=[]
 try:
  for i,row in enumerate(records):
   key=json.dumps([row['building_id'],row['source_id']]).encode();value=json.dumps(row,sort_keys=True,allow_nan=False).encode()
   metadata=producer.send(settings.topic,key=key,value=value).get(timeout=30)
   assert metadata.offset==i;digests.append(payload_digest(key,value))
 finally:producer.close(timeout=30)
 result=run_worker(settings,max_messages=len(records),idle_timeout=10)
 assert result['accepted']==300 and result['processed_deliveries']==300 and result['quarantined']==0
 with engine.connect() as c:
  measurements=[dict(x) for x in c.execute(select(s.measurements).where(s.measurements.c.run_id==settings.run_id).order_by(s.measurements.c.kafka_offset)).mappings()]
  assert len(measurements)==300 and len({r['event_id'] for r in measurements})==300
  for row,raw in zip(measurements,records):assert row['wire_record']==raw
  ledger=[dict(x) for x in c.execute(select(s.receipts).where(s.receipts.c.run_id==settings.run_id).order_by(s.receipts.c.offset)).mappings()]
  assert [x['offset'] for x in ledger]==list(range(300)) and [x['payload_sha256'] for x in ledger]==digests
  assert all(x['outcome']=='accepted' for x in ledger)
  checkpoint=dict(c.execute(select(s.checkpoints).where(s.checkpoints.c.run_id==settings.run_id)).mappings().one());assert checkpoint['next_offset']==300
  scores=[dict(x) for x in c.execute(select(s.scores).where(s.scores.c.run_id==settings.run_id)).mappings()]
  forecasts=[dict(x) for x in c.execute(select(s.forecasts).where(s.forecasts.c.run_id==settings.run_id)).mappings()]
  episodes=[dict(x) for x in c.execute(select(s.episodes).where(s.episodes.c.run_id==settings.run_id)).mappings()]
  combined=[dict(x) for x in c.execute(select(s.combined_decisions).where(s.combined_decisions.c.run_id==settings.run_id)).mappings()]
  combined_events=[dict(x) for x in c.execute(select(s.combined_episodes).where(s.combined_episodes.c.run_id==settings.run_id)).mappings()]
  models=[dict(x) for x in c.execute(select(s.models)).mappings()]
  notification_count=c.execute(select(func.count()).select_from(s.notifications).where(s.notifications.c.run_id==settings.run_id)).scalar_one()
 assert (len(forecasts),len(scores),len(combined),notification_count)==(600,900,300,0)
 consumer=KafkaConsumer(bootstrap_servers=settings.bootstrap_servers,group_id=settings.group_id,enable_auto_commit=False)
 tp=TopicPartition(settings.topic,0)
 assert consumer.end_offsets([tp])[tp]==consumer.committed(tp)==300
 consumer.close(autocommit=False)
 by_score={(x['measurement_id'],x['detector']):x for x in scores};by_combined={x['measurement_id']:x for x in combined}
 by_primary={x['forecast_target_timestamp']:x for x in forecasts if x['purpose']=='primary_forecast'}
 points=[]
 for measurement in measurements:
  mid=measurement['measurement_id'];stamp=measurement['measurement_timestamp'];f=by_primary.get(stamp)
  row={'measurement_id':mid,'timestamp':stamp,'energy_wh':measurement['energy_wh'],'HGB20_target_forecast_wh':f['predicted_energy_wh'] if f else None,'HGB20_forecast_origin':f['forecast_origin'] if f else None,'unanimous_flag':by_combined[mid]['flag'],'unanimous_status':by_combined[mid]['status']}
  for detector in ['isolation_forest','autoencoder','residual']:
   score=by_score[mid,detector]
   for key in ['score','threshold','flag','status']:row[detector+'_'+key]=score[key]
   if detector=='residual':
    row['RF21_target_forecast_wh']=score['prediction_wh'];row['RF21_origin']=score['forecast_origin'];row['RF21_target']=score['forecast_target_timestamp']
    if score['status']=='ready':assert score['forecast_target_timestamp']==stamp and datetime.fromisoformat(score['forecast_origin'])+timedelta(seconds=600)==datetime.fromisoformat(stamp)
  points.append(row)
 report=dict(run_id=settings.run_id,topic=settings.topic,group_id=settings.group_id,delta_wh=a.delta,records=300,start=records[0]['timestamp'],end=records[-1]['timestamp'],intervention_start=records[lo]['timestamp'],intervention_end=records[hi-1]['timestamp'],return_to_original=records[hi]['timestamp'],changes=changes,worker=result,counts=dict(measurements=300,forecasts=600,scores=900,combined_decisions=300,episodes=len(episodes),combined_episodes=len(combined_events),notifications=notification_count),integrity=dict(original_other_fields_unchanged=True,valid_schema=True,ordered_600_seconds=True,wire_records_match=True,unique_event_ids=300,ledger_hashes_match=True,db_checkpoint=300,kafka_committed=300,kafka_end_offset=300),models=models,episodes=episodes,combined_episodes=combined_events,points=points)
 print('DEMO_RESULT='+json.dumps(report,default=str,sort_keys=True,allow_nan=False),flush=True);engine.dispose()
if __name__=='__main__':main()
