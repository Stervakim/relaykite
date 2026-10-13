"""Root-local fixed control requests to the installed mode supervisor."""
import argparse,json,os,time,uuid
from pathlib import Path

FILES=Path('/data/data/org.relaykite.runtime/files')

def request(mode,ident=None,timeout=45):
    if os.geteuid()!=0:raise PermissionError('Installed root control requires root')
    if mode not in ('app','root','root-termux','stop','reconcile'):raise ValueError('Unknown mode')
    uid=FILES.parent.stat().st_uid
    if not 10000<uid<20000:raise ValueError('Unexpected application UID')
    descriptor=json.loads((FILES/'root-control.json').read_text())
    if not descriptor.get('available') or not 0<=time.time()-descriptor.get('updated',0)<=75:raise RuntimeError('Installed supervisor is unavailable')
    ident=ident or 'local_'+uuid.uuid4().hex
    from root_supervisor import private_json
    private_json(FILES/'mode-request.json',{'request_id':ident,'mode':mode},uid)
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        state=json.loads((FILES/'mode-status.json').read_text())
        receipt=state.get('receipt',{})
        if receipt.get('request_id')==ident:return state
        time.sleep(.2)
    raise RuntimeError('Control request pending; inspect its original ID '+ident)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('app','root','root-termux','stop','reconcile'));p.add_argument('--request-id');a=p.parse_args()
    print(json.dumps(request(a.mode,a.request_id)))
