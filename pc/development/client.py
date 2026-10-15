"""Owner-scoped worker adapter; model arguments cannot choose a service URL."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise PermissionError('Local runtime redirects are forbidden')


def _receipt(root):
    file = root / 'service.json'
    if file.is_symlink() or not file.is_file():
        return None
    try:
        value = json.loads(file.read_text('utf-8'))
        url = urllib.parse.urlsplit(value['url'])
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.path or url.query or url.fragment or url.username:
            return None
        if not isinstance(value.get('token'), str) or len(value['token']) < 32:
            return None
        return value
    except (ValueError, KeyError, OSError):
        return None


def _request(receipt, path, payload=None, timeout=45):
    headers = {'Authorization': 'Bearer ' + receipt['token']}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(receipt['url'] + path, data=json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None, headers=headers)
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('Runtime response is too large; use local control room')
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        try:
            value = json.loads(error.read(2048))
            raise ValueError(str(value.get('error', 'Local runtime request failed'))[:500]) from None
        finally:
            error.close()


def _check_mode(receipt, execution_policy, android_ui):
    if (receipt.get('execution_policy', 'workspace-write') != execution_policy
            or receipt.get('android_ui', False) is not android_ui):
        raise ValueError('The existing development service uses a different execution policy or UI mode; stop it explicitly before changing mode')


def ensure_service(root, *, execution_policy='workspace-write', android_ui=False, child_env=None):
    if execution_policy not in ('workspace-write','android-root') or not isinstance(android_ui, bool):
        raise ValueError('Invalid trusted development service mode')
    root = Path(root)
    receipt = _receipt(root)
    if receipt:
        _check_mode(receipt, execution_policy, android_ui)
        try:
            _request(receipt, '/api/health', timeout=2)
            return receipt
        except (OSError, ValueError):
            pass
    root.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'development', 'serve', '--data', str(root), '--port', '0']
    if execution_policy != 'workspace-write':
        command += ['--execution-policy', execution_policy]
    if android_ui:
        command.append('--android-ui')
    environment = os.environ.copy()
    if child_env is not None:
        if not isinstance(child_env, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in child_env.items()):
            raise ValueError('Invalid trusted child environment')
        environment.update(child_env)
    subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[1]), env=environment, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                     start_new_session=os.name != 'nt')
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        receipt = _receipt(root)
        if receipt:
            _check_mode(receipt, execution_policy, android_ui)
            try:
                _request(receipt, '/api/health', timeout=1)
                return receipt
            except (OSError, ValueError):
                pass
        time.sleep(.15)
    raise ValueError('Local development service did not start. Run python -m development serve manually to inspect setup.')


def _bounded(value):
    if isinstance(value, dict) and 'events' in value:
        events = []
        for event in value['events'][:12]:
            event = dict(event)
            raw = json.dumps(event.get('data'), ensure_ascii=False)
            if len(raw) > 1100:
                event['data'] = {'excerpt': raw[:1000], 'truncated': True, 'full_record': 'local_control_room'}
            events.append(event)
        return {'events': events, 'next_cursor': events[-1]['id'] if events else None,
                'has_more': len(value['events']) > len(events)}
    if isinstance(value, dict):
        value = dict(value)
        if isinstance(value.get('prompt'), str) and len(value['prompt']) > 2000:
            value['prompt'] = value['prompt'][:2000] + '…'
        if 'checkpoint' in value and len(json.dumps(value['checkpoint'])) > 6000:
            value['checkpoint'] = {'truncated': True, 'full_record': 'local_control_room'}
        if 'runs' in value:
            value['runs'] = [_bounded(run) for run in value['runs'][:12]]
    return value


def call(arguments, base, *, scope, execution_policy='workspace-write', android_ui=False, child_env=None):
    if not isinstance(scope, str) or not scope:
        raise PermissionError('An authenticated pairing scope is required')
    operation = arguments.get('operation')
    if operation not in ('capabilities', 'start', 'status', 'events', 'artifacts', 'pause', 'resume', 'cancel'):
        raise ValueError('Unsupported development operation')
    root = Path(base) / 'development' / hashlib.sha256(scope.encode('utf-8')).hexdigest()[:24]
    receipt = ensure_service(root, execution_policy=execution_policy, android_ui=android_ui, child_env=child_env)
    if operation == 'capabilities':
        return _request(receipt, '/api/capabilities')
    if operation == 'start':
        payload = {key: arguments[key] for key in ('prompt', 'workspace', 'request_id', 'limits', 'verify_command') if key in arguments}
        return _bounded(_request(receipt, '/api/runs', payload))
    ident = arguments.get('run_id')
    if operation == 'status' and ident is None:
        return _bounded(_request(receipt, '/api/runs'))
    if not isinstance(ident, str) or len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident):
        raise ValueError('A valid run_id is required')
    path = '/api/runs/' + ident
    if operation in ('pause', 'resume', 'cancel'):
        return _bounded(_request(receipt, path + '/' + operation, {}))
    if operation in ('events', 'artifacts'):
        path += '/' + operation
        if operation == 'events':
            cursor = arguments.get('after', 0)
            if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
                raise ValueError('after must be a nonnegative event cursor')
            path += '?after=' + str(cursor)
    return _bounded(_request(receipt, path))
