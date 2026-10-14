"""Bundled worker for explicitly selected modes; this process never requests su."""
import os,json,signal,subprocess,time,urllib.request,threading,select
from pathlib import Path
from contextlib import contextmanager
from runtime_paths import BASE,MODE

def memory_command():
    verify_mode()
    cfg=BASE/'memory-node.json';value=json.loads(cfg.read_text())
    data=BASE/'memory-service/data'
    if cfg.is_symlink() or value.get('data_dir')!=str(data) or value.get('scope')!='codaki-owner-phone':raise ValueError('Memory configuration scope mismatch')
    if not isinstance(value.get('key'),str) or len(value['key'])<40:raise ValueError('Private memory credential required')
    native=Path(os.environ['RELAYKITE_NATIVE'])
    command=[str(native/'librelaykite_node.so'),str(Path(__file__).with_name('memory-runtime')/'codaki-external.mjs'),str(cfg)]
    return command,value

def verify_mode():
    if MODE=='app' and os.geteuid()==0:raise PermissionError('App worker requires the actual Android app UID')
    if MODE in ('root','root-termux') and os.geteuid()!=0:raise PermissionError('Root mode requires the separately authorized root executor')
    if MODE not in ('app','root','root-termux'):raise ValueError('Unknown runtime mode')

def validate_memory_ready(raw,port):
    if not isinstance(raw,bytes) or len(raw)>8192:raise ValueError('Invalid memory startup receipt')
    value=json.loads(raw)
    if not isinstance(value,dict) or value.get('ready') is not True or value.get('engine')!='tencentdb-original-external' or value.get('port')!=port:raise ValueError('Owned memory listener did not start')
    return value

@contextmanager
def owner_pid(path):
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Unsafe worker PID path')
    value=str(os.getpid());next_file=path.with_suffix('.next')
    with next_file.open('w') as out:out.write(value+'\n');out.flush();os.fsync(out.fileno())
    next_file.chmod(0o600);next_file.replace(path)
    try:yield
    finally:
        if path.exists() and not path.is_symlink() and path.read_text().strip()==value:path.unlink()

def owned_child(receipt,uid,born,argv,pgid):
    return uid==receipt.get('uid')==os.geteuid() and born is not None and born==receipt.get('generation') and argv==receipt.get('argv') and pgid==receipt.get('pid')

def reap_previous(path):
    from terminal_manager import generation
    if not path.exists():return
    if path.is_symlink() or path.stat().st_size>8192:raise ValueError('Unsafe memory process receipt')
    receipt=json.loads(path.read_text());pid=receipt['pid']
    if type(pid)!=int or pid<=1:raise ValueError('Invalid memory process receipt')
    proc=Path('/proc')/str(pid)
    def matches():
        try:return owned_child(receipt,proc.stat().st_uid,generation(pid),[os.fsdecode(a) for a in (proc/'cmdline').read_bytes().split(b'\0') if a],os.getpgid(pid))
        except ProcessLookupError:return False
        except FileNotFoundError:return False
    if matches():
        os.killpg(pid,signal.SIGTERM);until=time.monotonic()+5
        while matches() and time.monotonic()<until:time.sleep(.1)
        if matches():os.killpg(pid,signal.SIGKILL)
    path.unlink()

def main():
    verify_mode()
    os.umask(0o077);BASE.mkdir(mode=0o700,parents=True,exist_ok=True)
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    # No relay requests until the original private installation has been
    # explicitly imported. Waiting never creates a new credential or account.
    if not (BASE/'enabled').is_file() or not (BASE/'config.json').is_file():
        print('RelayKite '+MODE+' mode ready; private configuration not imported',flush=True)
        while not stopping:time.sleep(.2)
        return
    from configure import read_config,inspect_storage
    inspect_storage(BASE);config=read_config(BASE/'config.json')
    from phone_agent import acquire_instance_lock,run_agent
    with acquire_instance_lock(Path(config['state_dir'])),owner_pid(BASE/'agent.pid'):
        command,memory=memory_command()
        receipt=Path(config['state_dir'])/'memory-node.pid';reap_previous(receipt)
        env=os.environ.copy();env.pop('PYTHONPATH',None)
        child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
        from terminal_manager import generation
        monitoring=threading.Event()
        def watch_memory():
            while not monitoring.wait(.2):
                if child.poll() is not None:
                    os.kill(os.getpid(),signal.SIGTERM)
                    monitoring.wait(1)
        monitor=threading.Thread(target=watch_memory,daemon=True)
        try:
            next_receipt=receipt.with_suffix('.next');next_receipt.write_text(json.dumps({'pid':child.pid,'generation':generation(child.pid),'uid':os.geteuid(),'argv':command}));os.chmod(next_receipt,0o600);next_receipt.replace(receipt)
            # Only the child that successfully bound the port can emit this
            # receipt. A live older service with the same key is insufficient.
            startup=bytearray();until=time.monotonic()+15
            while b'\n' not in startup and time.monotonic()<until and child.poll() is None and not stopping:
                readers,_,_=select.select([child.stdout],[],[],.2)
                if readers:
                    chunk=os.read(child.stdout.fileno(),4096)
                    if not chunk:break
                    startup.extend(chunk)
                    if len(startup)>8192:raise ValueError('Memory startup output exceeds limit')
            validate_memory_ready(bytes(startup).split(b'\n',1)[0],memory['port'])
            child.stdout.close()
            ready=False;opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(50):
                if stopping or child.poll() is not None:break
                try:
                    req=urllib.request.Request('http://127.0.0.1:'+str(memory['port'])+'/health',headers={'Authorization':'Bearer '+memory['key']})
                    with opener.open(req,timeout=1) as response:health=json.loads(response.read(16384))
                    if health.get('engine')!='tencentdb-original-external' or not health.get('fts_available'):raise ValueError('Original memory engine unavailable')
                    ready=True;break
                except (OSError,ValueError):time.sleep(.2)
            if not ready or stopping or child.poll() is not None:raise RuntimeError('Owned memory service not ready')
            print('RelayKite '+MODE+' mode ready; original Tencent memory verified',flush=True)
            monitor.start()
            # run_agent installs its own graceful stop handler and owns the
            # original durable journal/managed managers until it returns.
            run_agent(config,Path(config['state_dir']))
        finally:
            monitoring.set()
            if monitor.is_alive():monitor.join(timeout=1)
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            receipt.unlink(missing_ok=True)
            child.stdout.close()

if __name__=='__main__':
    try:main()
    except Exception as error:
        # No exception messages/configuration in public service status.
        print('RelayKite app worker stopped: '+type(error).__name__,flush=True)
        raise SystemExit(1)
