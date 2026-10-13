"""One explicit legacy-owner migration to the verified embedded root runtime.

Run only after staging the matching signed APK. Private config, memory, backups
and the existing task journal remain on-device. No grants or accounts change.
"""
import argparse,hashlib,json,os,shutil,signal,sqlite3,subprocess,sys,time,uuid,urllib.request
from pathlib import Path
from contextlib import closing
ROOT=Path('/data/adb/mini-codex');MODULE=Path('/data/adb/modules/mini_codex')
LEGACY=Path('/data/data/com.termux/files/usr')

def write(path,value):
    temp=path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
    with temp.open('x') as out:json.dump(value,out);out.flush();os.fsync(out.fileno())
    temp.chmod(0o600);temp.replace(path)
def health(config):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req=urllib.request.Request(config['url'].rstrip('/')+'/health',headers={'Authorization':'Bearer '+config['key']})
    with opener.open(req,timeout=5) as response:return json.loads(response.read(16384))
def environment():
    env=os.environ.copy();env.pop('LD_LIBRARY_PATH',None);env.pop('LD_PRELOAD',None);env['PATH']='/system/bin:/system/xbin';return env
def process(pid):
    path=Path('/proc')/str(pid)
    try:return {'pid':pid,'uid':path.stat().st_uid,'argv':[os.fsdecode(a) for a in (path/'cmdline').read_bytes().split(b'\0') if a]}
    except (FileNotFoundError,ProcessLookupError):return None
def stop(receipt,timeout=35):
    from terminal_manager import generation
    pid=receipt['pid'];born=receipt['generation']
    def same():
        actual=process(pid)
        return actual is not None and generation(pid)==born and actual['uid']==receipt['uid'] and actual['argv']==receipt['argv']
    if same():
        os.kill(pid,signal.SIGTERM);until=time.monotonic()+timeout
        while same() and time.monotonic()<until:time.sleep(.1)
        if same():os.kill(pid,signal.SIGKILL)
        until=time.monotonic()+5
        while same() and time.monotonic()<until:time.sleep(.1)
        if same():raise RuntimeError('Original owned process did not stop')

