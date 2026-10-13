"""Magisk supervisor; storage runs as the existing Termux application UID."""
from pathlib import Path
import os,signal,subprocess,time

BASE=Path('/data/adb/mini-codex');MOD=Path('/data/adb/modules/mini_codex')
PREFIX='/data/data/com.termux/files/usr'

def enabled(base=BASE,mod=MOD):
    return (base/'enabled').is_file() and not (mod/'disable').exists() and not (mod/'remove').exists()

def child_command(uid):
    if type(uid)!=int or not 10000<=uid<=19999:raise ValueError('Expected an Android application UID')
    cmd=[PREFIX+'/bin/node',PREFIX+'/lib/codaki-memory/codaki-external.mjs',PREFIX+'/var/lib/codaki-memory/service.json']
    env=dict(os.environ,PATH=PREFIX+'/bin:/system/bin',LD_LIBRARY_PATH=PREFIX+'/lib',HOME='/data/data/com.termux/files/home')
    return cmd,env

def is_owned_node(args,process_uid,uid,cmd):
    return process_uid==uid and args[:3]==[x.encode() for x in cmd]

def main():
    import fcntl
    lock=(BASE/'state'/'memory-service.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    (BASE/'state'/'memory-supervisor.pid').write_text(str(os.getpid()))
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    uid=Path('/data/data/com.termux').stat().st_uid
    cmd,env=child_command(uid)
    # A killed supervisor may leave its Node child alive. Only after acquiring
    # the single-instance lock, reap this service's exact UID+command tuple.
    orphans=[]
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if is_owned_node((proc/'cmdline').read_bytes().split(b'\0'),proc.stat().st_uid,uid,cmd):
                pid=int(proc.name);os.kill(pid,signal.SIGTERM);orphans.append(pid)
        except (OSError,ValueError):pass
    for _ in range(10):
        if not any((Path('/proc')/str(pid)).exists() for pid in orphans):break
        time.sleep(1)
    log=BASE/'state'/'memory-service.log'
    while not stopping and enabled():
        if log.exists() and log.stat().st_size>1024*1024:log.replace(log.with_suffix('.previous.log'))
        with log.open('ab') as out:
            child=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True,user=uid,group=uid,extra_groups=[])
            try:
                while child.poll() is None and not stopping and enabled():time.sleep(1)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
        for _ in range(15):
            if stopping or not enabled():break
            time.sleep(1)
    (BASE/'state'/'memory-supervisor.pid').unlink(missing_ok=True)

if __name__=='__main__':main()
