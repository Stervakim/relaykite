import hashlib, json, os, sqlite3, time
from pathlib import Path

def canonical(value): return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()

class Journal:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,check_same_thread=False)
        if os.name!='nt':os.chmod(path,0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, op TEXT NOT NULL, status TEXT NOT NULL, result TEXT, created REAL NOT NULL)')
        # Keep batch checkpoints: completed steps and inflight identity are
        # needed to reconcile a crash without repeating already applied input.
        self.db.execute("UPDATE requests SET status='uncertain',result=json_set(COALESCE(result,'{}'),'$.status','uncertain','$.error','Interrupted operation','$.code','UNCERTAIN') WHERE status='started'")
        self.db.commit()
        self.compact()
    def get(self,rid):
        r=self.db.execute('SELECT fingerprint,status,result FROM requests WHERE id=?',(rid,)).fetchone()
        return None if r is None else (r[0],r[1],json.loads(r[2]) if r[2] else None)
    def begin(self,rid,op,args):
        if self.db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]>=100000:raise RuntimeError('Journal capacity exhausted; archive before continuing')
        self.db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?)',(rid,digest([op,args]),op,'started',None,time.time()));self.db.commit()
    def finish(self,rid,status,result):
        self.db.execute('UPDATE requests SET status=?,result=? WHERE id=?',(status,canonical(result),rid));self.db.commit();self.compact()
    def compact(self,max_bytes=64*1024*1024):
        # Keep immutable IDs/fingerprints forever; discarding a payload must
        # never make an already executed request eligible to run again.
        expired=canonical({'error':'Receipt payload expired; do not replay','code':'RESULT_EXPIRED'})
        self.db.execute("UPDATE requests SET status='compacted',result=? WHERE status='completed' AND created<?",(expired,time.time()-86400))
        rows=self.db.execute("SELECT id,LENGTH(CAST(result AS BLOB)) FROM requests WHERE status='completed' ORDER BY created,id").fetchall()
        total=sum(size or 0 for _,size in rows)
        for rid,size in rows:
            if total<=max_bytes:break
            self.db.execute("UPDATE requests SET status='compacted',result=? WHERE id=?",(expired,rid));total-=size or 0
        self.db.commit()
    def uncertain(self): return [r[0] for r in self.db.execute("SELECT id FROM requests WHERE status='uncertain'")]
    def close(self):self.db.close()
