"""Package trusted Bionic runtimes into Android's executable nativeLibDir.

Input is an externally supplied checksum inventory, never a user's configuration.
Only allocated ELF dynamic strings are shortened; no instructions are changed.
"""
import argparse,hashlib,json,re,struct,sys,zipfile
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parent))
from relocate_elf import relocate_bytes
ROOT=Path(__file__).resolve().parents[1]

def library_name(name):
    if not re.fullmatch(r'lib[^/]+\.so(?:\.\d+)*',name):raise ValueError('Invalid native library name')
    return name.split('.so',1)[0]+'.so'

def apk_elf(raw,aliases):
    raw,_=relocate_bytes(raw,'$ORIGIN')
    header=struct.unpack_from('<HHIQQQIHHHHHH',raw,16)
    segments=[struct.unpack_from('<IIQQQQQQ',raw,header[4]+i*header[8]) for i in range(header[9])]
    loads=[p for p in segments if p[0]==1];strings=None;size=None;references=[]
    for seg in (p for p in segments if p[0]==2):
        for pos in range(seg[2],seg[2]+seg[5],16):
            tag,value=struct.unpack_from('<qQ',raw,pos)
            if tag==0:break
            if tag==5:strings=value
            if tag==10:size=value
            if tag in (1,14):references.append(value)
    if not references:return raw
    segment=next((p for p in loads if p[3]<=strings and strings+size<=p[3]+p[5]),None)
    if segment is None:raise ValueError('Unmapped ELF strings')
    start=segment[2]+strings-segment[3];out=bytearray(raw)
    for rel in set(references):
        if rel>=size:raise ValueError('Invalid dynamic string')
        pos=start+rel;end=raw.find(b'\0',pos,start+size)
        if end<0:raise ValueError('Unterminated dynamic string')
        name=raw[pos:end].decode('ascii');replacement=aliases.get(name,name).encode('ascii')
        if len(replacement)>end-pos:raise ValueError('Native alias exceeds allocation')
        out[pos:end+1]=replacement+b'\0'*(end-pos+1-len(replacement))
    return bytes(out)

def pack(source,output):
    inventory=json.loads((source/'manifest.json').read_text());files=inventory['files']
    aliases={Path(name).name:library_name(Path(name).name) for name in files if name.startswith('lib/') and name.count('/')==1}
    if len(set(aliases.values()))!=len(aliases):raise ValueError('Native dependency alias collision')
    output.mkdir(parents=True,exist_ok=True);native={};assets={};links={};provenance={}
    for name,entry in sorted(files.items()):
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or '\0' in name:raise ValueError('Unsafe runtime source name')
        path=source/name
        if not path.resolve().is_relative_to(source.resolve()) or path.is_symlink() or not path.is_file():raise ValueError('Unsafe runtime source')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Runtime source checksum mismatch')
        if any(p.startswith('config-') for p in Path(name).parts):continue
        if raw[:4]==b'\x7fELF':
            if name=='bin/python':dest='librelaykite_python.so'
            elif name=='bin/node':dest='librelaykite_node.so'
            elif '/lib-dynload/' in name:dest='libpy_'+Path(name).name.split('.',1)[0]+'.so';links[name]=dest
            else:dest=aliases[Path(name).name]
            raw=apk_elf(raw,aliases)
            if dest in native:raise ValueError('Duplicate APK native library')
            native[dest]=raw
            provenance[dest]={'input':name,'input_sha256':entry['sha256'],'sha256':hashlib.sha256(raw).hexdigest()}
        else:assets[name]=raw
    for path in sorted((ROOT/'agent').glob('*.py')):
        if not path.name.startswith('test_'):assets['agent/'+path.name]=path.read_bytes()
    development=ROOT/'pc/development'
    for name in json.loads((development/'release-files.json').read_text(encoding='utf-8')):
        source=development/name
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(development.resolve()):
            raise ValueError('Unsafe development runtime release input')
        assets['agent/development/'+name]=source.read_bytes()
    assets['agent/tool-definitions.json']=(ROOT/'agent/tool-definitions.json').read_bytes()
    assets['agent/development-engine-lock.json']=(ROOT/'agent/development-engine-lock.json').read_bytes()
    assets['agent/relocate_elf.py']=(ROOT/'scripts/relocate_elf.py').read_bytes()
    for name in ('SKILL.md','services.md'):assets['agent/support/'+name]=(ROOT/'agent/support'/name).read_bytes()
    assets['agent/graph-runtime.zip']=(ROOT/'agent/graph-runtime.zip').read_bytes()
    for path in sorted((ROOT/'agent/memory-runtime').iterdir()):
        if path.name=='codaki-external.mjs' or path.name.startswith('LICENSE.'):assets['agent/memory-runtime/'+path.name]=path.read_bytes()
    assets['agent/runtime_probe.py']=(ROOT/'device-runtime/runtime_probe.py').read_bytes()
    manifest={'version':'0.3.0','architecture':'arm64-v8a','origin':inventory['origin'],'packages':inventory['packages'],
              'native':provenance,'links':links,'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in assets.items()}}
    assets['runtime-manifest.json']=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    for name,items,prefix in [('native.zip',native,'lib/arm64-v8a/'),('runtime.zip',assets,'')]:
        with zipfile.ZipFile(output/name,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for dest,raw in sorted(items.items()):
                info=zipfile.ZipInfo(prefix+dest,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,raw)
    (output/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return {'native_libraries':len(native),'asset_files':len(assets),'native_sha256':hashlib.sha256((output/'native.zip').read_bytes()).hexdigest(),'runtime_sha256':hashlib.sha256((output/'runtime.zip').read_bytes()).hexdigest()}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);a=parser.parse_args();print(json.dumps(pack(a.source,a.output)))
