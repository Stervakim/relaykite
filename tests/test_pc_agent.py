import importlib.util
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mini_pc_test', ROOT/'pc/mini_codex_pc.py')
pc = importlib.util.module_from_spec(spec); spec.loader.exec_module(pc)


class PCTests(unittest.TestCase):
    def test_optional_model_start_failure_does_not_stop_pc_queue(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);journal=Mock()
            with patch.dict(sys.modules,{'model_runtime':Mock(ensure=Mock(side_effect=OSError('model unavailable')))}),patch.object(pc,'InstanceLock'),patch.object(pc,'Journal',return_value=journal),patch.object(pc,'load_config',return_value={'connections':{}}) as load:
                pc.run(base,once=True)
            load.assert_called_once();journal.db.close.assert_called_once()
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.base = self.root/'private'; self.base.mkdir()
        self.workspace = self.root/'workspace'; self.workspace.mkdir()
        self.config = {'capabilities': ['files_read', 'files_write'], 'roots': [str(self.workspace)]}
    def tearDown(self): self.temp.cleanup()

    def job(self):
        return {'id': '12345678-1234-1234-1234-123456789abc', 'tool': 'pc_write_file',
                'arguments': {'path': str(self.workspace/'note.txt'), 'text': 'one'}, 'expires_at': int(time.time())+120}

    def test_no_phone_required_and_ungranted_terminal_refused(self):
        value = pc.execute('pc_status', {}, self.config, self.base)
        self.assertIn('client_tools', str(value))
        with patch.object(pc, 'bounded_process') as process:
            with self.assertRaises(PermissionError): pc.execute('pc_terminal', {'command': 'anything'}, self.config, self.base)
            process.assert_not_called()

    def test_file_roots_and_private_storage_are_enforced(self):
        for path in (self.root/'outside', self.base/'config.json', self.workspace/'..'/'outside'):
            with self.subTest(path=path), self.assertRaises(PermissionError):
                pc.execute('pc_write_file', {'path': str(path), 'text': 'bad'}, self.config, self.base)
        self.assertFalse((self.root/'outside').exists())
        with self.assertRaises(ValueError): pc.allowed_path('relative.txt', self.config, self.base)

    def test_existing_file_is_backed_up_before_write(self):
        path = self.workspace/'note.txt'; path.write_text('original')
        pc.execute('pc_write_file', {'path': str(path), 'text': 'new'}, self.config, self.base)
        self.assertEqual(path.read_text(), 'new')
        self.assertEqual(next((self.base/'backups').glob('*.txt')).read_text(), 'original')

    def test_terminal_default_cwd_can_contain_private_storage_without_exposing_it_to_file_tools(self):
        config = {'capabilities': ['terminal', 'files_read'], 'roots': [str(self.root)]}
        with patch.object(pc.shutil, 'which', return_value='powershell'), patch.object(pc, 'bounded_process', return_value={'exit_code': 0}) as process:
            self.assertEqual(pc.execute('pc_terminal', {'command': 'Get-Date'}, config, self.base)['exit_code'], 0)
            self.assertEqual(process.call_args.args[1], self.root)
        for path in (self.root, self.base, self.base/'config.json'):
            with self.subTest(path=path), self.assertRaises(PermissionError):
                pc.execute('pc_list_files', {'path': str(path)}, config, self.base)

    def test_duplicate_delivery_never_repeats_side_effect(self):
        journal = pc.Journal(self.base)
        try:
            job = self.job(); journal.execute_job('link', job, self.config, self.base)
            with patch.object(pc, 'execute', side_effect=AssertionError('replayed')):
                state, result = journal.execute_job('link', job, self.config, self.base)
            self.assertEqual(state, 'completed'); self.assertEqual(result['written'], 3)
            self.assertEqual(len(journal.unsent('link')), 1)
            journal.acknowledge('link:'+job['id']); self.assertEqual(journal.unsent('link'), [])
            with self.assertRaises(ValueError): journal.execute_job('link', {**job, 'tool': 'pc_status'}, self.config, self.base)
        finally: journal.db.close()

    def test_restart_recovers_uncertain_action_without_replay(self):
        journal = pc.Journal(self.base); job = self.job()
        fingerprint = pc.hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()
        journal.db.execute("INSERT INTO jobs(id,fingerprint,status,created) VALUES(?,?,'started',?)", ('link:'+job['id'], fingerprint, time.time()))
        journal.db.commit(); journal.db.close()
        journal = pc.Journal(self.base)
        try:
            with patch.object(pc, 'execute', side_effect=AssertionError('replayed')):
                state, result = journal.execute_job('link', job, self.config, self.base)
            self.assertEqual(state, 'uncertain'); self.assertIn('restarted', result['error'])
        finally: journal.db.close()

    def test_expired_job_cannot_execute(self):
        journal = pc.Journal(self.base)
        try:
            with patch.object(pc, 'execute') as execute:
                state, _ = journal.execute_job('link', {**self.job(), 'expires_at': time.time()-1}, self.config, self.base)
            execute.assert_not_called(); self.assertEqual(state, 'uncertain')
        finally: journal.db.close()

    def test_process_output_bounded_and_timeout_uncertain(self):
        value = pc.bounded_process([sys.executable, '-c', 'print("x"*100000)'], self.workspace)
        self.assertEqual(value['exit_code'], 0); self.assertTrue(value['truncated'])
        self.assertLessEqual(len(value['output']), pc.MAX_OUTPUT)
        value = pc.bounded_process([sys.executable, '-c', 'import time; time.sleep(10)'], self.workspace, timeout=1)
        self.assertEqual(value['status'], 'uncertain')

    def test_https_only_and_no_redirect_forwarding(self):
        for url in ('http://example.com', 'https://x:y@example.com', 'https://example.com?token=x'):
            with self.assertRaises(ValueError): pc.Relay({'relay_url': url})
        self.assertIsNone(pc.NoRedirect().redirect_request(None, None, None, None, None, None))

    def test_many_connections_survive_restart_without_a_fixed_count_limit(self):
        config = {'version': 1, 'connections': {str(n): {'email': 'owner@example.com', 'token': secrets.token_hex(32)} for n in range(500)}}
        pc.save_config(self.base, config)
        self.assertEqual(pc.load_config(self.base), config)

    def test_only_one_worker_owns_journal(self):
        with pc.InstanceLock(self.base):
            with self.assertRaises(RuntimeError):
                with pc.InstanceLock(self.base): pass

    @unittest.skipUnless(pc.shutil.which('pwsh') or pc.shutil.which('powershell'), 'PowerShell not installed')
    def test_real_powershell_round_trip_in_test_workspace(self):
        value = pc.execute('pc_terminal', {'command': "[Console]::WriteLine('mini-codex-test')", 'cwd': str(self.workspace)},
                           {**self.config, 'capabilities': ['terminal']}, self.base)
        self.assertEqual(value['exit_code'], 0)
        self.assertIn('mini-codex-test', value['output'])

    def test_expired_result_delivery_does_not_block_new_polling_or_replay(self):
        config={'version':1,'connections':{'link':{**self.config,'enabled':True}}}
        pc.save_config(self.base,config)
        journal=pc.Journal(self.base)
        journal.execute_job('link',self.job(),self.config,self.base); journal.db.close()
        from urllib.error import HTTPError
        with patch.object(pc,'Relay') as relay, patch.object(pc,'execute',side_effect=AssertionError('replayed')):
            relay.return_value.call.side_effect=[HTTPError('https://relay.invalid',410,'expired',{},None), {'job':None,'capabilities':[]}]
            pc.run(self.base,once=True)
            self.assertEqual([call.args[0] for call in relay.return_value.call.call_args_list],['result','next'])


if __name__ == '__main__': unittest.main()
