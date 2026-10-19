"""Verify actual published ports and that worker cannot reach the loopback-only API."""
import json
import subprocess
from integration.demo import compose,environment,ROOT,COMPOSE


def main():
    env=environment()
    command=['docker','compose','--env-file',str(ROOT/'.env.mvp'),'-p',env.get('MVP_COMPOSE_PROJECT','energy-dashboard'),'-f',str(COMPOSE)]
    verified={}
    for service in ('api','postgres','kafka'):
        identity=subprocess.check_output([*command,'ps','-q',service],cwd=ROOT,env=env,text=True).strip()
        if not identity: raise SystemExit(service+' is not running')
        ports=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .NetworkSettings.Ports}}',identity],text=True)) or {}
        bindings=[(port,binding['HostIp']) for port,values in ports.items() for binding in values or []]
        if service=='api':
            if not bindings or any(port!='8080/tcp' or ip!='127.0.0.1' for port,ip in bindings):
                raise SystemExit('Only localhost Dashboard port may be published')
        elif bindings: raise SystemExit(service+' unexpectedly publishes a host port')
        verified[service]=bindings
    code='''import socket
try:
    socket.create_connection(('api',8000),timeout=3)
except OSError:
    print('API port 8000 inaccessible from worker network')
else:
    raise SystemExit('API unexpectedly accessible outside its loopback namespace')
'''
    compose('exec','-T','worker','python','-c',code)
    print(json.dumps({'published_ports':verified,'api_loopback_only':True}))

if __name__=='__main__': main()
