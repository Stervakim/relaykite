import argparse, json, os, signal, sys, threading
from pathlib import Path
from .engine import Engine
from .mcp import handle

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['stdio','agent','local','check']);p.add_argument('--platform',choices=['android','windows'],default='android');p.add_argument('--windows-backend',choices=['native','sky'],default='native');p.add_argument('--config',type=Path);p.add_argument('--state',type=Path,default=Path('state'));p.add_argument('--device-id',default='local');p.add_argument('--local-ipc-windows',action='store_true');p.add_argument('--local-ipc',action='store_true');a=p.parse_args()
    if a.local_ipc_windows and (a.platform!='windows' or a.mode!='agent'):p.error('Windows local IPC requires the existing Windows agent mode')
    if a.local_ipc and (a.platform!='android' or a.mode!='agent'):p.error('Android local IPC requires the existing Android agent mode')
    if a.mode=='agent' and not a.config:p.error('--config required for agent mode')
    if a.platform=='android':from .android import AndroidBackend as Backend
    elif a.windows_backend=='sky':from .sky import SkyBackend as Backend
    else:from .windows_native import WindowsBackend as Backend
    a.state.mkdir(parents=True,exist_ok=True)
    lock=None
    if os.name!='nt':
        import fcntl
        lock=(a.state/'agent.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    else:
        import msvcrt
        lock=(a.state/'agent.lock').open('a+b');lock.seek(0);lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    if a.platform=='windows':
        from .windows_sessions import WindowsSessions
        engine=WindowsSessions(Backend,a.state/'journal.sqlite3')
    else:
        from .android_sessions import AndroidSessions
        engine=AndroidSessions(a.state/'journal.sqlite3')
    if a.platform=='android':
        from .local import LockedEngine
        engine=LockedEngine(engine)
    backend=engine.backend;stop=threading.Event();local_rpc=None;boundary=None;ipc=None
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    try:
        if a.mode=='check':print(json.dumps(engine._run('capabilities',{}),ensure_ascii=False));return
        if a.mode=='local':
            if a.platform!='android':p.error('local socket mode requires Android')
            from .local import serve
            serve(engine,stop,str(a.state/'portable.sock'))
        elif a.mode=='agent':
            from .agent import Agent,Relay
            if not a.config:p.error('--config required for agent mode')
            cfg=json.loads(a.config.read_text(encoding='utf-8'));cfg['device_id']=cfg.get('device_id',a.device_id)
            relay=Relay(cfg);agent=Agent(engine,relay,a.state/'outbox.sqlite3')
            try:
                if a.local_ipc_windows:
                    from .windows_ipc import Boundary,LocalRPC
                    boundary=Boundary(engine,a.state/'mini-bridge.sqlite3');local_rpc=LocalRPC(boundary).start()
                if a.local_ipc:
                    from .local import LocalServer
                    ipc=LocalServer(engine,stop,str(a.state.absolute()/'portable.sock')).start()
                agent.run(stop,local_rpc=local_rpc)
            finally:
                if local_rpc:local_rpc.close()
                if boundary:boundary.close()
                agent.close();relay.close()
        else:
            def reap():
                while not stop.wait(1):
                    try:engine.expire()
                    except Exception:pass
            timer=threading.Thread(target=reap,daemon=True);timer.start()
            for line in sys.stdin:
                if len(line.encode())>1024*1024:raise ValueError('MCP request too large')
                try:out=handle(engine,json.loads(line),a.device_id)
                except ValueError:out={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON'}}
                if out is not None:print(json.dumps(out,ensure_ascii=False),flush=True)
                if stop.is_set():break
    finally:
        stop.set()
        if ipc:ipc.close()
        engine.close()
        if lock:lock.close()

if __name__=='__main__':main()
