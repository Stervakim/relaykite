"""Typed jobs/PTYs hosted by the one owner-bound phone worker."""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import stat
import struct
import threading

OPERATIONS=('phone_task_start','phone_task_status','phone_task_result','phone_task_cancel',
            'phone_terminal_open','phone_terminal_list','phone_terminal_read','phone_terminal_write','phone_terminal_resize','phone_terminal_close',
            'phone_command_start','phone_command_status','phone_command_result','phone_command_terminate',
            'phone_file_stat','phone_file_checksum','phone_file_copy','phone_file_move','phone_file_rename','phone_file_delete',
            'phone_transfer_start','phone_transfer_status','phone_transfer_chunk','phone_transfer_commit','phone_transfer_abort','phone_file_open')
from runtime_paths import BASE
SOCKET=BASE/'state/managed.sock'
_runtime=None

def definitions():
    string=lambda maximum=4096:{'type':'string','minLength':1,'maxLength':maximum}
    ident={'type':'string','minLength':8,'maxLength':100,'pattern':'^[A-Za-z0-9_-]+$'}
    integer=lambda low,high:{'type':'integer','minimum':low,'maximum':high}
    mode={'type':'string','enum':['app','system','root','termux']}
    opening={'request_id':ident,'mode':mode,'cwd':string(),'timeout_seconds':integer(1,3600)}
    tid={'terminal_id':string(100)}
    reading={**tid,'cursor':integer(0,2**53-1),'max_bytes':integer(1,65536)}
    specs={
      'phone_task_start':({'request_id':ident,'tool':string(80),'arguments':{'type':'object'},'timeout_seconds':integer(1,3600)},['request_id','tool','arguments']),
      'phone_task_status':({'task_id':ident},['task_id']),
      'phone_task_result':({'task_id':ident},['task_id']),
      'phone_task_cancel':({'task_id':ident},['task_id']),
      'phone_terminal_open':(opening,['request_id','mode']),
      'phone_terminal_list':({},[]),
      'phone_terminal_read':(reading,['terminal_id']),
      'phone_terminal_write':({**tid,'request_id':ident,'base64':string(87384)},['terminal_id','request_id','base64']),
      'phone_terminal_resize':({**tid,'rows':integer(1,300),'columns':integer(1,500)},['terminal_id','rows','columns']),
      'phone_terminal_close':(tid,['terminal_id']),
      'phone_command_start':({**opening,'command':string(65536)},['request_id','mode','command']),
      'phone_command_status':(tid,['terminal_id']),
      'phone_command_result':(reading,['terminal_id']),
      'phone_command_terminate':(tid,['terminal_id']),
    }
    digest={'type':'string','pattern':'^[a-f0-9]{64}$','minLength':64,'maxLength':64}
    file_args={'request_id':ident,'source':string(),'destination':string(),'overwrite':{'type':'boolean'},'expected_sha256':digest}
    for name in ('phone_file_copy','phone_file_move','phone_file_rename'):specs[name]=(file_args,['request_id','source','destination'])
    specs.update({
      'phone_file_stat':({'path':string()},['path']),
      'phone_file_checksum':({'path':string()},['path']),
      'phone_file_delete':({'request_id':ident,'path':string(),'expected_sha256':digest},['request_id','path']),
      'phone_transfer_start':({'request_id':ident,'destination':string(),'total_bytes':integer(0,2*1024**3),'sha256':digest,'overwrite':{'type':'boolean'}},['request_id','destination','total_bytes','sha256']),
      'phone_transfer_status':({'transfer_id':string(100)},['transfer_id']),
      'phone_transfer_chunk':({'transfer_id':string(100),'offset':integer(0,2*1024**3),'base64':string(349528),'sha256':digest},['transfer_id','offset','base64','sha256']),
      'phone_transfer_commit':({'transfer_id':string(100)},['transfer_id']),
      'phone_transfer_abort':({'transfer_id':string(100)},['transfer_id']),
      'phone_file_open':({'request_id':ident,'session_id':string(100),'app_id':string(512),'path':string(),'mime_type':string(128)},['request_id','session_id','app_id','path','mime_type']),
    })
    descriptions={
      'phone_task_start':'Start an owner-authorized tool as a durable bounded background task. Reuse request_id; poll status/result. Short calls and independent resources remain responsive.',
      'phone_task_cancel':'Cancel only a queued managed task. Running effects require supported targeted termination and are never claimed cancelled.',
      'phone_terminal_open':'Open a real interactive PTY with explicit system (UID 2000), root or optional Termux backend. Stable request ID prevents reopening after restart.',
      'phone_terminal_write':'Send base64 stdin once using a stable request ID. An uncertain write must be inspected, never replayed under a new ID.',
      'phone_command_start':'Start a shell command in its own PTY/process group, with bounded output and deadline. Read its original terminal_id; do not repeat an uncertain command.',
    }
    readonly={'phone_task_status','phone_task_result','phone_terminal_list','phone_terminal_read','phone_command_status','phone_command_result','phone_file_stat','phone_file_checksum','phone_transfer_status'}
    return [{'name':name,'description':descriptions.get(name,'Read or control the selected owned managed task/terminal; preserve IDs and inspect uncertain outcomes.'),
             'annotations':{'readOnlyHint':name in readonly,'destructiveHint':name not in readonly,'idempotentHint':name in readonly,'openWorldHint':False},
             'inputSchema':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}
            for name,(properties,required) in specs.items()]

