"""Bounded project-only facade over the original Graphify 0.9.88 reader."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path

runtime=Path(__file__).with_name('graph-runtime.zip')
if runtime.is_file():sys.path.insert(0,str(runtime))
from graphify.serve import _read_graph,_query_graph_text,_resolve_single_node,_shortest_path_text

VERSION='0.9.88'
from runtime_paths import BASE
DEFAULT_DIR=BASE/'project-graph'
_cache={}

def _text(value,name):
    if not isinstance(value,str) or not value.strip() or len(value)>2000 or '\0' in value:raise ValueError('Invalid '+name)
    return value

class ProjectGraph:
    def __init__(self,directory:Path=DEFAULT_DIR):self.directory=directory
    def _load(self):
        p=self.directory/'graph.json';manifest=self.directory/'manifest.json'
        if p.is_symlink() or manifest.is_symlink():raise ValueError('Graph symlink rejected')
        if not p.exists() or not manifest.exists():raise ValueError('Project graph is not installed')
        if p.stat().st_size>25*1024**2 or manifest.stat().st_size>256*1024:raise ValueError('Graph exceeds size limit')
        raw=p.read_bytes();m=json.loads(manifest.read_text(encoding='utf-8'))
        digest=hashlib.sha256(raw).hexdigest()
        if m.get('sha256')!=digest:raise ValueError('Graph checksum mismatch')
        data=json.loads(raw);metadata=data.get('graph',{})
        if m.get('graphify_version')!=VERSION or metadata.get('graphify_version')!=VERSION:raise ValueError('Unsupported Graphify version')
        if str(metadata.get('schema_version')) not in ('1','1.0','1.0.0'):raise ValueError('Unsupported graph schema')
        if not isinstance(data.get('nodes'),list) or len(data['nodes'])>50000 or len(data.get('links',data.get('edges',[])))>200000:raise ValueError('Graph exceeds node/edge limits')
        key=(str(p.resolve()),digest)
        if key not in _cache:
            _cache.clear();_cache[key]=_read_graph(str(p))
        changed=[]
        for name,expected in m.get('sources',{}).items():
            src=Path(name)
            if src.is_symlink() or not src.is_file() or hashlib.sha256(src.read_bytes()).hexdigest()!=expected:changed.append(name)
        return _cache[key],m,changed
    def _result(self,result:str,m:dict,changed:list)->dict:
        r={'engine':'graphify-original','graphify_version':VERSION,'graph_revision':m.get('revision',m['sha256']),
           'created_at':m.get('created_at',''),'stale':bool(changed),'changed_sources':changed[:10],'text':result}
        if len(json.dumps(r,ensure_ascii=False).encode())>6144:
            r['truncated']=True
            overhead=len(json.dumps({**r,'text':''},ensure_ascii=False).encode())
            r['text']=result.encode()[:max(0,6144-overhead-80)].decode('utf-8',errors='ignore')+'\n[truncated]'
        if len(json.dumps(r,ensure_ascii=False).encode())>6144:raise ValueError('Graph metadata exceeds response budget')
        return r
    def query(self,question:str)->dict:
        _text(question,'question');G,m,changed=self._load()
        result=_query_graph_text(G,question,depth=2,token_budget=900)
        return self._result(result,m,changed)
    def node(self,label:str)->dict:
        _text(label,'label');G,m,changed=self._load();node,error=_resolve_single_node(G,label.lower())
        if error or node is None:raise ValueError(error or 'Node not found')
        result=_query_graph_text(G,label,depth=1,token_budget=900,seeds=[node])
        return self._result(result,m,changed)
    def path(self,source:str,target:str)->dict:
        _text(source,'source');_text(target,'target');G,m,changed=self._load()
        return self._result(_shortest_path_text(G,{'source':source,'target':target,'max_hops':6}),m,changed)
