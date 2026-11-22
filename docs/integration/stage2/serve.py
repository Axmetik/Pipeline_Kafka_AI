# Reuse the existing isolated read-only API/local reverse proxy pattern.
import threading,urllib.request,urllib.error
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
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
