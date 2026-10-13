"""Root-only Unix IPC sharing the running agent's existing engine and journal."""
import errno, json, os, socket, stat, struct, threading, time
from pathlib import Path
from .engine import UseError
SOCKET='/data/adb/codaki-portable-use/state/portable.sock'
REQUEST_LIMIT=1024*1024
RESULT_LIMIT=4*1024*1024

class LockedEngine:
    """Cover agent capabilities/expiry reads with the engine's existing RLock."""
    def __init__(self,engine):self.engine=engine
    def __getattr__(self,name):return getattr(self.engine,name)
    def execute(self,*args,**kwargs):
        with self.engine.lock:return self.engine.execute(*args,**kwargs)
    def expire(self):
        with self.engine.lock:return self.engine.expire()
    def _run(self,*args,**kwargs):
        with self.engine.lock:return self.engine._run(*args,**kwargs)
    def close(self):
        with self.engine.lock:return self.engine.close()

def _require_root():
    if getattr(os,'geteuid',lambda:-1)()!=0:raise UseError('Phone IPC requires root')

def _peer_uid(connection):
    if not hasattr(socket,'SO_PEERCRED'):raise UseError('Kernel peer authentication unavailable')
    raw=connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i'))
    return struct.unpack('3i',raw)[1]

def receive(connection,limit=REQUEST_LIMIT,stop_event=None,timeout_seconds=40):
    data=bytearray();deadline=time.monotonic()+timeout_seconds
    while len(data)<=limit:
        if stop_event is not None and stop_event.is_set():raise ValueError('IPC stopped')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('IPC read deadline exceeded')
        connection.settimeout(min(.25,remaining))
        try:chunk=connection.recv(min(65536,limit+1-len(data)))
        except socket.timeout:continue
        if not chunk:break
        data.extend(chunk)
        if b'\n' in data:break
    if len(data)>limit or b'\n' not in data:raise ValueError('Invalid IPC framing')
    frame,trailing=bytes(data).split(b'\n',1)
    if trailing.strip():raise ValueError('One IPC request per connection')
    return json.loads(frame)

def dispatch(engine,request):
    if (not isinstance(request,dict) or set(request)!={'op','args','request_id'}
        or not isinstance(request['op'],str) or not isinstance(request['args'],dict)
        or not isinstance(request['request_id'],str)):
        return {'error':'Expected op,args,request_id','code':'REJECTED'}
    try:return engine.execute(request['op'],request['args'],request['request_id'])
    except UseError as e:return {'error':str(e),'code':e.code}

def _prepare_listener(path):
    _require_root();path=Path(path)
    if not path.is_absolute():raise UseError('IPC socket path must be absolute')
    for parent in (path.parent,*path.parent.parents):
        if parent.is_symlink():raise UseError('Unsafe socket directory')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.parent.stat().st_uid!=0:raise UseError('IPC state directory must belong to root')
    path.parent.chmod(0o700)
    if os.path.lexists(path):
        existing=path.lstat()
        if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid!=0:raise UseError('Unsafe socket path')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
            probe.settimeout(.25)
            try:probe.connect(str(path))
            except OSError as e:
                if e.errno not in (errno.ECONNREFUSED,errno.ENOENT):raise UseError('Existing IPC socket cannot be checked') from None
            else:raise UseError('IPC server is already running')
        path.unlink(missing_ok=True)
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        listener.bind(str(path));path.chmod(0o600);listener.listen(4);listener.settimeout(.25)
        identity=path.lstat()
        return listener,path,(identity.st_dev,identity.st_ino)
    except Exception:listener.close();raise

class LocalServer:
    """One IPC thread, one existing Engine; stop interrupts partial client reads."""
    def __init__(self,engine,stop_event,path=SOCKET):
        self.engine=engine;self.external_stop=stop_event;self.stop_event=threading.Event()
        self.listener,self.path,self.identity=_prepare_listener(path)
        self.connection=None;self.connection_lock=threading.Lock()
        self.thread=threading.Thread(target=self._run,name='portable-local-ipc',daemon=True)
    def start(self):self.thread.start();return self
    def _stopping(self):return self.stop_event.is_set() or self.external_stop.is_set()
    def _run(self):
        try:
            while not self._stopping():
                try:connection,_=self.listener.accept()
                except socket.timeout:self.engine.expire();continue
                except OSError:
                    if self._stopping():break
                    raise
                with connection:
                    with self.connection_lock:self.connection=connection
                    try:
                        if _peer_uid(connection)!=0:raise UseError('Phone IPC requires root peer')
                        request=receive(connection,stop_event=self.stop_event,timeout_seconds=2)
                        if self._stopping():continue
                        out=dispatch(self.engine,request)
                        raw=(json.dumps(out,ensure_ascii=False)+'\n').encode()
                        if len(raw)>RESULT_LIMIT:raw=b'{"error":"Result exceeds IPC limit; inspect journal without replay","code":"RESULT_TOO_LARGE"}\n'
                    except (ValueError,TypeError,KeyError,OSError,UseError):raw=b'{"error":"Malformed or unauthorized IPC request","code":"REJECTED"}\n'
                    except Exception:raw=b'{"error":"IPC outcome unavailable; inspect journal without replay","code":"UNCERTAIN"}\n'
                    try:connection.settimeout(.5);connection.sendall(raw)
                    except OSError:pass
                    finally:
                        with self.connection_lock:self.connection=None
        finally:
            self.listener.close()
            try:
                current=self.path.lstat()
                if (current.st_dev,current.st_ino)==self.identity:self.path.unlink()
            except FileNotFoundError:pass
    def close(self):
        self.stop_event.set()
        with self.connection_lock:
            if self.connection is not None:
                try:self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:pass
        # Join before engine cleanup. Already started actions must finish their receipt.
        self.thread.join()

def serve(engine,stop_event,path=SOCKET):
    server=LocalServer(LockedEngine(engine),stop_event,path).start()
    try:
        while server.thread.is_alive() and not stop_event.wait(.25):pass
    finally:server.close()

def call(request,path=SOCKET):
    _require_root();raw=(json.dumps(request,ensure_ascii=False)+'\n').encode()
    if len(raw)>REQUEST_LIMIT:raise UseError('IPC request exceeds limit')
    path=Path(path);details=path.lstat()
    if path.is_symlink() or not stat.S_ISSOCK(details.st_mode) or details.st_uid!=0 or details.st_mode&0o077:raise UseError('Unsafe IPC socket')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(40);connection.connect(str(path))
        if _peer_uid(connection)!=0:raise UseError('Phone IPC server must be root')
        connection.sendall(raw)
        return receive(connection,RESULT_LIMIT)

def main():
    import sys
    raw=sys.stdin.buffer.read(REQUEST_LIMIT+1)
    if len(raw)>REQUEST_LIMIT:raise UseError('IPC request exceeds limit')
    print(json.dumps(call(json.loads(raw)),ensure_ascii=False))
if __name__=='__main__':main()
