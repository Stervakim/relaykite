"""Consistent SQLite and immutable-blob snapshots for explicit mode migration.

Callers must stop the task worker before copying its journal. Tencent version
blobs are immutable; taking its SQLite snapshot first preserves every referenced
blob while the source remains authoritative until the coordinator commits.
"""
import hashlib,os,shutil,sqlite3,stat
from contextlib import closing
from pathlib import Path

def regular_tree(root):
    root=Path(root).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)) or not root.is_dir():raise ValueError('Unsafe source tree')
    for path in sorted(root.rglob('*')):
        info=path.lstat()
        if stat.S_ISLNK(info.st_mode):raise ValueError('Source tree contains symlink')
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):raise ValueError('Source tree contains nonregular object')
        if stat.S_ISREG(info.st_mode):yield path

def copy_store(source,destination,max_bytes=5*1024**3):
    source=Path(source).absolute();destination=Path(destination).absolute()
    if destination.exists() or any(p.is_symlink() for p in (destination,*destination.parents)):raise ValueError('Snapshot destination must be a fresh private directory')
    files=list(regular_tree(source))
    if sum(p.stat().st_size for p in files)>max_bytes:raise ValueError('Snapshot source exceeds quota')
    databases=[]
    for path in files:
        if path.name.endswith(('-wal','-shm','-journal')):continue
        with path.open('rb') as stream:header=stream.read(16)
        if header==b'SQLite format 3\0':databases.append(path)
    destination.mkdir(parents=True,mode=0o700)
    hashes={};copied=0
    try:
        def ordered_files():
            yield from databases
            # Enumerate blobs after the database backup so a committed note's
            # immutable blob cannot be missed by an earlier directory listing.
            for path in regular_tree(source):
                if path not in databases and not path.name.endswith(('-wal','-shm','-journal')):yield path
        for path in ordered_files():
            relative=path.relative_to(source);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            if path in databases:
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)) as original,closing(sqlite3.connect(target)) as snapshot:
                    original.backup(snapshot)
                    if snapshot.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Snapshot database integrity failed')
            else:
                before=path.stat();shutil.copyfile(path,target);after=path.stat()
                if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):raise ValueError('Source blob changed while copying')
            target.chmod(0o600);copied+=target.stat().st_size
            if copied>max_bytes:raise ValueError('Snapshot exceeds quota')
            with target.open('rb') as stream:hashes[relative.as_posix()]=hashlib.file_digest(stream,'sha256').hexdigest()
        return {'files':hashes,'bytes':copied,'databases':len(databases)}
    except Exception:
        # This destination was created exclusively by this call. Preserve it for
        # inspection; a failed snapshot is never activated by this helper.
        raise
