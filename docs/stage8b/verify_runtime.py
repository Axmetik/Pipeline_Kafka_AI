"""Read-only Stage 8B checks against existing worker DB/Kafka; never runs inference."""
import argparse,csv,hashlib,json,math,time
from collections import Counter
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine,select,text
from kafka import KafkaConsumer,TopicPartition
from integration.settings import Settings
from integration.processor import payload_digest
from storage.postgres import schema as s


def verify(run_id,topic,group_id,expected):
    settings=Settings.from_env();engine=create_engine(settings.database_url,hide_parameters=True)
    tables={'measurements':s.measurements,'forecasts':s.forecasts,'scores':s.scores,'combined_decisions':s.combined_decisions,'episodes':s.episodes,'combined_episodes':s.combined_episodes,'receipts':s.receipts,'checkpoints':s.checkpoints,'notifications':s.notifications,'errors':s.errors}
    with engine.connect() as c,c.begin():
        c.execute(text('SET TRANSACTION READ ONLY'))
        c.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        revision=c.execute(text('select version_num from alembic_version')).scalar_one()
        rows={name:[dict(r) for r in c.execute(select(t).where(t.c.run_id==run_id)).mappings()] for name,t in tables.items()}
        registry=[dict(r) for r in c.execute(select(s.models).where(s.models.c.model_id.in_({f['model_id'] for f in rows['forecasts']}|{f['model_id'] for f in rows['scores']}))).mappings()]
    engine.dispose()
    m=sorted(rows['measurements'],key=lambda r:r['kafka_offset']); fm={r['forecast_id']:r for r in rows['forecasts']}
    mm={r['measurement_id']:r for r in m}; sm={r['measurement_id']:[] for r in m}
    assert revision=='0003_email'
    assert len(m)==expected and len(rows['forecasts'])==2*expected and len(rows['scores'])==3*expected and len(rows['combined_decisions'])==expected
    assert len({r['event_id'] for r in m})==expected and [r['kafka_offset'] for r in m]==list(range(expected))
    assert not rows['errors'] and len(rows['receipts'])==expected and all(r['outcome']=='accepted' for r in rows['receipts'])
    assert len(rows['checkpoints'])==1 and rows['checkpoints'][0]['next_offset']==expected
    assert all(r['time_basis']=='dataset_naive' and r['timezone'] is None and r['interval_seconds']==600 and r['measurement_time_utc'] is None for r in m)
    with open('/app/data/energy/raw/energydata_complete.csv') as f:
        original=list(csv.DictReader(f))[:expected]
    assert len(original)==expected
    for a,b in zip(m,original):
        assert datetime.fromisoformat(a['measurement_timestamp'])==datetime.fromisoformat(b['date'])
        assert a['energy_wh']==float(b['Appliances'])
    for f in rows['forecasts']:
        assert f['forecast_origin']==mm[f['measurement_id']]['measurement_timestamp']
        assert (datetime.fromisoformat(f['forecast_target_timestamp'])-datetime.fromisoformat(f['forecast_origin'])).total_seconds()==f['horizon_seconds']==600
        assert (f['predicted_energy_wh'] is None)==(f['status']!='ready')
    for score in rows['scores']:
        assert score['maturity']=='experimental'
        assert (score['score'] is None)==(score['status']!='ready')
        assert (score['flag'] is None)==(score['score'] is None)
        if score['score'] is not None:assert score['flag']==(score['score']>score['threshold'])
        sm[score['measurement_id']].append(score)
        if score['detector']=='residual' and score['status']=='ready':
            ref=fm[score['reference_forecast_id']];actual=mm[score['measurement_id']]
            assert ref['purpose']=='residual_reference' and ref['forecast_target_timestamp']==actual['measurement_timestamp']
            assert ref['forecast_origin']==score['forecast_origin'] and ref['generated_at']==score['reference_generated_at']
            assert math.isclose(abs(actual['energy_wh']-ref['predicted_energy_wh']),score['score'],abs_tol=1e-8)
            assert ref['generated_at']<=actual['received_at']
    for d in rows['combined_decisions']:
        available=[v for v in sm[d['measurement_id']] if v['status']=='ready' and v['flag'] is not None]
        assert d['coverage_count']==len(available) and d['rule']=='unanimous'
        if len(available)==3:
            votes=sum(v['flag'] for v in available)
            assert d['trigger_count']==votes and d['flag']==(votes==3)
        else:assert d['trigger_count'] is None and d['flag'] is None
    receipt={r['offset']:r['payload_sha256'] for r in rows['receipts']}
    consumer=KafkaConsumer(bootstrap_servers=settings.bootstrap_servers,enable_auto_commit=False,group_id=group_id)
    tp=TopicPartition(topic,0);consumer.assign([tp]);begin=consumer.beginning_offsets([tp])[tp];end=consumer.end_offsets([tp])[tp];committed=consumer.committed(tp)
    assert (begin,end,committed)==(0,expected,expected)
    consumer.seek(tp,0);seen={};deadline=time.monotonic()+30
    while len(seen)<expected and time.monotonic()<deadline:
        for record in consumer.poll(timeout_ms=1000,max_records=500).get(tp,[]):
            assert payload_digest(record.key,record.value)==receipt[record.offset]
            raw=json.loads(record.value)
            assert raw['event_id']==m[record.offset]['event_id']
            seen[record.offset]=True
    consumer.close(autocommit=False);assert len(seen)==expected
    groups=lambda key,field:[{key:k,'rows':len(v),'ready':sum(r['status']=='ready' for r in v),'null_values':sum(r[field] is None for r in v),'states':dict(Counter(r['status'] for r in v))} for k in sorted({r[key] for r in rows['forecasts' if key=='purpose' else 'scores']}) for v in [[r for r in rows['forecasts' if key=='purpose' else 'scores'] if r[key]==k]]]
    def signature(name,key):return hashlib.sha256(json.dumps(sorted(rows[name],key=lambda r:r[key]),sort_keys=True,default=str).encode()).hexdigest()
    return {'run_id':run_id,'revision':revision,'counts':{n:len(v) for n,v in rows.items()},'unique_event_ids':len({r['event_id'] for r in m}),'kafka':{'topic':topic,'group_id':group_id,'begin_offset':begin,'end_offset':end,'committed_offset':committed,'journal_payloads_verified':len(seen)},'forecast_states':groups('purpose','predicted_energy_wh'),'score_states':groups('detector','score'),'combined_states':dict(Counter(r['status'] for r in rows['combined_decisions'])),'combined_flags':sum(r['flag'] is True for r in rows['combined_decisions']),'original_flags_by_detector':dict(Counter(r['detector'] for r in rows['scores'] if r['flag'] is True)),'episodes':[{'detector':r['detector'],'status':r['status'],'flagged_points':r['flagged_points'],'start':r['start_timestamp'],'end':r['end_timestamp']} for r in rows['episodes']],'time_range':[m[0]['measurement_timestamp'],m[-1]['measurement_timestamp']],'model_registry':registry,'persisted_forecasts_sha256':signature('forecasts','forecast_id'),'persisted_scores_sha256':signature('scores','score_id'),'checks':{'dataset_values_exact':True,'forecast_target_alignment_600s':True,'residual_uses_preceding_forecast':True,'combined_unanimous_and_coverage':True,'kafka_db_checkpoint_and_payloads':True,'dataset_naive_semantics':True,'no_duplicates_or_rejections':True}}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-id',required=True);p.add_argument('--topic',required=True);p.add_argument('--group-id',required=True);p.add_argument('--expected',type=int,default=300);a=p.parse_args()
    print(json.dumps(verify(a.run_id,a.topic,a.group_id,a.expected),indent=2,default=str))
