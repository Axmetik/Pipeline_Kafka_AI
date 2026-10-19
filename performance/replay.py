"""Same dataset adapter, keys and acknowledged publication as Energy producer."""
import argparse
import itertools
import json
import os
from pathlib import Path
import time
from kafka import KafkaProducer
from integration.settings import Settings
from producer.appliances_dataset import iter_appliances
from performance.telemetry import Sink


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start',type=int,default=0)
    p.add_argument('--count',type=int,required=True)
    p.add_argument('--sleep',type=float,default=0)
    p.add_argument('--phase',required=True)
    a=p.parse_args()
    if a.start<0 or a.count<1 or a.sleep<0:
        p.error('Invalid replay bounds')
    settings=Settings.from_env()
    sink=Sink(os.environ['PERF_OUTPUT']+'/producer.jsonl')
    from performance.clock_domain import domain
    sink.emit('clock_domain',**domain())
    producer=KafkaProducer(bootstrap_servers=settings.bootstrap_servers,
                          value_serializer=lambda record:json.dumps(record,allow_nan=False).encode())
    try:
        records=itertools.islice(iter_appliances('data/energy/raw/energydata_complete.csv'),a.start,a.start+a.count)
        sent=0
        for index,record in enumerate(records,a.start):
            if sent and a.sleep:
                time.sleep(a.sleep)
            key=json.dumps([record['building_id'],record['source_id']]).encode()
            epoch=time.time_ns();start=time.perf_counter_ns()
            metadata=producer.send(settings.topic,record,key=key).get(timeout=30)
            sink.emit('publication',index=index,phase=a.phase,event_id=record['event_id'],
                      offset=metadata.offset,partition=metadata.partition,topic=metadata.topic,
                      send_epoch_ns=epoch,send_mono_ns=start,ack_ns=time.perf_counter_ns()-start)
            if sent==0:
                (Path(os.environ.get('PERF_CONTROL',os.environ['PERF_OUTPUT']))/(a.phase+'.start')).write_text('first publication acknowledged\n')
            sent+=1
        if sent!=a.count:
            raise ValueError('Dataset exhausted')
    finally:
        producer.close(timeout=30)
        sink.close()


if __name__=='__main__':
    main()
