"""Stage a host-verified signed APK runtime as immutable root-owned code.

The expected APK digest must come from the authenticated installation flow,
after apksigner verification. Staging does not stop workers or change credentials.
"""
import argparse,hashlib,io,json,os,shutil,stat,uuid,zipfile
from pathlib import Path,PurePosixPath

def sha(raw):return hashlib.sha256(raw).hexdigest()
def relative(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or '\0' in name:raise ValueError('Unsafe runtime entry')
    return p

def read_package(apk,expected):
    if len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected):raise ValueError('Expected APK SHA-256 required')
    if apk.is_symlink() or not apk.is_file() or apk.stat().st_size>128*1024**2:raise ValueError('Unsafe APK input')
    raw=apk.read_bytes()
    if sha(raw)!=expected:raise ValueError('APK digest mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.namelist())!=len(set(archive.namelist())):raise ValueError('Duplicate APK entry')
        manifest=json.loads(archive.read('assets/runtime-manifest.json'))
        if manifest.get('version')!='0.2.5' or manifest.get('architecture')!='arm64-v8a':raise ValueError('Unsupported runtime')
        runtime=archive.read('assets/runtime.zip')
        native={}
        for name,entry in manifest['native'].items():
            if not name.startswith('lib') or not name.endswith('.so') or len(relative(name).parts)!=1:raise ValueError('Unsafe native name')
            raw=archive.read('lib/arm64-v8a/'+name)
            if sha(raw)!=entry['sha256'] or len(raw)>80*1024**2:raise ValueError('Native digest or size mismatch')
            native[name]=raw
        assets={}
        with zipfile.ZipFile(io.BytesIO(runtime)) as payload:
            if len(payload.namelist())!=len(set(payload.namelist())):raise ValueError('Duplicate runtime entry')
            expected_names=set(manifest['files'])|{'runtime-manifest.json'}
            if set(payload.namelist())!=expected_names:raise ValueError('Unlisted runtime asset')
            if sum(i.file_size for i in payload.infolist())>64*1024**2:raise ValueError('Runtime assets exceed capacity')
            for name,digest in manifest['files'].items():
                relative(name);raw=payload.read(name)
                if sha(raw)!=digest:raise ValueError('Runtime asset digest mismatch')
                assets[name]=raw
        for name,target in manifest['links'].items():
            relative(name)
            if name in assets or target not in native:raise ValueError('Invalid native module mapping')
        return manifest,assets,native

def stage(apk,expected,base):
    manifest,assets,native=read_package(apk,expected)
    base=base.absolute()
    if any(p.is_symlink() for p in (base,*base.parents)):raise ValueError('Unsafe runtime installation root')
    base.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=base/expected
    if target.exists():
        if target.is_symlink() or not target.is_dir():raise ValueError('Invalid existing runtime version')
        for name,raw in {**assets,**{'native/'+n:v for n,v in native.items()}}.items():
            path=target/name
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p!=base) or not path.is_file() or sha(path.read_bytes())!=sha(raw):raise ValueError('Existing runtime verification failed')
        for name,dest in manifest['links'].items():
            path=target/name
            if not path.is_symlink() or path.resolve()!=(target/'native'/dest).resolve():raise ValueError('Existing native module mapping mismatch')
        return target
    temporary=base/('.stage-'+uuid.uuid4().hex);temporary.mkdir(mode=0o700)
    try:
        for name,raw in {**assets,**{'native/'+n:v for n,v in native.items()}}.items():
            path=temporary/name;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
            path.chmod(0o755 if name.startswith('native/') else 0o644)
        for name,dest in manifest['links'].items():
            path=temporary/name;path.parent.mkdir(parents=True,exist_ok=True)
            # Relative links survive the atomic staging-directory rename.
            path.symlink_to(os.path.relpath(temporary/'native'/dest,path.parent))
        (temporary/'installation.json').write_text(json.dumps({'apk_sha256':expected,'runtime_manifest':manifest},indent=2)+'\n')
        for path in temporary.rglob('*'):
            if path.is_dir():path.chmod(0o755)
        temporary.chmod(0o755);temporary.rename(target)
        return target
    except Exception:
        # Only remove the exact staging directory created above, under base.
        if temporary.parent==base and temporary.name.startswith('.stage-') and not temporary.is_symlink():shutil.rmtree(temporary)
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apk',type=Path,required=True);p.add_argument('--expected-sha256',required=True);p.add_argument('--base',type=Path,default=Path('/data/adb/relaykite-runtime/versions'));a=p.parse_args()
    if getattr(os,'geteuid',lambda:-1)()!=0:raise PermissionError('Staging root runtime requires authorized root')
    result=stage(a.apk,a.expected_sha256,a.base);print(json.dumps({'staged':str(result),'apk_sha256':a.expected_sha256,'active_installation_changed':False}))
