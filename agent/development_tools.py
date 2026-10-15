"""Typed phone entry and owner-installed project selection policy.

Project roots constrain task workspace selection. Android root execution has no
sandbox isolation; this policy never claims to restrict the agent's root tools.
"""
import json
import os
from pathlib import Path
import stat
import sys

OPERATIONS = ('capabilities','install','start','status','events','artifacts','pause','resume','cancel')


def engine_environment(base):
    engine = Path(base) / 'development-engine'
    for part in (engine, engine/'bin', engine/'toolchain', engine/'toolchain/bin', engine/'toolchain/lib',
                 engine/'toolchain/libexec/git-core', engine/'toolchain/share/git-core/templates',
                 engine/'bin/codex', engine/'toolchain/bin/git'):
        info = part.lstat()
        if part.is_symlink() or (not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode)):
            raise PermissionError('Unsafe owner-installed development-engine path')
        if os.name != 'nt' and (info.st_uid != 0 or info.st_mode & 0o022):
            raise PermissionError('Development engine must be root-owned and not writable by other users')
    native = os.environ.get('RELAYKITE_NATIVE') or str(Path(sys.executable).parent)
    return {'RELAYKITE_CODEX':str(engine/'bin/codex'), 'PATH':str(engine/'toolchain/bin')+':/system/bin',
            'SHELL':'/system/bin/sh','LD_LIBRARY_PATH':str(engine/'toolchain/lib')+':'+native,
            'GIT_EXEC_PATH':str(engine/'toolchain/libexec/git-core'),
            'GIT_TEMPLATE_DIR':str(engine/'toolchain/share/git-core/templates'),
            'GIT_SSL_CAINFO':str(engine/'toolchain/etc/tls/cert.pem'),
            'CURL_CA_BUNDLE':str(engine/'toolchain/etc/tls/cert.pem')}


def definition():
    limits = {'type':'object','properties':{
        'max_steps':{'type':'integer','minimum':1,'maximum':10000},
        'max_seconds':{'type':'integer','minimum':1,'maximum':86400},
        'max_turns':{'type':'integer','minimum':1,'maximum':100}}, 'additionalProperties':False}
    arguments = {'type':'object','properties':{
        'prompt':{'type':'string','minLength':1,'maxLength':32000},
        'workspace':{'type':'string','minLength':1,'maxLength':4096},
        'verify_command':{'type':'string','minLength':1,'maxLength':4096},
        'limits':limits,
        'run_id':{'type':'string','pattern':'[a-f0-9]{32}'},
        'after':{'type':'integer','minimum':0,'maximum':9223372036854775807}}, 'additionalProperties':False}
    return {'name':'phone_development',
            'description':'Owner-bound phone backend for relaykite_dev. Runs Codex through ordinary saved ChatGPT conversations on the rooted Android phone, without Termux or a PC. Explicit Android root execution has no sandbox isolation. Start workspaces must be within the owner-installed development-policy.json project roots. Keep request_id stable for retries; inspect uncertain receipts before resuming.',
            'inputSchema':{'type':'object','properties':{
                'operation':{'type':'string','enum':list(OPERATIONS)},
                'request_id':{'type':'string','minLength':1,'maxLength':200,'pattern':'[A-Za-z0-9][A-Za-z0-9._:-]{0,199}'},
                'arguments':arguments},'required':['operation','request_id'],'additionalProperties':False},
            'annotations':{'readOnlyHint':False,'destructiveHint':True,'idempotentHint':True}}


def operation_arguments(operation, arguments):
    allowed = {'start':{'prompt','workspace','verify_command','limits'}, 'status':{'run_id'},
               'events':{'run_id','after'}, 'artifacts':{'run_id'},
               'pause':{'run_id'}, 'resume':{'run_id'}, 'cancel':{'run_id'}, 'capabilities':set(), 'install':set()}
    if operation not in allowed or not isinstance(arguments, dict) or set(arguments) - allowed[operation]:
        raise ValueError('Unsupported development operation arguments')
    if operation == 'start' and any(not arguments.get(key) for key in ('prompt','workspace')):
        raise ValueError('start requires prompt and workspace')
    if operation in ('events','artifacts','pause','resume','cancel') and not arguments.get('run_id'):
        raise ValueError('This development operation requires run_id')
    return dict(arguments)


def selected_workspace(base, workspace):
    base = Path(base).absolute()
    policy = base / 'development-policy.json'
    for part in (base, *base.parents, policy):
        if part.is_symlink():
            raise PermissionError('Development policy storage must not use symlinks')
    info = policy.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
        raise ValueError('Use a regular owner-installed development policy smaller than 16 KiB')
    if os.name != 'nt' and (info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022):
        raise PermissionError('Development policy must be root-owned and not writable by other users')
    value = json.loads(policy.read_text('utf8'))
    roots = value.get('workspace_roots') if isinstance(value,dict) else None
    if (not isinstance(value,dict) or set(value) != {'workspace_roots'} or not isinstance(roots,list)
            or not 1 <= len(roots) <= 16):
        raise ValueError('Owner policy must explicitly list 1–16 workspace_roots')
    allowed = []
    for value in roots:
        if not isinstance(value,str) or not Path(value).is_absolute() or not Path(value).is_dir():
            raise ValueError('Policy workspace roots must be existing absolute directories')
        allowed.append(Path(value).resolve())
    if not isinstance(workspace,str) or not Path(workspace).is_absolute() or not Path(workspace).is_dir():
        raise ValueError('Workspace must be an existing absolute project directory')
    selected = Path(workspace).resolve()
    if not any(selected.is_relative_to(root) for root in allowed):
        raise PermissionError('Workspace is outside the owner-configured project roots')
    return str(selected)
