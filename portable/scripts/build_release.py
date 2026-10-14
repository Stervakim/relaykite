"""Create a public bundle from an explicit allowlist, including the Android ZIP."""
import argparse, hashlib, json, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION=(ROOT/'VERSION').read_text(encoding='ascii').strip()
ROOT_FILES={'README.md','CODEX_INSTALL.md','AGENTS.md','CHANGELOG.md','LICENSE','VERSION',
            'START_WINDOWS_AGENT.cmd','agent-windows.example.json','requirements-windows.txt','.gitignore'}
TREE_SUFFIXES={'src':{'.py','.json'},'core':{'.jar','.json'},'android':{'.java'},'magisk':{'.sh','.json','.prop'},
               'scripts':{'.py','.ps1'},'cloud':{'.js','.mjs','.json','.md','.sh','.example'},
               'tests':{'.py'},'docs':{'.md'},'.github':{'.yml'}}

def files():
    result=[ROOT/name for name in sorted(ROOT_FILES)]
    for tree,suffixes in TREE_SUFFIXES.items():
        for path in (ROOT/tree).rglob('*'):
            if not path.is_file() or path.suffix not in suffixes: continue
            parts=path.relative_to(ROOT).parts
            if any(part in {'__pycache__','node_modules','dist','state','.venv'} for part in parts): continue
            if path.name in {'agent.json','agent-windows.json','config.json','hosting.json','runtime.env'}: continue
            result.append(path)
    return sorted(set(result),key=lambda p:p.relative_to(ROOT).as_posix())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist'/f'codaki-portable-use-{VERSION}-full.zip')
    args=parser.parse_args()
    android=ROOT/'dist'/f'codaki-portable-use-{VERSION}-android.zip'
    if not android.is_file(): parser.error('Build the Android archive first')
    entries={p.relative_to(ROOT).as_posix():p.read_bytes() for p in files()}
    entries['packages/'+android.name]=android.read_bytes()
    manifest={name:hashlib.sha256(raw).hexdigest() for name,raw in entries.items()}
    entries['MANIFEST.sha256.json']=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in sorted(entries.items()):
            info=zipfile.ZipInfo(name,(2026,10,11,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3; info.external_attr=(0o100755 if name.endswith('.sh') else 0o100644)<<16
            archive.writestr(info,raw)
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
        for name,expected in manifest.items(): assert hashlib.sha256(archive.read(name)).hexdigest()==expected
    paths=(android,args.output)
    (ROOT/'dist/SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in paths),encoding='ascii')
    print(json.dumps({'version':VERSION,'files':len(entries),'archive':str(args.output),'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest()}))

if __name__=='__main__': main()
