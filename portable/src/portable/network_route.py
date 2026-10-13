"""Respect Shadow VLESS standby while an existing Android VPN owns routing."""
import json,os,time,stat
from pathlib import Path
STATUS=Path('/data/adb/gpt-vless/status.json')
def choose_proxy(configured,status_path=STATUS,require_root=True):
    if configured != 'http://127.0.0.1:17890':return configured
    try:
        p=Path(status_path);s=p.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_size>4096:return configured
        if require_root and (s.st_uid!=0 or s.st_mode&0o022):return configured
        if not 0<=time.time()-s.st_mtime<=60:return configured
        value=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(value,dict):return configured
        if value.get('mode')=='standby' and value.get('any_android_vpn') is True:return ''
    except (OSError,ValueError,TypeError):pass
    return configured
