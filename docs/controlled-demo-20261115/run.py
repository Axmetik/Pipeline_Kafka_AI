"""Run the bounded paired demonstration in disposable, uniquely named services.
Prerequisites: existing trusted Docker artifacts/images, built dashboard and Chrome.
Does not build images, train, use the work DB, or start a notifier.
"""
import argparse,ast,csv,hashlib,json,os,subprocess,tempfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
PLAN=json.loads((OUT/'plan.json').read_text())
def execute(args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def hashes():
 paths=[PLAN['dataset'],'artifacts/mvp/docker/manifest.json','artifacts/mvp/docker/hgb/model.joblib','artifacts/mvp/docker/bundle.joblib','configs/combined-rule-v1.json']
 return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
def proxy_template():
 tree=ast.parse((ROOT/'tests/source_catalog_browser.py').read_text())
 return next(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and 'uvicorn.run(' in n.value and 'ThreadingHTTPServer' in n.value)
def main():
 global OUT
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args();OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=True)
 if (OUT/'execution.json').exists():raise SystemExit('Evidence already exists. Use a new evidence copy/directory; do not overwrite a completed demonstration.')
 assert (ROOT/'dashboard/dist/index.html').is_file(),'Build this branch frontend first; never rebuild the main Docker project'
 before=hashes();key=uuid.uuid4().hex[:8];net='controlled-demo-'+key;pg=net+'-pg';kafka=net+'-kafka';api=net+'-api'
 reports=[];chosen=None;worker_names=[];started=time.monotonic()
 with tempfile.TemporaryDirectory(prefix='controlled-demo-') as temp:
  Path(temp).chmod(0o755);Path(temp,'serve.py').write_text(proxy_template())
  try:
   execute(['docker','network','create',net],stdout=subprocess.DEVNULL)
   execute(['docker','run','-d','--pull','never','--name',pg,'--network',net,'--memory','512m','--cpus','1','--tmpfs','/var/lib/postgresql:size=256m','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:18-alpine'],stdout=subprocess.DEVNULL)
   env={'KAFKA_NODE_ID':'1','KAFKA_PROCESS_ROLES':'broker,controller','KAFKA_LISTENERS':'INTERNAL://:29092,CONTROLLER://:9093','KAFKA_ADVERTISED_LISTENERS':'INTERNAL://kafka:29092','KAFKA_LISTENER_SECURITY_PROTOCOL_MAP':'INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT','KAFKA_INTER_BROKER_LISTENER_NAME':'INTERNAL','KAFKA_CONTROLLER_LISTENER_NAMES':'CONTROLLER','KAFKA_CONTROLLER_QUORUM_VOTERS':'1@kafka:9093','KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR':'1','KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR':'1','KAFKA_TRANSACTION_STATE_LOG_MIN_ISR':'1','KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS':'0','KAFKA_AUTO_CREATE_TOPICS_ENABLE':'false','KAFKA_HEAP_OPTS':'-Xms256m -Xmx256m','KAFKA_LOG_DIRS':'/tmp/demo-kafka-logs'}
   kafka_args=['docker','run','-d','--pull','never','--name',kafka,'--network',net,'--network-alias','kafka','--memory','1g','--cpus','1']
   for k,v in env.items():kafka_args+=['-e',k+'='+v]
   execute([*kafka_args,'apache/kafka:3.9.0'],stdout=subprocess.DEVNULL)
   for _ in range(50):
    if subprocess.run(['docker','exec',pg,'pg_isready','-U','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0 and subprocess.run(['docker','exec',kafka,'/opt/kafka/bin/kafka-topics.sh','--bootstrap-server','kafka:29092','--list'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
    time.sleep(1)
   else:raise RuntimeError('Private infrastructure did not become ready')
   common=['--pull','never','--network',net,'--read-only','--memory','2g','--cpus','1','--tmpfs','/tmp:size=128m','-e','PYTHONPATH=/work','-e','PYTHONDONTWRITEBYTECODE=1','-e','OMP_NUM_THREADS=1','-e','OPENBLAS_NUM_THREADS=1','-e','EMAIL_NOTIFICATIONS_ENABLED=false','-e','MVP_BOOTSTRAP_SERVERS=kafka:29092','-e','MVP_ARTIFACT_MANIFEST=/work/artifacts/mvp/docker/manifest.json','-e',f'MVP_DATABASE_URL=postgresql+psycopg://postgres@{pg}:5432/postgres','-v',str(ROOT)+':/work:ro','-v',temp+':/checks:ro','-w','/work']
   for delta in [0,*PLAN['candidate_deltas_wh_in_order']]:
    name='control' if delta==0 else f'plus-{delta}';run_id=net+'-'+name
    print('Running real Kafka -> ML worker -> PostgreSQL:',name,flush=True)
    worker_name=run_id+'-worker';worker_names.append(worker_name)
    args=['docker','run','--rm','--name',worker_name,*common]
    for variable in ['MVP_RUN_ID','MVP_GROUP_ID','MVP_TOPIC']:args+=['-e',variable+'='+run_id]
    result=execute([*args,'energy-monitoring-backend:local','python','docs/controlled-demo-20261115/pipeline.py','--delta',str(delta)],cwd=ROOT,capture_output=True,text=True,timeout=300)
    lines=result.stdout.splitlines();markers=[line for line in lines if line.startswith('DEMO_RESULT=')];assert len(markers)==1
    report=json.loads(markers[0].split('=',1)[1]);points=report.pop('points');report['points_file']=name+'-points.csv'
    with (OUT/report['points_file']).open('w') as f:
     writer=csv.DictWriter(f,fieldnames=list(points[0]),lineterminator="\n");writer.writeheader();writer.writerows(points)
    (OUT/(name+'-worker.log')).write_text('\n'.join(line for line in lines if not line.startswith('DEMO_RESULT='))+'\n'+result.stderr)
    reports.append(report)
    if delta==0:control=points
    else:
     additional={method:[p['timestamp'] for p,q in zip(points,control) if report['intervention_start']<=p['timestamp']<=report['intervention_end'] and p[method+'_flag'] is True and q[method+'_flag'] is not True] for method in ['isolation_forest','autoencoder','residual','unanimous']}
     report['additional_positive_timestamps_during_injection']=additional
     if any(additional.values()):chosen=report;break
    (OUT/(name+'-summary.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
   if chosen is None:chosen=reports[-1]
   for report in reports:
    name='control' if report['delta_wh']==0 else 'plus-'+str(report['delta_wh'])
    (OUT/(name+'-summary.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
   execute(['docker','run','-d','--name',api,*common,'-p','127.0.0.1::8099','energy-monitoring-backend:local','python','/checks/serve.py'],stdout=subprocess.DEVNULL)
   binding=subprocess.check_output(['docker','port',api,'8099/tcp'],text=True).strip();assert binding.startswith('127.0.0.1:')
   context={'control_run':reports[0]['run_id'],'selected_run':chosen['run_id'],'selected_delta_wh':chosen['delta_wh'],'reports':['control-summary.json',f"plus-{chosen['delta_wh']}-summary.json"],'building_id':PLAN['building_id'],'source_id':PLAN['source_id'],'view_window_measurements':144}
   (OUT/'context.json').write_text(json.dumps(context,indent=2)+'\n')
   execute(['node','docs/controlled-demo-20261115/browser.mjs'],cwd=ROOT,env={**os.environ,'CONTROLLED_DEMO_BASE':'http://'+binding,'CONTROLLED_DEMO_OUTPUT':str(OUT)})
   execute(['python3',str(Path(__file__).with_name('analyze.py')),'--input',str(OUT)],stdout=subprocess.DEVNULL)
   assert hashes()==before,'Original dataset/model/config changed'
   execution={'completed':True,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'plan_sha256':hashlib.sha256((OUT/'plan.json').read_bytes()).hexdigest(),'inputs_sha256_unchanged':before,'attempted_deltas_wh':[r['delta_wh'] for r in reports if r['delta_wh']],'planned_not_executed_deltas_wh':[d for d in PLAN['candidate_deltas_wh_in_order'] if d not in [r['delta_wh'] for r in reports]],'selected_delta_wh':chosen['delta_wh'],'elapsed_wall_seconds_including_setup_browser':time.monotonic()-started,'not_a_performance_benchmark':True,'main_environment_untouched':True,'notifier_started':False,'rules_integrated':['combined-q99-v1-unanimous']}
   (OUT/'execution.json').write_text(json.dumps(execution,indent=2)+'\n');print(json.dumps(execution),flush=True)
  except subprocess.CalledProcessError as exc:
   (OUT/'failure.log').write_text((exc.stdout or '')+'\n'+(exc.stderr or ''));raise
  finally:
   for name in (*worker_names,api,kafka,pg):subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   subprocess.run(['docker','network','rm',net],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if __name__=='__main__':main()
