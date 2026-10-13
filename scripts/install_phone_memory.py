"""Run on the owner's phone as root. Never emits configuration or note contents."""
from pathlib import Path
import datetime,gzip,hashlib,json,os,re,secrets,shutil,signal,sqlite3,subprocess,sys,time

BASE=Path('/data/adb/mini-codex');MOD=Path('/data/adb/modules/mini_codex')
PREFIX=Path('/data/data/com.termux/files/usr');STAGE=Path('/data/local/tmp/codaki-memory-in')
SERVICE=PREFIX/'var/lib/codaki-memory';LIB=PREFIX/'lib/codaki-memory'
FILES=('memory_bridge.py','memory_service.py','project_graph.py','native_phone.py','support_runtime.py','graph-runtime.zip','tool-definitions.json')

def write_private(path,data,uid=0):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.new')
    with temp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.chmod(temp,0o600);os.chown(temp,uid,uid);temp.replace(path)

def restore_boot_watcher():
    target=str(MOD/'service.sh').encode()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args=(proc/'cmdline').read_bytes().split(b'\0')
            if target in args and Path(os.fsdecode(args[0])).name in ('sh','busybox'):return
        except OSError:pass
    env=dict(os.environ,PATH=str(PREFIX/'bin')+':/system/bin',LD_LIBRARY_PATH=str(PREFIX/'lib'),PYTHONDONTWRITEBYTECODE='1')
    subprocess.Popen(['/system/bin/sh',str(MOD/'service.sh')],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

def install():
    if os.geteuid()!=0:raise RuntimeError('Root required')
    if not (BASE/'enabled').is_file() or (MOD/'disable').exists() or (MOD/'remove').exists():raise RuntimeError('Agent must already be enabled')
    uid=Path('/data/data/com.termux').stat().st_uid
    if not 10000<=uid<=19999:raise RuntimeError('Unexpected Termux UID')
    # All staged code is validated before modifying the installed worker.
    for name in FILES:
        p=STAGE/name
        if p.is_symlink() or not p.is_file():raise RuntimeError('Missing staged component')
        if name.endswith('.py'):compile(p.read_bytes(),name,'exec')
    backup=BASE/'memory-backups'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True,mode=0o700);(backup/'agent').mkdir(mode=0o700)
    for name in FILES:
        p=MOD/'agent'/name
        if p.is_file():shutil.copy2(p,backup/'agent'/name)
    shutil.copy2(MOD/'service.sh',backup/'service.sh')
    old=BASE/'memory/notes.sqlite3'
    if old.exists():
        with sqlite3.connect('file:'+str(old)+'?mode=ro',uri=True) as src,sqlite3.connect(backup/'notes.sqlite3') as dst:src.backup(dst)
        os.chmod(backup/'notes.sqlite3',0o600)
        (backup/'archives').mkdir(mode=0o700)
        with sqlite3.connect(backup/'notes.sqlite3') as db:
            for (name,) in db.execute('SELECT file FROM archives'):
                if not re.fullmatch(r'[0-9a-f]{32}\.json\.gz',name):raise RuntimeError('Invalid legacy archive')
                p=BASE/'memory/archives'/name
                if p.is_symlink() or not p.is_file():raise RuntimeError('Legacy archive missing')
                shutil.copy2(p,backup/'archives'/name)
    for path in (SERVICE,SERVICE/'data',LIB):path.mkdir(parents=True,exist_ok=True,mode=0o700);os.chown(path,uid,uid);os.chmod(path,0o700)
    key=secrets.token_urlsafe(48)
    if (BASE/'memory-service.json').exists():key=json.loads((BASE/'memory-service.json').read_text())['key']
    cfg={'scope':'codaki-owner-phone','key':key,'port':8420,'data_dir':str(SERVICE/'data'),'quota_bytes':5*1024**3}
    write_private(SERVICE/'service.json',json.dumps(cfg).encode(),uid)
    write_private(LIB/'codaki-external.mjs',(STAGE/'codaki-external.mjs').read_bytes(),uid)
    write_private(LIB/'LICENSE.Tencent',(STAGE/'LICENSE.Tencent').read_bytes(),uid)
    for name in FILES:write_private(MOD/'agent'/name,(STAGE/name).read_bytes())
    graph=BASE/'project-graph';graph.mkdir(exist_ok=True,mode=0o700)
    for name in ('graph.json','manifest.json','LICENSE.Graphify','LICENSE.NetworkX'):write_private(graph/name,(STAGE/name).read_bytes())
    env=dict(os.environ,PATH=str(PREFIX/'bin')+':/system/bin',LD_LIBRARY_PATH=str(PREFIX/'lib'),PYTHONDONTWRITEBYTECODE='1')
    # Stop the shell watcher before stopping its child; otherwise recovery can
    # race the update and immediately create a new supervisor with the old code.
    target=str(MOD/'service.sh').encode()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args=(proc/'cmdline').read_bytes().split(b'\0')
            if target in args and Path(os.fsdecode(args[0])).name in ('sh','busybox'):os.kill(int(proc.name),signal.SIGTERM)
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    supervisor=BASE/'state/memory-supervisor.pid'
    if supervisor.exists():
        pid=int(supervisor.read_text())
        try:
            if b'memory_service.py' not in (Path('/proc')/str(pid)/'cmdline').read_bytes():raise RuntimeError('Unexpected supervisor PID')
            os.kill(pid,signal.SIGTERM)
        except FileNotFoundError:pass
        for _ in range(20):
            if not (Path('/proc')/str(pid)).exists():
                if supervisor.exists() and supervisor.read_text().strip()==str(pid):supervisor.unlink()
                break
            if not supervisor.exists():break
            time.sleep(1)
        else:raise RuntimeError('Previous memory supervisor did not stop')
    # Migrate orphaned children from the prior Magisk-su launch method.
    node=str(PREFIX/'bin/node').encode();bundle=str(LIB/'codaki-external.mjs').encode();configuration=str(SERVICE/'service.json').encode()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args=(proc/'cmdline').read_bytes().split(b'\0')
            if args[:3]==[node,bundle,configuration] and proc.stat().st_uid==uid:
                os.kill(int(proc.name),signal.SIGTERM)
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    time.sleep(1)
    subprocess.Popen([str(PREFIX/'bin/python'),str(MOD/'agent/memory_service.py')],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    # Publish bridge configuration only after authenticated Node health succeeds.
    sys.path.insert(0,str(MOD/'agent'));from memory_bridge import MemoryBridge
    bridge_cfg={'url':'http://127.0.0.1:8420','key':key,'data_dir':str(SERVICE/'data'),
                'accounting_roots':[str(BASE/'memory'),str(BASE/'memory-backups'),str(BASE/'state'),str(graph),str(SERVICE/'data')]}
    probe=BASE/'memory-service.probe.json';write_private(probe,json.dumps(bridge_cfg).encode())
    for _ in range(20):
        try:
            health=MemoryBridge(probe).health()
            if health.get('adapter_revision')!=hashlib.sha256((STAGE/'codaki-external.mjs').read_bytes()).hexdigest():raise RuntimeError('Old memory bundle is still running')
            break
        except RuntimeError:time.sleep(1)
    else:raise RuntimeError('New memory service did not start; existing worker left enabled')
    probe.replace(BASE/'memory-service.json')
    write_private(MOD/'service.sh',(STAGE/'service.sh').read_bytes());os.chmod(MOD/'service.sh',0o755)
    (BASE/'memory-backups/latest').write_text(str(backup))
    # Replace shell supervisors so this update's recovery loop is live now.
    target=str(MOD/'service.sh').encode()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args=(proc/'cmdline').read_bytes().split(b'\0')
            if target in args and Path(os.fsdecode(args[0])).name in ('sh','busybox'):os.kill(int(proc.name),signal.SIGTERM)
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    subprocess.Popen(['/system/bin/sh',str(MOD/'service.sh')],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    # Existing shell supervisor and nonblocking worker lock perform the restart.
    pidpath=BASE/'agent.pid'
    if pidpath.exists():
        pid=int(pidpath.read_text());cmd=(Path('/proc')/str(pid)/'cmdline').read_bytes()
        if b'phone_agent.py' not in cmd:raise RuntimeError('Unexpected worker PID')
        os.kill(pid,signal.SIGTERM)
    print(json.dumps({'installed':True,'backup':str(backup),'engine':'tencentdb-original-external','worker_restart_requested':True}))

def migrate():
    sys.path.insert(0,str(MOD/'agent'));from memory_bridge import MemoryBridge
    from native_phone import redact_memory
    bridge=MemoryBridge();backup=Path((BASE/'memory-backups/latest').read_text())
    if not backup.is_relative_to(BASE/'memory-backups'):raise RuntimeError('Invalid backup location')
    receipt=[];counts={'notes':0,'archives':0}
    with sqlite3.connect('file:'+str(backup/'notes.sqlite3')+'?mode=ro',uri=True) as db:
        rows=[]
        for ident,name,title,summary,tags,updated in db.execute('SELECT id,file,title,summary,tags,updated FROM archives ORDER BY updated,id'):
            p=backup/'archives'/name
            raw=gzip.decompress(p.read_bytes())
            if len(raw)>128*1024:raise RuntimeError('Archive exceeds summary limit')
            data=json.loads(raw);rows.append(('archives',str(ident),data['title'][:120]+' [archive:'+str(ident)+']',data['content'],data['tags'],data['updated'],'L0'))
        for ident,title,content,tags,updated in db.execute('SELECT id,title,content,tags,updated FROM notes ORDER BY updated,id'):
            rows.append(('notes',str(ident),title,content,json.loads(tags),updated,'L1'))
    for kind,ident,title,content,tags,updated,layer in rows:
        source_id='legacy:'+kind+':'+ident
        payload={'title':redact_memory(title),'content':redact_memory(content),'tags':[redact_memory(x) for x in tags],
                 'memory':{'layer':layer,'status':'historical','source':'legacy SQLite backup','source_id':source_id,'device':'android','project':'codaki','valid_from':str(updated)}}
        result=bridge.save(**payload)
        check=bridge.read(result['id'])['notes'][0]
        if check['content']!=payload['content'] or check['memory']['source_id']!=source_id:raise RuntimeError('Imported note read-back differs')
        counts[kind]+=1;receipt.append({'source_id':source_id,'id':result['id'],'version':result['version'],'sha256':hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()})
    report={'imported':counts,'verified':len(receipt),'engine':'tencentdb-original-external','status':'historical','records':receipt}
    write_private(BASE/'memory-migration.json',json.dumps(report).encode())
    print(json.dumps({k:report[k] for k in ('imported','verified','engine','status')}))

if __name__=='__main__':
    if sys.argv[1:]==['install']:
        try:install()
        except Exception:
            restore_boot_watcher()
            raise
    elif sys.argv[1:]==['migrate']:migrate()
    else:raise SystemExit('Expected install or migrate')
