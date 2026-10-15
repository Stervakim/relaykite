from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc'))
from development.store import RunStore
from development.supervisor import Supervisor, android_environment, verification_matches


class FixtureRpc:
    instances = []
    sandbox_type = 'workspaceWrite'
    def __init__(self, command, **kwargs):
        self.command = command
        self.callback = kwargs['on_notification']
        self.environment = kwargs.get('env', {})
        self.calls = []
        self.closed = False
        self.__class__.instances.append(self)

    def request(self, method, params=None, timeout=30):
        self.calls.append((method, params))
        if method == 'thread/start' or method == 'thread/resume':
            return {'thread': {'id': 'fixture-thread'}, 'sandbox': {'type': self.__class__.sandbox_type}}
        if method == 'turn/start':
            turn = 'turn-' + str(len(self.calls))
            self.callback('item/completed', {'threadId': 'fixture-thread', 'turnId': turn,
                          'item': {'id': 'cmd', 'type': 'commandExecution', 'command': 'python -m unittest', 'exitCode': 0}})
            self.callback('turn/completed', {'threadId': 'fixture-thread', 'turn': {'id': turn, 'status': 'completed'}})
            return {'turn': {'id': turn}}
        return {}

    def notify(self, *args): pass
    def close(self): self.closed = True


def wait_state(store, ident):
    for _ in range(400):
        run = store.get(ident)
        if run['status'] not in ('queued', 'running', 'recovering'):
            return run
        time.sleep(.02)
    raise AssertionError('Supervisor did not settle')


