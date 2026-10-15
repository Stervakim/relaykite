"""Local-only phone entry, scope, schema and trusted execution-mode checks."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
sys.path.insert(0, str(ROOT / 'pc'))
import native_phone
import development_tools
from development import client


class RootOwnedFixturePath(type(Path())):
    """Represent Android private root-owned files, independent of host/umask."""
    fixture_uid = 0
    fixture_permissions = 0o700

    def stat(self, *, follow_symlinks=True):
        values = list(super().stat(follow_symlinks=follow_symlinks))
        values[0] = stat.S_IFMT(values[0]) | self.fixture_permissions
        values[4] = self.fixture_uid
        return os.stat_result(values)

    def lstat(self):
        return self.stat(follow_symlinks=False)


class PhoneDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'private'; self.base.mkdir()
        self.projects = self.root / 'projects'; self.projects.mkdir()
        self.workspace = self.projects / 'task'; self.workspace.mkdir()
        self.policy = self.base / 'development-policy.json'
        self.policy.write_text(json.dumps({'workspace_roots': [str(self.projects)]}), encoding='utf8')
        self.engine = self.base / 'development-engine'
        for directory in ('bin','toolchain/bin','toolchain/lib','toolchain/libexec/git-core','toolchain/share/git-core/templates'):
            (self.engine / directory).mkdir(parents=True, exist_ok=True)
        for name in ('bin/codex','toolchain/bin/git'):
            (self.engine / name).write_text('local test executable', encoding='utf8')
            (self.engine / name).chmod(0o755)
        self.patches = [patch.object(native_phone, 'SUPPORT_BASE', self.base),
                        patch.object(development_tools, 'Path', RootOwnedFixturePath),
                        patch.object(development_tools, 'os', SimpleNamespace(name='posix', environ=os.environ)),
                        patch.object(native_phone, 'runtime_identity', return_value={'mode':'root','uid':0,'root_active':True}),
                        patch('development.supervisor.execution_profile', return_value={'policy':'android-root'})]
        for entry in self.patches: entry.start(); self.addCleanup(entry.stop)

    def test_non_root_or_writable_engine_and_policy_are_rejected_on_android(self):
        android_os = SimpleNamespace(name='posix', environ=os.environ)
        for uid, permissions in [(10001, 0o700), (0, 0o702)]:
            with self.subTest(uid=uid, permissions=permissions), \
                    patch.object(development_tools, 'os', android_os), \
                    patch.multiple(RootOwnedFixturePath, fixture_uid=uid, fixture_permissions=permissions):
                with self.assertRaisesRegex(PermissionError, 'root-owned'):
                    development_tools.engine_environment(self.base)
                with self.assertRaisesRegex(PermissionError, 'root-owned'):
                    development_tools.selected_workspace(self.base, str(self.workspace))

    def call(self, **kwargs):
        function = getattr(native_phone, 'phone_development', None)
        self.assertIsNotNone(function, 'Owner-bound phone development entry is missing')
        return function(**kwargs)

    def test_phone_start_uses_fixed_owner_scope_and_trusted_android_flags(self):
        arguments = {'prompt':'Fix project', 'workspace':str(self.workspace)}
        with patch('development.client.call', return_value={'id':'a'*32}) as call:
            self.call(operation='start', request_id='start-1', arguments=arguments)
        self.assertEqual(call.call_args.args[0], {**arguments,'operation':'start','request_id':'start-1'})
        self.assertEqual(call.call_args.args[1], self.base)
        options = call.call_args.kwargs
        self.assertEqual({key:value for key,value in options.items() if key!='child_env'},
                         {'scope':'phone-owner','execution_policy':'android-root','android_ui':True})
        self.assertEqual(options['child_env']['RELAYKITE_CODEX'], str(self.engine / 'bin/codex'))
        self.assertEqual(options['child_env']['PATH'], str(self.engine / 'toolchain/bin') + ':/system/bin')
        self.assertEqual(options['child_env']['SHELL'], '/system/bin/sh')
        self.assertEqual(options['child_env']['GIT_EXEC_PATH'], str(self.engine / 'toolchain/libexec/git-core'))
        self.assertEqual(options['child_env']['GIT_TEMPLATE_DIR'], str(self.engine / 'toolchain/share/git-core/templates'))
        self.assertNotIn('com.termux', json.dumps(options['child_env']))

    def test_missing_engine_capabilities_returns_setup_state_without_starting_service(self):
        (self.engine / 'bin/codex').unlink()
        with patch('development.client.call') as call:
            result = self.call(operation='capabilities', request_id='setup-1')
        self.assertEqual(result['state'], 'waiting_user')
        self.assertFalse(result['ready'])
        self.assertEqual(result['execution_policy'], 'android-root')
        self.assertEqual(result['isolation'], 'none')
        self.assertIn('development-engine', result['reason'])
        call.assert_not_called()

    def test_install_uses_existing_managed_journal_and_fixed_pinned_command(self):
        with patch.object(native_phone,'phone_command_start',return_value={'terminal_id':'owned'}) as start,patch('development.client.call') as call:
            result=self.call(operation='install',request_id='install:owner.1')
        self.assertEqual(result,{'terminal_id':'owned'})
        self.assertEqual(start.call_args.kwargs['mode'],'root')
        self.assertEqual(start.call_args.kwargs['cwd'],str(self.base))
        self.assertIn('development_install.py',start.call_args.kwargs['command'])
        self.assertTrue(start.call_args.kwargs['command'].endswith(' --install'))
        call.assert_not_called()

    def test_missing_policy_and_workspace_outside_roots_fail_before_service(self):
        with patch('development.client.call') as call:
            for workspace in (str(self.root), 'relative/path'):
                with self.subTest(workspace=workspace), self.assertRaises((ValueError, PermissionError)):
                    self.call(operation='start', request_id='start-1', arguments={'prompt':'Fix', 'workspace':workspace})
            self.policy.unlink()
            with self.assertRaises((ValueError, PermissionError, FileNotFoundError)):
                self.call(operation='start', request_id='start-1', arguments={'prompt':'Fix', 'workspace':str(self.workspace)})
            call.assert_not_called()

    def test_unknown_fields_or_mode_injection_fail_before_service(self):
        with patch('development.client.call') as call:
            for arguments in ({'execution_policy':'workspace-write'}, {'android_ui':False}, {'url':'http://127.0.0.1:9'},
                              {'request_id':'overridden'}, {'limits':{'unknown':True}}, {'run_id':'bad'}):
                with self.subTest(arguments=arguments), self.assertRaises((ValueError, TypeError)):
                    self.call(operation='status', request_id='stable', arguments=arguments)
            call.assert_not_called()

    def test_phone_entry_requires_explicit_root_runtime_and_android(self):
        with patch('development.client.call') as call:
            for identity in ({'mode':'app','uid':0,'root_active':True}, {'mode':'root','uid':2000,'root_active':False},
                             {'mode':'root-termux','uid':0,'root_active':True}):
                with patch.object(native_phone, 'runtime_identity', return_value=identity), self.assertRaises(PermissionError):
                    self.call(operation='capabilities', request_id='probe-1')
            with patch('development.supervisor.execution_profile', side_effect=ValueError('actual Android required')):
                with self.assertRaises(ValueError): self.call(operation='capabilities', request_id='probe-2')
            call.assert_not_called()

    def test_phone_schema_is_identical_in_all_typed_registries(self):
        schemas = []
        for name in ('agent/tool-definitions.json','relay/lib/phone-tools.json','pc/phone-tools.json'):
            values = [tool for tool in json.loads((ROOT / name).read_text('utf8')) if tool['name']=='phone_development']
            self.assertEqual(len(values), 1, name)
            schemas.append(values[0]['inputSchema'])
        self.assertEqual(schemas[0], schemas[1]); self.assertEqual(schemas[0], schemas[2])
        native_phone.validate_schema({'operation':'events','request_id':'cursor-1','arguments':{'run_id':'a'*32,'after':5}}, schemas[0])
        with self.assertRaises(ValueError):
            native_phone.validate_schema({'operation':'start','request_id':'x','arguments':{'endpoint':'bad'}}, schemas[0])

    def test_trusted_service_flags_are_forwarded_and_receipt_modes_checked(self):
        receipt = {'url':'http://127.0.0.1:1','token':'x'*40,'execution_policy':'android-root','android_ui':True}
        with patch.object(client, '_receipt', side_effect=[None, receipt]), patch.object(client, '_request', return_value={}), \
                patch.object(client.subprocess, 'Popen') as popen:
            previous = os.environ.get('RELAYKITE_CODEX')
            trusted = {'RELAYKITE_CODEX': '/owner/engine/codex','PATH':'/owner/engine/bin:/system/bin'}
            result = client.ensure_service(self.base, execution_policy='android-root', android_ui=True, child_env=trusted)
            self.assertEqual(os.environ.get('RELAYKITE_CODEX'), previous)
            self.assertEqual(trusted, {'RELAYKITE_CODEX': '/owner/engine/codex','PATH':'/owner/engine/bin:/system/bin'})
        self.assertEqual(result, receipt)
        command = popen.call_args.args[0]
        self.assertEqual(command[-3:], ['--execution-policy','android-root','--android-ui'])
        self.assertEqual(popen.call_args.kwargs['env']['RELAYKITE_CODEX'], '/owner/engine/codex')
        with patch.object(client, '_receipt', return_value=receipt), patch.object(client, '_request', return_value={}), \
                patch.object(client.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'policy|mode'):
                client.ensure_service(self.base)
            popen.assert_not_called()


if __name__ == '__main__': unittest.main()