def migrate(runtime,service,expected_service_sha):
    if os.geteuid()!=0:raise PermissionError('Authorized root migration required')
    runtime=runtime.resolve()
    if runtime.parent!=Path('/data/adb/relaykite-runtime/versions') or len(runtime.name)!=64:raise ValueError('Use the verified installed runtime version')
    sys.path.insert(0,str(runtime/'agent'))
    from state_snapshot import copy_store
    from terminal_manager import generation
    from configure import read_config
    from root_supervisor import Backend
    cfg=read_config(ROOT/'config.json')
    bridge=json.loads((ROOT/'memory-service.json').read_text())
    original=json.loads((LEGACY/'var/lib/codaki-memory/service.json').read_text())
    if original.get('scope')!='codaki-owner-phone' or original.get('key')!=bridge.get('key') or original.get('data_dir')!=bridge.get('data_dir'):raise PermissionError('Original Tencent memory authority mismatch')
    if hashlib.sha256(service.read_bytes()).hexdigest()!=expected_service_sha:raise ValueError('Service source digest mismatch')
    if (ROOT/'memory-node.json').exists() or (ROOT/'memory-service').exists():raise RuntimeError('Migration already committed or staged; inspect its original receipt instead of repeating')
    before=health(bridge)
    if before.get('engine')!='tencentdb-original-external' or not before.get('fts_available'):raise RuntimeError('Original memory health unavailable')
    primary=process(int((ROOT/'agent.pid').read_text()))
    if primary is None or primary['uid']!=0 or str(MODULE/'agent/phone_agent.py') not in primary['argv'] or str(ROOT/'config.json') not in primary['argv']:raise PermissionError('Original worker identity mismatch')
    primary['generation']=generation(primary['pid'])
    watchers=[];nodes=[];termux_uid=LEGACY.parents[1].stat().st_uid
    for entry in Path('/proc').glob('[0-9]*'):
        value=process(int(entry.name))
        if value is None:continue
        args=value['argv']
        if value['uid']==0 and (str(MODULE/'service.sh') in args or str(MODULE/'agent/memory_service.py') in args):
            value['generation']=generation(value['pid']);watchers.append(value)
        if value['uid']==termux_uid and args[:3]==[str(LEGACY/'bin/node'),str(LEGACY/'lib/codaki-memory/codaki-external.mjs'),str(LEGACY/'var/lib/codaki-memory/service.json')]:
            value['generation']=generation(value['pid']);nodes.append(value)
    backup=ROOT/('native-migration-'+uuid.uuid4().hex);backup.mkdir(mode=0o700)
    report={'phase':'prepared','backup':str(backup),'runtime':str(runtime),'original_notes':before['notes_count'],'committed':False}
    receipt=backup/'receipt.json';write(receipt,report)
    for name in ('config.json','memory-service.json'):shutil.copyfile(ROOT/name,backup/name);(backup/name).chmod(0o600)
    shutil.copyfile(MODULE/'service.sh',backup/'service.sh');(backup/'service.sh').chmod(0o600)
    committed=False
    try:
        for watcher in watchers:stop(watcher,timeout=15)
        stop(primary)
        for node in nodes:stop(node,timeout=10)
        # Original PTY receipts name precise process generations. Reap them and
        # any recorded owned Node before copying the now-quiescent store.
        owned_uid=Path('/data/data/org.relaykite.runtime').stat().st_uid
        Backend(runtime,owned_uid).stop('root')
        report['phase']='stopped';write(receipt,report)
        journal=ROOT/'state/jobs.sqlite3'
        with closing(sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(backup/'jobs.sqlite3')) as destination:source.backup(destination)
        (backup/'jobs.sqlite3').chmod(0o600)
        snapshot=copy_store(Path(bridge['data_dir']),ROOT/'memory-service/data')
        node={**original,'data_dir':str(ROOT/'memory-service/data'),'port':8420,'quota_bytes':5*1024**3-32*1024**2}
        updated={**bridge,'data_dir':node['data_dir'],'accounting_roots':[str(ROOT),str(Path('/data/data/org.relaykite.runtime/files/owner')),bridge['data_dir']]}
        write(ROOT/'memory-node.json',node);write(ROOT/'memory-service.json',updated)
        committed=True;report.update(phase='committed',committed=True,snapshot_files=len(snapshot['files']),snapshot_bytes=snapshot['bytes']);write(receipt,report)
        temporary=MODULE/'service.sh.next';shutil.copyfile(service,temporary);temporary.chmod(0o755);temporary.replace(MODULE/'service.sh')
        subprocess.Popen(['/system/bin/sh',str(MODULE/'service.sh')],env=environment(),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        until=time.monotonic()+40
        while time.monotonic()<until:
            try:
                current=process(int((ROOT/'agent.pid').read_text()));active=health(updated)
                if current is not None and current['uid']==0 and str(runtime/'agent/app_worker.py') in current['argv'] and active['notes_count']==before['notes_count']:
                    report.update(phase='verified',native_worker_pid=current['pid'],notes_preserved=True,owner_config_preserved=(ROOT/'config.json').read_bytes()==(backup/'config.json').read_bytes());write(receipt,report);return report
            except (OSError,ValueError,KeyError):pass
            time.sleep(.2)
        raise RuntimeError('Committed native worker needs inspection; original receipts and memory remain authoritative')
    except Exception as error:
        report.update(phase='uncertain' if committed else 'failed',error=type(error).__name__,committed=committed);write(receipt,report)
        if not committed:
            # Queue actions have not moved to a new authority. Restart only the
            # original supervisor with its untouched owner config/journal.
            subprocess.Popen(['/system/bin/sh',str(MODULE/'service.sh')],env=environment(),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--service',type=Path,required=True);p.add_argument('--service-sha256',required=True);a=p.parse_args()
    try:print(json.dumps(migrate(a.runtime,a.service,a.service_sha256)))
    except Exception as error:print(json.dumps({'error':type(error).__name__,'instruction':'Inspect the on-device migration receipt; never repeat a committed migration blindly.'}));raise SystemExit(1)
