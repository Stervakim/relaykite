"""Optional memory-only producer; model results are always proposed records."""
import hashlib,json,sqlite3,threading,time,urllib.error
from pathlib import Path
from contextlib import closing
from runtime_paths import BASE
from memory_power import phone_state,permitted

class SummaryPump:
    def __init__(self,relay,base=BASE):
        self.relay=relay;self.base=Path(base);self.stop=threading.Event();self.thread=None
    def tick(self):
        config=self.base/'summary-route.json'
        if not config.is_file() or config.is_symlink() or self.stop.is_set():return {'enabled':False}
        value=json.loads(config.read_text())
        if set(value)!={'enabled','connection_id'} or value.get('enabled') is not True:return {'enabled':False}
        connection=value['connection_id']
        if not isinstance(connection,str) or len(connection)!=36:raise ValueError('Existing paired PC connection required')
        # Cleanup is independent of battery gating and has its own durable ID.
        cleanup=self.base/'model-cleanup.json'
        if not cleanup.is_file() and self.base==Path('/data/data/org.relaykite.runtime/files/owner'):
            cleanup=self.base.parent/'model-cleanup.json'
        if not cleanup.is_file() and getattr(__import__('os'),'geteuid',lambda:-1)()==0:
            cleanup=Path('/data/data/org.relaykite.runtime/files/model-cleanup.json')
        if cleanup.is_file():
            request=json.loads(cleanup.read_text())
            if set(request)!={'request_id','package'} or request['package']!='com.openai.chatgpt':raise ValueError('Invalid local model cleanup signal')
            receipt=self.relay.request('/bridge/api',{'action':'from_phone','connection_id':connection,'operation':'call','tool':'pc_memory_model_remove','arguments':{},'request_id':request['request_id']})
            if receipt.get('status')=='completed' and receipt.get('result',{}).get('removed') is True:
                cleanup.unlink();return {'enabled':False,'reason':'model_removed'}
            return {'enabled':False,'reason':'model_cleanup_pending'}
        if not permitted(phone_state(self.base)):return {'enabled':True,'reason':'battery_paused'}
        from memory_bridge import MemoryBridge
        memory=MemoryBridge(self.base/'memory-service.json')
        records=memory.search('RelayKite',limit=2,filters={'project':'codaki','layer':'L1','status':'verified'}).get('notes',[])
        if self.stop.is_set():return {'stopped':True}
        events=[{'id':r['id'],'version':r['version'],'title':r['title'][:100],'content':r['content'][:600]} for r in records]
        ident='summary_'+hashlib.sha256(json.dumps([connection,events],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:48]
        with closing(sqlite3.connect(self.base/'state/jobs.sqlite3',timeout=5)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS background_summaries(id TEXT PRIMARY KEY,job_id TEXT,status TEXT,updated REAL,payload TEXT)')
            if 'payload' not in {r[1] for r in db.execute('PRAGMA table_info(background_summaries)')}:db.execute('ALTER TABLE background_summaries ADD COLUMN payload TEXT')
            pending=db.execute("SELECT id,job_id,payload FROM background_summaries WHERE status='started' AND payload IS NOT NULL ORDER BY updated LIMIT 1").fetchone()
            if pending:
                selected=json.loads(pending[2]);ident=pending[0];events=selected['events']
                if selected['connection_id']!=connection:
                    db.execute("UPDATE background_summaries SET status='unavailable',payload=NULL WHERE id=?",(ident,));db.commit();return {'request_id':ident,'status':'unavailable'}
            elif not records:return {'enabled':True,'reason':'no_sources'}
            old=db.execute('SELECT job_id,status FROM background_summaries WHERE id=?',(ident,)).fetchone()
            if old and old[1] in ('completed','unavailable'):return {'request_id':ident,'status':old[1]}
            if not old:
                if db.execute('SELECT count(*) FROM background_summaries').fetchone()[0]>=1000:return {'enabled':True,'reason':'receipt_capacity'}
                db.execute("INSERT INTO background_summaries(id,job_id,status,updated,payload) VALUES(?,NULL,'started',?,?)",(ident,time.time(),json.dumps({'connection_id':connection,'events':events})));db.commit()
            body={'action':'from_phone','connection_id':connection}
            if old and old[0]:
                try:reply=self.relay.request('/bridge/api',body|{'operation':'result','job_id':old[0]})
                except urllib.error.HTTPError as error:
                    try:
                        expired=error.code in (400,403,404,410) and json.loads(error.read(1024)).get('error')=='Job not found or expired; inspect PC state before retrying'
                    except (ValueError,AttributeError):expired=False
                    finally:error.close()
                    if not expired:raise
                    db.execute("UPDATE background_summaries SET status='unavailable',payload=NULL WHERE id=?",(ident,));db.commit()
                    return {'request_id':ident,'status':'unavailable','reason':'receipt_expired'}
            else:
                reply=self.relay.request('/bridge/api',body|{'operation':'call','tool':'pc_memory_summarize','arguments':{'events':events},'request_id':ident})
            if self.stop.is_set():return {'stopped':True}
            job=reply.get('job_id')
            if not isinstance(job,str):raise ValueError('Summary job receipt missing')
            db.execute('UPDATE background_summaries SET job_id=?,updated=? WHERE id=?',(job,time.time(),ident));db.commit()
            if reply.get('status')=='cancelled':
                db.execute("UPDATE background_summaries SET status='unavailable',payload=NULL WHERE id=?",(ident,));db.commit()
                return {'request_id':ident,'status':'unavailable','reason':'cancelled'}
            if reply.get('status') not in ('completed','uncertain'):return {'request_id':ident,'status':'pending'}
            result=reply.get('result',{})
            if reply.get('status')=='uncertain' or not isinstance(result,dict) or result.get('available') is not True:
                db.execute("UPDATE background_summaries SET status='unavailable',payload=NULL WHERE id=?",(ident,));db.commit();return {'request_id':ident,'status':'unavailable'}
            content=result.get('summary');sources=[{'id':r['id'],'version':r['version']} for r in events]
            if result.get('status')!='proposed' or result.get('source_records')!=sources or not isinstance(content,str) or not 1<=len(content.encode())<=4096:raise ValueError('Invalid proposed summary evidence')
            if self.stop.is_set():return {'stopped':True}
            saved=memory.save('Background summary '+ident,content,['background-summary','relaykite'],{'layer':'L1','status':'proposed','device':'shared','project':'codaki','source_id':ident,'source':json.dumps(sources),'versions':'PC local Qwen3-0.6B; no tool authority'})
            if not saved.get('saved'):raise ValueError('Proposed summary not saved')
            db.execute("UPDATE background_summaries SET status='completed',payload=NULL WHERE id=?",(ident,));db.commit()
            return {'request_id':ident,'status':'completed','memory_id':saved['id']}
    def start(self):
        if not (self.base/'summary-route.json').is_file():return
        def work():
            while not self.stop.wait(15):
                try:result=self.tick();delay=0 if result.get('status')=='pending' else 1200
                except Exception:delay=1200  # Optional failures cannot escape to queue/tools.
                if self.stop.wait(delay):break
        self.thread=threading.Thread(target=work,name='relaykite-memory-summary',daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread is not None:self.thread.join(timeout=25)
