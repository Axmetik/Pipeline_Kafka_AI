"""One isolated Processor → PostgreSQL → API → production UI smoke.
Uses existing images, no builds, Kafka campaign, fitting or real model inference.
Temporary containers/network only; no named volumes or existing services touched.
Run: python3 tests/rule_ui_smoke.py
"""
import json, os, subprocess, tempfile, time, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'docs/energy-rules/api-ui-integration-20261109'

def run(args, **kwargs): return subprocess.run(args, check=True, **kwargs)
def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:10]
    net, pg, api = ('rule-ui-'+suffix+x for x in ('-net','-pg','-api'))
    with tempfile.TemporaryDirectory(prefix='rule-ui-') as temp:
        Path(temp).chmod(0o755)
        # Only the temporary facade listens outside loopback *inside* the isolated
        # container. API still sees a loopback proxy and host port binds 127.0.0.1.
        Path(temp, 'serve.py').write_text("""
import threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import uvicorn
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory='/work/dashboard/dist',**kw)
 def do_GET(self):
  if self.path.startswith(('/api/','/health/')):
   try:
    with urllib.request.urlopen('http://127.0.0.1:8000'+self.path,timeout=10) as r:status,body=r.status,r.read()
   except urllib.error.HTTPError as e:status,body=e.code,e.read()
   self.send_response(status);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
  else:super().do_GET()
threading.Thread(target=ThreadingHTTPServer(('0.0.0.0',8099),Handler).serve_forever,daemon=True).start()
uvicorn.run('api.main:create_app',factory=True,host='127.0.0.1',port=8000,log_level='warning')
""")
        try:
            run(['docker','network','create',net],stdout=subprocess.DEVNULL)
            run(['docker','run','-d','--pull','never','--name',pg,'--network',net,'--memory','512m','--cpus','1','--tmpfs','/var/lib/postgresql:size=256m','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:18-alpine'],stdout=subprocess.DEVNULL)
            for _ in range(30):
                if subprocess.run(['docker','exec',pg,'pg_isready','-U','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0: break
                time.sleep(1)
            else: raise RuntimeError('Private PostgreSQL not ready')
            common=['--pull','never','--network',net,'--read-only','--memory','2g','--cpus','1','--tmpfs','/tmp:size=128m','-e','PYTHONPATH=/work','-e','PYTHONDONTWRITEBYTECODE=1','-e','OMP_NUM_THREADS=1','-e','OPENBLAS_NUM_THREADS=1','-e','MKL_NUM_THREADS=1','-e','EMAIL_NOTIFICATIONS_ENABLED=false','-e',f'MVP_DATABASE_URL=postgresql+psycopg://postgres@{pg}:5432/postgres','-v',str(ROOT)+':/work:ro','-v',temp+':/checks:ro','-w','/work']
            run(['docker','run','--rm',*common,'energy-monitoring-backend:local','python','tests/rule_ui_fixture.py','init'])
            run(['docker','run','-d','--name',api,*common,'-p','127.0.0.1::8099','energy-monitoring-backend:local','python','/checks/serve.py'],stdout=subprocess.DEVNULL)
            binding=subprocess.check_output(['docker','port',api,'8099/tcp'],text=True).strip()
            assert binding.startswith('127.0.0.1:')
            env={**os.environ,'RULE_UI_BASE':'http://'+binding,'RULE_UI_CONTAINER':api,'RULE_UI_OUTPUT':str(OUTPUT)}
            run(['node','dashboard/e2e/rule-layer-smoke.mjs'],env=env)
        except Exception:
            subprocess.run(['docker','logs',api],check=False)
            raise
        finally:
            for name in (api,pg):subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['docker','network','rm',net],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

if __name__ == '__main__': main()
