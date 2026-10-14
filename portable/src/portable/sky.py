import json, os, subprocess, threading, uuid, time, queue
from pathlib import Path
from .engine import UseError

class SkyBackend:
    def __init__(self,node='node'):
        self.bridge=Path(os.environ['CODAKI_SKY_BRIDGE']) if os.environ.get('CODAKI_SKY_BRIDGE') else None
        self.lock=threading.Lock()
        if self.bridge:return
        script=Path(__file__).resolve().parents[1]/'windows/stdio.mjs'
        self.process=subprocess.Popen([node,str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,text=True,encoding='utf-8')
        self.responses=queue.Queue()
        def read():
            for line in self.process.stdout:self.responses.put(line)
            self.responses.put(None)
        threading.Thread(target=read,daemon=True).start()
    def _call(self,name,*args):
        with self.lock:
            ident=uuid.uuid4().hex
            payload=json.dumps({'id':ident,'method':name,'args':args},ensure_ascii=False)
            if self.bridge:
                if not (self.bridge/'bridge.lock').is_file() or (self.bridge/'working.json').exists() or (self.bridge/'request.json').exists():raise UseError('Host bridge unavailable or busy')
                response=self.bridge/'response.json';response.unlink(missing_ok=True)
                temp=self.bridge/'request.tmp';temp.write_text(payload,encoding='utf-8');temp.replace(self.bridge/'request.json')
                deadline=time.monotonic()+30
                while not response.exists():
                    if time.monotonic()>=deadline:raise RuntimeError('Host bridge outcome unknown; do not replay')
                    time.sleep(0.05)
                line=response.read_text(encoding='utf-8');response.unlink()
            else:
                self.process.stdin.write(payload+'\n');self.process.stdin.flush()
                try:line=self.responses.get(timeout=30)
                except queue.Empty:self.process.terminate();raise RuntimeError('Computer Use receipt timeout')
            if not line:raise RuntimeError('Computer Use runtime did not return a receipt')
            data=json.loads(line)
            if 'error' in data:
                e=data['error']
                if e.get('applied') is False:raise UseError(e['message'],e.get('code','REJECTED'))
                raise RuntimeError('Computer Use action outcome unknown')
            if data.get('id')!=ident:raise RuntimeError('Mismatched backend receipt')
            return data['result']
    def capabilities(self):return self._call('capabilities')
    def apps(self):return self._call('apps')
    def start(self,**args):return self._call('start',args)
    def stop(self):return self._call('stop')
    def extend(self,seconds):return self._call('extend',seconds)
    def snapshot(self,screenshot=False):return self._call('snapshot',screenshot)
    def launch(self,app):return self._call('launch',app)
    def action(self,action,observation):return self._call('action',action,observation)
    def diagnostics(self):return self._call('diagnostics')
    def close(self):
        if not self.bridge:self.process.terminate();self.process.wait(timeout=5)
