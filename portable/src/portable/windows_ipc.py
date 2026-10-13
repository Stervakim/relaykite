"""Authenticated owner-local RPC; UI work stays on the Portable agent thread."""
import copy,hashlib,hmac,json,os,queue,re,secrets,sqlite3,subprocess,threading,time
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from .engine import UseError,FIELDS
from .journal import digest

REQUEST_LIMIT=1024*1024
RESULT_LIMIT=4*1024*1024

def descriptor_path():return Path(os.environ['LOCALAPPDATA'])/'CodakiPortableUseIPC'/'endpoint.json'

def safe_path(path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('Unsafe local RPC path')
    if path.is_file() and path.stat().st_nlink!=1:raise ValueError('Unsafe local RPC file')
    return path

def protect(path):
    path=safe_path(path)
    if os.name=='nt':
        info=subprocess.run(['whoami','/user','/fo','csv'],capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        sid=re.search(r'S-1-5-[0-9-]+',info.stdout)
        if not sid:raise RuntimeError('Windows owner identity unavailable')
        suffix=':(OI)(CI)F' if path.is_dir() else ':F'
        for args in ([str(path),'/reset'],[str(path),'/inheritance:r'],[str(path),'/grant:r','*'+sid.group()+suffix,'*S-1-5-18'+suffix]):
            subprocess.run(['icacls',*args],capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    else:path.chmod(0o700 if path.is_dir() else 0o600)

def encoded_id(scope,rid):return 'mini_'+hashlib.sha256((scope+'\0'+rid).encode()).hexdigest()

def encode_receipt(value):
    payload=json.dumps(value,ensure_ascii=False).encode()
    if len(payload)<=RESULT_LIMIT:return payload
    receipt=copy.deepcopy(value)
    def strip(item):
        if isinstance(item,dict):
            item.pop('screenshot',None)
            for child in item.values():strip(child)
        elif isinstance(item,list):
            for child in item:strip(child)
    strip(receipt);receipt['transport_warning']='Screenshot omitted to fit local RPC limit; original engine receipt retained. Do not replay.'
    payload=json.dumps(receipt,ensure_ascii=False).encode()
    if len(payload)>RESULT_LIMIT:
        summary={k:receipt[k] for k in ('applied','status','completed','total','stopped_at','request_id','session_id') if k in receipt}
        summary.update(error='Original receipt exceeds local RPC limit; inspect its journal without replay',code='RESULT_TOO_LARGE',original_code=receipt.get('code'))
        payload=json.dumps(summary).encode()
    return payload

class Boundary:
    def __init__(self,engine,path):
        self.engine=engine;self.path=safe_path(path)
        self.db=sqlite3.connect(self.path)
        self.db.execute('CREATE TABLE IF NOT EXISTS bridge_requests(scope TEXT,public_id TEXT,engine_id TEXT UNIQUE,op TEXT,PRIMARY KEY(scope,public_id))')
        self.db.execute('CREATE TABLE IF NOT EXISTS bridge_sessions(id TEXT PRIMARY KEY,scope TEXT)');self.db.commit();protect(self.path)
    def close(self):self.db.close()
    def _register(self,scope,public_id,engine_id,op):
        row=self.db.execute('SELECT engine_id,op FROM bridge_requests WHERE scope=? AND public_id=?',(scope,public_id)).fetchone()
        if row and row!=(engine_id,op):raise UseError('Request identity already belongs to another operation','REQUEST_SCOPE')
        self.db.execute('INSERT OR IGNORE INTO bridge_requests VALUES(?,?,?,?)',(scope,public_id,engine_id,op));self.db.commit()
    def _target(self,scope,rid):
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',rid):raise UseError('Invalid target request identity')
        row=self.db.execute('SELECT engine_id FROM bridge_requests WHERE scope=? AND public_id=?',(scope,rid)).fetchone()
        if row:return row[0]
        raise UseError('Request is unknown or belongs to another Mini connection','REQUEST_SCOPE')
    def _receipt(self,scope,value):
        aliases=dict(self.db.execute('SELECT engine_id,public_id FROM bridge_requests WHERE scope=?',(scope,)))
        def walk(item):
            if isinstance(item,dict):
                for key,child in list(item.items()):
                    if key in ('request_id','inflight_request_id','reconciled') and isinstance(child,str):item[key]=aliases.get(child,child)
                    else:walk(child)
            elif isinstance(item,list):
                for child in item:walk(child)
        out=copy.deepcopy(value);walk(out);return out
    def execute(self,request):
        rid=request.get('request_id') if isinstance(request,dict) else None
        try:
            if not isinstance(request,dict) or set(request)!={'scope','op','args','request_id'}:raise UseError('Expected scope,op,args,request_id')
            scope,op,args=request['scope'],request['op'],copy.deepcopy(request['args'])
            if not isinstance(scope,str) or not re.fullmatch(r'[a-f0-9-]{36}',scope):raise UseError('Invalid Mini connection scope')
            if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',rid):raise UseError('Invalid request identity')
            if not isinstance(op,str) or op not in FIELDS or not isinstance(args,dict):raise UseError('Unknown operation or arguments')
            from .mcp import TOOLS,validate
            parameters=copy.deepcopy(args)
            if op in ('result','reconcile'):parameters['target_request_id']=parameters.pop('request_id',None)
            validate(next(t['inputSchema'] for t in TOOLS if t['name']=='use_'+op),{**parameters,'request_id':rid,'device_id':'local'})
            if 'session_id' in args:
                owner=self.db.execute('SELECT scope FROM bridge_sessions WHERE id=?',(args['session_id'],)).fetchone()
                if owner!=(scope,):raise UseError('Session is not owned by this Mini connection','SESSION_SCOPE')
            if op in ('result','reconcile'):args['request_id']=self._target(scope,args.get('request_id'))
            engine_id=encoded_id(scope,rid);self._register(scope,rid,engine_id,op)
            if op=='batch':
                # Register child aliases before input so restart reconciliation
                # still knows their owner even if the parent never returns.
                for index in range(len(args['steps'])):
                    child='batch_'+digest(engine_id)[:48]+'_%02d'%index
                    self._register(scope,child,child,'action')
            value=self.engine.execute(op,args,engine_id)
            if op=='session_start' and value.get('session_id'):
                self.db.execute('INSERT OR IGNORE INTO bridge_sessions VALUES(?,?)',(value['session_id'],scope));self.db.commit()
            if op=='diagnostics':
                own={row[0] for row in self.db.execute('SELECT id FROM bridge_sessions WHERE scope=?',(scope,))}
                value['sessions']=[s for s in value.get('sessions',[]) if s['session_id'] in own]
                aliases=dict(self.db.execute('SELECT engine_id,public_id FROM bridge_requests WHERE scope=?',(scope,)))
                uncertain=value.get('uncertain_requests',[])
                value['blocked_by_other_scope']=any(r not in aliases for r in uncertain)
                value['uncertain_requests']=[aliases[r] for r in uncertain if r in aliases]
            return self._receipt(scope,value)
        except UseError as error:return {'error':str(error),'code':error.code,'request_id':rid}

class LocalRPC:
    def __init__(self,boundary,descriptor=None,timeout=60):
        self.boundary=boundary;self.path=safe_path(descriptor or descriptor_path());self.timeout=timeout
        self.pending=queue.Queue(maxsize=8);self.closed=False;self.token=secrets.token_hex(32);self.instance=secrets.token_hex(16)
        self.path.parent.mkdir(parents=True,exist_ok=True);protect(self.path.parent)
        rpc=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def setup(self):super().setup();self.connection.settimeout(2)
            def do_POST(self):
                if self.path!='/rpc' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+rpc.token):
                    self.send_error(403);return
                try:
                    if self.headers.get('Transfer-Encoding'):raise ValueError('Unsupported framing')
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=REQUEST_LIMIT:raise ValueError('Invalid request size')
                    raw=self.rfile.read(length)
                    if len(raw)!=length:raise ValueError('Incomplete request')
                    request=json.loads(raw)
                except (ValueError,OSError):self.send_error(400);return
                job={'request':request,'deadline':time.monotonic()+rpc.timeout,'done':threading.Event(),'expired':False}
                try:rpc.pending.put_nowait(job)
                except queue.Full:self.send_error(429);return
                if job['done'].wait(rpc.timeout):out=job['result']
                else:
                    job['expired']=True
                    out={'error':'Local RPC deadline expired; inspect the original result and do not replay input','code':'IPC_DEADLINE','request_id':request.get('request_id') if isinstance(request,dict) else None}
                payload=encode_receipt(out)
                try:
                    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
                except OSError:pass
        self.http=HTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,name='portable-windows-rpc',daemon=True)
    def start(self):
        temp=safe_path(self.path.with_name('endpoint-'+self.instance+'.new'))
        try:
            with temp.open('x',encoding='utf-8') as stream:
                json.dump({'version':1,'url':'http://127.0.0.1:%d/rpc'%self.http.server_port,'token':self.token,'instance':self.instance,'pid':os.getpid()},stream)
            protect(temp);os.replace(temp,self.path);self.thread.start();return self
        except Exception:
            temp.unlink(missing_ok=True);self.http.server_close();raise
    def pump(self):
        # Called only by the original agent/UIA thread, never the HTTP thread.
        try:job=self.pending.get_nowait()
        except queue.Empty:return
        if job['expired'] or time.monotonic()>=job['deadline']:
            job['result']={'error':'Expired before local execution','code':'IPC_DEADLINE'}
        else:
            try:job['result']=self.boundary.execute(job['request'])
            except Exception:job['result']={'error':'IPC execution outcome unknown; inspect original engine receipt','code':'UNCERTAIN'}
        job['done'].set()
    def close(self):
        if self.closed:return
        self.closed=True
        while True:
            try:job=self.pending.get_nowait()
            except queue.Empty:break
            job['expired']=True;job['result']={'error':'RPC closed before execution','code':'IPC_DEADLINE'};job['done'].set()
        if self.thread.is_alive():self.http.shutdown();self.thread.join(timeout=3)
        self.http.server_close()
        try:
            if json.loads(self.path.read_text())['instance']==self.instance:self.path.unlink()
        except (OSError,ValueError,KeyError):pass
