"""Durable explicit mode changes; commit authority before starting a new worker."""
import hashlib,json,re,sqlite3,threading,time
from pathlib import Path
from contextlib import closing

MODES=('app','root','root-termux')
class Coordinator:
    def __init__(self,path,backend,initial='root'):
        if initial not in MODES:raise ValueError('Unknown initial mode')
        path=Path(path).absolute()
        if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Unsafe mode journal')
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(path,check_same_thread=False,timeout=10);path.chmod(0o600)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS mode_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),mode TEXT,epoch INTEGER,enabled INTEGER DEFAULT 1)')
        if 'enabled' not in {r[1] for r in self.db.execute('PRAGMA table_info(mode_state)')}:self.db.execute('ALTER TABLE mode_state ADD COLUMN enabled INTEGER DEFAULT 1')
        self.db.execute('INSERT OR IGNORE INTO mode_state(singleton,mode,epoch,enabled) VALUES(1,?,0,1)',(initial,))
        self.db.execute('CREATE TABLE IF NOT EXISTS mode_changes(id TEXT PRIMARY KEY,mode TEXT,previous TEXT,status TEXT,committed INTEGER,error TEXT,created REAL)')
        self.db.execute("UPDATE mode_changes SET status='uncertain',error='Interrupted transition; reconcile selected mode and worker before new changes' WHERE status='started'");self.db.commit()
        self.backend=backend;self.lock=threading.RLock()
    def state(self):
        with self.lock:
            mode,epoch,enabled=self.db.execute('SELECT mode,epoch,enabled FROM mode_state WHERE singleton=1').fetchone()
            uncertain=self.db.execute("SELECT id FROM mode_changes WHERE status='uncertain' ORDER BY created DESC LIMIT 1").fetchone()
            return {'mode':mode,'epoch':epoch,'enabled':bool(enabled),'uncertain_request':uncertain[0] if uncertain else None}
    def result(self,ident):
        row=self.db.execute('SELECT mode,previous,status,committed,error FROM mode_changes WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Unknown mode request')
        return dict(zip(('mode','previous','status','committed','error'),row))|{'request_id':ident}
    def change(self,ident,mode):
        if not isinstance(ident,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',ident) or mode not in MODES:raise ValueError('Explicit mode and stable request ID required')
        with self.lock:
            old=self.db.execute('SELECT mode FROM mode_changes WHERE id=?',(ident,)).fetchone()
            if old:
                if old[0]!=mode:raise ValueError('Mode request ID reused')
                return self.result(ident)
            state=self.state()
            if state['uncertain_request']:raise RuntimeError('Previous mode change requires reconciliation')
            if self.db.execute('SELECT count(*) FROM mode_changes').fetchone()[0]>=1000:raise RuntimeError('Mode receipt capacity reached')
            previous=state['mode']
            self.backend.preflight(previous,mode)
            self.db.execute("INSERT INTO mode_changes VALUES(?,?,?,'started',0,NULL,?)",(ident,mode,previous,time.time()));self.db.commit()
            committed=False
            try:
                self.backend.stop(previous)
                if mode!=previous:self.backend.prepare(previous,mode,ident)
                # No worker exists during commit. Once this durable pointer
                # changes, the new copy is authoritative even if launch fails.
                self.db.execute('UPDATE mode_state SET mode=?,epoch=epoch+1,enabled=1 WHERE singleton=1',(mode,))
                self.db.execute('UPDATE mode_changes SET committed=1 WHERE id=?',(ident,));self.db.commit();committed=True
                self.backend.start(mode)
                self.db.execute("UPDATE mode_changes SET status='completed' WHERE id=?",(ident,));self.db.commit()
            except Exception as error:
                # Never roll back an authority pointer after the new worker
                # might have performed a queue action.
                self.db.execute("UPDATE mode_changes SET status='uncertain',error=? WHERE id=?",(type(error).__name__,ident));self.db.commit()
            return self.result(ident)
    def stop(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',ident):raise ValueError('Stable stop request ID required')
        with self.lock:
            old=self.db.execute('SELECT mode FROM mode_changes WHERE id=?',(ident,)).fetchone()
            if old:
                if old[0]!='stop':raise ValueError('Stop request ID reused')
                return self.result(ident)
            state=self.state()
            if state['uncertain_request']:raise RuntimeError('Previous change requires reconciliation')
            if self.db.execute('SELECT count(*) FROM mode_changes').fetchone()[0]>=1000:raise RuntimeError('Mode receipt capacity reached')
            # Persist owner stop before signalling: boot/recovery cannot undo it.
            self.db.execute("INSERT INTO mode_changes VALUES(?,'stop',?,'started',1,NULL,?)",(ident,state['mode'],time.time()))
            self.db.execute('UPDATE mode_state SET enabled=0,epoch=epoch+1 WHERE singleton=1');self.db.commit()
            try:
                self.backend.stop(state['mode']);self.db.execute("UPDATE mode_changes SET status='completed' WHERE id=?",(ident,))
            except Exception as error:self.db.execute("UPDATE mode_changes SET status='uncertain',error=? WHERE id=?",(type(error).__name__,ident))
            self.db.commit();return self.result(ident)
    def reconcile(self,ident):
        with self.lock:
            receipt=self.result(ident)
            if receipt['status']!='uncertain':return receipt
            mode=self.state()['mode']
            if self.state()['enabled']:self.backend.reconcile(mode)
            else:self.backend.stop(mode)
            self.db.execute("UPDATE mode_changes SET status='reconciled',error=NULL WHERE id=?",(ident,));self.db.commit()
            return self.result(ident)
    def close(self):self.db.close()
