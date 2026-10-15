"""Private loopback bridge to original Tencent storage; no model client."""
from __future__ import annotations
import json, os, stat, urllib.request, urllib.error, urllib.parse
from pathlib import Path

CAP=5*1024**3
ENGINE='tencentdb-original-external'
from runtime_paths import BASE
DEFAULT_CONFIG=BASE/'memory-service.json'
class MemoryUnavailable(RuntimeError):pass

def allocated_bytes(path:Path,*,allow_symlinks=False)->int:
    try:s=path.lstat()
    except FileNotFoundError:return 0
    if stat.S_ISLNK(s.st_mode):
        if not allow_symlinks:raise ValueError('Storage symlink rejected')
        # Account only the link inode. Never traverse a runtime/project link,
        # including a broken link, external directory or a cycle.
        return getattr(s,'st_blocks',0)*512 or s.st_size
    if stat.S_ISREG(s.st_mode):return getattr(s,'st_blocks',0)*512 or s.st_size
    if not stat.S_ISDIR(s.st_mode):return 0  # IPC sockets/FIFOs have no records.
    return sum(allocated_bytes(p,allow_symlinks=allow_symlinks) for p in path.iterdir())

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('Memory service redirect rejected')

class MemoryBridge:
    def __init__(self,configuration:Path=DEFAULT_CONFIG):
        self.configured=False;self.config={};self.data_dir=None
        if not configuration.exists():return
        if configuration.is_symlink():raise ValueError('Memory configuration symlink rejected')
        self.config=json.loads(configuration.read_text(encoding='utf-8'))
        data_dir=self.config.get('data_dir')
        if data_dir is not None:
            if not isinstance(data_dir,str) or not Path(data_dir).is_absolute():raise ValueError('Expected absolute memory data_dir')
            self.data_dir=Path(data_dir)
        reserve=self.config.get('external_reserved_bytes',0)
        if type(reserve)!=int or not 0<=reserve<CAP:raise ValueError('Invalid external storage reservation')
        u=urllib.parse.urlsplit(self.config.get('url',''))
        if u.scheme!='http' or u.hostname!='127.0.0.1' or u.username or u.password or u.query or u.fragment or u.path not in ('','/') or not u.port:
            raise ValueError('Memory service must use a fixed loopback URL')
        if not isinstance(self.config.get('key'),str) or not 40<=len(self.config['key'])<=256:raise ValueError('Invalid local memory key')
        self.url=self.config['url'].rstrip('/');self.configured=True
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    def request(self,route:str,payload:dict|None=None)->dict:
        if not self.configured:raise RuntimeError('Tencent memory is not configured')
        if route not in ('/save','/search','/read','/health'):raise ValueError('Unsupported memory route')
        body=None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
        if body is not None and len(body)>256*1024:raise ValueError('Memory request exceeds limit')
        req=urllib.request.Request(self.url+route,data=body,headers={'Authorization':'Bearer '+self.config['key'],'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=5) as response:
                raw=response.read(256*1024+1)
                if len(raw)>256*1024:raise RuntimeError('Memory response exceeds limit')
        except urllib.error.HTTPError as e:
            try:data=json.loads(e.read(8192));message=data.get('error','Memory request failed')
            except Exception:message='Memory request failed'
            finally:e.close()
            raise RuntimeError(str(message)[:500]) from None
        except (urllib.error.URLError,TimeoutError,OSError):raise MemoryUnavailable('Tencent memory service is unavailable') from None
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get('engine')!=ENGINE:raise RuntimeError('Unexpected memory engine response')
        return data
    def save(self,title:str,content:str,tags:list,memory:dict|None=None)->dict:
        roots=[Path(p) for p in self.config.get('accounting_roots',[])]
        # Memory records remain a strict, link-free store. Broader accounting
        # roots also contain the Codex/Git runtime and owner projects, where
        # legitimate executable links must not prevent saving unrelated memory.
        if self.data_dir is not None:allocated_bytes(self.data_dir)
        if self.config.get('external_reserved_bytes',0)+sum(allocated_bytes(p,allow_symlinks=self.data_dir is not None) for p in roots)+len(content.encode())*8+65536>CAP:raise ValueError('Combined Codaki storage quota exceeded')
        p={'title':title,'content':content,'tags':tags}
        if memory is not None:p['memory']=memory
        return self.request('/save',p)
    def search(self,query:str,limit:int=5,filters:dict|None=None)->dict:
        return self.request('/search',{'query':query,'limit':limit,'filters':filters or {}})
    def read(self,record_id:str)->dict:return self.request('/read',{'id':record_id})
    def health(self)->dict:return self.request('/health')