class SupervisorTests(unittest.TestCase):
    def test_verification_accepts_only_exact_commands_or_known_shell_wrappers(self):
        command = 'python -m unittest discover -s tests'
        self.assertTrue(verification_matches(command, command))
        self.assertTrue(verification_matches('"C:\\\\Program Files\\\\PowerShell\\\\7\\\\pwsh.exe" -Command \'' + command + "'", command))
        self.assertTrue(verification_matches("/bin/bash -lc '" + command + "'", command))
        self.assertFalse(verification_matches("powershell -Command '" + command + "; echo passed'", command))
        self.assertFalse(verification_matches("echo '" + command + "'", command))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.store = RunStore(self.root / 'state')
        self.supervisor = Supervisor(self.store, 'http://127.0.0.1:8768', 'test-provider-token',
                                     command=[sys.executable], rpc_factory=FixtureRpc)
        FixtureRpc.instances.clear()
        FixtureRpc.sandbox_type = 'workspaceWrite'

    def tearDown(self):
        self.supervisor.close()
        self.store.close()
        self.temp.cleanup()

    def test_original_codex_is_configured_with_sandbox_and_local_provider(self):
        run = self.store.create('Fix tests', str(self.workspace), 'start-1', {'verify_command': 'python -m unittest'})
        self.supervisor.start(run['id'])
        result = wait_state(self.store, run['id'])
        self.assertEqual(result['status'], 'completed')
        start = next(p for m, p in FixtureRpc.instances[0].calls if m == 'thread/start')
        self.assertEqual(start['sandbox'], 'workspace-write')
        self.assertEqual(start['approvalPolicy'], 'never')
        self.assertNotIn('mcp_servers',start['config'])
        self.assertEqual(start['config']['model_provider'], 'relaykite-free')
        self.assertIn('/model/' + run['id'], start['config']['model_providers']['relaykite-free']['base_url'])

    def test_child_codex_does_not_inherit_global_plugin_auth_or_configuration(self):
        run = self.store.create('test', str(self.workspace), 'isolated-codex', {'verify_command': 'python -m unittest'})
        self.supervisor.start(run['id'])
        wait_state(self.store, run['id'])
        home = FixtureRpc.instances[0].environment.get('CODEX_HOME')
        self.assertEqual(Path(home), self.root / 'state' / 'codex')

    def test_no_verification_command_never_claims_completion(self):
        run = self.store.create('Change unknown project', str(self.workspace), 'start-2')
        self.supervisor.start(run['id'])
        result = wait_state(self.store, run['id'])
        self.assertEqual(result['status'], 'waiting_user')
        details = [e['data'].get('detail') or '' for e in self.store.events(run['id']) if e['type'] == 'status']
        self.assertTrue(any('провер' in detail.lower() for detail in details))

    def test_cancelled_queue_cannot_start_model_process(self):
        run = self.store.create('Never execute', str(self.workspace), 'start-3')
        self.store.transition(run['id'], 'cancelled')
        self.supervisor.start(run['id'])
        time.sleep(.05)
        self.assertEqual(FixtureRpc.instances, [])

    def test_downgraded_sandbox_stops_before_any_model_turn(self):
        FixtureRpc.sandbox_type = 'readOnly'
        run = self.store.create('Change files', str(self.workspace), 'sandbox-fail')
        self.supervisor.start(run['id'])
        self.assertEqual(wait_state(self.store, run['id'])['status'], 'waiting_user')
        self.assertFalse(any(method == 'turn/start' for method, _ in FixtureRpc.instances[0].calls))

    def test_missing_workspace_does_not_launch_codex(self):
        run = self.store.create('Do something', str(self.root / 'missing'), 'start-4')
        self.supervisor.start(run['id'])
        result = wait_state(self.store, run['id'])
        self.assertEqual(result['status'], 'waiting_user')
        self.assertEqual(FixtureRpc.instances, [])

    def test_android_root_requires_android_and_effective_root(self):
        for android, uid in ((False, 0), (True, 2000), (False, 2000)):
            with self.subTest(android=android, uid=uid), \
                    patch('development.supervisor.android_environment', return_value=android), \
                    patch('development.supervisor.os.geteuid', create=True, return_value=uid):
                with self.assertRaises(ValueError):
                    Supervisor(self.store, 'http://127.0.0.1:1', 'fixture', execution_policy='android-root')

    def test_unknown_policy_never_falls_back_to_another_policy(self):
        with self.assertRaises(ValueError):
            Supervisor(self.store, 'http://127.0.0.1:1', 'fixture', execution_policy='root')

    def test_android_detection_requires_real_executable_and_positive_system_sdk(self):
        with patch('development.supervisor.Path.is_file', return_value=False), \
                patch('development.supervisor.subprocess.run') as command:
            self.assertFalse(android_environment())
            command.assert_not_called()
        for code, output, expected in ((0, '35\n', True), (1, '35', False),
                                       (0, '0', False), (0, 'Android', False), (0, '', False)):
            with self.subTest(code=code, output=output), \
                    patch('development.supervisor.Path.is_file', return_value=True), \
                    patch('development.supervisor.os.access', return_value=True), \
                    patch('development.supervisor.subprocess.run',
                          return_value=subprocess.CompletedProcess([], code, stdout=output)):
                self.assertEqual(android_environment(), expected)

    def test_default_policy_rejects_unexpected_root_permissions(self):
        FixtureRpc.sandbox_type = 'dangerFullAccess'
        run = self.store.create('Edit source', str(self.workspace), 'unexpected-root')
        self.supervisor.start(run['id'])
        self.assertEqual(wait_state(self.store, run['id'])['status'], 'waiting_user')
        self.assertFalse(any(method == 'turn/start' for method, _ in FixtureRpc.instances[0].calls))

    def test_thread_cannot_resume_under_a_different_execution_policy(self):
        run = self.store.create('Resume source changes', str(self.workspace), 'changed-policy')
        self.store.checkpoint(run['id'], {'thread_id': 'old-thread', 'execution_policy': 'android-root'})
        self.supervisor.start(run['id'])
        self.assertEqual(wait_state(self.store, run['id'])['status'], 'waiting_user')
        calls = FixtureRpc.instances[0].calls
        self.assertFalse(any(method in ('thread/resume', 'turn/start') for method, _ in calls))

    def test_explicit_rooted_android_uses_original_codex_root_policy_and_shell(self):
        self.supervisor.close()
        with patch('development.supervisor.android_environment', return_value=True), \
                patch('development.supervisor.os.geteuid', create=True, return_value=0):
            self.supervisor = Supervisor(self.store, 'http://127.0.0.1:8768', 'fixture',
                command=[sys.executable], rpc_factory=FixtureRpc, execution_policy='android-root')
            FixtureRpc.sandbox_type = 'dangerFullAccess'
            run = self.store.create('Inspect this phone', str(self.workspace), 'android-root',
                                    {'verify_command': 'python -m unittest'})
            self.supervisor.start(run['id'])
            self.assertEqual(wait_state(self.store, run['id'])['status'], 'completed')
        rpc = FixtureRpc.instances[0]
        start = next(p for method, p in rpc.calls if method == 'thread/start')
        self.assertEqual(start['sandbox'], 'danger-full-access')
        self.assertEqual(start['config']['sandbox_mode'], 'danger-full-access')
        self.assertEqual(start['config']['model_context_window'], 12000)
        self.assertEqual(start['config']['model_auto_compact_token_limit'], 8000)
        native=start['config']['mcp_servers']['relaykite_android']
        self.assertEqual(native['command'],sys.executable)
        self.assertIn('development.android_mcp',native['args'])
        self.assertIn(run['id'],native['args'])
        self.assertTrue(native['enabled'])
        self.assertIn('sandbox_mode="danger-full-access"', rpc.command)
        prompt = next(p for method, p in rpc.calls if method == 'turn/start')['input'][0]['text']
        self.assertIn('/system/bin/sh', prompt)
        self.assertIn('login=false', prompt)
        started = next(e['data'] for e in self.store.events(run['id']) if e['type'] == 'run.started')
        self.assertEqual(started['execution']['policy'], 'android-root')
        self.assertEqual(started['execution']['isolation'], 'none')
        self.assertTrue(started['execution']['root_access'])

    def test_root_policy_rejects_unconfirmed_native_permissions_before_turn(self):
        self.supervisor.close()
        with patch('development.supervisor.android_environment', return_value=True), \
                patch('development.supervisor.os.geteuid', create=True, return_value=0):
            self.supervisor = Supervisor(self.store, 'http://127.0.0.1:8768', 'fixture',
                command=[sys.executable], rpc_factory=FixtureRpc, execution_policy='android-root')
            FixtureRpc.sandbox_type = 'workspaceWrite'
            run = self.store.create('root task', str(self.workspace), 'android-root-unconfirmed')
            self.supervisor.start(run['id'])
            self.assertEqual(wait_state(self.store, run['id'])['status'], 'waiting_user')
        self.assertFalse(any(method == 'turn/start' for method, _ in FixtureRpc.instances[0].calls))

    def test_root_policy_is_rechecked_if_service_loses_privilege(self):
        self.supervisor.close()
        with patch('development.supervisor.android_environment', return_value=True), \
                patch('development.supervisor.os.geteuid', create=True, return_value=0):
            self.supervisor = Supervisor(self.store, 'http://127.0.0.1:8768', 'fixture',
                command=[sys.executable], rpc_factory=FixtureRpc, execution_policy='android-root')
        with patch('development.supervisor.android_environment', return_value=True), \
                patch('development.supervisor.os.geteuid', create=True, return_value=2000):
            run = self.store.create('root task', str(self.workspace), 'android-root-recheck')
            self.supervisor.start(run['id'])
            self.assertEqual(wait_state(self.store, run['id'])['status'], 'waiting_user')
        self.assertEqual(FixtureRpc.instances, [])


if __name__ == '__main__': unittest.main()
