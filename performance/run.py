"""Resumable, isolated Docker performance runs. Does not train or change models."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/system-performance-v1.json'


def instrumentation_digest():
    digest=hashlib.sha256()
    for path in sorted((ROOT/'performance').glob('*.py'))+[ROOT/'performance/browser.cjs',ROOT/'dashboard/src/useMonitor.ts']:
        digest.update(path.name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()


def execute(command, *, env=None, timeout=None, log=None):
    result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=timeout)
    if log:
        with Path(log).open('a') as stream:
            # Commands contain paths/IDs, never DB credentials. Avoid verbose
            # Compose config or inspect Config.Env, including on failure.
            stream.write(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {command[0:3]}; see private-safe run log')
    return result.stdout.strip()


def get(url):
    with urllib.request.urlopen(url,timeout=10) as response:
        return json.load(response)


class Run:
    def __init__(self, label, mode, warmup, measured, instrumented=True):
        self.config=json.loads(CONFIG.read_text())
        token=datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%S')+'-'+uuid.uuid4().hex[:6]
        self.id='s6-'+label+'-'+mode+'-'+token
        self.directory=ROOT/'docs/stage6/raw'/self.id
        self.directory.mkdir(parents=True)
        self.env={**os.environ,'MVP_RUN_ID':self.id,'MVP_GROUP_ID':self.id,'MVP_TOPIC':self.id,
                  'MVP_ARTIFACT_MANIFEST':self.config['manifest'],'MVP_WEB_PORT':'8089',
                  'LOCAL_UID':str(os.getuid()),'LOCAL_GID':str(os.getgid()),'PERF_RUN_DIR':str(self.directory)}
        self.command=['docker','compose','--env-file',str(ROOT/'.env.mvp'),'-p',self.id,
                      '-f',str(ROOT/'docker/docker-compose.dashboard.yml'),'-f',str(ROOT/'docker/docker-compose.performance.yml')]
        if not instrumented:
            override=self.directory/'baseline.json'
            override.write_text(json.dumps({'services':{'worker':{'command':['python','-m','integration.energy_worker']}}}))
            self.command+=['-f',str(override)]
        self.manifest=dict(run_id=self.id,mode=mode,label=label,warmup=warmup,measured=measured,
                           sleep=self.config['modes'][mode],instrumented=instrumented,
                           protocol='stage6-v1',status='created',started_at=datetime.now(timezone.utc).isoformat())
        self.manifest['config_sha256']=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
        self.manifest['instrumentation_sha256']=instrumentation_digest()
        self.manifest['manifest_sha256']=hashlib.sha256((ROOT/self.config['manifest']).read_bytes()).hexdigest()
        self.stop=threading.Event();self.children=[]
        self.save()

    def save(self):
        (self.directory/'run.json').write_text(json.dumps(self.manifest,indent=2)+'\n')

    def compose(self,*args,timeout=240):
        return execute([*self.command,*args],env=self.env,timeout=timeout,log=self.directory/'containers.log')

    def child(self,command,log):
        stream=(self.directory/log).open('a')
        process=subprocess.Popen(command,cwd=ROOT,env=self.env,stdout=stream,stderr=subprocess.STDOUT)
        stream.close();self.children.append(process)
        return process

    def wait_count(self,count):
        deadline=time.monotonic()+self.config['drain_timeout_seconds']
        while time.monotonic()<deadline:
            try:
                status=get('http://127.0.0.1:8089/api/pipeline-status?run_id='+self.id)
                if status['rejected_messages'] or status['duplicate_deliveries']:
                    raise RuntimeError('Unexpected rejected/duplicate delivery')
                if status['unique_measurements']==count and status['checkpoints'][0]['next_offset']==count:
                    return status
            except (OSError,KeyError,IndexError):
                pass
            time.sleep(.1)
        raise TimeoutError('Drain deadline exceeded')

    def replay(self,start,count,delay,phase):
        self.compose('run','--rm','--no-deps','tools','python','-m','performance.replay',
                     '--start',str(start),'--count',str(count),'--sleep',str(delay),'--phase',phase,
                     timeout=max(180,count*(delay+.5)+900))

    def resources(self):
        with (self.directory/'resources.jsonl').open('a') as stream:
            while not self.stop.is_set():
                start=time.monotonic()
                try:
                    ids=execute(['docker','ps','-q','--filter','label=com.docker.compose.project='+self.id],env=self.env).splitlines()
                    output=execute(['docker','stats','--no-stream','--format','{{json .}}',*ids],timeout=15)
                    for line in output.splitlines():
                        row=json.loads(line)
                        stream.write(json.dumps(dict(kind='resource',epoch_ns=time.time_ns(),**row))+'\n')
                    stream.flush()
                except Exception as exc:
                    stream.write(json.dumps({'kind':'resource_error','error':type(exc).__name__})+'\n')
                self.stop.wait(max(0,1-(time.monotonic()-start)))

    def browser(self):
        api=self.compose('ps','-q','api')
        command=['docker','run','--rm','--init','--shm-size=1g','--network','container:'+api,
                 '--label','com.docker.compose.project='+self.id,'--name',self.id+'-browser',
                 '-v',str(self.directory)+':/evaluation','-e','PERF_OUTPUT=/evaluation',
                 '-e','MVP_RUN_ID='+self.id,'-e','PERF_ENABLED='+str(int(self.manifest['instrumented'])),
                 'energy-performance-browser:local']
        process=self.child(command,'browser.log')
        deadline=time.monotonic()+60
        while not (self.directory/'browser.ready').exists():
            if process.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('Browser did not become ready; see browser.log')
            time.sleep(.2)

    def api_load(self,clients):
        api=self.compose('ps','-q','api')
        return self.child(['docker','run','--rm','--network','container:'+api,
            '--label','com.docker.compose.project='+self.id,'--name',self.id+'-http',
            '-v',str(ROOT/'performance')+':/app/performance:ro',
            '-v',str(self.directory)+':/evaluation','-e','PERF_OUTPUT=/evaluation',
            '-e','MVP_RUN_ID='+self.id,'energy-monitoring-backend:local',
            'python','-m','performance.api_load','--clients',str(clients)],'http.log')

    def watch_recovery(self,start):
        path=self.directory/'worker.jsonl'
        while not self.stop.is_set():
            if path.exists():
                for line in path.read_text().splitlines():
                    try:row=json.loads(line)
                    except ValueError:continue
                    if row.get('kind')=='message' and row['offset']>=self.manifest['warmup']:
                        self.manifest['recovery_resumed_observed_ns']=time.monotonic_ns()-start
                        self.manifest['recovery_first_db_ack_epoch_ns']=row['db_ack_epoch_ns']
                        self.save();return
            self.stop.wait(.01)

    def watch_measured_start(self):
        path=self.directory/'measured.start'
        while not self.stop.is_set():
            if path.exists():
                self.manifest['publication_observed_mono_ns']=time.monotonic_ns()
                return
            self.stop.wait(.01)

    def run(self,recovery=False,api_clients=None):
        resources=None
        try:
            self.manifest['status']='starting';self.save()
            self.compose('up','-d','--wait','--wait-timeout','240')
            ids=self.compose('ps','-q','worker','postgres','kafka','api','dashboard').splitlines()
            details=execute(['docker','inspect','--format',
                '{{json .Name}} {{json .Image}} {{json .HostConfig.NanoCpus}} {{json .HostConfig.Memory}} {{json .HostConfig.CpusetCpus}}',*ids],env=self.env)
            (self.directory/'container-limits.txt').write_text(details+'\n')
            if self.manifest['instrumented']:
                self.child([*self.command,'run','--rm','--no-deps','tools','python','-m','performance.database','observe'],'observer.log')
            self.browser()
            resources=threading.Thread(target=self.resources,daemon=True);resources.start()
            self.replay(0,self.manifest['warmup'],0,'warmup')
            self.wait_count(self.manifest['warmup'])
            if recovery:
                self.compose('run','--rm','--no-deps','tools','python','-m','performance.database','snapshot')
                before=json.loads((self.directory/'integrity.json').read_text())
                (self.directory/'before-restart.json').write_text(json.dumps(before,indent=2)+'\n')
                start=time.monotonic_ns();epoch=time.time_ns()
                threading.Thread(target=self.watch_recovery,args=(start,),daemon=True).start()
                self.compose('restart','worker')
                self.manifest['recovery_start_epoch_ns']=epoch
                self.manifest['restart_command_ns']=time.monotonic_ns()-start
            self.manifest['status']='measuring';self.save()
            start=time.monotonic_ns()
            self.manifest['measured_start_epoch_ns']=time.time_ns();self.save()
            threading.Thread(target=self.watch_measured_start,daemon=True).start()
            http=self.api_load(api_clients) if api_clients else None
            if self.manifest['measured']:
                self.replay(self.manifest['warmup'],self.manifest['measured'],self.manifest['sleep'],'measured')
            if http is not None:
                if http.wait(timeout=600)!=0:raise RuntimeError('HTTP load process failed')
            self.wait_count(self.manifest['warmup']+self.manifest['measured'])
            self.manifest['measured_duration_ns']=time.monotonic_ns()-start
            if 'publication_observed_mono_ns' in self.manifest:
                self.manifest['observed_completion_duration_ns']=time.monotonic_ns()-self.manifest['publication_observed_mono_ns']
            self.manifest['measured_end_epoch_ns']=time.time_ns()
            time.sleep(5)  # final normal polling cycles, outside throughput timing
            self.compose('run','--rm','--no-deps','tools','python','-m','performance.database','snapshot',
                         '--expected',str(self.manifest['warmup']+self.manifest['measured']))
            if recovery:
                after=json.loads((self.directory/'integrity.json').read_text())
                unchanged=all(after['forecasts_by_id'].get(k)==v for k,v in before['forecasts_by_id'].items())
                if not unchanged:raise RuntimeError('Saved forecasts changed after restart')
                self.manifest['recovery_forecasts_unchanged']=unchanged
                if any(after['scores_by_id'].get(k)!=v for k,v in before['scores_by_id'].items()):
                    raise RuntimeError('Saved scores changed after restart')
                episodes={r['episode_id']:r for r in after['episode_rows']}
                for old in before['episode_rows']:
                    new=episodes.get(old['episode_id'])
                    if new is None or new['start_timestamp']!=old['start_timestamp'] or new['flagged_points']<old['flagged_points']:
                        raise RuntimeError('Episode continuity lost after restart')
                    if old['status']=='closed' and new!=old:raise RuntimeError('Closed episode changed after restart')
                self.manifest['recovery_episode_continuity']=True
            self.manifest['status']='complete'
        except BaseException as exc:
            self.manifest['status']='failed';self.manifest['failure']=str(exc)
            raise
        finally:
            self.stop.set()
            if resources:resources.join(timeout=20)
            for name in ('observer','browser'):(self.directory/(name+'.stop')).touch()
            for process in self.children:
                try:process.wait(timeout=30)
                except subprocess.TimeoutExpired:process.terminate()
            try:self.compose('stop','worker')  # graceful Python exit flushes queue
            except Exception:pass
            self.manifest['ended_at']=datetime.now(timezone.utc).isoformat();self.save()
            from performance.analysis import summarize
            try:
                summarize(self.directory)
                if self.manifest['status']=='complete' and self.manifest['instrumented']:
                    from performance.gate import check
                    issues=check(self.directory)['issues']
                    if issues:
                        self.manifest['status']='failed';self.manifest['failure']='Telemetry validation: '+str(issues)
                        self.save()
                        raise RuntimeError(self.manifest['failure'])
            finally:
                # Cleanup must still happen if post-processing a retained run fails.
                # Only this explicitly unique evaluation project's volumes.
                self.compose('--profile','tools','down','-v','--remove-orphans')
        return self.directory


def environment():
    config=json.loads(CONFIG.read_text())
    checksum=hashlib.sha256((ROOT/config['dataset']).read_bytes()).hexdigest()
    if checksum!=config['dataset_sha256']:raise ValueError('Dataset checksum mismatch')
    result=dict(registered_config=config,host=platform.uname()._asdict(),python=sys.version,
                git=execute(['git','rev-parse','HEAD']),dataset_sha256=checksum,
                manifest=json.loads((ROOT/config['manifest']).read_text()))
    result['docker']=json.loads(execute(['docker','info','--format','{{json .}}']))
    # Whitelist only nonsecret hardware information from docker info.
    result['docker']={k:result['docker'].get(k) for k in ('ServerVersion','NCPU','MemTotal','Architecture','KernelVersion','OperatingSystem')}
    if sys.platform=='darwin':
        hardware=json.loads(execute(['system_profiler','-json','SPHardwareDataType']))['SPHardwareDataType'][0]
        result['host_hardware']={k:hardware.get(k) for k in ('chip_type','physical_memory','number_processors','machine_name','machine_model')}
    else:
        result['host_hardware']={'processor':platform.processor(),'cpu_count':os.cpu_count()}
    result['background_containers']=execute(['docker','ps','--format','{{.Names}} {{.Image}}'])
    result['images']=execute(['docker','image','ls','--digests','--format','{{.Repository}} {{.Tag}} {{.ID}} {{.Digest}}'])
    path=ROOT/'docs/stage6/environment.json';path.write_text(json.dumps(result,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('series',choices=['environment','pilot','overhead','main','recovery','api'])
    p.add_argument('--resume',action='store_true',help='Explicitly skip matching completed runs; failed attempts stay retained')
    args=p.parse_args();config=json.loads(CONFIG.read_text())
    if args.series=='environment':environment();return
    jobs=[]
    if args.series=='pilot':jobs=[('pilot',mode,config['pilot']['warmup'],config['pilot']['measured'],True) for mode in ('slow','demo','max')]
    elif args.series=='overhead':
        jobs=[('overhead-'+config['overhead']['campaign']+'-'+str(i+1), 'max',config['overhead']['warmup'],config['overhead']['measured'],enabled) for i,pair in enumerate(config['overhead']['orders']) for enabled in pair]
    elif args.series=='main':
        if not (ROOT/'docs/stage6/pilot-approved.json').exists():
            raise SystemExit('Pilot gate missing: complete and review pilot + overhead first')
        approved=json.loads((ROOT/'docs/stage6/pilot-approved.json').read_text())
        if (approved.get('config_sha256')!=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
                or approved.get('instrumentation_sha256')!=instrumentation_digest()
                or approved.get('manifest_sha256')!=hashlib.sha256((ROOT/config['manifest']).read_bytes()).hexdigest()):
            raise SystemExit('Configuration/instrumentation/artifact manifest changed since pilot gate; review and validate again')
        jobs=[('main-'+str(i+1),mode,config['warmup'],config['measured'],True) for i,modes in enumerate(config['orders']) for mode in modes]
    elif args.series=='recovery':jobs=[('recovery-'+str(i+1),'demo',config['recovery']['warmup'],config['recovery']['measured'],True) for i in range(5)]
    elif args.series=='api':
        jobs=[('api-'+str(i+1)+'-clients'+str(clients)+'-'+context,'demo',300,3600 if context=='replay' else 0,True)
              for i in range(5) for clients in (1,5) for context in ('idle','replay')]
    for job in jobs:
        previous=[json.loads(p.read_text()) for p in (ROOT/'docs/stage6/raw').glob('*/run.json')]
        matching=[r for r in previous if r['label']==job[0] and r['mode']==job[1] and r['warmup']==job[2]
                  and r['measured']==job[3] and r['instrumented']==job[4] and r['status']=='complete']
        if matching:
            if args.resume:
                print('RETAIN COMPLETED',matching[-1]['run_id'],flush=True);continue
            raise SystemExit('Completed matching run exists. Use --resume explicitly: '+matching[-1]['run_id'])
        print('START',job,flush=True)
        clients=int(job[0].split('clients')[1].split('-')[0]) if args.series=='api' else None
        path=Run(*job).run(recovery=args.series=='recovery',api_clients=clients)
        print('COMPLETE',path,flush=True)


if __name__=='__main__':main()
