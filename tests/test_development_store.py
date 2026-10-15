"""Behavioral persistence, concurrency and boundary tests for development runs."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from pc.development.store import RunStore


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = RunStore(self.root / 'state')
        self.workspace = str(self.root.resolve())

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def create(self, request_id='request-1', **kwargs):
        return self.store.create('Build a small tool', self.workspace, request_id, **kwargs)

    def test_create_persists_fields_and_deduplicates_after_reopen(self):
        run = self.create(limits={'turns': 12}, mode='test')
        self.assertEqual(run['status'], 'queued')
        self.assertEqual(run['limits'], {'turns': 12})
        self.assertEqual(run['mode'], 'test')
        self.assertIsInstance(run['created_at'], (int, float))
        self.assertIsNone(run['checkpoint'])
        self.assertIsNone(run['error'])
        self.store.close()
        self.store = RunStore(self.root / 'state')
        self.assertEqual(self.create(limits={'turns': 12}, mode='test')['id'], run['id'])
        self.assertEqual(len(self.store.list_runs()), 1)

    def test_reused_request_with_changed_inputs_is_rejected(self):
        self.create(limits={'turns': 12})
        for change in ({'prompt': 'different'}, {'workspace': str(self.root / 'other')},
                       {'limits': {'turns': 13}}, {'mode': 'test'}):
            args = {'prompt': 'Build a small tool', 'workspace': self.workspace,
                    'request_id': 'request-1', 'limits': {'turns': 12}}
            args.update(change)
            with self.assertRaises(ValueError):
                self.store.create(**args)

    def test_concurrent_duplicate_create_produces_one_run(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: self.create()['id'], range(24)))
        self.assertEqual(len(set(ids)), 1)

    def test_two_store_instances_share_idempotency_and_events(self):
        other = RunStore(self.root / 'state')
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                ids = list(pool.map(lambda n: (self.store if n % 2 else other).create(
                    'task', self.workspace, 'shared')['id'], range(24)))
            self.assertEqual(len(set(ids)), 1)
            other.append_event(ids[0], 'note', {'message': 'visible'})
            self.assertEqual(self.store.events(ids[0])[-1]['data'], {'message': 'visible'})
        finally:
            other.close()

    def test_legal_transitions_and_terminal_guard(self):
        run = self.create()
        with self.assertRaises(ValueError):
            self.store.transition(run['id'], 'completed')
        for status in ('running', 'waiting_model', 'running', 'paused', 'running', 'completed'):
            self.assertEqual(self.store.transition(run['id'], status)['status'], status)
        for status in ('running', 'cancelled', 'failed'):
            with self.assertRaises(ValueError):
                self.store.transition(run['id'], status)

    def test_failure_detail_and_checkpoint_survive_restart(self):
        run = self.create()
        self.store.checkpoint(run['id'], {'thread_id': 'thread-a', 'summary': 'Tests next'})
        self.store.transition(run['id'], 'failed', 'Executable unavailable')
        self.store.close()
        self.store = RunStore(self.root / 'state')
        got = self.store.get(run['id'])
        self.assertEqual(got['checkpoint']['thread_id'], 'thread-a')
        self.assertEqual(got['error'], 'Executable unavailable')

    def test_recovery_marks_active_effects_uncertain_and_never_replays(self):
        active = self.create('active')
        waiting = self.create('waiting')
        paused = self.create('paused')
        self.store.transition(active['id'], 'running')
        self.store.transition(waiting['id'], 'running')
        self.store.transition(waiting['id'], 'waiting_model')
        self.store.transition(paused['id'], 'paused')
        self.store.recover()
        self.assertEqual(self.store.get(active['id'])['status'], 'uncertain')
        self.assertEqual(self.store.get(waiting['id'])['status'], 'uncertain')
        self.assertEqual(self.store.get(paused['id'])['status'], 'paused')
        before = self.store.events(active['id'])
        self.store.recover()
        self.assertEqual(self.store.events(active['id']), before)
        self.assertTrue(any(e['type'] == 'recovery' for e in before))

    def test_event_ids_are_monotonic_and_cursor_results_are_bounded(self):
        run = self.create()
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda n: self.store.append_event(run['id'], 'step', {'n': n}), range(225)))
        page = self.store.events(run['id'])
        self.assertEqual(len(page), 200)
        self.assertTrue(all(isinstance(e['id'], int) for e in page))
        self.assertEqual([e['id'] for e in page], sorted(set(e['id'] for e in page)))
        tail = self.store.events(run['id'], after=page[-1]['id'])
        self.assertGreater(len(tail), 0)
        self.assertTrue(all(e['id'] > page[-1]['id'] for e in tail))

    def test_runs_are_newest_first_with_a_hard_page_bound(self):
        ids = [self.create(str(n))['id'] for n in range(105)]
        page = self.store.list_runs()
        self.assertEqual(len(page), 100)
        self.assertEqual(page[0]['id'], ids[-1])

    def test_artifacts_are_atomic_metadata_and_available_after_restart(self):
        run = self.create()
        meta = self.store.artifact(run['id'], 'report.txt', 'готово', 'text/plain; charset=utf-8')
        self.assertEqual(meta['name'], 'report.txt')
        self.assertEqual(meta['size'], len('готово'.encode()))
        self.assertNotIn('content', meta)
        self.assertEqual(self.store.artifact_path(run['id'], 'report.txt').read_text(encoding='utf-8'), 'готово')
        self.store.artifact(run['id'], 'report.txt', b'updated')
        self.assertEqual(self.store.artifacts(run['id'])[0]['size'], 7)
        self.store.close()
        self.store = RunStore(self.root / 'state')
        self.assertEqual(self.store.artifact_path(run['id'], 'report.txt').read_bytes(), b'updated')

    def test_path_traversal_and_windows_special_names_are_rejected(self):
        run = self.create()
        for name in ('../secret', '..\\secret', '/absolute', 'C:\\secret', 'a/b', 'a\\b',
                     '.', '..', '', 'CON', 'nul.txt', 'file:stream', 'trailing.', 'trailing ', 'a\x00b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.artifact(run['id'], name, b'bad')
        with self.assertRaises((KeyError, ValueError)):
            self.store.artifact('../../escape', 'x', b'bad')

    def test_existing_artifact_symlink_cannot_escape(self):
        run = self.create()
        self.store.artifact(run['id'], 'link.txt', b'first')
        destination = self.store.artifact_path(run['id'], 'link.txt')
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'private')
        destination.unlink()
        try:
            destination.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('Creating symlinks is unavailable on this system')
        with self.assertRaises(ValueError):
            self.store.artifact_path(run['id'], 'link.txt')
        with self.assertRaises(ValueError):
            self.store.artifact(run['id'], 'link.txt', b'replaced')
        self.assertEqual(outside.read_bytes(), b'private')

    def test_invalid_requests_are_rejected_and_missing_ids_are_not_created(self):
        for change in ({'prompt': ''}, {'request_id': ''}, {'workspace': 'relative'}, {'mode': 'pretend'}):
            args = {'prompt': 'task', 'workspace': self.workspace, 'request_id': 'request'}
            args.update(change)
            with self.assertRaises(ValueError):
                self.store.create(**args)
        for operation in (self.store.get, self.store.events, self.store.artifacts):
            with self.assertRaises(KeyError):
                operation('missing')

    def test_linked_run_directory_cannot_access_another_runs_artifacts(self):
        first, second = self.create('first'), self.create('second')
        self.store.artifact(first['id'], 'report.txt', b'first')
        self.store.artifact(second['id'], 'report.txt', b'second')
        first_dir = self.store.artifact_path(first['id'], 'report.txt').parent
        second_dir = self.store.artifact_path(second['id'], 'report.txt').parent
        (first_dir / 'report.txt').unlink()
        first_dir.rmdir()
        try:
            first_dir.symlink_to(second_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Creating symlinks is unavailable on this system')
        with self.assertRaises(ValueError):
            self.store.artifact_path(first['id'], 'report.txt')
        with self.assertRaises(ValueError):
            self.store.artifact(first['id'], 'report.txt', b'overwrite')
        self.assertEqual((second_dir / 'report.txt').read_bytes(), b'second')

    def test_checkpoint_and_events_are_detached_from_callers_mutations(self):
        run = self.create()
        checkpoint = {'progress': ['tests']}
        self.store.checkpoint(run['id'], checkpoint)
        checkpoint['progress'].append('changed')
        got = self.store.get(run['id'])
        self.assertEqual(got['checkpoint'], {'progress': ['tests']})
        got['checkpoint']['progress'].append('changed')
        self.assertEqual(self.store.get(run['id'])['checkpoint'], {'progress': ['tests']})

    def test_preflight_waiting_and_explicit_resume_are_legal(self):
        run = self.create()
        for state in ('waiting_user', 'running', 'waiting_model', 'running'):
            self.store.transition(run['id'], state)
        self.assertEqual(self.store.get(run['id'])['status'], 'running')

    def test_cursor_and_limit_arguments_are_validated(self):
        run = self.create()
        for value in (-1, True, '7', 2**64):
            with self.assertRaises(ValueError):
                self.store.events(run['id'], after=value)
        for value in (0, -1, True, '10'):
            with self.assertRaises(ValueError):
                self.store.list_runs(limit=value)
        self.assertLessEqual(len(self.store.events(run['id'], limit=1000)), 200)


if __name__ == '__main__':
    unittest.main()
