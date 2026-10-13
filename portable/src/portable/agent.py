import http.client, json, os, random, sqlite3, ssl, time
from pathlib import Path
from urllib.parse import urlsplit
from .engine import UseError
from .network_route import choose_proxy

class Relay:
    def __init__(self,config):
        self.config=config;self.url=urlsplit(config['relay_url']);self.connection=None;self.route=None
        if self.url.scheme!='https' or not self.url.hostname or self.url.username or self.url.password or self.url.query or self.url.fragment:raise ValueError('relay_url must be a clean HTTPS base URL')
        if not isinstance(config.get('agent_token'),str) or len(config['agent_token'])<40:raise ValueError('Private device credential missing')
    def close(self):
        if self.connection:self.connection.close()
        self.connection=None
    def request(self,path,data):
        route=choose_proxy(self.config.get('proxy_url',''))
        if route!=self.route:self.close();self.route=route
        if self.connection is None:
            context=ssl.create_default_context()
            if route:
                p=urlsplit(route)
                if p.scheme!='http' or p.username or p.password or p.path not in ('','/'):raise ValueError('Proxy must be a plain HTTP CONNECT endpoint')
                self.connection=http.client.HTTPSConnection(p.hostname,p.port or 8080,timeout=25,context=context);self.connection.set_tunnel(self.url.hostname,self.url.port or 443)
            else:self.connection=http.client.HTTPSConnection(self.url.hostname,self.url.port or 443,timeout=25,context=context)
        payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
        if len(payload)>4*1024*1024:raise ValueError('Transport payload too large')
        headers={'Authorization':'Bearer '+self.config['agent_token'],'X-Device-ID':self.config['device_id'],'Content-Type':'application/json','Accept':'application/json','User-Agent':'CodakiPortableUse/0.1.1'}
        if self.config.get('site_access_token'):
            headers['OAI-Sites-Authorization']='Bearer '+self.config['site_access_token']
        try:
            self.connection.request('POST',self.url.path.rstrip('/')+path,body=payload,headers=headers)
            r=self.connection.getresponse();raw=r.read(4*1024*1024+1)
            if len(raw)>4*1024*1024 or r.status!=200:raise OSError('Relay did not acknowledge request')
            result=json.loads(raw)
            if not isinstance(result,dict):raise OSError('Malformed relay receipt')
            return result
        except Exception:self.close();raise

class Agent:
    def __init__(self,engine,relay,outbox_path):
        self.engine=engine;self.relay=relay;path=Path(outbox_path);path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path);self.db.execute('CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, result TEXT NOT NULL)');self.db.commit()
        if os.name!='nt':path.chmod(0o600)
    def close(self):self.db.close()
    def flush(self):
        for ident,raw in self.db.execute('SELECT id,result FROM outbox ORDER BY rowid').fetchall():
            try:r=self.relay.request('/agent/result',{'job_id':ident,'result':json.loads(raw)})
            except (OSError,ValueError):return False
            if not r.get('saved'):return False
            self.db.execute('DELETE FROM outbox WHERE id=?',(ident,));self.db.commit()
        return True
    def process(self,job):
        ident=job['id']
        if self.db.execute('SELECT id FROM outbox WHERE id=?',(ident,)).fetchone():return self.flush()
        receipt=self.relay.request('/agent/claim',{'job_id':ident})
        if receipt.get('claimed') is not True:return False
        try:result=self.engine.execute(job['op'],job['args'],job['request_id'])
        except UseError as e:result={'error':str(e),'code':e.code}
        raw=json.dumps(result,ensure_ascii=False,separators=(',',':'))
        if len(raw.encode())>4*1024*1024-8192:raw=json.dumps({'error':'Result exceeded transport limit; original outcome is stored in the local journal. Do not replay.','code':'RESULT_TOO_LARGE'})
        self.db.execute('INSERT OR IGNORE INTO outbox VALUES (?,?)',(ident,raw));self.db.commit()
        return self.flush()
    def run(self,stop_event,local_rpc=None):
        failures=0
        while not stop_event.is_set():
            try:
                if local_rpc:local_rpc.pump()
                self.engine.expire()
                if not self.flush():raise OSError('Pending result not acknowledged')
                r=self.relay.request('/agent/next',{'capabilities':self.engine._run('capabilities',{})})
                if r.get('job'):self.process(r['job'])
                else:stop_event.wait(0.05)  # Match proven Android Use relay responsiveness
                failures=0
            except (OSError,ValueError,UseError):
                failures+=1
                until=time.monotonic()+min(30,2**min(failures,4))+random.random()
                while not stop_event.is_set() and time.monotonic()<until:
                    if local_rpc:local_rpc.pump()
                    stop_event.wait(.05)
