"""One bounded paired replay. Creates and RETAINS uniquely owned local services.
Never removes containers/volumes, never rebuilds images, never trains/sends email.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PLAN = json.loads((OUT/'plan.json').read_text())


def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


def write(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str, allow_nan=False)+'\n')


def hashes():
    files = [Path(PLAN['dataset_host'])]
    trusted = Path(PLAN['artifacts_host'])
    files += [trusted/'manifest.json', trusted/'hgb/model.joblib', trusted/'bundle.joblib']
    files += [ROOT/'configs/combined-rule-v1.json', ROOT/'processing/energy_rules.py', ROOT/'integration/rule_layer.py']
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New evidence directory only; never overwrites existing results')
    args = parser.parse_args()
    if args.output is not None:
        OUT = args.output.resolve()
        OUT.mkdir(parents=True, exist_ok=True)
    assert not (OUT/'environment.json').exists(), 'Existing evidence/environment: inspect and reuse, never overwrite/replay automatically'
    sha = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    # Later documentation commits are allowed only when runtime paths are byte-identical to the frozen code.
    if sha != PLAN['code_sha']:
        subprocess.run(['git','diff','--exit-code',PLAN['code_sha'],'HEAD','--',
                        'integration','processing','storage','api','anomaly','ai','producer','configs',
                        'dashboard/src','alembic','alembic-rules','alembic.ini','alembic-rules.ini'], cwd=ROOT, check=True)
    assert not (ROOT/'.env.mvp').exists()
    assert (ROOT/'dashboard/dist/index.html').is_file()
    initial = hashes()
    key = 'ei-stage2-'+uuid.uuid4().hex[:8]
    pg, kafka, api = (key+'-'+role for role in ('pg','kafka','api'))
    env = dict(created_at=datetime.now(timezone.utc).isoformat(), code_sha=sha, prefix=key, network=key,
               postgres=pg, kafka=kafka, api=api, postgres_volume=pg+'-data', kafka_volume=kafka+'-data',
               rules_enabled=True, email_enabled=False, main_environment_modified=False, status='initializing',
               plan_sha256=hashlib.sha256((Path(__file__).with_name('plan.json')).read_bytes()).hexdigest(), inputs_sha256=initial,
               scenarios={name:dict(run_id=key+'-'+name, topic=key+'-'+name, group_id=key+'-'+name) for name in PLAN['scenarios']})
    write('environment.json',env)
    try:
        run(['docker','network','create',key],stdout=subprocess.DEVNULL)
        for volume in (env['postgres_volume'],env['kafka_volume']):
            run(['docker','volume','create',volume],stdout=subprocess.DEVNULL)
        run(['docker','run','-d','--pull','never','--name',pg,'--network',key,'--memory','512m','--cpus','1',
             '-v',env['postgres_volume']+':/var/lib/postgresql','-e','POSTGRES_HOST_AUTH_METHOD=trust',
             'postgres:18-alpine'],stdout=subprocess.DEVNULL)
        kafka_env = dict(KAFKA_NODE_ID='1',KAFKA_PROCESS_ROLES='broker,controller',
            KAFKA_LISTENERS='INTERNAL://:29092,CONTROLLER://:9093',KAFKA_ADVERTISED_LISTENERS='INTERNAL://kafka:29092',
            KAFKA_LISTENER_SECURITY_PROTOCOL_MAP='INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT',
            KAFKA_INTER_BROKER_LISTENER_NAME='INTERNAL',KAFKA_CONTROLLER_LISTENER_NAMES='CONTROLLER',
            KAFKA_CONTROLLER_QUORUM_VOTERS='1@kafka:9093',KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR='1',
            KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR='1',KAFKA_TRANSACTION_STATE_LOG_MIN_ISR='1',
            KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS='0',KAFKA_AUTO_CREATE_TOPICS_ENABLE='false',
            KAFKA_HEAP_OPTS='-Xms256m -Xmx256m',KAFKA_LOG_DIRS='/tmp/stage2-kafka-logs',KAFKA_LOG_RETENTION_HOURS='8760')
        # Apache Kafka runs as uid1000; initialize only this newly owned volume.
        run(['docker','run','--rm','--pull','never','--user','0','--entrypoint','/bin/sh',
             '-v',env['kafka_volume']+':/stage2-volume','apache/kafka:3.9.0','-c','chown 1000:1000 /stage2-volume'])
        args = ['docker','run','-d','--pull','never','--name',kafka,'--network',key,'--network-alias','kafka',
                '--memory','1g','--cpus','1','-v',env['kafka_volume']+':/tmp/stage2-kafka-logs']
        for k,v in kafka_env.items(): args += ['-e',k+'='+v]
        run([*args,'apache/kafka:3.9.0'],stdout=subprocess.DEVNULL)
        for _ in range(60):
            p = subprocess.run(['docker','exec',pg,'pg_isready','-U','postgres'],capture_output=True)
            k = subprocess.run(['docker','exec',kafka,'/opt/kafka/bin/kafka-topics.sh','--bootstrap-server','kafka:29092','--list'],capture_output=True)
            if p.returncode == k.returncode == 0: break
            time.sleep(1)
        else: raise RuntimeError('Isolated infrastructure not ready; retained for diagnosis')
        common = ['--pull','never','--network',key,'--read-only','--memory','2g','--cpus','1','--tmpfs','/tmp:size=128m']
        values = dict(PYTHONPATH='/work',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
            EMAIL_NOTIFICATIONS_ENABLED='false',MVP_ENERGY_RULES_ENABLED='true',MVP_BOOTSTRAP_SERVERS='kafka:29092',
            MVP_ARTIFACT_MANIFEST='/trusted/manifest.json',MVP_DATABASE_URL=f'postgresql+psycopg://postgres@{pg}:5432/postgres')
        for k,v in values.items(): common += ['-e',k+'='+v]
        common += ['-v',str(ROOT)+':/work:ro','-v',PLAN['artifacts_host']+':/trusted:ro',
                   '-v',PLAN['dataset_host']+':/datasets/appliances.csv:ro','-w','/work']
        write('launch-config.json',dict(common_backend_arguments=common,kafka_environment=kafka_env,
            images={i:subprocess.check_output(['docker','image','inspect',i,'--format','{{.Id}}'],text=True).strip()
                    for i in ('energy-monitoring-backend:local','postgres:18-alpine','apache/kafka:3.9.0')},
            dataset_timestamps='dataset_naive', notification_worker_started=False,
            postgres_security='trust only on private Docker network, no published PG/Kafka ports; demo only',
            dashboard_assets_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'dashboard/dist').rglob('*')) if p.is_file()}))
        reports = {}
        for name, ids in env['scenarios'].items():
            print('REAL PAIRED REPLAY',name,flush=True)
            args = ['docker','run','--rm','--name',ids['run_id']+'-worker',*common]
            for field,variable in [('run_id','MVP_RUN_ID'),('topic','MVP_TOPIC'),('group_id','MVP_GROUP_ID')]: args += ['-e',variable+'='+ids[field]]
            result = subprocess.run([*args,'energy-monitoring-backend:local','python','docs/integration/stage2/pipeline.py','--scenario',name],cwd=ROOT,capture_output=True,text=True,timeout=600)
            lines = result.stdout.splitlines()
            (OUT/(name+'-worker.log')).write_text('\n'.join(x for x in lines if not x.startswith('STAGE2_RESULT='))+'\n'+result.stderr)
            result.check_returncode()
            markers = [x for x in lines if x.startswith('STAGE2_RESULT=')]
            assert len(markers) == 1
            report = json.loads(markers[0].split('=',1)[1])
            points = report.pop('points')
            # Full history stays in retained PG/Kafka. Export only the fixed 300-point fragment.
            selected = [x for x in points if x['timestamp'] >= PLAN['original_fragment_start']]
            assert len(selected) == 300
            with (OUT/(name+'-points.csv')).open('w') as f:
                writer = csv.DictWriter(f, fieldnames=list(selected[0]), lineterminator='\n')
                writer.writeheader()
                for row in selected:
                    writer.writerow({k:json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in row.items()})
            report['points_file'] = name+'-points.csv'
            reports[name] = report
            write(name+'-summary.json',report)
        run(['docker','run','-d','--name',api,*common,'-p','127.0.0.1::8099','energy-monitoring-backend:local',
             'python','docs/integration/stage2/serve.py'],stdout=subprocess.DEVNULL)
        binding = subprocess.check_output(['docker','port',api,'8099/tcp'],text=True).strip()
        assert binding.startswith('127.0.0.1:')
        base = 'http://'+binding
        env['base_url'] = base
        for _ in range(40):
            try:
                with urlopen(base+'/health/ready',timeout=5) as response: assert response.status == 200
                break
            except Exception: time.sleep(1)
        else: raise RuntimeError('Isolated API not ready')
        api_checks = {}
        resources = {'measurements':'measurements','forecasts':'forecasts','anomaly-scores':'scores',
                     'rule-assessments':'rule_assessments','hybrid-decisions':'hybrid_decisions',
                     'hybrid-events':'hybrid_episodes','events':'episodes','combined-decisions':'combined_decisions',
                     'combined-events':'combined_episodes','notifications':'notifications'}
        for name, report in reports.items():
            checked = {}
            for endpoint, count_key in resources.items():
                params = dict(run_id=report['run_id'],building_id='appliances-house-1',source_id='uci-appliances',limit=1000)
                count, requests = 0, 0
                while True:
                    with urlopen(base+'/api/'+endpoint+'?'+urlencode(params),timeout=15) as response: page = json.load(response)
                    count += len(page['items']); requests += 1
                    assert all(x['run_id'] == report['run_id'] for x in page['items'])
                    if endpoint in ('rule-assessments','hybrid-decisions','hybrid-events'): assert page['channel_status'] == 'available'
                    if not page['next_cursor']: break
                    params['cursor'] = page['next_cursor']
                assert count == report['counts'][count_key], (name,endpoint,count,report['counts'][count_key])
                checked[endpoint] = dict(rows=count,pages=requests,db_count_matches=True)
            api_checks[name] = checked
        with urlopen(base,timeout=10) as response: assert response.status == 200 and b'<div id="root">' in response.read()
        assert hashes() == initial, 'Original models/dataset/config or production rules changed'
        write('api-checks.json',dict(base_url=base,health_ready=True,production_dashboard_index_served=True,
                                   browser_visual_validation_performed=False,scenarios=api_checks))
        env.update(status='completed_retained',finished_at=datetime.now(timezone.utc).isoformat(),inputs_unchanged=True,
                   worker_status='Both finite replays stopped normally; PG/Kafka/API+Dashboard retained',
                   access={name:base+'/?'+urlencode(dict(run=ids['run_id'],building='appliances-house-1',source='uci-appliances'))+'#analytics' for name,ids in env['scenarios'].items()})
        write('environment.json',env)
        print(json.dumps(dict(status=env['status'],base_url=base,runs=env['scenarios']),indent=2),flush=True)
    except Exception as exc:
        env.update(status='failed_retained',failure=type(exc).__name__+': '+str(exc))
        write('environment.json',env)
        raise


if __name__ == '__main__':
    main()
