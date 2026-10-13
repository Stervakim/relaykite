import json, tempfile, unittest, sys, socket
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from memory_bridge import MemoryBridge

class BridgeTests(unittest.TestCase):
 @unittest.skipUnless(hasattr(socket,'AF_UNIX'),'Unix socket required')
 def test_accounting_ignores_live_ipc_socket_but_counts_regular_storage(self):
  from memory_bridge import allocated_bytes
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bytes';p.write_bytes(b'owned-data')
   with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as endpoint:
    endpoint.bind(str(Path(d)/'managed.sock'))
    self.assertGreaterEqual(allocated_bytes(Path(d)),10)
 def test_missing_config_is_explicit(self):
  b=MemoryBridge(Path('missing-memory-config.json'))
  self.assertFalse(b.configured)
  with self.assertRaises(RuntimeError): b.search('x')
 def test_remote_url_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json';p.write_text(json.dumps({'url':'https://example.com','key':'k'*48}))
   with self.assertRaises(ValueError): MemoryBridge(p)
 def test_unavailable_core_never_looks_like_success(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json';p.write_text(json.dumps({'url':'http://127.0.0.1:8420','key':'k'*48,'accounting_roots':[]}))
   b=MemoryBridge(p)
   with patch.object(b,'request',side_effect=RuntimeError('unavailable')):
    with self.assertRaises(RuntimeError):b.save('title','content',[],{'layer':'L2'})
 def test_payload_preserves_old_fields_and_new_metadata(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json';p.write_text(json.dumps({'url':'http://127.0.0.1:8420','key':'k'*48,'accounting_roots':[]}))
   b=MemoryBridge(p)
   with patch.object(b,'request',return_value={'saved':True}) as req:
    self.assertTrue(b.save('title','content',['x'],{'layer':'L2'})['saved'])
    self.assertEqual(req.call_args.args[1],{'title':'title','content':'content','tags':['x'],'memory':{'layer':'L2'}})
 def test_symlink_accounting_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json';p.write_text(json.dumps({'url':'http://127.0.0.1:8420','key':'k'*48,'accounting_roots':[d]}))
   b=MemoryBridge(p)
   with patch('memory_bridge.allocated_bytes',side_effect=ValueError('symlink')):
    with self.assertRaises(ValueError):b.save('t','c',[])
 def test_app_reservation_counts_inaccessible_root_storage_before_saving(self):
  from memory_bridge import CAP
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json';p.write_text(json.dumps({'url':'http://127.0.0.1:8420','key':'k'*48,'accounting_roots':[],'external_reserved_bytes':CAP-100}))
   b=MemoryBridge(p)
   with patch.object(b,'request') as request:
    with self.assertRaises(ValueError):b.save('title','content',[])
    request.assert_not_called()

if __name__=='__main__':unittest.main()
