"""Independent read-only visibility observer and final business integrity checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from sqlalchemy import create_engine,text
from kafka import KafkaConsumer,TopicPartition
from integration.settings import Settings
from performance.telemetry import Sink


def snapshot(engine, settings):
    with engine.connect() as c:
        counts={}
        for table in ('measurements','forecasts','scores','receipts','errors','episodes'):
            counts[table]=c.execute(text('SELECT count(*) FROM mvp_'+table+' WHERE run_id=:run'),{'run':settings.run_id}).scalar_one()
        counts['event_ids']=c.execute(text('SELECT count(DISTINCT event_id) FROM mvp_measurements WHERE run_id=:run'),{'run':settings.run_id}).scalar_one()
        counts['measurement_ids']=c.execute(text('SELECT count(DISTINCT measurement_id) FROM mvp_measurements WHERE run_id=:run'),{'run':settings.run_id}).scalar_one()
        counts['duplicate_deliveries']=c.execute(text("SELECT count(*) FROM mvp_receipts WHERE run_id=:run AND outcome <> 'accepted'"),{'run':settings.run_id}).scalar_one()
        counts['next_offset']=c.execute(text('SELECT next_offset FROM mvp_checkpoints WHERE run_id=:run'),{'run':settings.run_id}).scalar()
        counts['offsets']=list(c.execute(text('SELECT min("offset"),max("offset"),count(DISTINCT "offset") FROM mvp_receipts WHERE run_id=:run'),{'run':settings.run_id}).one())
        counts['rows']=[dict(row) for row in c.execute(text('SELECT measurement_id,event_id,kafka_offset,measurement_timestamp FROM mvp_measurements WHERE run_id=:run ORDER BY kafka_offset'),{'run':settings.run_id}).mappings()]
        # Hash actual stored outputs; no generated_at normalization in immutability checks.
        counts['forecasts_by_id']={r['forecast_id']:hashlib.sha256(json.dumps(dict(r),default=str,sort_keys=True).encode()).hexdigest() for r in c.execute(text('SELECT * FROM mvp_forecasts WHERE run_id=:run ORDER BY forecast_id'),{'run':settings.run_id}).mappings()}
        counts['outputs']=[list(r) for r in c.execute(text('SELECT m.kafka_offset,f.purpose,f.predicted_energy_wh,f.status FROM mvp_forecasts f JOIN mvp_measurements m USING(measurement_id) WHERE f.run_id=:run ORDER BY m.kafka_offset,f.purpose'),{'run':settings.run_id})]
        counts['score_outputs']=[list(r) for r in c.execute(text('SELECT m.kafka_offset,s.detector,s.score,s.flag,s.status FROM mvp_scores s JOIN mvp_measurements m USING(measurement_id) WHERE s.run_id=:run ORDER BY m.kafka_offset,s.detector'),{'run':settings.run_id})]
        counts['scores_by_id']={r['score_id']:hashlib.sha256(json.dumps(dict(r),default=str,sort_keys=True).encode()).hexdigest() for r in c.execute(text('SELECT * FROM mvp_scores WHERE run_id=:run ORDER BY score_id'),{'run':settings.run_id}).mappings()}
        counts['episode_rows']=[dict(r) for r in c.execute(text('SELECT * FROM mvp_episodes WHERE run_id=:run ORDER BY episode_id'),{'run':settings.run_id}).mappings()]
    return counts


def validate(counts, expected):
    failures=[]
    for field,want in dict(measurements=expected,event_ids=expected,measurement_ids=expected,
                           forecasts=2*expected,scores=3*expected,receipts=expected,errors=0,
                           duplicate_deliveries=0,next_offset=expected,broker_next_offset=expected,kafka_end_offset=expected).items():
        if counts.get(field)!=want:
            failures.append(f'{field}: expected {want}, got {counts.get(field)}')
    if counts['offsets']!=[0,expected-1,expected]:
        failures.append('Noncontiguous receipt offsets')
    return failures


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['observe','snapshot'])
    p.add_argument('--interval',type=float,default=.2)
    p.add_argument('--expected',type=int);a=p.parse_args()
    settings=Settings.from_env();engine=create_engine(settings.database_url,pool_pre_ping=True)
    output=Path(os.environ['PERF_OUTPUT'])
    control=Path(os.environ.get('PERF_CONTROL',str(output)))
    if a.command=='snapshot':
        counts=snapshot(engine,settings)
        consumer=KafkaConsumer(bootstrap_servers=settings.bootstrap_servers,group_id=settings.group_id,enable_auto_commit=False)
        tp=TopicPartition(settings.topic,0)
        try:
            counts['broker_next_offset']=consumer.committed(tp)
            counts['kafka_end_offset']=consumer.end_offsets([tp])[tp]
        finally:
            consumer.close(autocommit=False)
        counts['failures']=validate(counts,a.expected) if a.expected is not None else []
        (control/'integrity.json').write_text(json.dumps(counts,default=str,indent=2)+'\n')
        if counts['failures']:
            raise SystemExit('Business integrity check failed')
        return
    sink=Sink(output/'visibility.jsonl');last_offset=-1;previous=time.time_ns();previous_mono=time.perf_counter_ns()
    from performance.clock_domain import domain
    sink.emit('clock_domain',**domain())
    try:
        while not (control/'observer.stop').exists():
            tick=time.perf_counter();lower=previous;lower_mono=previous_mono;begin=time.time_ns();begin_mono=time.perf_counter_ns()
            with engine.connect() as c:
                rows=list(c.execute(text('SELECT measurement_id,event_id,kafka_offset FROM mvp_measurements WHERE run_id=:run AND kafka_offset>:offset ORDER BY kafka_offset'),{'run':settings.run_id,'offset':last_offset}).mappings())
            end_mono=time.perf_counter_ns();end=time.time_ns()
            sink.emit('visibility_poll',start_epoch_ns=begin,end_epoch_ns=end,count=len(rows))
            for row in rows:
                sink.emit('visible',**dict(row),available_lower_ns=lower,available_upper_ns=end,
                          available_lower_mono_ns=lower_mono,available_upper_mono_ns=end_mono)
                last_offset=row['kafka_offset']
            previous=begin;previous_mono=begin_mono
            time.sleep(max(0,a.interval-(time.perf_counter()-tick)))
    finally:
        sink.close();engine.dispose()


if __name__=='__main__':main()
