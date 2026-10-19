"""Closed-loop HTTP load inside Docker; separate from primary worker trials."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
import urllib.request
from performance.telemetry import Sink


def main():
    p=argparse.ArgumentParser();p.add_argument('--clients',type=int,choices=[1,5],required=True)
    p.add_argument('--requests',type=int,default=1000);p.add_argument('--warmup',type=int,default=50)
    a=p.parse_args();sink=Sink(os.environ['PERF_OUTPUT']+'/http.jsonl')
    paths=['measurements','forecasts','anomaly-scores','events','pipeline-status']
    run=os.environ['MVP_RUN_ID']
    def client(index):
        for i in range(a.warmup+a.requests):
            endpoint=paths[i%len(paths)]
            suffix='' if endpoint=='pipeline-status' else '&limit=100'
            url='http://127.0.0.1:8080/api/'+endpoint+'?run_id='+run+suffix
            start=time.perf_counter_ns();epoch=time.time_ns();error=None;status=None;size=0;timeout=False
            try:
                with urllib.request.urlopen(url,timeout=10) as response:
                    size=len(response.read());status=response.status
            except Exception as exc:
                error=type(exc).__name__
                status=getattr(exc,'code',None)
                timeout=isinstance(exc,TimeoutError) or isinstance(getattr(exc,'reason',None),TimeoutError)
            sink.emit('http',client=index,index=i,phase='warmup' if i<a.warmup else 'measured',
                      endpoint=endpoint,start_epoch_ns=epoch,duration_ns=time.perf_counter_ns()-start,
                      status=status,error=error,timeout=timeout,bytes=size)
    try:
        with ThreadPoolExecutor(max_workers=a.clients) as pool:list(pool.map(client,range(a.clients)))
    finally:sink.close()


if __name__=='__main__':main()
