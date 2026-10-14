"""Root-installed supervisor: fixed mode requests, one owner queue worker.

The app's private request file can select three fixed modes or stop. It cannot
supply a command, executable, credential, path or Android input to this broker.
"""
import hashlib,json,os,re,signal,socket,sqlite3,stat,struct,subprocess,sys,time,uuid
from pathlib import Path
from contextlib import closing
from mode_coordinator import Coordinator,MODES
from state_snapshot import copy_store
from terminal_manager import generation

ROOT=Path('/data/adb/mini-codex');MODULE=Path('/data/adb/modules/mini_codex')
APP=Path('/data/data/org.relaykite.runtime/files/owner')
CONTROL=Path('/data/adb/relaykite-runtime/control')
APPFILES=APP.parent
CAP=5*1024**3

def system_env():
    env=os.environ.copy();env.pop('LD_LIBRARY_PATH',None);env.pop('LD_PRELOAD',None);env['PATH']='/system/bin:/system/xbin';return env
def android(*args):
    return subprocess.run(['/system/bin/am',*args],env=system_env(),capture_output=True,text=True,timeout=15)
def private_json(path,value,uid=0):
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Unsafe control file path')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
    with temporary.open('x') as out:json.dump(value,out);out.flush();os.fsync(out.fileno())
    os.chmod(temporary,0o600);os.chown(temporary,uid,uid);temporary.replace(path)
    if uid:subprocess.run(['/system/bin/restorecon',str(path)],env=system_env(),capture_output=True,check=True,timeout=5)
def terminate_receipt(receipt,allowed):
    pid=receipt.get('pid');born=receipt.get('generation');uid=receipt.get('uid');argv=receipt.get('argv')
    if type(pid)!=int or pid<=1 or born is None or uid not in allowed or not isinstance(argv,list):raise ValueError('Invalid owned process receipt')
    proc=Path('/proc')/str(pid)
    def matches():
        try:return generation(pid)==born and proc.stat().st_uid==uid and os.getpgid(pid)==pid and [os.fsdecode(a) for a in (proc/'cmdline').read_bytes().split(b'\0') if a]==argv
        except (FileNotFoundError,ProcessLookupError):return False
    if matches():
        os.killpg(pid,signal.SIGTERM);until=time.monotonic()+30
        while matches() and time.monotonic()<until:time.sleep(.1)
        if matches():os.killpg(pid,signal.SIGKILL)
        until=time.monotonic()+5
        while matches() and time.monotonic()<until:time.sleep(.1)
        if matches():raise RuntimeError('Owned process did not stop')

def owned_app_worker(uid,args,expected_uid):
    if uid!=expected_uid or len(args)!=2 or Path(args[0]).name!='librelaykite_python.so':return False
    script=Path(args[1])
    return script.name=='app_worker.py' and script.parent.name=='agent' and script.parent.parent.parent==APPFILES and re.fullmatch(r'runtime-[a-f0-9]{24}',script.parent.parent.name) is not None

