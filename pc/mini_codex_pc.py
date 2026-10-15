"""Mini Codex background PC worker: HTTPS polling, local consent, no listener."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parent))

VERSION = '0.3.0'
CAPABILITIES = {'terminal', 'files_read', 'files_write', 'codex'}
OPERATIONS = {'pc_status': None, 'pc_terminal': 'terminal', 'pc_read_file': 'files_read',
              'pc_write_file': 'files_write', 'pc_list_files': 'files_read', 'pc_codex': 'codex'}
PORTABLE_OPERATIONS=('apps','capabilities','diagnostics','session_start','session_extend','session_stop','observe','launch','action','batch','result','reconcile')
OPERATIONS.update({'pc_use_'+op:'terminal' for op in PORTABLE_OPERATIONS})
OPERATIONS['pc_memory_summarize']=None
OPERATIONS['pc_memory_model_remove']=None
OPERATIONS['relaykite_dev']='codex'
MAX_OUTPUT = 24000  # UTF-8 JSON expansion remains below the relay result limit.


def storage():
    return Path(os.environ['LOCALAPPDATA'])/'CodakiMiniCodex' if os.name == 'nt' else Path.home()/'.codaki-mini-codex-pc'


def real_storage(path):
    path = Path(path).absolute()
    for parent in [path, *path.parents]:
        if parent.is_symlink() or parent.is_junction():
            raise ValueError('Private storage must not contain symlinks or junctions')
    return path


def protect(path):
    path = real_storage(path)
    if os.name == 'nt':
        info = subprocess.run(['whoami', '/user', '/fo', 'csv'], capture_output=True, text=True, errors='replace', check=True,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        sid = re.search(r'S-1-5-[0-9-]+', info.stdout)
        if not sid: raise RuntimeError('Cannot identify Windows owner')
        # Reset explicit entries before removing inherited grants; do not retain Everyone.
        for args in ([str(path), '/reset'], [str(path), '/inheritance:r'],
                     [str(path), '/grant:r', '*'+sid.group()+':(OI)(CI)F' if path.is_dir() else '*'+sid.group()+':F']):
            subprocess.run(['icacls', *args], capture_output=True, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


def prepare(path):
    path = real_storage(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    protect(path)
    return path


def save_config(base, config):
    real_storage(base/'config.json')
    temp = base/'config.new'
    real_storage(temp)
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    protect(temp)
    os.replace(temp, base/'config.json')


def load_config(base):
    path = real_storage(base/'config.json')
    if not path.exists(): return {'version': 1, 'connections': {}}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('connections'), dict):
        raise ValueError('Unsupported configuration')
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


class Relay:
    def __init__(self, config):
        url = urllib.parse.urlparse(config['relay_url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('An HTTPS relay URL without credentials/query/fragment is required')
        self.base = config['relay_url'].rstrip('/')
        self.token = config.get('token', '')
        if self.token and not re.fullmatch(r'[a-f0-9]{64}', self.token): raise ValueError('Invalid device credential')
        self.authorization = config.get('sites_authorization', '')
        if any(c in self.authorization for c in '\r\n'): raise ValueError('Invalid hosting authorization')
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, action, **args):
        raw = json.dumps({'action': action, **args}, ensure_ascii=False).encode('utf-8')
        limit=4*1024*1024+8192 if action=='result' else 256000
        if len(raw) > limit: raise ValueError('Request too large')
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.token: headers['Authorization'] = 'Bearer '+self.token
        if self.authorization: headers['OAI-Sites-Authorization'] = self.authorization
        req = urllib.request.Request(self.base+'/bridge/api', data=raw, headers=headers, method='POST')
        with self.opener.open(req, timeout=25) as response:
            data = response.read(256001)
            if len(data) > 256000: raise ValueError('Response too large')
            return json.loads(data)


def bounded_process(argv, cwd, stdin='', timeout=60):
    """No shell interpolation, bounded output, and entire process-tree timeout."""
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    process = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, **kwargs)
    output = bytearray()
    truncated = [False]
    def drain():
        while True:
            chunk = process.stdout.read(4096)
            if not chunk: break
            remaining = max(0, MAX_OUTPUT-len(output))
            output.extend(chunk[:remaining])
            if len(chunk) > remaining: truncated[0] = True
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        process.stdin.write(stdin.encode('utf-8')); process.stdin.close()
    except BrokenPipeError: pass
    try:
        process.wait(timeout=timeout)
        reader.join(timeout=1)
        if reader.is_alive(): raise subprocess.TimeoutExpired(argv, timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        process.wait(); reader.join(timeout=2)
        if not reader.is_alive(): process.stdout.close()
        return {'status': 'uncertain', 'error': 'Command timed out or was interrupted. Inspect actual state before retrying.',
                'output': output.decode('utf-8', 'replace'), 'truncated': truncated[0]}
    process.stdout.close()
    return {'exit_code': process.returncode, 'output': output.decode('utf-8', 'replace'), 'truncated': truncated[0]}


def allowed_path(value, config, base, *, file_target=True):
    if not isinstance(value, str) or not value or '\x00' in value: raise ValueError('Path required')
    path = Path(value)
    if not path.is_absolute(): raise ValueError('Use an absolute path')
    # Reject every reparse component before and after resolving containment.
    real_storage(path)
    path = path.resolve()
    roots = [Path(p).resolve() for p in config.get('roots', [])]
    if file_target and (path.is_relative_to(base.resolve()) or base.resolve().is_relative_to(path)):
        raise PermissionError('Private Mini Codex storage is not a file-tool target')
    if not any(path.is_relative_to(root) for root in roots): raise PermissionError('Path outside owner-approved roots')
    return path


def execute(tool, args, config, base, scope=None):
    if tool not in OPERATIONS: raise ValueError('Unknown PC operation')
    cap = OPERATIONS[tool]
    if cap and cap not in config.get('capabilities', []): raise PermissionError('Capability disabled locally')
    if not isinstance(args, dict): raise ValueError('Arguments object required')
    if tool == 'relaykite_dev':
        if not isinstance(scope, str) or not scope:
            raise PermissionError('Authenticated pairing scope required for development')
        from development.client import call
        local = dict(args)
        if local.get('operation') == 'start':
            local['workspace'] = str(allowed_path(local.get('workspace'), config, base))
        return call(local, base, scope=scope)
    if tool=='pc_memory_model_remove':
        if args:raise ValueError('Model cleanup accepts no path or command')
        from model_runtime import remove
        result=remove();(base/'summary.json').unlink(missing_ok=True)
        return result
    if tool=='pc_memory_summarize':
        if set(args)!={'events'}:raise ValueError('Only memory source events permitted')
        from memory_summary import summarize
        return summarize(args['events'],base)
    if tool.startswith('pc_use_'):
        from portable_client import invoke
        return invoke(tool.removeprefix('pc_use_'),args,scope)
    if tool == 'pc_status':
        from portable_client import status as portable_status
        return {'version': VERSION, 'platform': sys.platform, 'capabilities': config.get('capabilities', []),
                'roots': config.get('roots', []), 'powershell': bool(shutil.which('pwsh') or shutil.which('powershell')),
                'codex': bool(config.get('codex_argv')), 'portable_use':portable_status(config.get('capabilities',[])),
                'plugin_integration': {'mode': 'client_tools', 'instructions': 'GPT may combine Mini Codex with available Computer Use, Sites and other plugins. Those tools need their own permissions and must target this exact PC. This worker does not inherit or enumerate ChatGPT plugin credentials.'}}
    if tool in ('pc_list_files', 'pc_read_file', 'pc_write_file'):
        path = allowed_path(args.get('path'), config, base)
        if tool == 'pc_list_files':
            items = []
            for entry in path.iterdir():
                items.append({'name': entry.name, 'directory': entry.is_dir(), 'link': entry.is_symlink() or entry.is_junction()})
                if len(items) >= 100: break
            return {'entries': items, 'limit': 100}
        if path.exists() and (not path.is_file() or path.stat().st_nlink > 1):
            raise PermissionError('Only regular files without hard links are supported')
        if tool == 'pc_read_file':
            with path.open('rb') as stream: raw = stream.read(MAX_OUTPUT+1)
            return {'text': raw[:MAX_OUTPUT].decode('utf-8', 'replace'), 'truncated': len(raw) > MAX_OUTPUT}
        value = args.get('text')
        if not isinstance(value, str) or len(value.encode('utf-8')) > 64000: raise ValueError('Text exceeds 64 kB')
        # Existing files are backed up locally before replacement.
        if path.exists():
            if path.stat().st_size > 64000: raise ValueError('Existing file too large for reversible write')
            backup = base/'backups'; backup.mkdir(exist_ok=True, mode=0o700)
            entries = sorted(backup.glob('*.txt'), key=lambda p: p.stat().st_mtime)
            for old in entries[:-99]: old.unlink()
            (backup/(secrets.token_hex(12)+'.txt')).write_bytes(path.read_bytes())
        with path.open('w', encoding='utf-8', newline='') as stream: stream.write(value)
        return {'written': len(value.encode('utf-8')), 'path': str(path)}
    # Selecting a working directory does not read it. PowerShell already has
    # the explicitly approved Windows-user grant; file tools retain the guard.
    cwd = allowed_path(args.get('cwd', config.get('roots', [''])[0]), config, base, file_target=False)
    if not cwd.is_dir(): raise ValueError('Working directory must exist')
    seconds = args.get('timeout_seconds', 60)
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 90: raise ValueError('timeout_seconds must be 1..90')
    if tool == 'pc_terminal':
        command = args.get('command')
        if not isinstance(command, str) or not command or len(command) > 16000: raise ValueError('Command must be 1..16000 characters')
        shell = shutil.which('pwsh') or shutil.which('powershell')
        if not shell: raise RuntimeError('PowerShell is not installed')
        script = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n$ErrorActionPreference = 'Stop'\n"+command+'\n'
        return bounded_process([shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', '-'], cwd, script, seconds)
    argv = config.get('codex_argv')
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise RuntimeError('Owner must configure an installed Codex CLI launcher first')
    prompt = args.get('prompt')
    if not isinstance(prompt, str) or not prompt or len(prompt) > 16000: raise ValueError('Prompt required')
    # Deliberate Codex grant; keep its sandbox and approval rules in force.
    return bounded_process([*argv, 'exec', '--sandbox', 'workspace-write', '--skip-git-repo-check', '--color', 'never', '-'], cwd, prompt, seconds)


class Journal:
    def __init__(self, base):
        real_storage(base/'journal.sqlite')
        self.db = sqlite3.connect(base/'journal.sqlite')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, fingerprint TEXT, status TEXT, result TEXT, sent INTEGER DEFAULT 0, created REAL)')
        self.db.execute("UPDATE jobs SET status='uncertain', result=? WHERE status='started'", (json.dumps({'error': 'Worker restarted; outcome unknown. Inspect PC before retrying.'}),))
        self.db.commit()

    def execute_job(self, connection, job, config, base):
        if not isinstance(job, dict) or not re.fullmatch(r'[a-f0-9-]{36}', str(job.get('id', ''))): raise ValueError('Invalid job ID')
        key = connection+':'+job['id']
        fingerprint = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()
        row = self.db.execute('SELECT fingerprint,status,result FROM jobs WHERE id=?', (key,)).fetchone()
        if row:
            if row[0] != fingerprint: raise ValueError('Job ID changed payload')
            return row[1], json.loads(row[2])
        deadline = job.get('expires_at', 0)
        if not isinstance(deadline, (int, float)) or not time.time() < deadline <= time.time()+300:
            return 'uncertain', {'error': 'Expired job; no command executed'}
        self.db.execute("INSERT INTO jobs(id,fingerprint,status,created) VALUES(?,?,'started',?)", (key, fingerprint, time.time()))
        self.db.commit()  # Durable marker must precede every side effect.
        try:
            value = execute(job.get('tool'), job.get('arguments'), config, base, scope=connection)
            portable=value.get('structuredContent',{}) if str(job.get('tool','')).startswith('pc_use_') else {}
            state = 'uncertain' if value.get('status') == 'uncertain' or portable.get('status')=='uncertain' or portable.get('original_code')=='UNCERTAIN' or portable.get('code') in ('UNCERTAIN','IPC_FAILED','IPC_DEADLINE') else 'completed'
        except (ValueError, PermissionError) as error:
            state, value = 'completed', {'error': str(error), 'executed': False}
        except Exception:
            state, value = 'uncertain', {'error': 'Executor failed. Inspect PC state before retrying.'}
        self.db.execute('UPDATE jobs SET status=?,result=? WHERE id=?', (state, json.dumps(value, ensure_ascii=False), key))
        self.db.commit()
        return state, value

    def unsent(self, connection):
        return self.db.execute('SELECT id,status,result FROM jobs WHERE sent=0 AND status IN (\'completed\',\'uncertain\') AND id LIKE ? LIMIT 8', (connection+':%',)).fetchall()

    def acknowledge(self, ident):
        self.db.execute('UPDATE jobs SET sent=1 WHERE id=?', (ident,))
        self.db.execute('DELETE FROM jobs WHERE sent=1 AND created<?', (time.time()-86400,))
        self.db.commit()


class InstanceLock:
    def __init__(self, base): self.path = real_storage(base/'worker.lock')
    def __enter__(self):
        self.file = self.path.open('a+b')
        self.file.seek(0); self.file.write(b'0'); self.file.flush(); self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close(); raise RuntimeError('Another worker is running') from None
        return self
    def __exit__(self, *_): self.file.close()


def run(base, once=False):
    with InstanceLock(base):
        from model_runtime import ensure
        try:ensure()
        except Exception:pass  # Optional model setup cannot stop core PC tools.
        journal = Journal(base)
        try:
            while not (base/'disabled').exists():
                config = load_config(base)
                try:ensure()
                except Exception:pass
                for ident, local in config['connections'].items():
                    if not local.get('enabled'): continue
                    try:
                        relay = Relay(local)
                        # Retry delivery of cached results before polling, without re-execution.
                        for key, state, raw in journal.unsent(ident):
                            try:
                                relay.call('result', job_id=key.split(':', 1)[1], status=state, result=json.loads(raw))
                            except urllib.error.HTTPError as error:
                                if error.code != 410: raise
                                # Relay retention expired. Keep no blocked delivery loop;
                                # acknowledge the old cache without executing it again.
                            journal.acknowledge(key)
                        reply = relay.call('next')
                        job = reply.get('job')
                        if job and not (base/'disabled').exists():
                            # Reload local grants after receiving the job; revocation cannot be overwritten remotely.
                            current = load_config(base)['connections'].get(ident)
                            if not current or not current.get('enabled'): continue
                            current = {**current, 'capabilities': sorted(set(current['capabilities']) & set(reply['capabilities']))}
                            state, value = journal.execute_job(ident, job, current, base)
                            relay.call('result', job_id=job['id'], status=state, result=value)
                            journal.acknowledge(ident+':'+job['id'])
                    except urllib.error.HTTPError:
                        # A denied/revoked link receives no jobs. Retain saved consent
                        # across transient hosting-auth failures; never re-pair silently.
                        # Do not log payloads, tokens or authenticated URLs.
                        pass
                    except Exception: pass  # Offline: retain connection and cached result, retry later.
                if once: return
                for _ in range(30):
                    if (base/'disabled').exists(): return
                    time.sleep(.1)
        finally: journal.db.close()


def pair(base, args):
    config = load_config(base)
    roots = [str(real_storage(Path(p).resolve())) for p in args.root]
    if not roots or any(not Path(p).is_dir() for p in roots): raise ValueError('At least one existing --root directory required')
    caps = sorted(set(args.allow))
    print('Capabilities:', ', '.join(caps) or 'status only')
    print('Terminal and Codex grants may access data with your Windows-user rights; file roots do not sandbox PowerShell.')
    if input('Type ALLOW to request these grants for this PC: ').strip() != 'ALLOW': return
    import getpass
    code = getpass.getpass('Invitation code (not logged): ')
    hosting = getpass.getpass('Sites service authorization, if required (Enter to omit): ')
    local = {'relay_url': args.relay, 'token': secrets.token_hex(32), 'capabilities': caps, 'roots': roots,
             'label': args.label, 'sites_authorization': hosting, 'enabled': False}
    reply = Relay(local).call('pair', code=code, token=local['token'], label=args.label, capabilities=caps)
    ident = reply['connection_id']
    # Save before browser approval so an interrupted setup can be resumed.
    local.update(email=reply['email'], fingerprint=reply['fingerprint'])
    config['connections'][ident] = local; save_config(base, config)
    print('Connection:', ident, '\nFingerprint:', reply['fingerprint'])
    print('Open:', local['relay_url'].rstrip('/')+'/bridge?id='+urllib.parse.quote(ident, safe=''))
    print('Sign in with:', reply['email'], 'Compare the fingerprint and approve, then run activate --connection', ident)


def mcp(base, connection):
    session = secrets.token_hex(12)
    definitions = json.loads((Path(__file__).parent/'phone-tools.json').read_text(encoding='utf-8'))
    definitions += [{'name': 'phone_job_result', 'description': 'Poll an existing phone job; never repeat uncertain commands.', 'inputSchema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}}, 'required': ['job_id']}}]
    for line in sys.stdin:
        ident = None
        try:
            if len(line.encode()) > 256000: raise ValueError('Request too large')
            message = json.loads(line); ident = message.get('id')
            if 'id' not in message: continue
            method = message.get('method')
            if method == 'initialize':
                value = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'Mini Codex paired phone', 'version': VERSION}}
            elif method == 'ping': value = {}
            elif method == 'tools/list': value = {'tools': definitions}
            elif method == 'tools/call':
                local = load_config(base)['connections'][connection]
                if not local.get('enabled'): raise PermissionError('Connection disabled locally')
                params = message.get('params', {})
                value = Relay(local).call('phone_call', tool=params.get('name'), arguments=params.get('arguments', {}), request_id=session+':'+str(ident))
            else: raise ValueError('Unsupported MCP method')
            response = {'jsonrpc': '2.0', 'id': ident, 'result': value}
        except Exception:
            response = {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32603, 'message': 'Phone unavailable or access denied; inspect connection before retrying'}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=storage())
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pair'); p.add_argument('--relay', required=True); p.add_argument('--label', default='My PC')
    p.add_argument('--root', action='append', required=True); p.add_argument('--allow', action='append', choices=sorted(CAPABILITIES), default=[])
    sub.add_parser('connections'); sub.add_parser('stop'); sub.add_parser('start')
    sub.add_parser('run').add_argument('--once', action='store_true')
    for name in ('activate', 'revoke', 'mcp', 'phone-call', 'configure'):
        p = sub.add_parser(name); p.add_argument('--connection', required=True)
        if name == 'phone-call':
            p.add_argument('--tool', required=True); p.add_argument('--arguments', default='{}'); p.add_argument('--request-id', required=True)
        if name == 'configure':
            p.add_argument('--codex-launcher', help='JSON argv of the owner-installed Codex launcher, for example ["codex"]')
            p.add_argument('--disable-cap', action='append', choices=sorted(CAPABILITIES), default=[])
    args = parser.parse_args(); os.umask(0o077)
    base = prepare(args.state)
    if args.command == 'pair': pair(base, args); return
    if args.command == 'run': run(base, args.once); return
    config = load_config(base)
    if args.command == 'connections':
        print(json.dumps([{'connection_id': k, **{p: v.get(p) for p in ('email', 'label', 'enabled', 'capabilities', 'roots')}} for k, v in config['connections'].items()], ensure_ascii=False, indent=2)); return
    if args.command == 'stop': (base/'disabled').touch(); return
    if args.command == 'start':
        (base/'disabled').unlink(missing_ok=True)
        if os.name == 'nt':
            subprocess.run(['schtasks', '/Run', '/TN', 'Codaki Mini Codex PC'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        return
    local = config['connections'][args.connection]
    if args.command == 'activate':
        reply = Relay(local).call('pair_status')
        if reply['status'] != 'active': raise PermissionError('Recipient must sign in and approve first')
        local.update(enabled=True, owner=reply['owner'], inviter=reply['inviter'], phone_access=reply['phone_access'])
        local['capabilities'] = sorted(set(local['capabilities']) & set(reply['capabilities']))
        save_config(base, config); print('Saved and enabled:', args.connection)
    elif args.command == 'configure':
        local['capabilities'] = sorted(set(local['capabilities'])-set(args.disable_cap))
        if args.codex_launcher:
            argv = json.loads(args.codex_launcher)
            if not isinstance(argv, list) or not argv or not all(isinstance(p, str) and p for p in argv): raise ValueError('JSON argv required')
            if 'codex' not in local['capabilities']: raise PermissionError('Codex capability was not approved')
            local['codex_argv'] = argv
        save_config(base, config)
    elif args.command == 'revoke':
        # Disable immediately even when the relay cannot be reached.
        local['enabled'] = False; save_config(base, config)
        Relay(local).call('revoke'); del config['connections'][args.connection]; save_config(base, config)
    elif args.command == 'phone-call':
        if not local.get('enabled'): raise PermissionError('Disabled connection')
        print(json.dumps(Relay(local).call('phone_call', tool=args.tool, arguments=json.loads(args.arguments), request_id=args.request_id), ensure_ascii=False))
    elif args.command == 'mcp': mcp(base, args.connection)


if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: sys.exit(130)
    except Exception as error:
        # Deliberately redact subprocess, network and credential-bearing details.
        print('Mini Codex:', type(error).__name__, '— setup failed; check connection, local permissions and configuration.', file=sys.stderr)
        sys.exit(1)
