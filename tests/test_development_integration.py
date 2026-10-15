import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dev_integration_worker', ROOT / 'pc' / 'mini_codex_pc.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerIntegrationTests(unittest.TestCase):
    def test_development_requires_existing_codex_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PermissionError, 'Capability'):
                worker.execute('relaykite_dev', {'operation': 'capabilities'}, {'capabilities': []}, Path(tmp), 'owner-link')

    def test_start_cannot_escape_owner_workspace_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = root / 'allowed'; allowed.mkdir()
            private = root / 'private'; private.mkdir()
            config = {'capabilities': ['codex'], 'roots': [str(allowed)]}
            with self.assertRaises(PermissionError):
                worker.execute('relaykite_dev', {'operation': 'start', 'workspace': str(private), 'prompt': 'test', 'request_id': 'start'}, config, root / 'worker', 'owner-link')

    def test_valid_start_preserves_pairing_scope_and_normalizes_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / 'project'; project.mkdir()
            config = {'capabilities': ['codex'], 'roots': [str(project)]}
            with patch('development.client.call', return_value={'status': 'queued'}) as call:
                result = worker.execute('relaykite_dev', {'operation': 'start', 'workspace': str(project), 'prompt': 'test', 'request_id': 'start'}, config, root / 'worker', 'owner-link')
            self.assertEqual(result['status'], 'queued')
            self.assertEqual(call.call_args.kwargs['scope'], 'owner-link')
            self.assertEqual(Path(call.call_args.args[0]['workspace']), project.resolve())

    def test_unscoped_remote_development_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PermissionError, 'pair'):
                worker.execute('relaykite_dev', {'operation': 'status', 'run_id': 'x'}, {'capabilities': ['codex']}, Path(tmp))


if __name__ == '__main__': unittest.main()
