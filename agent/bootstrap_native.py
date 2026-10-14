"""Minimal bootstrap after trusted APK assets are unpacked: pure stdlib only."""
import json,os,sys

def main(prefix,native):
    prefix=os.path.realpath(prefix);native=os.path.realpath(native)
    if os.geteuid()!=0 or not os.path.isdir(prefix) or not os.path.isdir(native):raise ValueError('Authorized root bootstrap requires existing private directories')
    with open(prefix+'/runtime-manifest.json',encoding='utf-8') as stream:manifest=json.load(stream)
    for name,target in manifest['links'].items():
        if not isinstance(name,str) or not isinstance(target,str) or name.startswith('/') or '..' in name.split('/') or '\\' in name or '/' in target or not target.startswith('lib') or not target.endswith('.so'):raise ValueError('Invalid bootstrap module mapping')
        link=prefix+'/'+name;source=native+'/'+target
        if not os.path.isfile(source) or os.path.islink(source):raise ValueError('Native module unavailable')
        os.makedirs(os.path.dirname(link),mode=0o700,exist_ok=True)
        if os.path.lexists(link):raise ValueError('Bootstrap module path already exists')
        os.symlink(source,link)

def activate(next_path,current):
    base='/data/adb/relaykite-runtime'
    if os.geteuid()!=0 or os.path.dirname(next_path)!=base or not os.path.basename(next_path).startswith('.current-') or current!=base+'/current':raise ValueError('Invalid runtime pointer paths')
    if not os.path.islink(next_path) or os.lstat(next_path).st_uid!=0:raise ValueError('Root-owned next pointer required')
    selected=os.readlink(next_path)
    digest=selected.removeprefix('versions/')
    if not selected.startswith('versions/') or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Invalid version pointer')
    if os.path.lexists(current) and not os.path.islink(current):raise ValueError('Existing runtime pointer is not a link')
    os.replace(next_path,current)

if __name__=='__main__':
    if sys.argv[1]=='--activate':activate(sys.argv[2],sys.argv[3])
    else:main(sys.argv[1],sys.argv[2])
