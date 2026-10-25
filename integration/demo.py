"""Local Docker MVP lifecycle. Never deletes volumes or overwrites experiment artifacts."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from integration.settings import ROOT
from integration.setup import main as setup

COMPOSE=ROOT/'docker/docker-compose.dashboard.yml'


def environment():
    env=dict(os.environ)
    env.setdefault('LOCAL_UID',str(os.getuid()))
    env.setdefault('LOCAL_GID',str(os.getgid()))
    # Separate manifest for the container's exact library versions (e.g. CPU torch).
    env['MVP_ARTIFACT_MANIFEST']=env.get('MVP_DOCKER_ARTIFACT_MANIFEST','artifacts/mvp/docker/manifest.json')
    path=Path(env['MVP_ARTIFACT_MANIFEST'])
    if path.is_absolute() or '..' in path.parts or path.parts[:1]!=('artifacts',):
        raise ValueError('MVP_DOCKER_ARTIFACT_MANIFEST must be a repository-relative artifacts/... path')
    return env


def compose_command(env):
    return ['docker','compose','--env-file',str(ROOT/'.env.mvp'),'-p',env.get('MVP_COMPOSE_PROJECT','energy-dashboard'),'-f',str(COMPOSE)]


def compose(*args,check=True,env_overrides=None,**kwargs):
    env={**environment(),**(env_overrides or {})}
    return subprocess.run([*compose_command(env),*args],cwd=ROOT,env=env,check=check,**kwargs)


def prepare(a,build=True,parser=None):
    def fail(message):
        if parser: parser.error(message)
        raise ValueError(message)
    (ROOT/'artifacts').mkdir(exist_ok=True);(ROOT/'data').mkdir(exist_ok=True)
    if build: compose('build','worker','api','dashboard')
    dataset='data/energy/raw/energydata_complete.csv'
    if not (ROOT/dataset).exists():
        compose('run','--rm','--no-deps','tools','python','-m','producer.download_appliances','--output',dataset)
    output=Path(environment()['MVP_ARTIFACT_MANIFEST'])
    if not (ROOT/output).exists():
        if bool(a.hgb)!=bool(a.anomaly): fail('--hgb and --anomaly must be provided together')
        if a.hgb:
            for path in (a.hgb,a.anomaly):
                if path.is_absolute() or '..' in path.parts or path.parts[:1]!=('artifacts',): fail('Use trusted artifacts/... relative paths')
            compose('run','--rm','--no-deps','tools','python','-m','integration.artifacts','register',
                    '--hgb',str(a.hgb),'--anomaly',str(a.anomaly),'--output',str(output))
        else:
            compose('run','--rm','--no-deps','tools','python','-m','integration.artifacts','prepare',
                    '--dataset',dataset,'--output',str(output.parent))
    compose('run','--rm','--no-deps','tools','python','-c',
            'from integration.artifacts import load_manifest; from integration.settings import Settings; load_manifest(Settings.from_env().artifact_manifest); print("Trusted container artifacts ready")')
    print('Ready: python3 -m integration.demo up; then open http://127.0.0.1:'+environment().get('MVP_WEB_PORT','8088'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','up','replay','restart','status','stop','logs','showcase'])
    parser.add_argument('--limit',type=int,default=300)
    parser.add_argument('--sleep',type=float,default=None)
    parser.add_argument('--hgb',type=Path,help='Optional trusted existing HGB artifact (pair with --anomaly)')
    parser.add_argument('--anomaly',type=Path)
    a=parser.parse_args(argv)
    if a.sleep is None: a.sleep=.5 if a.command=='showcase' else .15
    if a.limit<1 or a.sleep<0: parser.error('positive limit and nonnegative sleep required')
    if a.command=='showcase':
        from integration.showcase import run
        return run(a)
    setup()
    if a.command=='prepare':
        prepare(a,parser=parser)
    elif a.command=='up':
        if not (ROOT/environment()['MVP_ARTIFACT_MANIFEST']).exists():
            parser.error('Container artifact manifest missing. First: python3 -m integration.demo prepare')
        compose('up','-d','--wait','--wait-timeout','180')
        print('Dashboard: http://127.0.0.1:'+environment().get('MVP_WEB_PORT','8088'))
    elif a.command=='replay':
        compose('run','--rm','--no-deps','tools','python','-m','integration.replay',
                '--dataset','data/energy/raw/energydata_complete.csv','--limit',str(a.limit),'--sleep',str(a.sleep))
    elif a.command=='restart': compose('restart','worker','dashboard')
    elif a.command=='status': compose('ps')
    elif a.command=='stop': compose('stop')
    elif a.command=='logs': compose('logs','--tail','80','worker','api','dashboard')

if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError as exc: sys.exit(exc.returncode)
    except ValueError as exc: sys.exit(str(exc))
