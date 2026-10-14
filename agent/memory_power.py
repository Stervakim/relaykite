"""Fail-closed phone model power gate; independent of primary phone tools."""
import json,os,time,socket,struct
from pathlib import Path
def permitted(state):
    return (isinstance(state,dict) and state.get('enabled') is True
            and type(state.get('battery')) is int and 20<state['battery']<=100)
def sdk_state(path):
    try:
        path=Path(path)
        if path.is_symlink() or path.stat().st_size>1024:return {}
        value=json.loads(path.read_text());age=time.time()-value['updated']
        return value if 0<=age<=90 else {}
    except (OSError,ValueError,KeyError,TypeError):return {}
def phone_state(base):
    if os.environ.get('RELAYKITE_MODE') in ('root','root-termux') and getattr(os,'geteuid',lambda:-1)()==0:
        try:return {'enabled':True,'battery':int(Path('/sys/class/power_supply/battery/capacity').read_text().strip())}
        except (OSError,ValueError):return {}
    # Query the app's Android SDK broker at request time. Handler heartbeat
    # timers can sleep with the device; their age is not a battery observation.
    try:
        uid=Path(base).stat().st_uid
        if uid<10000:return {}
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
            peer.settimeout(2);peer.connect('\0relaykite-power-'+str(uid))
            _,owner,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if owner!=uid:return {}
            raw=b''
            while True:
                chunk=peer.recv(1025-len(raw))
                if not chunk:break
                raw+=chunk
                if len(raw)>1024:return {}
            return json.loads(raw)
    except (OSError,ValueError,AttributeError):return {}
