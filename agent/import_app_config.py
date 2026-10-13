"""First explicit APK configuration import, without replacing an existing owner."""
import argparse,json,os,secrets
from pathlib import Path
from runtime_paths import BASE,MODE
from configure import validate,safe_path

def first_import(source):
    if MODE!='app' or getattr(os,'geteuid',lambda:0)()==0:raise PermissionError('Import through the ordinary owned app')
    source=safe_path(source)
    if not source.is_file() or source.stat().st_size>32768:raise ValueError('Configuration file exceeds32KiB or is not regular')
    if (BASE/'config.json').exists():raise ValueError('Existing owner configuration preserved; use the mode migration flow')
    value=json.loads(source.read_text());allowed={'relay_url','agent_token','sites_authorization','poll_seconds','outbound_proxy','state_dir','memory_dir','disable_file'}
    if not isinstance(value,dict) or set(value)-allowed:raise ValueError('Unsupported configuration fields')
    value={k:v for k,v in value.items() if k not in ('state_dir','memory_dir','disable_file')};config=validate(value,BASE,BASE)
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name in ('state','memory','memory-service/data'):(BASE/name).mkdir(parents=True,exist_ok=True,mode=0o700)
    key=secrets.token_urlsafe(48)
    node={'scope':'codaki-owner-phone','key':key,'port':8420,'data_dir':str(BASE/'memory-service/data'),'quota_bytes':5*1024**3}
    bridge={'url':'http://127.0.0.1:8420','key':key,'data_dir':node['data_dir'],'accounting_roots':[str(BASE)]}
    for name,data in (('memory-node.json',node),('memory-service.json',bridge),('config.json',config)):
        target=BASE/name
        with target.open('x') as out:json.dump(data,out);out.flush();os.fsync(out.fileno())
        target.chmod(0o600)
    (BASE/'enabled').touch(mode=0o600)
    return {'imported':True,'mode':'app','credentials_printed':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
    try:print(json.dumps(first_import(a.source)))
    except Exception as error:print(json.dumps({'error':type(error).__name__,'imported':False}));raise SystemExit(1)
