import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc'))
from development.app_server import JsonRpcClient, RpcError, discover_codex


FIXTURE = r'''
import sys,json
for line in sys.stdin:
    m=json.loads(line)
    if 'id' not in m: continue
    method=m.get('method')
    if method=='probe':
        print(json.dumps({'method':'item/completed','params':{'item':{'type':'commandExecution','exitCode':0}}}),flush=True)
        print(json.dumps({'id':m['id'],'result':{'ok':True}}),flush=True)
    elif method=='error':
        print(json.dumps({'id':m['id'],'error':{'code':-1,'message':'fixture failure'}}),flush=True)
    elif method=='exit': sys.exit(2)
    elif method=='quiet': pass
    else: print(json.dumps({'id':m['id'],'result':{}}),flush=True)
'''


class RpcTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.script = Path(self.temp.name) / 'rpc.py'
        self.script.write_text(FIXTURE, encoding='utf-8')
        self.events = []
        self.client = JsonRpcClient([sys.executable, '-u', str(self.script)], on_notification=lambda method, params: self.events.append((method, params)))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_response_and_notification_are_delivered_independently(self):
        self.assertEqual(self.client.request('probe', {}), {'ok': True})
        self.assertEqual(self.events[0][0], 'item/completed')

    def test_rpc_error_preserves_message_without_hanging(self):
        with self.assertRaisesRegex(RpcError, 'fixture failure'):
            self.client.request('error', {})

    def test_dead_process_fails_pending_request(self):
        with self.assertRaises(RpcError):
            self.client.request('exit', {}, timeout=2)

    def test_request_deadline_and_process_cleanup(self):
        with self.assertRaises(TimeoutError):
            self.client.request('quiet', {}, timeout=.05)
        self.client.close()
        self.assertIsNotNone(self.client.process.poll())

    def test_discovery_returns_argument_vector_or_absent(self):
        value = discover_codex()
        self.assertTrue(value is None or isinstance(value, list))
        if value:
            self.assertTrue(Path(value[0]).is_absolute())


if __name__ == '__main__':
    unittest.main()
