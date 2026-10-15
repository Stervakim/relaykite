"""Opt-in real Codex/sandbox check with a deterministic LOCAL provider.

This deliberately does not claim a ChatGPT Free acceptance test.
"""
import json
import os
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc'))
from development.app_server import discover_codex
from development.server import DevelopmentServer


@contextmanager
def native_workspace_directory():
    # On Windows Python 3.14's TemporaryDirectory uses a private 0700 DACL.
    # Codex's unelevated LUA token cannot traverse that owner-only test root.
    # Ordinary mkdir inherits the project volume's ACLs, matching real repos;
    # DevelopmentServer separately protects its private state subdirectory.
    parent = Path(__file__).resolve().parents[2]
    name = 'native-engine-' + uuid.uuid4().hex
    root = parent / name
    root.mkdir()
    try:
        yield root
    finally:
        resolved = root.resolve()
        if resolved.parent != parent or resolved.name != name or root.is_symlink():
            raise RuntimeError('Native fixture cleanup target escaped its owned directory')
        shutil.rmtree(resolved)


class LocalToolFixture:
    def __init__(self, workspace): self.requests = 0; self.workspace = str(workspace)
    def capabilities(self): return {'ready': True, 'live_verified': False, 'reason': 'Deterministic local protocol fixture'}
    def cancel_active(self, run_id=None): pass
    def generate(self, request, *, run_id=None, cancel_event=None):
        self.requests += 1
        if self.requests == 1:
            self.tool_schema = [tool for tool in request.get('tools', []) if tool.get('name') == 'exec_command']
        step = self.requests
        item = {'id': 'item_probe_' + str(step), 'status': 'completed'}
        if step in (1, 2):
            filename = '../outside.txt' if step == 1 else 'hello.txt'
            item.update(type='custom_tool_call', name='apply_patch', call_id='probe_call_' + str(step),
                        input='*** Begin Patch\n*** Add File: ' + filename + '\n+relaykite verified\n*** End Patch')
        elif step <= 21:
            # The rejected boundary probe is not an executed native fileChange.
            # Require twenty completed actions in addition to that denied call.
            command = 'python -m unittest discover -s tests' if step == 21 else 'python -c "print(\'step-' + str(step) + '\')"'
            if step == 3:
                command = 'python -c "import os; print(os.getcwd()); print(os.listdir(\'tests\'))"'
            item.update(type='function_call', name='exec_command', call_id='probe_call_' + str(step),
                        arguments=json.dumps({'cmd': command, 'workdir': self.workspace, 'login': False, 'yield_time_ms': 10000, 'max_output_tokens': 1500}))
        else:
            item.update(type='message', role='assistant', content=[{'type': 'output_text', 'text': 'Local fixture complete; inspect verification and sandbox assertions.', 'annotations': []}])
        return {'id': 'resp_probe_' + str(step), 'object': 'response', 'created_at': int(time.time()),
                'status': 'completed', 'model': 'chatgpt-free', 'output': [item]}


@unittest.skipUnless(os.environ.get('RELAYKITE_CODEX_ENGINE_TESTS') == '1', 'opt-in real Codex process/sandbox check')
class RealEngineTests(unittest.TestCase):
    def test_twenty_native_tool_steps_patch_and_sandbox_boundary(self):
        self.assertIsNotNone(discover_codex(), 'Install the pinned Codex CLI first')
        with native_workspace_directory() as root:
            workspace = root / 'project'
            (workspace / 'tests').mkdir(parents=True)
            (workspace / 'tests' / 'test_result.py').write_text(
                'from pathlib import Path\nimport unittest\nclass Result(unittest.TestCase):\n'
                ' def test_patch(self):\n  self.assertEqual(Path("hello.txt").read_text().strip(), "relaykite verified")\n', encoding='utf-8')
            subprocess.run(['git', 'init', '-q', str(workspace)], check=True)
            fixture = LocalToolFixture(workspace)
            service = DevelopmentServer(root / 'state', port=0, provider=fixture).start()
            try:
                run = service.store.create('Exercise only the deterministic local fixture commands.', str(workspace), 'native-20-steps',
                                           {'verify_command': 'python -m unittest discover -s tests', 'max_steps': 100, 'max_seconds': 120})
                service.supervisor.start(run['id'])
                deadline = time.monotonic() + 110
                while time.monotonic() < deadline:
                    current = service.store.get(run['id'])
                    if current['status'] not in ('queued', 'running'):
                        break
                    time.sleep(.1)
                events = []
                while True:
                    page = service.store.events(run['id'], after=events[-1]['id'] if events else 0)
                    events.extend(page)
                    if len(page) < 200: break
                states = [event['data'] for event in events if event['type'] in ('status', 'error')]
                diagnostic = [(e['data']['item'].get('type'), e['data']['item'].get('command'), e['data']['item'].get('exitCode'), str(e['data']['item'].get('aggregatedOutput', ''))[-2500:]) for e in events if e['type'] == 'item/completed' and 'item' in e['data'] and (e['data']['item'].get('exitCode') not in (0, None) or 'os.getcwd' in e['data']['item'].get('command', ''))]
                self.assertEqual(service.store.get(run['id'])['status'], 'completed', str({'states': states, 'requests': fixture.requests, 'schema': fixture.tool_schema, 'items': diagnostic})[-12000:])
                self.assertFalse((root / 'outside.txt').exists(), 'Native sandbox allowed a write outside workspace')
                self.assertEqual((workspace / 'hello.txt').read_text().strip(), 'relaykite verified')
                self.assertEqual(fixture.requests, 22)
                items = [event['data']['item'] for event in events if event['type'] == 'item/completed' and 'item' in event['data']]
                self.assertGreaterEqual(len([item for item in items if item.get('type') in ('commandExecution', 'fileChange')]), 20)
                evidence = json.loads(service.store.artifact_path(run['id'], 'verification.json').read_text('utf-8'))
                self.assertEqual(evidence['exit_code'], 0)
                self.assertFalse(evidence['live_free_acceptance_verified'])
            finally:
                service.close()


if __name__ == '__main__': unittest.main()