def resources(tool,args):
    result=[]
    if tool.startswith('phone_use_'):
        if args.get('session_id'):result.append('session:'+args['session_id'])
        if tool not in ('phone_use_batch','phone_use_observe','phone_use_result','phone_use_diagnostics','phone_use_capabilities','phone_use_apps'):result.append('ui:android')
    if tool in ('read_ui','tap','swipe','keypress','launch_app','screenshot'):result.append('ui:physical')
    if tool=='root_shell':result.append('system:root-shell')
    if tool=='phone_install_apk':result.append('package-manager')
    for key in ('path','source','destination'):
        if isinstance(args.get(key),str):result.append('path:'+str(Path(args[key]).resolve()))
    return result

class Runtime:
    def __init__(self,state,executor,*,backend=None):
        from job_scheduler import Scheduler
        from terminal_manager import TerminalManager
        from file_ops import FileStore
        state=Path(state);state.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.scheduler=Scheduler(state/'jobs.sqlite3',executor)
        try:self.terminals=TerminalManager(state/'jobs.sqlite3',**({} if backend is None else {'backend':backend}))
        except Exception:self.scheduler.close();raise
        try:self.files=FileStore(state/'jobs.sqlite3')
        except Exception:self.scheduler.close();self.terminals.close();raise
        self.share_lock=threading.RLock()

    def invoke(self,tool,args):
        import native_phone
        definition=next((d for d in definitions() if d['name']==tool),None)
        if definition is None:raise ValueError('Unknown managed operation')
        native_phone.validate_schema(args,definition['inputSchema'])
        if tool=='phone_task_start':
            requested=args['tool'];arguments=args['arguments']
            if requested.startswith(('phone_task_','phone_terminal_','phone_command_','phone_job_')):raise ValueError('Recursive/process-control scheduling is not allowed')
            target=next((d for d in native_phone.tool_definitions() if d['name']==requested),None)
            if target is None:raise ValueError('Unknown owner-authorized tool')
            native_phone.validate_schema(arguments,target['inputSchema'])
            return self.scheduler.submit(args['request_id'],requested,arguments,resources=resources(requested,arguments),timeout_seconds=args.get('timeout_seconds',300))
        if tool in ('phone_task_status','phone_task_result'):return self.scheduler.status(args['task_id'])
        if tool=='phone_task_cancel':return self.scheduler.cancel(args['task_id'])
        if tool in ('phone_terminal_open','phone_command_start'):
            return self.terminals.open(args['request_id'],mode=args['mode'],cwd=args.get('cwd'),command=args.get('command'),timeout_seconds=args.get('timeout_seconds',1800))
        if tool=='phone_terminal_list':return {'terminals':self.terminals.list()}
        if tool in ('phone_terminal_read','phone_command_result'):return self.terminals.read(args['terminal_id'],args.get('cursor',0),args.get('max_bytes',65536))
        if tool=='phone_command_status':
            with self.terminals.lock:return self.terminals._info(args['terminal_id'])
        if tool=='phone_terminal_write':return self.terminals.write(args['terminal_id'],args['request_id'],args['base64'])
        if tool=='phone_terminal_resize':return self.terminals.resize(args['terminal_id'],args['rows'],args['columns'])
        if tool=='phone_file_stat':return self.files.stat(args['path'])
        if tool=='phone_file_checksum':return self.files.checksum(args['path'])
        if tool in ('phone_file_copy','phone_file_move','phone_file_rename'):
            return self.files.operate(args['request_id'],tool.removeprefix('phone_file_'),args['source'],args['destination'],overwrite=args.get('overwrite',False),expected_sha256=args.get('expected_sha256'))
        if tool=='phone_file_delete':return self.files.operate(args['request_id'],'delete',args['path'],expected_sha256=args.get('expected_sha256'))
        if tool=='phone_transfer_start':return self.files.start_transfer(args['request_id'],args['destination'],args['total_bytes'],args['sha256'],overwrite=args.get('overwrite',False))
        if tool=='phone_transfer_status':return self.files.transfer_status(args['transfer_id'])
        if tool=='phone_transfer_chunk':return self.files.write_chunk(args['transfer_id'],args['offset'],args['base64'],args['sha256'])
        if tool=='phone_transfer_commit':return self.files.commit_transfer(args['transfer_id'])
        if tool=='phone_transfer_abort':return self.files.abort_transfer(args['transfer_id'])
        if tool=='phone_file_open':
            from file_bridge import FileBridge
            with self.share_lock:
                if not hasattr(self,'shares'):self.shares=FileBridge(Path(self.files.db.execute('PRAGMA database_list').fetchone()[2]))
            shared=self.shares.prepare(args['request_id'],args['path'],args['mime_type'])
            from portable_peer import call
            import hashlib
            receipt=call('file_open',{'session_id':args['session_id'],'app_id':args['app_id'],'uri':shared['uri'],'mime_type':args['mime_type']},'open_'+hashlib.sha256(args['request_id'].encode()).hexdigest()[:48])
            if receipt.get('error'):raise RuntimeError(receipt['error'])
            return {**receipt,'file':shared}
        return self.terminals.stop(args['terminal_id'])

    def close(self):
        self.scheduler.close();self.terminals.close();self.files.close()
        if hasattr(self,'shares'):self.shares.close()

