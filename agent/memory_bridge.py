"""Private loopback bridge to original Tencent storage; no model client."""
from __future__ import annotations
import json, os, stat, urllib.request, urllib.error, urllib.parse
from pathlib import Path

CAP=5*1024**3
ENGINE='tencentdb-original-external'
DEFAULT_CONFIG=Path('/data/adb/mini-codex/memory-service.json')
class MemoryUnavailable(RuntimeError):pass

def allocated_bytes(path:Path)->int:
    if not path.exists():return 0
    if path.is_symlink():raise ValueError('Storage symlink rejected')
    if path.is_file():
        s=path.stat();return getattr(s,'st_blocks',0)*512 or s.st_size
    return sum(allocated_bytes(p) for p in path.iterdir())

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('Memory service redirect rejected')

class MemoryBridge:
    def __init__(self,configuration:Path=DEFAULT_CONFIG):
        self.configured=False;self.config={}
        if not configuration.exists():return
        if configuration.is_symlink():raise ValueError('Memory configuration symlink rejected')
        self.config=json.loads(configuration.read_text(encoding='utf-8'))
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
        if sum(allocated_bytes(p) for p in roots)+len(content.encode())*8+65536>CAP:raise ValueError('Combined Codaki storage quota exceeded')
        p={'title':title,'content':content,'tags':tags}
        if memory is not None:p['memory']=memory
        return self.request('/save',p)
    def search(self,query:str,limit:int=5,filters:dict|None=None)->dict:
        return self.request('/search',{'query':query,'limit':limit,'filters':filters or {}})
    def read(self,record_id:str)->dict:return self.request('/read',{'id':record_id})
    def health(self)->dict:return self.request('/health')
