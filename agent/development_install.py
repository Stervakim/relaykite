"""Install pinned upstream Codex/Git into private Android storage.

No package manager, Termux app, model API key or PC is required. Downloads are
authenticated HTTPS and checked against the shipped lock before parsing. This
does not replace an existing engine or edit connection credentials.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid

PREFIX = 'data/data/com.termux/files/usr/'
SYSTEM_LIBS = {'libc.so','libm.so','libdl.so','liblog.so','libandroid.so','libz.so'}
MAX_ARCHIVE = 256 * 1024**2


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(name):
    if not isinstance(name,str) or not name or '\\' in name or '\0' in name:
        raise ValueError('Unsafe upstream archive path')
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe upstream archive path')
    return path.as_posix()


def private_directory(path):
    path=Path(path).absolute()
    for entry in reversed((path,*path.parents)):
        if entry.is_symlink(): raise ValueError('Private engine storage must not use symlinks')
        if entry.exists() and not entry.is_dir(): raise ValueError('Engine storage must be a directory')
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=='posix' and (path.stat().st_uid!=os.geteuid() or path.stat().st_mode & 0o022):
        raise PermissionError('Engine storage must be owned by the installer and not writable by others')
    return path


def load_lock(path=None):
    path=Path(path) if path else Path(__file__).with_name('development-engine-lock.json')
    if path.is_symlink() or path.stat().st_size>65536: raise ValueError('Unsafe engine lock')
    lock=json.loads(path.read_text(encoding='utf8'))
    if lock.get('format')!=1 or lock.get('architecture')!='aarch64': raise ValueError('Unsupported engine lock')
    for entry in [lock['codex'],*lock['packages']]:
        url=urllib.parse.urlsplit(entry['url'])
        allowed=(url.hostname=='github.com' and url.path.startswith('/openai/codex/releases/download/')) or (
            url.hostname=='packages-cf.termux.dev' and url.path.startswith('/apt/termux-main/pool/'))
        if url.scheme!='https' or url.username or url.query or url.fragment or not allowed:
            raise ValueError('Engine lock must use official upstream download locations')
        if len(entry['sha256'])!=64 or any(c not in '0123456789abcdef' for c in entry['sha256']):
            raise ValueError('Invalid pinned engine digest')
    return lock


def fetch(entry, cache, *, opener=urllib.request.urlopen):
    """Verified cache is reusable; partial/failed downloads are never executable."""
    cache=private_directory(cache)
    target=cache/entry['sha256']
    if target.is_symlink(): raise ValueError('Unsafe download cache')
    if target.exists():
        if not target.is_file() or target.stat().st_size>MAX_ARCHIVE: raise ValueError('Unsafe cached input')
        raw=target.read_bytes()
        if digest(raw)==entry['sha256']: return target
        raise ValueError('Cached upstream input failed its digest; remove only that corrupt cache entry before retrying')
    temp=cache/('.download-'+uuid.uuid4().hex)
    try:
        request=urllib.request.Request(entry['url'],headers={'User-Agent':'RelayKite/0.3.0'})
        for attempt in range(3):
            try:
                response=opener(request,timeout=60)
                break
            except urllib.error.HTTPError as error:
                code=error.code; error.close()
                if code not in (404,408,429,500,502,503,504) or attempt==2:
                    raise ValueError('Pinned upstream input unavailable: '+entry['url'].rsplit('/',1)[-1]+' (HTTP '+str(code)+')') from None
                time.sleep(attempt+1)
        with response, temp.open('xb') as output:
            os.chmod(temp,0o600)
            if urllib.parse.urlsplit(response.url).scheme!='https': raise ValueError('Insecure upstream redirect')
            size=0; hasher=hashlib.sha256()
            while data:=response.read(1024*1024):
                size+=len(data)
                if size>MAX_ARCHIVE: raise ValueError('Upstream archive exceeds limit')
                output.write(data); hasher.update(data)
            output.flush(); os.fsync(output.fileno())
        if hasher.hexdigest()!=entry['sha256'] or ('size' in entry and size!=entry['size']):
            raise ValueError('Upstream download checksum/size mismatch')
        os.replace(temp,target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def deb_payload(raw):
    if not raw.startswith(b'!<arch>\n') or len(raw)>MAX_ARCHIVE: raise ValueError('Invalid Debian archive')
    offset=8; payload=None
    while offset<len(raw):
        header=raw[offset:offset+60]
        if len(header)!=60 or header[58:]!=b'`\n': raise ValueError('Invalid Debian member header')
        size=int(header[48:58]); name=header[:16].decode('ascii').strip().rstrip('/')
        offset+=60
        if size<0 or offset+size>len(raw): raise ValueError('Invalid Debian member length')
        if name.startswith('data.tar'):
            if payload is not None: raise ValueError('Duplicate Debian payload')
            payload=raw[offset:offset+size]
        offset+=size+(size%2)
    if offset!=len(raw) or payload is None: raise ValueError('Missing Debian payload')
    return payload


def package_files(raw):
    """Interpret links in memory, never extract upstream paths onto the host."""
    files={}; links={}; total=0
    with tarfile.open(fileobj=io.BytesIO(deb_payload(raw)),mode='r:*') as archive:
        for member in archive:
            name=relative(member.name)
            if member.isdir(): continue
            if not name.startswith(PREFIX): raise ValueError('Unexpected upstream installation prefix')
            name=name[len(PREFIX):]
            if name in files or name in links: raise ValueError('Duplicate upstream file')
            if member.isfile():
                total+=member.size
                if member.size>64*1024**2 or total>128*1024**2: raise ValueError('Upstream package expansion limit')
                files[name]=archive.extractfile(member).read()
            elif member.issym() or member.islnk():
                target=member.linkname
                if member.islnk():
                    target=relative(target)
                    if not target.startswith(PREFIX): raise ValueError('Unsafe hardlink')
                    target=target[len(PREFIX):]
                else:
                    if target.startswith('/'):
                        if not target.startswith('/'+PREFIX): raise ValueError('Unsafe absolute link')
                        target=target[len(PREFIX)+1:]
                    else: target=posixpath.normpath(posixpath.join(posixpath.dirname(name),target))
                    relative(target)
                links[name]=target
            else: raise ValueError('Special upstream package member rejected')
    def resolve(name,trail=()):
        if name in files:return files[name]
        if name in trail or len(trail)>16 or name not in links: raise ValueError('Unresolved upstream link')
        return resolve(links[name],(*trail,name))
    return files,links,resolve


def needed(raw):
    if raw[:7]!=b'\x7fELF\x02\x01\x01': return []
    header=struct.unpack_from('<HHIQQQIHHHHHH',raw,16)
    if header[1]!=183 or header[8]!=56 or header[9]>128: raise ValueError('Expected AArch64 ELF')
    segments=[struct.unpack_from('<IIQQQQQQ',raw,header[4]+i*header[8]) for i in range(header[9])]
    dynamic=next((s for s in segments if s[0]==2),None)
    if not dynamic:return []
    entries=[]
    for position in range(dynamic[2],dynamic[2]+dynamic[5],16):
        tag,value=struct.unpack_from('<qQ',raw,position)
        if tag==0:break
        entries.append((tag,value))
    strings=next(value for tag,value in entries if tag==5)
    load=next(s for s in segments if s[0]==1 and s[3]<=strings<s[3]+s[5])
    start=load[2]+strings-load[3]
    return [raw[start+value:raw.index(b'\0',start+value)].decode('ascii') for tag,value in entries if tag==1]


def build_engine(lock, inputs, target, runtime):
    """Build from checked official archives; usable offline for release QA."""
    from relocate_elf import relocate_bytes
    target=Path(target)
    if target.exists() or target.is_symlink(): raise FileExistsError('Existing engine is preserved; no in-place overwrite')
    target.mkdir(mode=0o700)
    inventory={}; files={}; links={}
    def write(name,raw,executable=False,source_sha256=None):
        relative(name); path=target/name; path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with path.open('xb') as output: output.write(raw)
        path.chmod(0o700 if executable else 0o600)
        inventory[name]={'sha256':digest(raw),'source_sha256':source_sha256 or digest(raw)}
    for entry in lock['packages']:
        raw=Path(inputs[entry['sha256']]).read_bytes()
        if digest(raw)!=entry['sha256']: raise ValueError('Package checksum mismatch before parsing')
        package,aliases,_=package_files(raw)
        for name,data in package.items():
            if name in files and files[name]!=data: raise ValueError('Package file collision')
            files[name]=data
        for name,destination in aliases.items():
            if name in links and links[name]!=destination: raise ValueError('Package alias collision')
            links[name]=destination
        for name,data in package.items():
            if (name.startswith('share/doc/') or name.startswith('share/licenses/')) and any(
                word in PurePosixPath(name).name.lower() for word in ('copyright','license','copying')):
                write('licenses/'+entry['name']+'/'+PurePosixPath(name).name,data)
    def resolve(name,trail=()):
        if name in files:return files[name]
        if name not in links or name in trail or len(trail)>16: raise ValueError('Missing upstream dependency: '+name)
        return resolve(links[name],(*trail,name))
    queue=[('bin/git','toolchain/bin/git'),('bin/rg','toolchain/bin/rg'),('bin/less','toolchain/bin/less')]
    for name in sorted(set(files)|set(links)):
        if name.startswith('libexec/git-core/'):
            raw=resolve(name)
            if name in links and links[name]=='bin/git':
                path=target/'toolchain'/name; path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                path.symlink_to('../../bin/git')
            elif raw.startswith(b'\x7fELF'): queue.append((name,'toolchain/'+name))
        elif name.startswith('share/git-core/templates/'):
            write('toolchain/'+name,resolve(name))
    seen=set()
    while queue:
        source,destination=queue.pop()
        if destination in seen:continue
        seen.add(destination); raw=resolve(source)
        dependencies=needed(raw)
        for name in dependencies:
            if 'lib/'+name in files or 'lib/'+name in links: queue.append(('lib/'+name,'toolchain/lib/'+name))
            elif name not in SYSTEM_LIBS: raise ValueError('Unresolved native dependency: '+name)
        runpath='$ORIGIN/../lib' if destination.startswith('toolchain/bin/') else '$ORIGIN/../../lib' if destination.startswith('toolchain/libexec/') else '$ORIGIN'
        updated,_=relocate_bytes(raw,runpath)
        write(destination,updated,executable=True,source_sha256=digest(raw))
        inventory[destination]['needed']=dependencies
    # libcurl's compiled Termux CA path is replaced by explicit task environment.
    write('toolchain/etc/tls/cert.pem',resolve('etc/tls/cert.pem'))
    codex=Path(inputs[lock['codex']['sha256']]).read_bytes()
    if digest(codex)!=lock['codex']['sha256']: raise ValueError('Codex archive checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(codex),mode='r:*') as archive:
        candidates=[x for x in archive if x.isfile() and PurePosixPath(relative(x.name)).name=='codex-aarch64-unknown-linux-musl']
        if len(candidates)!=1 or candidates[0].size>MAX_ARCHIVE: raise ValueError('Unexpected official Codex archive')
        raw=archive.extractfile(candidates[0]).read()
    if digest(raw)!=lock['codex']['binary_sha256']: raise ValueError('Codex binary checksum mismatch')
    write('bin/codex',raw,executable=True)
    for name,executable in [('python','librelaykite_python.so'),('node','librelaykite_node.so')]:
        (target/'toolchain/bin'/name).symlink_to(str(Path(runtime)/'native'/executable))
    manifest={'format':1,'lock_sha256':digest(json.dumps(lock,sort_keys=True).encode()),'codex_version':lock['codex']['version'],
              'sources':[lock['codex'],*lock['packages']],'files':inventory,
              'note':'Upstream binaries; ELF RUNPATH strings relocated only. No Termux process or package manager. Android root has no sandbox isolation.'}
    write('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())
    return manifest


@contextmanager
def installation_lock(base):
    import fcntl
    path=base/'development-install.lock'
    fd=os.open(path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'a+') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def install(base, runtime, *, lock=None, inputs=None, execute=True):
    base=private_directory(base); lock=lock or load_lock()
    target=base/'development-engine'
    with installation_lock(base):
        if target.exists() or target.is_symlink():
            raise FileExistsError('An engine already exists. It was preserved. Inspect capabilities; upgrades require an explicit idle-engine migration.')
        if shutil.disk_usage(base).free<900*1024**2: raise ValueError('At least 900 MiB free storage is required for staging')
        downloads=inputs if inputs is not None else {entry['sha256']:fetch(entry,base/'development-downloads') for entry in [lock['codex'],*lock['packages']]}
        temporary=base/('.engine-stage-'+uuid.uuid4().hex)
        try:
            manifest=build_engine(lock,downloads,temporary,runtime)
            if execute:
                env=dict(os.environ,PATH=str(temporary/'toolchain/bin')+':/system/bin',
                         LD_LIBRARY_PATH=str(temporary/'toolchain/lib')+':'+str(Path(runtime)/'native'))
                for command,expected in [(temporary/'bin/codex','codex-cli '+lock['codex']['version']),
                                         (temporary/'toolchain/bin/git','git version '),(temporary/'toolchain/bin/rg','ripgrep ')]:
                    result=subprocess.run([str(command),'--version'],env=env,capture_output=True,text=True,timeout=20)
                    if result.returncode or expected not in result.stdout: raise ValueError('Staged engine execution check failed: '+command.name)
            projects=private_directory(base/'projects')
            policy=base/'development-policy.json'
            if not policy.exists():
                pending_policy=base/('.policy-stage-'+uuid.uuid4().hex)
                try:
                    with pending_policy.open('x',encoding='utf8') as output:
                        json.dump({'workspace_roots':[str(projects)]},output)
                        output.flush();os.fsync(output.fileno())
                    pending_policy.chmod(0o600)
                    try:os.link(pending_policy,policy)
                    except FileExistsError:pass  # Preserve an owner policy created concurrently.
                finally:pending_policy.unlink(missing_ok=True)
            # Publish last. A crash after policy preparation remains retryable;
            # a failed preparation never leaves an active but unusable engine.
            os.rename(temporary,target)
            return {'state':'installed','engine':str(target),'codex_version':manifest['codex_version'],
                    'workspace':str(projects),'execution_policy':'android-root','isolation':'none'}
        finally:
            if temporary.is_dir() and not temporary.is_symlink(): shutil.rmtree(temporary)


def main():
    from runtime_paths import BASE, identity
    from development.supervisor import execution_profile
    if sys.argv[1:]!=['--install']: raise ValueError('Use --install; URLs and paths are pinned in the release')
    current=identity()
    if current['mode']!='root' or current['uid']!=0: raise PermissionError('Select root mode before installing the development engine')
    execution_profile('android-root')
    runtime=Path(os.environ['PYTHONHOME'])
    print(json.dumps(install(BASE,runtime)),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'state':'not_installed','reason':str(error)[:600]}),flush=True)
        sys.exit(1)
