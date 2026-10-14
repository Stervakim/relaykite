"""Owner-only lifecycle for the optional PC model. No phone command dispatcher."""
import argparse,ctypes,hashlib,json,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
MODEL_SHA='9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031'
LLAMA_SHA='f2c1cd95861da57dbe4002f3bdf03c91646f46446cca37cb1219fa31e593cb36'
OMNI_INTEGRITY='sha512-VwwSt+bP9lJiPJXFJMz0nNGGuoewPZU3nFe1SLuO11ADgdSwTegGCxhg8Ov75+31m/cocPxHiO63zygn1XQ0MQ=='
def storage():return Path(os.environ['LOCALAPPDATA'])/'RelayKiteMemory'
def checked(root):
    root=Path(root).absolute()
    for path in (root,*root.parents):
        if path.is_symlink() or path.is_junction():raise ValueError('Model storage contains a link')
    return root
def private_json(path,value):
    from mini_codex_pc import protect
    next=path.with_suffix('.next');next.write_text(json.dumps(value),encoding='utf-8');protect(next);os.replace(next,path)
def identity(pid):
    if os.name!='nt':return None
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        name=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(name))
        stamps=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)) or not kernel.GetProcessTimes(handle,*[ctypes.byref(s) for s in stamps]):return None
        return {'image':str(Path(name.value).resolve()),'generation':(stamps[0].dwHighDateTime<<32)|stamps[0].dwLowDateTime}
    finally:kernel.CloseHandle(handle)
def alive(record):return isinstance(record,dict) and identity(record.get('pid',0))==record.get('identity') and record.get('identity') is not None
def stop(record):
    if alive(record):
        subprocess.run(['taskkill','/PID',str(record['pid']),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,check=True)
def ensure():
    if os.name!='nt':return
    root=checked(storage())
    if not (root/'install-receipt.json').is_file() or (root/'disabled').exists():return
    try:
        if alive(json.loads((root/'daemon.json').read_text())):return
    except (OSError,ValueError):pass
    subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),str(Path(__file__).resolve()),'run'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
def run():
    from mini_codex_pc import InstanceLock
    root=checked(storage());receipt=json.loads((root/'install-receipt.json').read_text())
    if receipt.get('owner_component')!='relaykite-pc-memory' or receipt.get('model_location')!='pc':raise ValueError('Missing PC model consent')
    if hashlib.file_digest((root/'Qwen3-0.6B-Q8_0.gguf').open('rb'),'sha256').hexdigest()!=MODEL_SHA:raise ValueError('Model checksum mismatch')
    with InstanceLock(root):
        private_json(root/'daemon.json',{'pid':os.getpid(),'identity':identity(os.getpid())})
        env={k:v for k,v in os.environ.items() if not k.startswith('LLAMA_') and k not in ('HF_TOKEN','OPENAI_API_KEY')};env.update(DATA_DIR=str(root/'private-router'),HOSTNAME='127.0.0.1',PORT='20128',OMNIROUTE_ALLOW_LOCAL_PROVIDER_URLS='true',OMNIROUTE_NO_BROWSER='1',NEXT_TELEMETRY_DISABLED='1')
        commands={
            'model':[str(root/'llama/llama-server.exe'),'-m',str(root/'Qwen3-0.6B-Q8_0.gguf'),'--host','127.0.0.1','--port','20129','--ctx-size','2048','--parallel','1','--threads','4','--alias','qwen3-0.6b-memory','--jinja','--reasoning-format','none','--chat-template-kwargs','{"enable_thinking":false}'],
            'router':[receipt['node'],str(root/'omniroute/node_modules/omniroute/dist/server.js')]}
        commands['model']+=['--no-webui','--no-agent']
        if receipt.get('backend')=='direct':
            commands.pop('router');client=json.loads((root/'summary-client.json').read_text());env['LLAMA_API_KEY']=client['key']
        handles={};backoff={k:0 for k in commands};records={}
        try:
            while not (root/'disabled').exists():
                for name,args in commands.items():
                    if name in handles and handles[name].poll() is None:continue
                    if time.time()<backoff[name]:continue
                    log=root/(name+'.log')
                    if log.exists() and log.stat().st_size>1024*1024:log.unlink()
                    with log.open('ab') as out:p=subprocess.Popen(args,env=env,cwd=root,stdin=subprocess.DEVNULL,stdout=out,stderr=out,creationflags=subprocess.CREATE_NO_WINDOW)
                    handles[name]=p;records[name]={'pid':p.pid,'identity':identity(p.pid),'argv':args};private_json(root/'processes.json',records);backoff[name]=time.time()+30
                time.sleep(1)
        finally:
            for record in records.values():stop(record)
