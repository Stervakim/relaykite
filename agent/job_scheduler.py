"""Bounded owner-local jobs in the original journal; never replay effects."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

class Scheduler:
    def __init__(self,path,executor,workers=4,max_pending=16,max_output_bytes=1024*1024):
        if type(workers)!=int or not 1<=workers<=8:raise ValueError('workers must be 1..8')
        if type(max_pending)!=int or not 1<=max_pending<=64:raise ValueError('pending limit must be 1..64')
        if type(max_output_bytes)!=int or not 64<=max_output_bytes<=2*1024*1024:raise ValueError('Invalid output limit')
        path=Path(path).absolute()
        if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Journal symlink rejected')
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.instance=(path.parent/'managed-tasks.lock').open('a+b')
        try:
            if os.name=='nt':
                import msvcrt
                self.instance.seek(0);self.instance.write(b'1');self.instance.flush();self.instance.seek(0)
                msvcrt.locking(self.instance.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.instance.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:
            self.instance.close();raise RuntimeError('Another scheduler owns this journal') from None
        self.executor=executor;self.max_pending=max_pending;self.max_output=max_output_bytes
        self.condition=threading.Condition(threading.RLock());self.active={};self.stopping=False
        self.db=sqlite3.connect(path,check_same_thread=False,timeout=10)
        os.chmod(path,0o600)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS managed_tasks (id TEXT PRIMARY KEY,fingerprint TEXT,operation TEXT,arguments TEXT,resources TEXT,deadline REAL,status TEXT,result TEXT,updated REAL)')
        self.db.execute("UPDATE managed_tasks SET status='uncertain',result=? WHERE status IN ('running','queued')",(json.dumps({'error':'Previous process stopped. Inspect state; automatic replay is blocked.'}),))
        self.db.commit()
        self.threads=[threading.Thread(target=self._worker,name='relaykite-task-'+str(i),daemon=True) for i in range(workers)]
        for thread in self.threads:thread.start()

    def submit(self,ident,operation,arguments,*,resources=(),timeout_seconds=300):
        if not isinstance(ident,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',ident):raise ValueError('Stable task ID required')
        if not isinstance(operation,str) or not re.fullmatch('[a-z][a-z0-9_]{0,79}',operation) or not isinstance(arguments,dict):raise ValueError('Invalid task')
        if type(timeout_seconds) not in (int,float) or not math.isfinite(timeout_seconds) or not 1<=timeout_seconds<=3600:raise ValueError('Deadline must be 1..3600 seconds')
        resources=list(resources)
        if len(resources)>16 or any(not isinstance(r,str) or not 1<=len(r)<=512 or '\0' in r for r in resources):raise ValueError('Invalid resources')
        resources=sorted(set(resources))
        raw=json.dumps(arguments,sort_keys=True,separators=(',',':'),allow_nan=False)
        if len(raw.encode())>256*1024:raise ValueError('Task arguments exceed limit')
        digest=hashlib.sha256(json.dumps([operation,raw,resources,timeout_seconds],separators=(',',':')).encode()).hexdigest()
        with self.condition:
            row=self.db.execute('SELECT fingerprint FROM managed_tasks WHERE id=?',(ident,)).fetchone()
            if row:
                if row[0]!=digest:raise ValueError('Task ID reused with different arguments')
                return self.status(ident)
            if self.stopping:raise RuntimeError('Scheduler is stopping')
            pending=self.db.execute("SELECT count(*) FROM managed_tasks WHERE status='queued'").fetchone()[0]
            count=self.db.execute('SELECT count(*) FROM managed_tasks').fetchone()[0]
            if pending>=self.max_pending:raise RuntimeError('Job queue full; backpressure')
            # Retain receipts to prevent replay even when callers reconnect
            # years later. Exhaustion refuses new effects rather than deleting IDs.
            if count>=1000:raise RuntimeError('Receipt capacity reached; no new task was executed')
            now=time.time()
            self.db.execute("INSERT INTO managed_tasks VALUES(?,?,?,?,?,?,'queued',NULL,?)",(ident,digest,operation,raw,json.dumps(resources),now+timeout_seconds,now))
            self.db.commit();self.condition.notify_all()
            return self.status(ident)

    def status(self,ident):
        with self.condition:
            row=self.db.execute('SELECT status,result,deadline,updated FROM managed_tasks WHERE id=?',(ident,)).fetchone()
            if row is None:raise ValueError('Task not found; do not resubmit an uncertain effect')
            return {'task_id':ident,'status':row[0],'result':json.loads(row[1]) if row[1] else None,'deadline':row[2],'updated':row[3]}

    def cancel(self,ident):
        with self.condition:
            out=self.status(ident)
            if out['status']=='queued':
                self._finish(ident,'cancelled',{'executed':False});self.condition.notify_all()
                return {**self.status(ident),'cancelled':True}
            return {**out,'cancelled':out['status']=='cancelled','instruction':'Running effects are not cancelled by queue cancellation. Use targeted process termination where supported.'}

    def _finish(self,ident,status,result):
        raw=json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        if len(raw.encode())>self.max_output:
            raw=json.dumps({'truncated':True,'output_bytes':len(raw.encode()),'instruction':'Effect finished once. Use bounded output reads; do not repeat.'})
        self.db.execute("UPDATE managed_tasks SET status=?,result=?,updated=?,arguments='{}',resources='[]' WHERE id=?",(status,raw,time.time(),ident))
        rows=self.db.execute("SELECT id,length(CAST(result AS BLOB)) FROM managed_tasks WHERE result IS NOT NULL ORDER BY updated DESC").fetchall()
        retained=0
        for old_id,size in rows:
            retained+=size or 0
            if retained>1024*1024:
                self.db.execute('UPDATE managed_tasks SET result=? WHERE id=?',(json.dumps({'truncated':True,'instruction':'Cached output compacted; effect must not be replayed.'}),old_id))
        self.db.commit()

    def _worker(self):
        while True:
            with self.condition:
                if self.stopping:return
                row=None;held=set().union(*self.active.values()) if self.active else set()
                for item in self.db.execute("SELECT id,operation,arguments,resources,deadline FROM managed_tasks WHERE status='queued' ORDER BY updated").fetchall():
                    if item[4]<=time.time():
                        self._finish(item[0],'expired',{'executed':False});continue
                    needed=set(json.loads(item[3]))
                    if needed&held:continue
                    row=item;self.active[item[0]]=needed
                    self.db.execute("UPDATE managed_tasks SET status='running',updated=? WHERE id=?",(time.time(),item[0]));self.db.commit()
                    break
                if row is None:self.condition.wait(.1);continue
            try:
                result=self.executor(row[1],json.loads(row[2]));state='completed'
                # Serialization failure after an effect is itself uncertain.
                json.dumps(result,allow_nan=False)
            except Exception:
                result={'error':'Executor failed. Outcome may be uncertain; inspect state before retrying.'};state='uncertain'
            with self.condition:
                self._finish(row[0],state,result);self.active.pop(row[0]);self.condition.notify_all()

    def close(self):
        with self.condition:
            if self.stopping:return
            self.stopping=True
            for (ident,) in self.db.execute("SELECT id FROM managed_tasks WHERE status='queued'").fetchall():self._finish(ident,'cancelled',{'executed':False})
            self.condition.notify_all()
        # Started effects finish their receipts. Owner-side executors enforce
        # bounded timeouts; shutdown never guesses that a thread was cancelled.
        for thread in self.threads:thread.join()
        self.db.close();self.instance.close()
