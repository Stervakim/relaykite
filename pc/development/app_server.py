"""Bounded JSON-RPC transport for the original Codex app-server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time


class RpcError(RuntimeError):
    pass


def discover_codex():
    """Resolve npm's Windows shim without interpolating a shell command."""
    candidate = os.environ.get('RELAYKITE_CODEX') or shutil.which('codex')
    if not candidate:
        return None
    path = Path(candidate).resolve()
    if path.suffix.lower() in ('.cmd', '.ps1'):
        script = path.parent / 'node_modules' / '@openai' / 'codex' / 'bin' / 'codex.js'
        node = shutil.which('node')
        return [str(Path(node).resolve()), str(script)] if node and script.is_file() else None
    return [str(path)] if path.is_file() else None


def codex_capabilities():
    command = discover_codex()
    if not command:
        return {'available': False, 'reason': 'Codex CLI is not installed; see setup instructions.'}
    try:
        result = subprocess.run(command + ['--version'], capture_output=True, timeout=8,
                                text=True, encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return {'available': result.returncode == 0, 'version': result.stdout.strip()[:120]}
    except (OSError, subprocess.TimeoutExpired):
        return {'available': False, 'reason': 'Codex CLI could not start.'}


class JsonRpcClient:
    def __init__(self, command, *, cwd=None, env=None, on_notification=None, on_request=None,
                 max_message=4 * 1024 * 1024):
        if not isinstance(command, list) or not command:
            raise ValueError('An explicit executable argument vector is required')
        self.max_message = max_message
        self.on_notification = on_notification or (lambda method, params: None)
        self.on_request = on_request
        self._lock = threading.RLock()
        self._pending = {}
        self._counter = 0
        self._closed = False
        self._failure = None
        self.stderr = bytearray()
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                        start_new_session=os.name != 'nt')
        self._reader = threading.Thread(target=self._read, daemon=True, name='codex-rpc-reader')
        self._drainer = threading.Thread(target=self._drain, daemon=True, name='codex-stderr')
        self._reader.start()
        self._drainer.start()

    def _write(self, value):
        raw = (json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        if len(raw) > self.max_message:
            raise RpcError('Codex request exceeds message limit')
        with self._lock:
            if self._closed or self._failure:
                raise RpcError(self._failure or 'Codex transport is closed')
            try:
                self.process.stdin.write(raw)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as error:
                raise RpcError('Codex transport disconnected') from error

    def request(self, method, params=None, timeout=30):
        with self._lock:
            if self._closed or self._failure:
                raise RpcError(self._failure or 'Codex transport is closed')
            self._counter += 1
            ident = self._counter
            inbox = self._pending[ident] = queue.Queue(maxsize=1)
        try:
            self._write({'id': ident, 'method': method, 'params': params or {}})
            try:
                response = inbox.get(timeout=timeout)
            except queue.Empty as error:
                raise TimeoutError('Codex request deadline exceeded: ' + method) from error
            if isinstance(response, Exception):
                raise response
            if 'error' in response:
                raise RpcError(str(response['error'].get('message', 'Codex request failed'))[:500])
            return response.get('result', {})
        finally:
            with self._lock:
                self._pending.pop(ident, None)

    def notify(self, method, params=None):
        self._write({'method': method, 'params': params or {}})

    def _fail(self, message):
        with self._lock:
            self._failure = message
            for inbox in self._pending.values():
                if inbox.empty():
                    inbox.put_nowait(RpcError(message))

    def _read(self):
        try:
            while True:
                raw = self.process.stdout.readline(self.max_message + 1)
                if not raw:
                    break
                if len(raw) > self.max_message:
                    raise ValueError('Codex response exceeds message limit')
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise ValueError('Invalid Codex RPC frame')
                if 'method' in message:
                    if 'id' in message:
                        self._answer(message)
                    else:
                        try:
                            self.on_notification(message['method'], message.get('params', {}))
                        except Exception:
                            self._fail('Codex event could not be persisted')
                            break
                else:
                    with self._lock:
                        inbox = self._pending.get(message.get('id'))
                        if inbox is not None and inbox.empty():
                            inbox.put_nowait(message)
        except (OSError, ValueError, UnicodeError) as error:
            self._fail(str(error)[:200])
        finally:
            self._fail('Codex app-server exited or disconnected')

    def _answer(self, message):
        method = message['method']
        if self.on_request:
            result = self.on_request(method, message.get('params', {}))
            self._write({'id': message['id'], 'result': result})
        elif method.endswith('/requestApproval'):
            self._write({'id': message['id'], 'result': {'decision': 'decline'}})
        else:
            self._write({'id': message['id'], 'error': {'code': -32601, 'message': 'This host does not support the requested interaction'}})

    def _drain(self):
        while True:
            raw = self.process.stderr.read(1024)
            if not raw:
                break
            self.stderr.extend(raw)
            if len(self.stderr) > 8192:
                del self.stderr[:-8192]

    def close(self):
        with self._lock:
            if self._closed:
                return
        if self.process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            else:
                import signal
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        with self._lock:
            self._closed = True
        self._fail('Codex transport closed')
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except OSError:
                pass