def cleanup_inputs():
    """Delete only completed dedicated download staging, including duplicate weights."""
    root=checked(Path(os.environ['LOCALAPPDATA'])/'RelayKiteMemoryInputs')
    status=root/'install-status.json'
    if not status.is_file() or status.is_symlink():return
    value=json.loads(status.read_text())
    if value.get('phase')!='installed' or value.get('explicit_choice')!='yes' or value.get('model_location')!='pc':return
    for name in ('Qwen3-0.6B-Q8_0.gguf','llama-b11588-bin-win-cpu-x64.zip','llama'):
        path=checked(root/name)
        if path.is_dir():
            for child in path.rglob('*'):
                if child.is_symlink() or child.is_junction():raise ValueError('Input cleanup refuses links')
            shutil.rmtree(path)
        elif path.is_file():path.unlink()

def remove(root=None):
    root=checked(root if root is not None else storage())
    if not root.exists():
        cleanup_inputs();return {'removed':True,'already_absent':True}
    receipt=root/'install-receipt.json'
    if not receipt.is_file() or receipt.is_symlink() or json.loads(receipt.read_text()).get('owner_component')!='relaykite-pc-memory':raise ValueError('Not an owned model installation')
    for path in root.rglob('*'):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('Model cleanup refuses links or escaped files')
    (root/'disabled').touch()
    try:
        for record in json.loads((root/'processes.json').read_text()).values():stop(record)
    except FileNotFoundError:pass
    try:stop(json.loads((root/'daemon.json').read_text()))
    except FileNotFoundError:pass
    # The final absolute target and all descendants were checked above.
    shutil.rmtree(root)
    cleanup_inputs()
    return {'removed':not root.exists(),'weights_removed':True,'original_memory_retained':True}
def arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('run');sub.add_parser('remove')
    install=sub.add_parser('install');install.add_argument('--model',required=True,choices=('yes','no'));install.add_argument('--source',type=Path)
    a=p.parse_args(argv)
    if a.action=='install' and a.model=='yes' and not a.source:p.error('Explicit PC model installation requires verified source inputs')
    return a
def install(source):
    from mini_codex_pc import prepare,protect
    source=checked(source);root=checked(storage())
    if root.exists():raise ValueError('Existing installation must be inspected; no replacement of private router data')
    if hashlib.file_digest((source/'Qwen3-0.6B-Q8_0.gguf').open('rb'),'sha256').hexdigest()!=MODEL_SHA:raise ValueError('Unverified model weights')
    archive=source/'llama-b11588-bin-win-cpu-x64.zip'
    if hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=LLAMA_SHA:raise ValueError('Unverified CPU runtime archive')
    import zipfile
    with zipfile.ZipFile(archive) as zip:
        for member in zip.infolist():
            if member.is_dir():continue
            path=source/'llama'/member.filename
            if not path.resolve().is_relative_to((source/'llama').resolve()) or path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256(zip.read(member)).digest():raise ValueError('CPU runtime differs from pinned official archive')
    direct=not (source/'omniroute').exists()
    if not direct:
        lock=json.loads((source/'omniroute/package-lock.json').read_text())
        if lock.get('packages',{}).get('node_modules/omniroute',{}).get('integrity')!=OMNI_INTEGRITY:raise ValueError('Router package lacks pinned npm integrity')
        metadata=json.loads((source/'omniroute/node_modules/omniroute/package.json').read_text())
        if metadata.get('name')!='omniroute' or metadata.get('version')!='3.8.51':raise ValueError('Only pinned OmniRoute is supported')
    names=('llama','Qwen3-0.6B-Q8_0.gguf') if direct else ('llama','omniroute','Qwen3-0.6B-Q8_0.gguf','private-router')
    for name in names:
        path=source/name
        if path.is_symlink() or path.is_junction():raise ValueError('Unsafe model input')
        if path.is_dir():
            for child in path.rglob('*'):
                if child.is_symlink() or child.is_junction() or not child.resolve().is_relative_to(path.resolve()):raise ValueError('Linked model source rejected')
    root=prepare(root)
    for name in names:
        if (source/name).is_dir():shutil.copytree(source/name,root/name)
    shutil.copyfile(source/'Qwen3-0.6B-Q8_0.gguf',root/'Qwen3-0.6B-Q8_0.gguf')
    if direct:
        from memory_summary import DIRECT_MODEL,DIRECT_URL
        client={'enabled':True,'url':DIRECT_URL,'model':DIRECT_MODEL,'key':secrets.token_urlsafe(40)}
        private_json(root/'summary-client.json',client)
        pc=prepare(Path(os.environ['LOCALAPPDATA'])/'CodakiMiniCodex');private_json(pc/'summary.json',client)
    private_json(root/'install-receipt.json',{'owner_component':'relaykite-pc-memory','model_location':'pc','model_sha256':MODEL_SHA,'node':shutil.which('node'),'backend':'direct' if direct else 'omniroute','installed':time.time()})
    ensure()
def main(argv=None):
    a=arguments(argv)
    if a.action=='run':run()
    elif a.action=='remove':print(json.dumps(remove()))
    elif a.model=='no':print(json.dumps({'model_installed':False}))
    else:install(a.source)
if __name__=='__main__':main()
