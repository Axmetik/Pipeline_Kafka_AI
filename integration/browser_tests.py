"""Run Chromium in an isolated Linux test image, optionally against the complete MVP."""
import argparse
import os
import subprocess
from integration.demo import ROOT,compose,environment


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--capture',action='store_true')
    a=parser.parse_args()
    subprocess.run(['docker','build','-f','docker/Dockerfile.e2e','-t','energy-dashboard-e2e:local','.'],cwd=ROOT,check=True)
    command=['docker','run','--rm','--init','--shm-size=1g','-v',f'{ROOT}:{ROOT}',
             '-v',f'{ROOT}/dashboard/node_modules','-w',str(ROOT/'dashboard')]
    if a.live:
        env=environment()
        # Find the existing API namespace without printing credentials/config.
        cp=subprocess.run(['docker','compose','--env-file',str(ROOT/'.env.mvp'),'-p',env.get('MVP_COMPOSE_PROJECT','energy-dashboard'),
                           '-f',str(ROOT/'docker/docker-compose.dashboard.yml'),'ps','-q','api'],cwd=ROOT,env=env,check=True,capture_output=True,text=True)
        command+=['--network','container:'+cp.stdout.strip(),'-v',os.getenv('MVP_DOCKER_SOCKET','/var/run/docker.sock')+':/var/run/docker.sock',
                  '-e','DOCKER_HOST=unix:///var/run/docker.sock','-e','E2E_REAL=1','-e','E2E_BASE_URL=http://127.0.0.1:8080']
        for name in ['MVP_RUN_ID','MVP_GROUP_ID','MVP_TOPIC','MVP_COMPOSE_PROJECT','MVP_DOCKER_ARTIFACT_MANIFEST','MVP_WEB_PORT']:
            if name in env: command+=['-e',name+'='+env[name]]
    if a.capture: command+=['-e','E2E_CAPTURE=1']
    command+=['energy-dashboard-e2e:local','sh','-c','npm ci && npm run e2e -- '+('e2e/live.spec.ts' if a.live else 'e2e/contracts.spec.ts')]
    subprocess.run(command,cwd=ROOT,check=True)

if __name__=='__main__': main()
