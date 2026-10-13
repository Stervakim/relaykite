"""Build an API-free Graphify code graph and a portable query-only runtime."""
from pathlib import Path
import argparse,hashlib,json,shutil,datetime,zipfile,importlib.metadata
from graphify.extract import extract
from graphify.build import build
from graphify.export import to_json

EXT={'.py','.ts','.tsx','.js','.mjs','.sh','.ps1','.java'}

def main():
    a=argparse.ArgumentParser();a.add_argument('--codaki',required=True);a.add_argument('--tencent',required=True);a.add_argument('--site',required=True);a.add_argument('--out',required=True)
    o=a.parse_args();out=Path(o.out).resolve();out.mkdir(parents=True,exist_ok=True);corpus=out/'corpus';corpus.mkdir(exist_ok=True)
    groups=[(Path(o.codaki)/'agent','codaki/agent'),(Path(o.codaki)/'pc','codaki/pc'),(Path(o.site)/'lib','codaki/relay'),
            (Path(o.codaki)/'portable/src','codaki/portable'),(Path(o.codaki)/'portable/android/java','codaki/android-core'),
            (Path(o.codaki)/'device-runtime/java','codaki/device-runtime'),(Path(o.codaki)/'scripts','codaki/scripts'),(Path(o.codaki)/'magisk','codaki/root-install'),
            (Path(o.tencent)/'MemoryCore/src/core/store','tencent/core/store'),(Path(o.tencent)/'MemoryCore/src/core/storage','tencent/core/storage'),(Path(o.tencent)/'MemoryCore/src/codaki','tencent/codaki')]
    files=[];sources={}
    for root,prefix in groups:
        for p in sorted(root.rglob('*')):
            if not p.is_file() or p.is_symlink() or p.suffix not in EXT:continue
            rel=p.relative_to(root)
            if p.name.startswith('test') or '.test.' in p.name or any(x in ('node_modules','__pycache__','__tests__','.git') for x in rel.parts):continue
            q=corpus/prefix/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);files.append(q)
            source='@runtime/agent/'+rel.as_posix() if prefix=='codaki/agent' else '@base/project-source/'+prefix+'/'+rel.as_posix()
            sources[source]=hashlib.sha256(p.read_bytes()).hexdigest()
    if not files:raise RuntimeError('No allowed source files')
    # Original deterministic AST extractor only; no semantic/model pass.
    extraction=extract(files,root=corpus,parallel=False)
    if extraction.get('failed_sources'):raise RuntimeError('Graphify could not extract '+str(len(extraction['failed_sources']))+' sources')
    graph=build([extraction],directed=True,root=corpus)
    to_json(graph,{},str(out/'graph.json'),force=True)
    raw=(out/'graph.json').read_bytes();digest=hashlib.sha256(raw).hexdigest()
    manifest={'sha256':digest,'revision':digest,'graphify_version':importlib.metadata.version('graphifyy'),'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sources':sources,'files':len(files),'nodes':len(graph),'edges':graph.number_of_edges(),'mode':'code-only','llm_calls':0}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    import graphify,networkx
    with zipfile.ZipFile(out/'graph-runtime.zip','w',zipfile.ZIP_DEFLATED) as z:
        for mod in (graphify,networkx):
            root=Path(mod.__file__).parent
            for p in root.rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.json','.txt','.md'):
                    z.write(p,mod.__name__+'/'+p.relative_to(root).as_posix())
    print(json.dumps({k:manifest[k] for k in ('files','nodes','edges','graphify_version','mode','llm_calls')}))

if __name__=='__main__':main()
