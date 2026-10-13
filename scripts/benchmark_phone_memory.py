"""Synthetic checks in disposable data, no owner notes or secrets in output."""
from pathlib import Path
import hashlib,json,os,secrets,signal,shutil,subprocess,sys,tempfile,time,urllib.request,urllib.error
sys.path.insert(0,'/data/adb/modules/mini_codex/agent')
from memory_bridge import MemoryBridge,allocated_bytes
from memory_service import child_command,PREFIX
from project_graph import ProjectGraph

def main():
 uid=Path('/data/data/com.termux').stat().st_uid
 parent=Path(PREFIX)/'var/lib/codaki-memory'
 root=Path(tempfile.mkdtemp(prefix='codaki-bench-',dir=parent));os.chown(root,uid,uid)
 key=secrets.token_urlsafe(48);cfg=root/'service.json';data=root/'data';data.mkdir();os.chown(data,uid,uid)
 cfg.write_text(json.dumps({'key':key,'scope':'synthetic-test','port':8421,'data_dir':str(data)}));os.chmod(cfg,0o600);os.chown(cfg,uid,uid)
 bridgecfg=root/'bridge.json';bridgecfg.write_text(json.dumps({'key':key,'url':'http://127.0.0.1:8421','accounting_roots':[str(data)]}));os.chmod(bridgecfg,0o600)
 b=MemoryBridge(bridgecfg);cmd,env=child_command(uid);cmd[2]=str(cfg)
 child=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,user=uid,group=uid,extra_groups=[])
 checks=[];saved={}
 def check(name,fn):
  start=time.perf_counter();fn();checks.append({'name':name,'passed':True,'ms':round((time.perf_counter()-start)*1000,2)})
 def require(value):
  if not value:raise AssertionError('Synthetic expectation failed')
 def rejects(fn):
  try:fn()
  except (RuntimeError,ValueError):return
  raise AssertionError('Invalid synthetic input accepted')
 try:
  for _ in range(20):
   try:b.health();break
   except RuntimeError:time.sleep(.2)
  check('original FTS without LLM',lambda:require(b.health()['fts_available'] and not b.health()['llm_enabled']))
  for layer in ('L0','L1','L2','L3'):
   def save(layer=layer):
    saved[layer]=b.save('Слой '+layer,'Проверенное восстановление Termux памяти '+layer,['termux'],{'layer':layer,'device':'android','project':'synthetic','status':'verified','source':'synthetic functional test'})
    require(saved[layer]['saved'])
   check('durable '+layer,save)
  check('Russian prefix search',lambda:require(len(b.search('ПАМЯТ')['notes'])==4))
  check('tag search',lambda:require(len(b.search('termux')['notes'])==4))
  check('device isolation',lambda:require(not b.search('termux',5,{'device':'windows'})['notes']))
  check('project isolation',lambda:require(not b.search('termux',5,{'project':'other'})['notes']))
  check('layer filter before limit',lambda:require(b.search('termux',1,{'layer':'L3'})['notes'][0]['memory']['layer']=='L3'))
  check('status filter',lambda:require(len(b.search('termux',5,{'status':'verified'})['notes'])==4))
  check('repeat delivery idempotent',lambda:require(b.save('Слой L1','Проверенное восстановление Termux памяти L1',['termux'],{'layer':'L1','device':'android','project':'synthetic','status':'verified','source':'synthetic functional test'})['unchanged']))
  check('record read-back',lambda:require(b.read(saved['L2']['id'])['notes'][0]['memory']['layer']=='L2'))
  check('version update',lambda:require(b.save('Слой L1','Новая проверка',['termux'],{'layer':'L1','device':'android','project':'synthetic','expected_version':1})['version']==2))
  check('stale version rejected',lambda:rejects(lambda:b.save('Слой L1','Конфликт',[],{'layer':'L1','device':'android','project':'synthetic','expected_version':1})))
  check('verified requires source',lambda:rejects(lambda:b.save('invalid','test',[],{'status':'verified'})))
  check('unknown metadata rejected',lambda:rejects(lambda:b.save('invalid','test',[],{'api_key':'fake'})))
  check('arbitrary record path rejected',lambda:rejects(lambda:b.read('../config.json')))
  b.save('устаревшее','снятый рецепт',[],{'status':'superseded'})
  check('superseded excluded',lambda:require(not b.search('рецепт')['notes']))
  check('superseded explicit retrieval',lambda:require(len(b.search('рецепт',5,{'status':'superseded'})['notes'])==1))
  for i in range(8):b.save('Бюджет '+str(i),'контекст '+'я'*2500,[],{'project':'budget'})
  check('UTF8 response budget',lambda:require(len(json.dumps(b.search('контекст',8),ensure_ascii=False).encode())<=6144))
  check('invalid result limit',lambda:rejects(lambda:b.search('x',31)))
  def unauthorized():
   try:urllib.request.urlopen('http://127.0.0.1:8421/health',timeout=2)
   except urllib.error.HTTPError as e:require(e.code==401);e.close();return
   raise AssertionError('Missing authorization accepted')
  check('unauthenticated request denied',unauthorized)
  graph=ProjectGraph()
  check('Graphify source hashes fresh',lambda:require(not graph._load()[2]))
  check('Graphify original query',lambda:require(graph.query('MemoryBridge')['engine']=='graphify-original'))
  check('Graphify node resolution',lambda:require(bool(graph.node('memory_bridge.py')['text'])))
  check('Graphify original path',lambda:require(bool(graph.path('memory_bridge.py','MemoryBridge')['text'])))
  rss=[]
  for p in Path('/proc').glob('[0-9]*'):
   try:
    raw=(p/'cmdline').read_bytes()
    if raw.startswith((PREFIX+'/bin/node').encode()) and b'codaki-external.mjs' in raw:
     fields={x.split(':',1)[0]:x.split(':',1)[1].strip() for x in (p/'status').read_text().splitlines() if ':' in x}
     rss.append({'pid':int(p.name),'uid':int(fields['Uid'].split()[0]),'rss_kib':int(fields['VmRSS'].split()[0]),'synthetic':str(cfg).encode() in raw})
   except (OSError,KeyError):pass
  print(json.dumps({'checks':checks,'passed':len(checks),'failed':0,'synthetic_only':True,'node_processes':rss,'production_data_bytes':allocated_bytes(parent/'data'),'graph_bytes':allocated_bytes(Path('/data/adb/mini-codex/project-graph'))},ensure_ascii=False))
 finally:
  if child.poll() is None:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
  if root.resolve().parent!=parent.resolve() or not root.name.startswith('codaki-bench-'):raise RuntimeError('Unsafe temporary cleanup path')
  shutil.rmtree(root)

if __name__=='__main__':main()
