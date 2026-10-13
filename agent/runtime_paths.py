"""Local installation paths and explicit privilege reporting."""
import os
from pathlib import Path
BASE=Path(os.environ.get('RELAYKITE_BASE','/data/adb/mini-codex'))
MODULE=Path(os.environ.get('RELAYKITE_MODULE','/data/adb/modules/mini_codex'))
MODE=os.environ.get('RELAYKITE_MODE','root-termux')
if MODE not in ('app','root','root-termux'):raise ValueError('Unknown installation mode')
if MODE=='app':MODULE=BASE

def identity():
    uid=getattr(os,'geteuid',lambda:-1)()
    return {'mode':MODE,'uid':uid,'root_active':uid==0,'termux_backend_enabled':MODE=='root-termux' and uid==0,
            'limitations':[] if uid==0 else ['System UID 2000/root shells and cross-app virtual-screen input require root mode. Files are limited by Android app permissions.']}
