"""Regression coverage for service lifetime, cancellation and final verification."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc'))
from development.server import DevelopmentServer
from development.provider import ProviderBridge, ProviderUnavailable
from development.store import RunStore
from development.supervisor import Supervisor
from development import client


class IdleSupervisor:
    def __init__(self, store, *args): self.store = store
    def start(self, ident): return self.store.get(ident)
    def control(self, ident, operation):
        return self.store.transition(ident, {'pause': 'paused', 'resume': 'running', 'cancel': 'cancelled'}[operation])
    def close(self): pass


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def service(self, provider=None):
        value = DevelopmentServer(self.root / 'state', port=0, provider=provider,
                                  supervisor_factory=IdleSupervisor).start()
        self.addCleanup(value.close)
        return value

    def request(self, service, path, payload, *, provider=False):
        token = service.provider_token if provider else service.token
        request = urllib.request.Request(service.url + path, json.dumps(payload).encode(),
                                        {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.load(response)

    def test_second_service_cannot_recover_or_replace_live_owner(self):
        first = self.service()
        run = first.store.create('active task', str(self.root), 'active')
        first.store.transition(run['id'], 'running')
        receipt = (first.root / 'service.json').read_bytes()
        second = None
        try:
            with self.assertRaisesRegex(RuntimeError, 'already'):
                second = DevelopmentServer(first.root, port=0, supervisor_factory=IdleSupervisor)
                second.start()
            self.assertEqual(first.store.get(run['id'])['status'], 'running')
            self.assertEqual((first.root / 'service.json').read_bytes(), receipt)
        finally:
            if second: second.close()

    def test_lifetime_lock_excludes_another_process_and_releases_on_close(self):
        first = self.service()
        script = ("import sys; from development.server import DevelopmentServer\n"
                  "try:\n s=DevelopmentServer(sys.argv[1],port=0)\n"
                  "except RuntimeError:\n print('locked')\n"
                  "else:\n s.close(); print('acquired')\n")
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'pc'))
        command = [sys.executable, '-c', script, str(first.root)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'locked')
        first.close()
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'acquired')

    def test_close_does_not_remove_receipt_with_same_pid_different_instance(self):
        first = self.service()
        receipt = first.root / 'service.json'
        value = json.loads(receipt.read_text('utf8'))
        value['instance_id'] = 'replacement-instance'
        receipt.write_text(json.dumps(value), encoding='utf8')
        first.close()
        self.assertTrue(receipt.exists())

    def test_simultaneous_clients_attach_to_one_lifetime_owner(self):
        original = subprocess.Popen
        barrier = threading.Barrier(2)
        children, receipts, errors = [], [], []
        def launch(*args, **kwargs):
            barrier.wait(5)
            child = original(*args, **kwargs)
            children.append(child)
            return child
        def ensure():
            try: receipts.append(client.ensure_service(self.root / 'concurrent'))
            except Exception as error: errors.append(error)
        try:
            with patch('development.client.subprocess.Popen', side_effect=launch):
                threads = [threading.Thread(target=ensure) for _ in range(2)]
                for thread in threads: thread.start()
                for thread in threads: thread.join(18)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            self.assertEqual(len(receipts), 2)
            self.assertEqual(receipts[0]['instance_id'], receipts[1]['instance_id'])
            deadline = time.monotonic() + 4
            while sum(child.poll() is None for child in children) > 1 and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(sum(child.poll() is None for child in children), 1)
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)

    def bridge(self, delay=20):
        script = self.root / 'driver.py'
        script.write_text("import json,sys,time\njson.load(sys.stdin)\n"
                          f"time.sleep({delay})\n"
                          f"open({str(self.root / 'sent')!r},'w').write('sent')\n"
                          "print(json.dumps({'status':'completed','text':json.dumps({'output':[{'type':'message','text':'ok'}]})}))\n", encoding='utf8')
        return ProviderBridge(self.root, [sys.executable, str(script)])

    def test_cancelling_resumed_queue_preserves_another_runs_driver(self):
        provider = self.bridge()
        service = self.service(provider)
        a = service.store.create('active', str(self.root), 'a')
        b = service.store.create('queue', str(self.root), 'b')
        service.store.transition(a['id'], 'running')
        errors = []
        def model():
            try: self.request(service, '/model/' + a['id'] + '/v1/responses', {'input': 'A'}, provider=True)
            except urllib.error.HTTPError as error: errors.append(error.code); error.close()
        thread = threading.Thread(target=model)
        thread.start()
        self.addCleanup(thread.join, 8)
        deadline = time.monotonic() + 3
        while provider._active_process is None and time.monotonic() < deadline: time.sleep(.01)
        process = provider._active_process
        self.assertIsNotNone(process)
        try:
            for operation in ('pause', 'resume', 'cancel'):
                self.request(service, '/api/runs/' + b['id'] + '/' + operation, {})
            self.assertIsNone(process.poll(), 'Cancelling B killed the active driver owned by A')
        finally:
            self.request(service, '/api/runs/' + a['id'] + '/cancel', {})
            thread.join(5)
        self.assertFalse(thread.is_alive())

    def test_cancel_between_model_acceptance_and_process_start_prevents_send(self):
        provider = self.bridge(delay=0)
        service = self.service(provider)
        run = service.store.create('race', str(self.root), 'race')
        service.store.transition(run['id'], 'running')
        accepted, release = threading.Event(), threading.Event()
        original = provider._driver
        def delayed(*args, **kwargs):
            accepted.set(); release.wait(5)
            return original(*args, **kwargs)
        errors = []
        def model():
            try: self.request(service, '/model/' + run['id'] + '/v1/responses', {'input': 'race'}, provider=True)
            except urllib.error.HTTPError as error: errors.append(error.code); error.close()
        with patch.object(provider, '_driver', side_effect=delayed):
            thread = threading.Thread(target=model); thread.start()
            try:
                self.assertTrue(accepted.wait(3))
                self.request(service, '/api/runs/' + run['id'] + '/cancel', {})
            finally:
                release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse((self.root / 'sent').exists(), 'Cancelled request still started the browser driver')
        self.assertEqual(service.store.get(run['id'])['status'], 'cancelled')

    def test_resuming_does_not_revive_an_earlier_cancelled_request_epoch(self):
        provider = self.bridge(delay=0)
        service = self.service(provider)
        run = service.store.create('resume race', str(self.root), 'resume-race')
        service.store.transition(run['id'], 'running')
        accepted, release = threading.Event(), threading.Event()
        original = provider._driver
        def delayed(*args, **kwargs):
            accepted.set(); release.wait(5)
            return original(*args, **kwargs)
        def model():
            try: self.request(service, '/model/' + run['id'] + '/v1/responses', {'input': 'old epoch'}, provider=True)
            except urllib.error.HTTPError as error: error.close()
        with patch.object(provider, '_driver', side_effect=delayed):
            thread = threading.Thread(target=model); thread.start()
            try:
                self.assertTrue(accepted.wait(3))
                for operation in ('pause', 'resume'):
                    self.request(service, '/api/runs/' + run['id'] + '/' + operation, {})
            finally:
                release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse((self.root / 'sent').exists())
        self.assertEqual(service.store.get(run['id'])['status'], 'running')
        self.assertEqual(self.request(service, '/model/' + run['id'] + '/v1/responses', {'input': 'fresh epoch'}, provider=True)['status'], 'completed')

    def test_successful_verification_is_invalidated_by_later_effectful_tool(self):
        for kind in ('commandExecution', 'mcpToolCall', 'dynamicToolCall', 'fileChange'):
            with self.subTest(kind=kind):
                class Rpc:
                    def __init__(self, *args, **kwargs): self.callback = kwargs['on_notification']
                    def close(self): pass
                    def notify(self, *args): pass
                    def request(self, method, params=None, timeout=30):
                        if method in ('thread/start', 'thread/resume'):
                            return {'thread': {'id': 't'}, 'sandbox': {'type': 'workspaceWrite'}}
                        if method == 'turn/start':
                            for item in ({'type': 'commandExecution', 'command': 'python -m unittest', 'exitCode': 0},
                                         {'type': kind, 'command': 'edit source', 'exitCode': 0}):
                                self.callback('item/completed', {'item': item})
                            self.callback('turn/completed', {'turn': {'id': 'u', 'status': 'completed'}})
                            return {'turn': {'id': 'u'}}
                        return {}
                store = RunStore(self.root / kind)
                supervisor = Supervisor(store, 'http://127.0.0.1:1', 'token', command=['fixture'], rpc_factory=Rpc)
                try:
                    run = store.create('change', str(self.root), kind, {'verify_command': 'python -m unittest', 'max_turns': 1})
                    supervisor.start(run['id'])
                    deadline = time.monotonic() + 3
                    while store.get(run['id'])['status'] in ('running', 'queued') and time.monotonic() < deadline: time.sleep(.01)
                    self.assertEqual(store.get(run['id'])['status'], 'paused')
                    self.assertNotIn('verification.json', [a['name'] for a in store.artifacts(run['id'])])
                finally:
                    supervisor.close(); store.close()


if __name__ == '__main__': unittest.main()
