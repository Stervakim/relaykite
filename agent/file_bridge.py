"""Copy only the explicitly selected file to the owned read-only URI cache."""
import hashlib,json,os,re,shutil,sqlite3,subprocess,threading,time,uuid
from pathlib import Path
from file_ops import safe,signature,checksum
from path_locks import hold

PACKAGE='org.relaykite.runtime';AUTHORITY=PACKAGE+'.files'
def system_environment():
    env=os.environ.copy();env.pop('LD_LIBRARY_PATH',None);env.pop('LD_PRELOAD',None);env['PATH']='/system/bin:/system/xbin'
    return env

def restore_app_context(path):
    # Root-created files lack the application's SELinux categories even when
    # chown is correct. Android restores the labels only for this owned cache.
    if getattr(os,'geteuid',lambda:1)()==0:
        subprocess.run(['/system/bin/restorecon','-R',str(path)],check=True,
                       capture_output=True,env=system_environment(),timeout=10)

class FileBridge:
    def __init__(self,state,*,directory=None,uid=None):
        self.production=directory is None
        if self.production:
            value=subprocess.run(['/system/bin/cmd','package','list','packages','-U',PACKAGE],capture_output=True,text=True,env=system_environment(),timeout=10)
            matched=re.fullmatch(r'package:org\.relaykite\.runtime uid:(\d+)\s*',value.stdout)
            if value.returncode or not matched:raise RuntimeError('Owned RelayKite scoped provider is unavailable')
            uid=int(matched[1]);directory=Path('/data/user/0')/PACKAGE/'cache/shared'
        self.directory=Path(directory);self.uid=uid;self.lock=threading.RLock()
        if any(p.is_symlink() for p in (self.directory,*self.directory.parents)):raise ValueError('Unsafe sharing cache')
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        if uid is not None:
            os.chown(self.directory,uid,uid)
            if self.production:os.chown(self.directory.parent,uid,uid)
        if self.production:restore_app_context(self.directory)
        state=Path(state).absolute()
        if any(p.is_symlink() for p in (state,*state.parents)):raise ValueError('Unsafe sharing journal')
        state.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(state,check_same_thread=False,timeout=10);os.chmod(state,0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS file_shares (id TEXT PRIMARY KEY,fingerprint TEXT,token TEXT,result TEXT,expires REAL)');self.db.commit()

    def prepare(self,request_id,path,mime_type):
        if not isinstance(request_id,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',request_id):raise ValueError('Stable sharing request ID required')
        if not isinstance(mime_type,str) or not re.fullmatch('[a-z0-9.+-]+/[a-z0-9.+-]+',mime_type):raise ValueError('Explicit MIME type required')
        digest=hashlib.sha256(json.dumps([path,mime_type]).encode()).hexdigest()
        with hold([path]),self.lock:
            old=self.db.execute('SELECT fingerprint,result FROM file_shares WHERE id=?',(request_id,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Sharing request ID reused')
                return json.loads(old[1])
            if self.db.execute('SELECT count(*) FROM file_shares').fetchone()[0]>=1000:raise RuntimeError('Sharing receipt capacity reached')
            source=safe(path);before=signature(source)
            if before is None:raise FileNotFoundError(path)
            if source.stat().st_size>128*1024*1024:raise ValueError('Scoped file view limit is128MiB; transfer/inspect larger files explicitly')
            for token, in self.db.execute('SELECT token FROM file_shares WHERE expires<?',(time.time(),)).fetchall():
                cached=self.directory/token
                if cached.is_symlink():raise ValueError('Sharing cache link rejected')
                cached.unlink(missing_ok=True)
            size=sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file())
            if size+source.stat().st_size>256*1024*1024:raise RuntimeError('Sharing cache capacity reached')
            if self.production:
                from memory_bridge import MemoryBridge,allocated_bytes,CAP
                config=MemoryBridge().config
                roots=[Path(p) for p in config.get('accounting_roots',[])]
                if sum(allocated_bytes(p) for p in roots)+size+source.stat().st_size>CAP:raise RuntimeError('Combined storage quota exceeded')
            extensions={'text/plain':'txt','text/html':'html','application/json':'json','application/pdf':'pdf','image/png':'png','image/jpeg':'jpg','image/webp':'webp'}
            extension=extensions.get(mime_type)
            if extension is None:raise ValueError('MIME type is not supported by the scoped provider')
            token=uuid.uuid4().hex+'.'+extension;target=self.directory/token
            with source.open('rb') as inp,target.open('xb') as out:
                shutil.copyfileobj(inp,out,1024*1024);out.flush();os.fsync(out.fileno())
            target.chmod(0o400)
            if self.uid is not None:os.chown(target,self.uid,self.uid)
            if self.production:restore_app_context(target)
            actual=checksum(target)
            if signature(source)!=before or checksum(source)!=actual:
                target.unlink();raise RuntimeError('Source changed while sharing')
            result={'uri':'content://'+AUTHORITY+'/'+token,'sha256':actual,'bytes':target.stat().st_size,'mime_type':mime_type,'expires_at':time.time()+1800,'read_only':True}
            self.db.execute('INSERT INTO file_shares VALUES(?,?,?,?,?)',(request_id,digest,token,json.dumps(result),result['expires_at']));self.db.commit()
            return result

    def close(self):self.db.close()
