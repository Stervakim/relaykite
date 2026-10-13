"""Exercise recovery of only Codaki's own memory service; no note contents."""
from pathlib import Path
import json,os,signal,sys,time
sys.path.insert(0,'/data/adb/modules/mini_codex/agent')
import native_phone as n
from memory_bridge import MemoryBridge,MemoryUnavailable

CFG=b'/data/data/com.termux/files/usr/var/lib/codaki-memory/service.json'
NODE=b'/data/data/com.termux/files/usr/bin/node'
BUNDLE=b'/data/data/com.termux/files/usr/lib/codaki-memory/codaki-external.mjs'

def nodes():
 result=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   a=(p/'cmdline').read_bytes().split(b'\0')
   if a[:3]==[NODE,BUNDLE,CFG]:
    fields={x.split(':',1)[0]:x.split(':',1)[1].strip() for x in (p/'status').read_text().splitlines() if ':' in x}
    result.append({'pid':int(p.name),'uid':int(fields['Uid'].split()[0]),'ppid':int(fields['PPid'])})
  except (OSError,KeyError):pass
 return result

def await_health(timeout=28):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:return MemoryBridge().health()
  except RuntimeError:time.sleep(.5)
 raise RuntimeError('Memory recovery exceeded deadline')

def main():
 initial=MemoryBridge().health();running=nodes()
 if len(running)!=1 or running[0]['uid']!=10480:raise RuntimeError('Unexpected memory process')
 os.kill(running[0]['pid'],signal.SIGTERM)
 for _ in range(10):
  try:MemoryBridge().health();time.sleep(.2)
  except MemoryUnavailable:break
 else:raise RuntimeError('Memory child did not stop')
 fallback=n.phone_memory_search('mini-codex-support',1)
 if fallback['engine']!='legacy-fallback':raise RuntimeError('Legacy fallback was not disclosed')
 try:n.phone_memory_save('recovery check must not save','synthetic',[],memory={'layer':'L2'})
 except MemoryUnavailable:pass
 else:raise RuntimeError('Structured save degraded silently')
 restarted=await_health()
 if restarted['notes_count']!=initial['notes_count']:raise RuntimeError('Recovery altered memory count')
 supervisor=Path('/data/adb/mini-codex/state/memory-supervisor.pid');old=int(supervisor.read_text())
 if b'memory_service.py' not in (Path('/proc')/str(old)/'cmdline').read_bytes():raise RuntimeError('Unexpected supervisor')
 os.kill(old,signal.SIGKILL)
 end=time.monotonic()+35
 while time.monotonic()<end:
  try:
   current=int(supervisor.read_text());running=nodes()
   if current!=old and len(running)==1 and running[0]['ppid']==current and running[0]['uid']==10480:
    health=MemoryBridge().health();break
  except (OSError,ValueError,RuntimeError):pass
  time.sleep(.5)
 else:raise RuntimeError('Boot watcher did not restore supervision')
 graph=n.phone_memory_health()['graph']
 if graph.get('stale'):raise RuntimeError('Graph source checksum is stale')
 print(json.dumps({'node_restart':True,'honest_legacy_search':True,'structured_save_failed_closed':True,'supervisor_crash_recovered':True,'single_node':True,'node_uid':running[0]['uid'],'notes_count':health['notes_count'],'adapter_revision':health['adapter_revision'],'graph':graph}))

if __name__=='__main__':main()