def _peer(connection):
    return struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]

def _receive(connection):
    connection.settimeout(5);raw=bytearray()
    while b'\n' not in raw and len(raw)<=3*1024*1024:
        chunk=connection.recv(65536)
        if not chunk:break
        raw.extend(chunk)
    if len(raw)>3*1024*1024 or not raw.endswith(b'\n'):raise ValueError('Invalid managed message')
    return json.loads(raw)

class Server:
    def __init__(self,runtime,path=SOCKET):
        self.uid=os.geteuid()
        self.runtime=runtime;self.path=Path(path);self.stop=threading.Event();self.clients=set();self.lock=threading.RLock();self.slots=threading.BoundedSemaphore(8)
        if any(p.is_symlink() for p in (self.path,*self.path.parents)):raise ValueError('Unsafe managed socket path')
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.path.exists():
            st=self.path.lstat()
            if not stat.S_ISSOCK(st.st_mode) or st.st_uid!=self.uid:raise ValueError('Unsafe socket')
            probe=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            try:
                probe.settimeout(.2)
                try:probe.connect(str(self.path))
                except (ConnectionRefusedError,FileNotFoundError):self.path.unlink()
                else:raise RuntimeError('Existing managed service is live')
            finally:probe.close()
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.listener.bind(str(self.path));self.path.chmod(0o600);self.listener.listen(8);self.listener.settimeout(.2)
        details=self.path.stat();self.identity=(details.st_dev,details.st_ino)
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()

    def _client(self,connection):
        try:
            with connection:
                if _peer(connection)!=self.uid:raise PermissionError('Same-owner peer required')
                request=_receive(connection)
                try:out={'result':self.runtime.invoke(request['tool'],request['arguments'])}
                except Exception as error:out={'error':type(error).__name__,'instruction':'Operation rejected or uncertain. Inspect the original receipt; do not replay.'}
                raw=(json.dumps(out,ensure_ascii=False)+'\n').encode()
                if len(raw)>3*1024*1024:raw=b'{"error":"Output exceeds transport limit; use bounded reads"}\n'
                connection.sendall(raw)
        except (OSError,ValueError,KeyError,PermissionError):pass
        finally:
            with self.lock:self.clients.discard(threading.current_thread())
            self.slots.release()

    def _run(self):
        while not self.stop.is_set():
            try:connection,_=self.listener.accept()
            except socket.timeout:continue
            except OSError:break
            if not self.slots.acquire(blocking=False):connection.close();continue
            thread=threading.Thread(target=self._client,args=(connection,),daemon=True)
            with self.lock:self.clients.add(thread)
            thread.start()

    def close(self):
        self.stop.set();self.listener.close();self.thread.join()
        with self.lock:clients=list(self.clients)
        for client in clients:client.join()
        try:
            details=self.path.lstat()
            if (details.st_dev,details.st_ino)==self.identity:self.path.unlink()
        except FileNotFoundError:pass

def start(state,executor):
    global _runtime
    _runtime=Runtime(state,executor)
    try:server=Server(_runtime,Path(state)/'managed.sock')
    except Exception:_runtime.close();_runtime=None;raise
    return server

def stop(server):
    global _runtime
    server.close();_runtime.close();_runtime=None

def invoke(tool,arguments):
    if _runtime is not None:return _runtime.invoke(tool,arguments)
    uid=getattr(os,'geteuid',lambda:-1)()
    info=SOCKET.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=uid or info.st_mode&0o077 or any(p.is_symlink() for p in (SOCKET,*SOCKET.parents)):raise ValueError('Unsafe managed socket')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(5);connection.connect(str(SOCKET))
        if _peer(connection)!=uid:raise PermissionError('Managed server owner mismatch')
        connection.sendall((json.dumps({'tool':tool,'arguments':arguments})+'\n').encode())
        out=_receive(connection)
    if 'error' in out:raise RuntimeError(out['error']+'; inspect the original receipt')
    return out['result']

def wrapper(tool):
    def call(**arguments):return invoke(tool,arguments)
    call.__name__=tool
    return call
