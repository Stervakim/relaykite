"""Atomic regular-file operations and resumable hash-verified transfers."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import threading
import uuid
from path_locks import hold

def safe(path):
    if not isinstance(path,str) or not Path(path).is_absolute() or '\0' in path or '\n' in path:raise ValueError('Absolute file path required')
    value=Path(path)
    if any(p.is_symlink() for p in (value,*value.parents)):raise ValueError('Symbolic links rejected')
    if value.exists() and not value.is_file():raise ValueError('Only regular files are supported')
    if not value.parent.is_dir():raise ValueError('Parent directory must exist')
    return value

def signature(path):
    if not path.exists():return None
    s=path.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]

def checksum(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def _id(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',value):raise ValueError('Stable request ID required')

def _hash(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):raise ValueError('Expected SHA-256 hex digest')

def _sync_parent(path):
    if os.name=='nt':return
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

class FileStore:
    def __init__(self,path):
        path=Path(path).absolute()
        if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Unsafe state path')
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=threading.RLock();self.db=sqlite3.connect(path,check_same_thread=False,timeout=10);os.chmod(path,0o600)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS file_operations (id TEXT PRIMARY KEY,fingerprint TEXT,status TEXT,result TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS file_transfers (id TEXT PRIMARY KEY,request_id TEXT UNIQUE,fingerprint TEXT,destination TEXT,part TEXT,total INTEGER,digest TEXT,offset INTEGER,status TEXT,original TEXT,result TEXT)')
        self.db.execute("UPDATE file_operations SET status='uncertain' WHERE status='started'")
        self.db.execute("UPDATE file_transfers SET status='uncertain' WHERE status='committing'");self.db.commit()

    def stat(self,path):
        with hold([path]):
            target=safe(path);s=target.stat()
            return {'path':str(target),'bytes':s.st_size,'mode':stat.S_IMODE(s.st_mode),'mtime_ns':s.st_mtime_ns}

    def checksum(self,path):
        with hold([path]):
            target=safe(path)
            return {'path':str(target),'sha256':checksum(target),'bytes':target.stat().st_size}

    def operate(self,request_id,operation,source,destination=None,*,overwrite=False,expected_sha256=None):
        _id(request_id)
        if operation not in ('copy','move','rename','delete'):raise ValueError('Unsupported regular-file operation')
        if type(overwrite)!=bool:raise ValueError('overwrite must be boolean')
        if operation!='delete' and destination is None:raise ValueError('Destination required')
        if operation=='delete' and destination is not None:raise ValueError('Delete has no destination')
        if expected_sha256 is not None:_hash(expected_sha256)
        digest=hashlib.sha256(json.dumps([operation,source,destination,overwrite,expected_sha256]).encode()).hexdigest()
        paths=[source]+([] if destination is None else [destination])
        with hold(paths):
            with self.lock:
                prior=self.db.execute('SELECT fingerprint,status,result FROM file_operations WHERE id=?',(request_id,)).fetchone()
                if prior:
                    if prior[0]!=digest:raise ValueError('File receipt ID reused')
                    if prior[1]!='completed':raise RuntimeError('Prior file operation rejected or uncertain; inspect paths before a new request')
                    return json.loads(prior[2])
                if self.db.execute('SELECT count(*) FROM file_operations').fetchone()[0]>=1000:raise RuntimeError('File receipt capacity reached')
                for path in paths:
                    if self.db.execute("SELECT id FROM file_transfers WHERE destination=? AND status IN ('receiving','committing','uncertain')",(str(Path(path).resolve()),)).fetchone():raise RuntimeError('File path has an active transfer lease')
            a=safe(source);b=safe(destination) if destination is not None else None
            if not a.exists():raise FileNotFoundError(source)
            if b is not None and a.resolve()==b.resolve():raise ValueError('Source and destination must differ')
            if b is not None and b.exists() and not overwrite:raise FileExistsError(destination)
            if expected_sha256 is not None and checksum(a)!=expected_sha256:raise ValueError('Source hash mismatch')
            before=signature(a);dest_before=signature(b) if b is not None else None
            with self.lock:
                self.db.execute("INSERT INTO file_operations VALUES(?,?,'started',NULL)",(request_id,digest));self.db.commit()
            stage=None
            try:
                if operation=='delete':a.unlink();_sync_parent(a);result={'path':source,'deleted':True}
                else:
                    stage=b.with_name('.relaykite-copy-'+uuid.uuid4().hex+'.part')
                    with a.open('rb') as inp,stage.open('xb') as out:
                        shutil.copyfileobj(inp,out,1024*1024);out.flush();os.fsync(out.fileno())
                    shutil.copystat(a,stage)
                    if hasattr(os,'chown') and os.geteuid()==0:
                        info=a.stat();os.chown(stage,info.st_uid,info.st_gid)
                    copied=checksum(stage)
                    if signature(a)!=before or checksum(a)!=copied:raise RuntimeError('Source changed during copy')
                    if signature(b)!=dest_before:raise RuntimeError('Destination changed during copy')
                    os.replace(stage,b);stage=None;_sync_parent(b)
                    if operation in ('move','rename'):
                        # Cross-filesystem moves publish verified bytes first.
                        # Crash before deletion remains uncertain; never replay.
                        if signature(a)!=before:raise RuntimeError('Source changed before move cleanup')
                        a.unlink();_sync_parent(a)
                    result={'source':source,'destination':destination,'bytes':b.stat().st_size,'sha256':copied}
                with self.lock:
                    self.db.execute("UPDATE file_operations SET status='completed',result=? WHERE id=?",(json.dumps(result),request_id));self.db.commit()
                return result
            except Exception:
                with self.lock:self.db.execute("UPDATE file_operations SET status='uncertain' WHERE id=?",(request_id,));self.db.commit()
                raise
            finally:
                if stage is not None:stage.unlink(missing_ok=True)

    def start_transfer(self,request_id,destination,total_bytes,sha256,*,overwrite=False):
        _id(request_id);_hash(sha256)
        if type(total_bytes)!=int or not 0<=total_bytes<=2*1024**3:raise ValueError('Transfer must be at most 2 GiB')
        if type(overwrite)!=bool:raise ValueError('overwrite must be boolean')
        digest=hashlib.sha256(json.dumps([destination,total_bytes,sha256,overwrite]).encode()).hexdigest()
        tid=hashlib.sha256(request_id.encode()).hexdigest()[:32]
        with hold([destination]),self.lock:
            old=self.db.execute('SELECT fingerprint FROM file_transfers WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Transfer request ID reused')
                return self.transfer_status(tid)
            if self.db.execute('SELECT count(*) FROM file_transfers').fetchone()[0]>=1000:raise RuntimeError('Transfer receipt capacity reached')
            if self.db.execute("SELECT count(*) FROM file_transfers WHERE status='receiving'").fetchone()[0]>=4:raise RuntimeError('Transfer capacity reached')
            target=safe(destination)
            if target.exists() and not overwrite:raise FileExistsError(destination)
            if shutil.disk_usage(target.parent).free<total_bytes+2*1024*1024:raise RuntimeError('Insufficient space for atomic transfer staging')
            # Every transfer reserves its canonical target until commit/abort.
            canonical=str(target.resolve())
            if self.db.execute("SELECT id FROM file_transfers WHERE destination=? AND status IN ('receiving','committing','uncertain')",(canonical,)).fetchone():raise RuntimeError('Destination already has a transfer lease')
            stage=target.with_name('.relaykite-transfer-'+tid+'.part')
            with stage.open('xb'):pass
            stage.chmod(0o600)
            self.db.execute("INSERT INTO file_transfers VALUES(?,?,?,?,?,?,?,0,'receiving',?,NULL)",(tid,request_id,digest,canonical,str(stage),total_bytes,sha256,json.dumps(signature(target))));self.db.commit()
            return self.transfer_status(tid)

    def _transfer(self,tid):
        row=self.db.execute('SELECT destination,part,total,digest,offset,status,original,result FROM file_transfers WHERE id=?',(tid,)).fetchone()
        if row is None:raise ValueError('Transfer not found')
        return row

    def transfer_status(self,tid):
        with self.lock:
            row=self._transfer(tid)
            return {'transfer_id':tid,'destination':row[0],'total_bytes':row[2],'sha256':row[3],'offset':row[4],'status':row[5]}

    def write_chunk(self,tid,offset,payload,sha256):
        _hash(sha256)
        data=base64.b64decode(payload,validate=True)
        if type(offset)!=int or offset<0 or not 1<=len(data)<=262144:raise ValueError('Invalid chunk offset/size')
        if hashlib.sha256(data).hexdigest()!=sha256:raise ValueError('Chunk hash mismatch')
        with self.lock:row=self._transfer(tid)
        with hold([row[0]]),self.lock:
            row=self._transfer(tid)
            if row[5]!='receiving':raise RuntimeError('Transfer is not receiving')
            if offset+len(data)>row[2] or offset>row[4]:raise ValueError('Chunk is outside expected range')
            stage=safe(row[1])
            with stage.open('r+b') as stream:
                stream.seek(offset)
                if offset<row[4] or stage.stat().st_size>row[4]:
                    if stream.read(len(data))!=data:raise ValueError('Previously written chunk differs; no overwrite')
                    if offset+len(data)<=row[4]:return {**self.transfer_status(tid),'written':False}
                elif stage.stat().st_size!=row[4]:raise RuntimeError('Transfer staging size changed')
                else:stream.write(data);stream.flush();os.fsync(stream.fileno())
            new_offset=max(row[4],offset+len(data))
            self.db.execute('UPDATE file_transfers SET offset=? WHERE id=?',(new_offset,tid));self.db.commit()
            return {**self.transfer_status(tid),'written':True}

    def commit_transfer(self,tid):
        with self.lock:row=self._transfer(tid)
        with hold([row[0]]):
            with self.lock:
                row=self._transfer(tid)
                if row[5]=='completed':return json.loads(row[7])
                if row[5]!='receiving':raise RuntimeError('Transfer commit is uncertain or unavailable; inspect destination')
            target=safe(row[0]);stage=safe(row[1])
            if row[4]!=row[2] or stage.stat().st_size!=row[2]:raise ValueError('Transfer is incomplete')
            actual=checksum(stage)
            if actual!=row[3]:raise ValueError('Final hash mismatch; destination preserved')
            if signature(target)!=json.loads(row[6]):raise RuntimeError('Destination changed; commit refused')
            if target.exists():
                shutil.copystat(target,stage)
                if hasattr(os,'chown') and os.geteuid()==0:
                    info=target.stat();os.chown(stage,info.st_uid,info.st_gid)
            with self.lock:self.db.execute("UPDATE file_transfers SET status='committing' WHERE id=?",(tid,));self.db.commit()
            os.replace(stage,target);_sync_parent(target)
            result={'transfer_id':tid,'destination':str(target),'bytes':row[2],'sha256':actual,'status':'completed'}
            with self.lock:self.db.execute("UPDATE file_transfers SET status='completed',result=? WHERE id=?",(json.dumps(result),tid));self.db.commit()
            return result

    def abort_transfer(self,tid):
        with self.lock:row=self._transfer(tid)
        with hold([row[0]]),self.lock:
            row=self._transfer(tid)
            if row[5]=='completed':raise ValueError('Completed transfer cannot be aborted')
            stage=safe(row[1]);stage.unlink(missing_ok=True)
            self.db.execute("UPDATE file_transfers SET status='aborted' WHERE id=?",(tid,));self.db.commit()
            return {'transfer_id':tid,'status':'aborted','destination_preserved':True}

    def close(self):self.db.close()
