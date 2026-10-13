"""Reach the existing root-only Portable Use engine from Mini Codex on Android."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import socket
import stat

SOCKET = Path('/data/adb/codaki-portable-use/state/portable.sock')
OPERATIONS = frozenset(('apps','capabilities','diagnostics','session_start','session_extend',
    'session_stop','observe','launch','action','batch','result','reconcile'))
MAX_REQUEST = 1024*1024
MAX_RESPONSE = 4*1024*1024


def call(operation: str, arguments: dict, request_id: str) -> dict:
    """Issue once. Reuse request_id to read/retry transport; never invent a replay."""
    if operation not in OPERATIONS or not isinstance(arguments, dict):
        raise ValueError('Unknown operation or invalid arguments')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request_id):
        raise ValueError('A stable request_id of 8..80 letters/digits/_/- is required')
    if getattr(os, 'geteuid', lambda: -1)() != 0:
        raise PermissionError('Portable IPC requires the phone root service')
    payload = json.dumps({'op':operation,'args':arguments,'request_id':request_id},
                         ensure_ascii=False, separators=(',',':')).encode()+b'\n'
    if len(payload)>MAX_REQUEST:
        raise ValueError('Portable IPC request too large')
    info = SOCKET.lstat()
    parent = SOCKET.parent.stat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise PermissionError('Portable socket must be owned by root and private')
    if SOCKET.parent.is_symlink() or parent.st_uid != 0 or parent.st_mode & 0o077:
        raise PermissionError('Portable state directory must be owned by root and private')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(40)
        connection.connect(str(SOCKET))
        connection.sendall(payload)
        data=bytearray()
        while len(data)<=MAX_RESPONSE:
            chunk=connection.recv(min(65536,MAX_RESPONSE+1-len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if b'\n' in chunk:
                break
    if len(data)>MAX_RESPONSE or b'\n' not in data:
        raise ValueError('Invalid or oversized Portable IPC response; do not replay input')
    result=json.loads(bytes(data).split(b'\n',1)[0])
    if not isinstance(result,dict):
        raise ValueError('Malformed Portable IPC response; inspect the saved request outcome')
    return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=sorted(OPERATIONS))
    parser.add_argument('--request-id', required=True)
    parser.add_argument('--arguments', default='{}')
    args=parser.parse_args()
    try:
        result=call(args.operation,json.loads(args.arguments),args.request_id)
    except FileNotFoundError:
        result={'error':'Portable IPC unavailable. Check the existing Portable Use worker; do not start a second engine.','code':'IPC_UNAVAILABLE'}
    except (OSError,ValueError,TypeError):
        result={'error':'Portable IPC failed. Check result/diagnostics with the same request identity before further input.','code':'IPC_FAILED'}
    print(json.dumps(result,ensure_ascii=False))
    # Keep a receipt visible through root_shell even for a stopped workflow.
    return 0


if __name__=='__main__':
    raise SystemExit(main())
