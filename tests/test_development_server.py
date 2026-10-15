import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc'))
from development.server import DevelopmentServer


class FixtureProvider:
    def capabilities(self): return {'ready': False, 'reason': 'Fixture: live Free not verified'}
    def cancel_active(self, run_id=None): pass
    def generate(self, request, **kwargs):
        return {'id': 'resp_fixture', 'object': 'response', 'status': 'completed', 'model': 'chatgpt-free',
                'output': [{'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'status': 'completed',
                            'content': [{'type': 'output_text', 'text': 'fixture result', 'annotations': []}]}]}


class FixtureSupervisor:
    def __init__(self, store, *args, **kwargs):
        self.store = store
        self.execution_policy = kwargs.get('execution_policy', 'workspace-write')
    def start(self, ident): return self.store.get(ident)
    def control(self, ident, op): return self.store.transition(ident, {'pause': 'paused', 'cancel': 'cancelled', 'resume': 'running'}[op])
    def close(self): pass


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = DevelopmentServer(self.root / 'state', port=0, provider=FixtureProvider(), supervisor_factory=FixtureSupervisor)
        self.service.start()

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def call(self, path, payload=None, token=True, headers=None):
        options = dict(headers or {})
        if token: options['Authorization'] = 'Bearer ' + self.service.token
        if payload is not None: options['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.service.url + path, json.dumps(payload).encode() if payload is not None else None, options)
        return urllib.request.urlopen(request, timeout=5)

    def test_controls_require_bearer_even_with_token_in_query(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call('/api/runs?token=' + self.service.token, token=False)
        self.assertEqual(error.exception.code, 401)
        error.exception.close()

    def test_create_persists_and_reuses_request_id(self):
        payload = {'prompt': 'Fix <script>alert(1)</script>', 'workspace': str(self.root), 'request_id': 'http-idempotent', 'limits': {'max_steps': 20}}
        with self.call('/api/runs', payload) as response: first = json.load(response)
        with self.call('/api/runs', payload) as response: second = json.load(response)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.service.store.list_runs()), 1)
        self.assertIn('<script>', self.service.store.get(first['id'])['prompt'])

    def test_cross_origin_control_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call('/api/runs', {}, headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_capabilities_never_expose_tokens(self):
        with self.call('/api/capabilities') as response:
            raw = response.read().decode()
        self.assertNotIn(self.service.token, raw)
        self.assertNotIn(self.service.provider_token, raw)
        self.assertIn('live_free_verified', raw)

    def test_default_capabilities_and_receipt_keep_workspace_isolation(self):
        caps = self.service.capabilities()
        self.assertEqual(caps['sandbox']['policy'], 'workspace-write')
        self.assertEqual(caps['execution']['policy'], 'workspace-write')
        self.assertFalse(caps['execution']['root_access'])
        receipt = json.loads((self.service.root / 'service.json').read_text('utf-8'))
        self.assertEqual(receipt['execution_policy'], 'workspace-write')

    def test_root_policy_is_rejected_on_non_android_before_start(self):
        with patch('development.supervisor.android_environment', return_value=False), \
                patch('development.supervisor.os.geteuid', create=True, return_value=0):
            with self.assertRaises(ValueError):
                DevelopmentServer(self.root / 'invalid-root', port=0, execution_policy='android-root')
        self.assertFalse((self.root / 'invalid-root').exists())

    def test_root_service_and_process_receipt_report_no_sandbox_isolation(self):
        with patch('development.supervisor.android_environment', return_value=True), \
                patch('development.supervisor.os.geteuid', create=True, return_value=0):
            service = DevelopmentServer(self.root / 'android', port=0, provider=FixtureProvider(),
                                        supervisor_factory=FixtureSupervisor, execution_policy='android-root')
            try:
                service.start()
                caps = service.capabilities()
                self.assertEqual(caps['execution']['policy'], 'android-root')
                self.assertEqual(caps['execution']['isolation'], 'none')
                self.assertTrue(caps['execution']['root_access'])
                self.assertEqual(caps['sandbox']['policy'], 'danger-full-access')
                self.assertIsNone(caps['sandbox']['enforced_by'])
                self.assertEqual(service.supervisor.execution_policy, 'android-root')
                receipt = json.loads((service.root / 'service.json').read_text('utf-8'))
                self.assertEqual(receipt['execution_policy'], 'android-root')
                self.assertEqual(receipt['execution']['isolation'], 'none')
            finally:
                service.close()

    def test_android_ui_chooses_explicit_portable_python_provider(self):
        with patch('development.supervisor.android_environment', return_value=True), \
                patch('development.supervisor.os.geteuid', create=True, return_value=0), \
                patch('development.server.ProviderBridge') as factory:
            service = DevelopmentServer(self.root / 'android-ui', port=0,
                supervisor_factory=FixtureSupervisor, execution_policy='android-root', android_ui=True)
            try:
                factory.assert_called_once_with(service.root,
                    driver_command=[sys.executable, '-m', 'development.android_ui',
                                    '--state', str(service.root / 'provider' / 'android-ui')])
            finally:
                service.close()

    def test_artifact_download_stays_inside_run(self):
        run = self.service.store.create('test', str(self.root), 'artifact-run')
        self.service.store.artifact(run['id'], 'result.txt', 'owner result')
        with self.call('/api/runs/' + run['id'] + '/artifact/result.txt') as response:
            self.assertEqual(response.read(), b'owner result')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call('/api/runs/' + run['id'] + '/artifact/..%2Fservice.json')
        self.assertIn(error.exception.code, (400, 404))
        error.exception.close()

    def test_provider_requires_separate_token_and_emits_canonical_sse(self):
        run = self.service.store.create('test', str(self.root), 'model-run')
        path = '/model/' + run['id'] + '/v1/responses'
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call(path, {'input': [], 'stream': True})
        self.assertEqual(error.exception.code, 401)
        error.exception.close()
        with self.call(path, {'input': [], 'stream': True}, token=False,
                       headers={'Authorization': 'Bearer ' + self.service.provider_token}) as response:
            raw = response.read().decode()
        self.assertIn('response.completed', raw)
        self.assertIn('fixture result', raw)


if __name__ == '__main__': unittest.main()