class Backend:
    def __init__(self,runtime,uid):
        self.runtime=runtime.resolve();self.uid=uid;self.child=None
    def base(self,mode):return APP if mode=='app' else ROOT
    def preflight(self,previous,mode):
        if mode not in MODES or previous not in MODES:raise ValueError('Invalid mode')
        if mode=='root-termux' and not Path('/data/data/com.termux/files/usr/bin/bash').is_file():raise RuntimeError('Optional Termux backend is absent')
        source=self.base(previous);target=self.base(mode)
        if not (source/'config.json').is_file() or not (source/'memory-node.json').is_file():raise RuntimeError('Original private installation must be migrated first')
        if any(p.is_symlink() for p in (source,target,*source.parents,*target.parents)):raise ValueError('Private mode storage symlink rejected')
        if source!=target and (target/'config.json').exists():
            a=json.loads((source/'config.json').read_text());b=json.loads((target/'config.json').read_text())
            if (a.get('relay_url'),a.get('agent_token'))!=(b.get('relay_url'),b.get('agent_token')):raise PermissionError('Another owner configuration must not be overwritten')
    def stop(self,mode):
        # Stop an APK worker first even if it was only waiting for config.
        android('stopservice','-n','org.relaykite.runtime/.WorkerService')
        # OEM freezing can prevent the Java service's onDestroy from running.
        # Reap only our exact app-UID worker generation, never its whole UID.
        for proc in Path('/proc').glob('[0-9]*/cmdline'):
            try:
                args=[os.fsdecode(a) for a in proc.read_bytes().split(b'\0') if a]
                pid=int(proc.parent.name);born=generation(pid)
                if born is None or not owned_app_worker(proc.parent.stat().st_uid,args,self.uid):continue
                def matches():
                    try:return generation(pid)==born and owned_app_worker(proc.parent.stat().st_uid,[os.fsdecode(a) for a in proc.read_bytes().split(b'\0') if a],self.uid)
                    except (FileNotFoundError,ProcessLookupError):return False
                os.kill(pid,signal.SIGTERM);until=time.monotonic()+(30 if (APP/'enabled').exists() else 3)
                while matches() and time.monotonic()<until:time.sleep(.1)
                if matches():os.kill(pid,signal.SIGKILL)
            except (FileNotFoundError,ProcessLookupError):pass
        if self.child is not None:
            if self.child.poll() is None:terminate_receipt(self.receipt(self.child),{0})
            self.child.wait(timeout=5);self.child=None
        saved=CONTROL/'root-worker.json'
        if saved.exists():terminate_receipt(json.loads(saved.read_text()),{0});saved.unlink()
        until=time.monotonic()+35
        for base in (ROOT,APP):
            lock=base/'state/agent.lock'
            if not lock.exists():continue
            import fcntl
            with lock.open('a+b') as handle:
                while True:
                    try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);break
                    except BlockingIOError:
                        if time.monotonic()>=until:raise RuntimeError('Another queue worker still owns its journal')
                        time.sleep(.1)
            # Reap exact durable PTY generations before an app-UID migration.
            journal=base/'state/jobs.sqlite3'
            if journal.exists():
                with closing(sqlite3.connect(journal)) as db:
                    table=db.execute("SELECT 1 FROM sqlite_master WHERE name='terminal_sessions'").fetchone()
                    if table:
                        for pid,born in db.execute("SELECT pid,generation FROM terminal_sessions WHERE status='running'").fetchall():
                            if pid is None or born is None or generation(pid)!=born:continue
                            if os.getpgid(pid)!=pid:raise RuntimeError('Terminal process group mismatch')
                            os.killpg(pid,signal.SIGTERM);time.sleep(.1)
                            if generation(pid)==born and os.getpgid(pid)==pid:os.killpg(pid,signal.SIGKILL)
            node=base/'state/memory-node.pid'
            if node.exists():terminate_receipt(json.loads(node.read_text()),{0,self.uid});node.unlink()
        # No boot/start event may reopen an inactive app copy while switching.
        (APP/'enabled').unlink(missing_ok=True)
    @staticmethod
    def receipt(child):
        return {'pid':child.pid,'generation':generation(child.pid),'uid':0,'argv':[os.fsdecode(a) for a in (Path('/proc')/str(child.pid)/'cmdline').read_bytes().split(b'\0') if a]}
    def prepare(self,previous,mode,ident):
        source=self.base(previous);target=self.base(mode)
        if source==target:return
        from memory_bridge import allocated_bytes
        used=allocated_bytes(ROOT)+allocated_bytes(APP)
        names=[name for name in ('state','memory','memory-service','project-graph','project-source','support') if (source/name).is_dir()]
        extra=sum(allocated_bytes(source/name) for name in names)
        if used+extra+64*1024**2>CAP:raise RuntimeError('Combined private storage quota cannot hold migration and backups')
        target.mkdir(parents=True,exist_ok=True,mode=0o700)
        staging=target/('mode-stage-'+ident);staging.mkdir(mode=0o700)
        for name in names:copy_store(source/name,staging/name,max_bytes=CAP-used)
        config=json.loads((source/'config.json').read_text());memory=json.loads((source/'memory-node.json').read_text());bridge=json.loads((source/'memory-service.json').read_text())
        config.update(state_dir=str(target/'state'),memory_dir=str(target/'memory'),disable_file=str((target if mode=='app' else MODULE)/'disable'))
        memory['data_dir']=str(target/'memory-service/data')
        if mode=='app':
            # The app cannot traverse root-owned inactive copies. Reserve their
            # current allocation rather than silently treating them as zero.
            reserve=allocated_bytes(ROOT)
            bridge.update(data_dir=memory['data_dir'],accounting_roots=[str(APP)],external_reserved_bytes=reserve)
            memory['quota_bytes']=min(memory.get('quota_bytes',CAP),CAP-reserve-32*1024**2)
        else:
            bridge.update(data_dir=memory['data_dir'],accounting_roots=[str(ROOT),str(APP)],external_reserved_bytes=0)
            memory['quota_bytes']=CAP-32*1024**2
        config_names=['config.json','memory-node.json','memory-service.json']
        for name,value in (('config.json',config),('memory-node.json',memory),('memory-service.json',bridge)):private_json(staging/name,value)
        if (source/'summary-route.json').is_file():
            private_json(staging/'summary-route.json',json.loads((source/'summary-route.json').read_text()));config_names.append('summary-route.json')
        backup=target/'mode-backups'/ident;backup.mkdir(parents=True,mode=0o700)
        for name in names+config_names:
            old=target/name
            if old.exists():old.rename(backup/name)
            (staging/name).rename(old)
        staging.rmdir()
        uid=self.uid if mode=='app' else 0
        for name in names+config_names:
            path=target/name
            for child in (path,*path.rglob('*')) if path.is_dir() else (path,):
                if child.is_symlink():raise ValueError('Migrated data must not contain links')
                os.chown(child,uid,uid);child.chmod(0o700 if child.is_dir() else 0o600)
        os.chown(target,uid,uid);target.chmod(0o700)
        if mode=='app':subprocess.run(['/system/bin/restorecon','-R',str(target)],env=system_env(),capture_output=True,check=True,timeout=15)
    def start(self,mode):
        base=self.base(mode)
        if mode=='app':
            (base/'enabled').touch(mode=0o600);os.chown(base/'enabled',self.uid,self.uid)
            subprocess.run(['/system/bin/restorecon',str(base/'enabled')],env=system_env(),capture_output=True,check=True,timeout=5)
            result=android('start-foreground-service','-n','org.relaykite.runtime/.WorkerService')
            if result.returncode or 'Error' in result.stdout+result.stderr:raise RuntimeError('Owned APK foreground start rejected')
        else:
            env=os.environ.copy();env.update(RELAYKITE_BASE=str(ROOT),RELAYKITE_MODULE=str(MODULE),RELAYKITE_MODE=mode,RELAYKITE_NATIVE=str(self.runtime/'native'),PYTHONHOME=str(self.runtime),PYTHONPATH=str(self.runtime/'agent'),LD_LIBRARY_PATH=str(self.runtime/'native'),PATH='/system/bin:/system/xbin',HOME=str(ROOT),TMPDIR=str(ROOT/'state'),SSL_CERT_FILE=str(self.runtime/'etc/tls/cert.pem'),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1');env.pop('LD_PRELOAD',None)
            logfile=ROOT/'state/runtime-startup.log'
            if logfile.exists() and logfile.stat().st_size>1024**2:logfile.replace(logfile.with_suffix('.previous.log'))
            with logfile.open('ab') as out:self.child=subprocess.Popen([str(self.runtime/'native/librelaykite_python.so'),str(self.runtime/'agent/app_worker.py')],env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True)
            private_json(CONTROL/'root-worker.json',self.receipt(self.child))
        until=time.monotonic()+30
        while time.monotonic()<until:
            if self.ready(mode):return
            if self.child is not None and self.child.poll() is not None:raise RuntimeError('Root worker failed before readiness')
            time.sleep(.2)
        raise RuntimeError('Worker readiness timeout; retain committed mode and inspect status')
    def ready(self,mode):
        # Socket existence alone can refer to an abandoned worker. The kernel
        # peer must be the currently recorded worker in the selected mode.
        base=self.base(mode);expected_uid=self.uid if mode=='app' else 0
        try:
            pid=int((base/'agent.pid').read_text())
            path=base/'state/managed.sock';info=path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=expected_uid or path.is_symlink():return False
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                client.settimeout(.5);client.connect(str(path))
                peer_pid,peer_uid,_=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if (peer_pid,peer_uid)!=(pid,expected_uid):return False
            proc=Path('/proc')/str(pid)
            args=[os.fsdecode(a) for a in (proc/'cmdline').read_bytes().split(b'\0') if a]
            env=(proc/'environ').read_bytes().split(b'\0')
            return len(args)==2 and args[1].endswith('/agent/app_worker.py') and ('RELAYKITE_MODE='+mode).encode() in env and ('RELAYKITE_BASE='+str(base)).encode() in env
        except (OSError,ValueError):return False
    def reconcile(self,mode):self.stop(mode);self.start(mode)

def main():
    if os.geteuid()!=0:raise PermissionError('Only installed root supervisor may run')
    import fcntl
    CONTROL.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (CONTROL/'supervisor.lock').open('a+b') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        uid=APPFILES.parent.stat().st_uid
        if not 10000<uid<20000:raise ValueError('Unexpected owned application UID')
        runtime=Path(__file__).resolve().parents[1];backend=Backend(runtime,uid)
        initial='app' if not (ROOT/'config.json').exists() and (APP/'config.json').exists() else 'root'
        coordinator=Coordinator(CONTROL/'mode.sqlite3',backend,initial=initial)
        stopping=False
        def stop(*_):
            nonlocal stopping
            stopping=True
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        private_json(APPFILES/'root-control.json',{'version':'0.2.5','available':True,'modes':list(MODES),'updated':int(time.time())},uid)
        try:
            if coordinator.state()['enabled']:backend.reconcile(coordinator.state()['mode'])
            else:backend.stop(coordinator.state()['mode'])
            private_json(APPFILES/'mode-status.json',coordinator.state(),uid)
            last_request=None;retry_at=0;retry_delay=2;next_descriptor=time.monotonic()+30
            while not stopping and (ROOT/'enabled').is_file() and not (MODULE/'disable').exists() and not (MODULE/'remove').exists():
                selected=coordinator.state()['mode']
                if time.monotonic()>=next_descriptor:
                    private_json(APPFILES/'root-control.json',{'version':'0.2.5','available':True,'modes':list(MODES),'updated':int(time.time())},uid);next_descriptor=time.monotonic()+30
                if coordinator.state()['enabled'] and selected!='app' and backend.child is not None and backend.child.poll() is not None and time.monotonic()>=retry_at:
                    try:backend.start(selected);retry_delay=2
                    except Exception as error:
                        private_json(APPFILES/'mode-status.json',coordinator.state()|{'error':type(error).__name__},uid)
                        retry_at=time.monotonic()+retry_delay;retry_delay=min(30,retry_delay*2)
                request=APPFILES/'mode-request.json'
                if request.exists():
                    info=request.lstat()
                    identity=(info.st_ino,info.st_mtime_ns,info.st_size)
                    if identity!=last_request and stat.S_ISREG(info.st_mode) and info.st_uid==uid and info.st_size<=1024 and not info.st_mode&0o077:
                        last_request=identity
                        try:
                            value=json.loads(request.read_text())
                            if set(value)!={'request_id','mode'}:raise ValueError('Fixed mode request fields required')
                            if value['mode']=='stop':receipt=coordinator.stop(value['request_id'])
                            elif value['mode']=='reconcile':receipt=coordinator.reconcile(value['request_id'])
                            else:receipt=coordinator.change(value['request_id'],value['mode'])
                            private_json(APPFILES/'mode-status.json',coordinator.state()|{'receipt':receipt},uid)
                        except Exception as error:private_json(APPFILES/'mode-status.json',coordinator.state()|{'error':type(error).__name__},uid)
                time.sleep(.5)
        finally:
            backend.stop(coordinator.state()['mode']);coordinator.close()
            private_json(APPFILES/'root-control.json',{'version':'0.2.5','available':False,'modes':list(MODES)},uid)

if __name__=='__main__':main()
