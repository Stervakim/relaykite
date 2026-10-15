"""Authenticated loopback service: control room, run API and model bridge."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sys
import threading
import urllib.parse

from .app_server import codex_capabilities
from .provider import ProviderBridge, ProviderUnavailable, response_events
from .store import RunStore
from .supervisor import Supervisor, TERMINAL, execution_profile

WEB = Path(__file__).parent / 'web'
MAX_BODY = 8 * 1024 * 1024


class ServiceLock:
    """An OS-owned lifetime lock; a crashed process releases it automatically."""
    def __init__(self, root):
        self.stream = open(Path(root) / 'service.lock', 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if self.stream.seek(0, os.SEEK_END) == 0:
                    self.stream.write(b'\0')
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise RuntimeError('A development service already owns this state directory') from error

    def close(self):
        if self.stream.closed:
            return
        try:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()


def private_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == 'nt':
            # Existing RelayKite helper applies owner-only Windows ACLs.
            from mini_codex_pc import protect
            protect(path)
        else:
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


class DevelopmentServer:
    def __init__(self, root, *, host='127.0.0.1', port=8768, provider=None, supervisor_factory=Supervisor,
                 execution_policy='workspace-write', android_ui=False):
        if host != '127.0.0.1':
            raise ValueError('Development service must bind to IPv4 loopback')
        self.execution_policy = execution_policy
        self.execution = execution_profile(execution_policy)
        if android_ui and not self.execution['android']:
            raise ValueError('The Android UI provider requires an actual Android system')
        if android_ui and provider is not None:
            raise ValueError('Choose either the Android UI provider or an injected provider')
        self.root = Path(root).resolve()
        self.android_ui = android_ui
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            from mini_codex_pc import protect
            protect(self.root)
        else:
            self.root.chmod(0o700)
        # Acquire before opening storage or recovering runs. An ephemeral port is
        # not a singleton: concurrent worker requests may each spawn a service.
        self._ownership = ServiceLock(self.root)
        try:
            self.instance_id = secrets.token_hex(16)
            self.token = secrets.token_urlsafe(32)
            self.provider_token = secrets.token_urlsafe(32)
            self.store = RunStore(self.root)
            if android_ui:
                self.provider = ProviderBridge(self.root, driver_command=[sys.executable, '-m', 'development.android_ui',
                    '--state', str(self.root / 'provider' / 'android-ui')])
            else:
                self.provider = provider if provider is not None else ProviderBridge(self.root)
            self.codex = codex_capabilities()
            self.http = ThreadingHTTPServer((host, port), Handler)
            self.http.daemon_threads = True
            self.http.service = self
            self.url = f'http://127.0.0.1:{self.http.server_port}'
            supervisor_options = {'execution_policy': execution_policy} if execution_policy != 'workspace-write' else {}
            self.supervisor = supervisor_factory(self.store, self.url, self.provider_token, **supervisor_options)
        except BaseException:
            if hasattr(self, 'http'):
                self.http.server_close()
            if hasattr(self, 'store'):
                self.store.close()
            self._ownership.close()
            raise
        self._model_lock = threading.RLock()
        self._cancel_events = {}
        self._thread = None
        self._closed = False

    def capabilities(self):
        return {'name': 'RelayKite Development', 'version': '0.1.0', 'codex': self.codex,
                'provider': self.provider.capabilities(), 'live_free_verified': False,
                'execution': dict(self.execution),
                'sandbox': {'policy': self.execution['codex_sandbox'],
                            'enforced_by': None if self.execution['root_access'] else 'codex',
                            'verified_on_this_device': False},
                'max_concurrent_runs': 1, 'context': {'strategy': 'codex-text-compaction-and-checkpoints', 'token_estimate': 'approximate'},
                'computer_use': {'relaykite_backend': True, 'bundled_openai_plugin_verified': False}}

    def start(self):
        if self._thread:
            return self
        try:
            self.store.recover()
            private_json(self.root / 'service.json', {'url': self.url, 'token': self.token, 'pid': os.getpid(),
                                                      'instance_id': self.instance_id, 'version': '0.1.0',
                                                      'android_ui': self.android_ui,
                                                      'execution_policy': self.execution_policy,
                                                      'execution': self.execution})
            self._thread = threading.Thread(target=self.http.serve_forever, kwargs={'poll_interval': .1}, daemon=True, name='relaykite-http')
            self._thread.start()
            for run in self.store.list_runs():
                if run['status'] == 'queued':
                    self.supervisor.start(run['id'])
        except BaseException:
            self.close()
            raise
        return self

    def control_run(self, ident, operation):
        with self._model_lock:
            if self.store.get(ident)['status'] in TERMINAL:
                return self.store.get(ident)
            if operation in ('pause', 'cancel'):
                # The event closes the acceptance-to-Popen gap. The provider
                # checks it under the same lock used to register process ownership.
                self._cancel_events.setdefault(ident, threading.Event()).set()
                self.provider.cancel_active(run_id=ident)
            result = self.supervisor.control(ident, operation)
            if operation == 'resume':
                # Old HTTP requests retain their cancelled epoch, even if they
                # finish after this run has explicitly resumed.
                self._cancel_events[ident] = threading.Event()
            return result

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            with self._model_lock:
                for event in self._cancel_events.values():
                    event.set()
            if hasattr(self.provider, 'cancel_active'):
                self.provider.cancel_active()
            self.supervisor.close()
            if self._thread and self._thread.is_alive():
                self.http.shutdown()
                self._thread.join(timeout=3)
            self.http.server_close()
            self.store.close()
            receipt = self.root / 'service.json'
            try:
                if json.loads(receipt.read_text('utf-8')).get('instance_id') == self.instance_id:
                    receipt.unlink()
            except (OSError, ValueError):
                pass
        finally:
            self._ownership.close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'RelayKite'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass  # Never log tokens, prompts or model payloads.

    def setup(self):
        super().setup()
        self.connection.settimeout(650)

    @property
    def service(self):
        return self.server.service

    def _send(self, code, value, content_type='application/json; charset=utf-8', filename=None):
        if not isinstance(value, bytes):
            value = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(value)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if filename:
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(filename))
        self.end_headers()
        try:
            self.wfile.write(value)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authorized(self, provider=False):
        expected = self.service.provider_token if provider else self.service.token
        supplied = self.headers.get('Authorization', '')
        return secrets.compare_digest(supplied.encode(), ('Bearer ' + expected).encode())

    def _check_host(self):
        allowed = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
        if self.headers.get('Host') not in allowed:
            raise PermissionError('Invalid local Host header')
        origin = self.headers.get('Origin')
        if origin and origin not in (self.service.url, 'http://localhost:' + str(self.server.server_port)):
            raise PermissionError('Cross-origin access is not allowed')

    def _body(self):
        size = int(self.headers.get('Content-Length', '-1'))
        if not 0 <= size <= MAX_BODY:
            raise ValueError('Request body is missing or exceeds 8 MiB')
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Content-Type application/json is required')
        body = json.loads(self.rfile.read(size), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid JSON constant')))
        if not isinstance(body, dict):
            raise ValueError('Request must be a JSON object')
        return body

    def do_GET(self):
        self._dispatch(False)

    def do_POST(self):
        self._dispatch(True)

    def _dispatch(self, post):
        try:
            self._check_host()
            parsed = urllib.parse.urlsplit(self.path)
            parts = [urllib.parse.unquote(s) for s in parsed.path.split('/') if s]
            provider = parts[:1] == ['model']
            if parsed.path.startswith('/api/') or provider:
                if not self._authorized(provider):
                    self._send(401, {'error': 'Local bearer token required'})
                    return
                if provider:
                    self._model(parts, self._body() if post else None)
                    return
                self._api(parts, urllib.parse.parse_qs(parsed.query), self._body() if post else None, post)
                return
            if post:
                self._send(405, {'error': 'Method not allowed'})
                return
            filename = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css'}.get(parsed.path)
            if not filename:
                self._send(404, {'error': 'Not found'})
                return
            path = WEB / filename
            self._send(200, path.read_bytes(), mimetypes.guess_type(filename)[0] + '; charset=utf-8')
        except PermissionError as error:
            self._send(403, {'error': str(error)})
        except (KeyError, FileNotFoundError):
            self._send(404, {'error': 'Run or artifact not found'})
        except (ValueError, TypeError) as error:
            self._send(400, {'error': str(error)[:500]})
        except (OSError, RuntimeError):
            self._send(503, {'error': 'Local runtime unavailable; inspect the run journal'})

    def _api(self, parts, query, body, post):
        service = self.service
        if parts == ['api', 'health'] and not post:
            self._send(200, {'name': 'RelayKite Development', 'pid': os.getpid(), 'version': '0.1.0'})
        elif parts == ['api', 'capabilities'] and not post:
            self._send(200, service.capabilities())
        elif parts == ['api', 'runs']:
            if not post:
                self._send(200, {'runs': service.store.list_runs()})
                return
            prompt = body.get('prompt')
            workspace = body.get('workspace')
            if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 32000:
                raise ValueError('Prompt must contain 1–32000 characters')
            if not isinstance(workspace, str) or not Path(workspace).is_absolute() or not Path(workspace).is_dir():
                raise ValueError('An existing absolute workspace path is required')
            limits = body.get('limits') or {}
            if not isinstance(limits, dict):
                raise ValueError('limits must be an object')
            limits = dict(limits)
            for key, default, maximum in [('max_steps', 100, 10000), ('max_seconds', 3600, 86400), ('max_turns', 8, 100)]:
                value = limits.get(key, default)
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                    raise ValueError('Invalid budget: ' + key)
                limits[key] = value
            verify = body.get('verify_command', limits.get('verify_command'))
            if verify is not None:
                if not isinstance(verify, str) or len(verify) > 4096 or '\x00' in verify or '\n' in verify or '\r' in verify:
                    raise ValueError('verify_command must be one command of at most 4096 characters')
                limits['verify_command'] = verify.strip()
            if body.get('mode', 'live') != 'live':
                raise ValueError('Only live Codex mode is exposed by this service')
            run = service.store.create(prompt.strip(), str(Path(workspace).resolve()), body.get('request_id'), limits, 'live')
            service.supervisor.start(run['id'])
            self._send(200, service.store.get(run['id']))
        elif len(parts) >= 3 and parts[:2] == ['api', 'runs']:
            ident = parts[2]
            if len(parts) == 3 and not post:
                self._send(200, service.store.get(ident))
            elif len(parts) == 4 and parts[3] == 'events' and not post:
                self._send(200, {'events': service.store.events(ident, after=int(query.get('after', ['0'])[0]))})
            elif len(parts) == 4 and parts[3] == 'artifacts' and not post:
                self._send(200, {'artifacts': service.store.artifacts(ident)})
            elif len(parts) == 5 and parts[3] == 'artifact' and not post:
                artifact = service.store.artifact_path(ident, parts[4])
                self._send(200, artifact.read_bytes(), 'application/octet-stream', parts[4])
            elif len(parts) == 4 and parts[3] in ('pause', 'resume', 'cancel') and post:
                self._send(200, service.control_run(ident, parts[3]))
            else:
                self._send(404, {'error': 'Unknown run operation'})
        else:
            self._send(404, {'error': 'Unknown API route'})

    def _model(self, parts, body):
        if len(parts) != 4 or parts[2:] != ['v1', 'responses']:
            self._send(404, {'error': {'message': 'Unsupported model endpoint'}})
            return
        if body is None:
            self._send(405, {'error': {'message': 'POST required'}})
            return
        ident = parts[1]
        with self.service._model_lock:
            run = self.service.store.get(ident)
            if self.service._closed or run['status'] in TERMINAL | {'paused', 'uncertain', 'waiting_model', 'waiting_user'}:
                self._send(409, {'error': {'message': 'Run is not accepting model requests', 'type': 'run_stopped'}})
                return
            cancel_event = self.service._cancel_events.setdefault(ident, threading.Event())
            self.service.store.append_event(ident, 'model.requested', {'transport': 'chatgpt-free-ui'})
        try:
            response = self.service.provider.generate(body, run_id=ident, cancel_event=cancel_event)
            with self.service._model_lock:
                if cancel_event.is_set():
                    self._send(409, {'error': {'message': 'Model request was cancelled', 'type': 'run_stopped'}})
                    return
                self.service.store.append_event(ident, 'model.completed', {'response_id': response.get('id'), 'transport': 'chatgpt-free-ui'})
            if body.get('stream'):
                raw = ''.join('data: ' + json.dumps(event, ensure_ascii=False) + '\n\n' for event in response_events(response)) + 'data: [DONE]\n\n'
                self._send(200, raw.encode('utf-8'), 'text/event-stream; charset=utf-8')
            else:
                self._send(200, response)
        except ProviderUnavailable as error:
            state = error.state if error.state in ('waiting_model', 'waiting_user', 'uncertain') else 'waiting_user'
            with self.service._model_lock:
                if not cancel_event.is_set() and not self.service._closed:
                    current = self.service.store.get(ident)['status']
                    if current not in TERMINAL | {'paused'}:
                        self.service.store.transition(ident, state, str(error.reason)[:1000])
            self._send(503, {'error': {'message': str(error.reason)[:1000], 'type': state}})
