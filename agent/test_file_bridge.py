import importlib.util
import hashlib
from pathlib import Path, PurePosixPath
import tempfile
import unittest
from unittest.mock import patch
class FileBridgeTests(unittest.TestCase):
 def test_root_staged_copy_restores_android_app_context(self):
  from file_bridge import restore_app_context
  with patch('file_bridge.os.geteuid',return_value=0,create=True),patch('file_bridge.subprocess.run') as run:
   restore_app_context(PurePosixPath('/data/user/0/org.relaykite.runtime/cache/shared/owned.txt'))
   self.assertEqual(run.call_args.args[0],['/system/bin/restorecon','-R','/data/user/0/org.relaykite.runtime/cache/shared/owned.txt'])
   self.assertTrue(run.call_args.kwargs['check'])
  with patch('file_bridge.os.geteuid',return_value=10515,create=True),patch('file_bridge.subprocess.run') as run:
   restore_app_context(PurePosixPath('/data/user/0/org.relaykite.runtime/cache/shared/owned.txt'))
   run.assert_not_called()
 def test_stable_share_uri_preserves_original_and_rejects_reused_id(self):
  self.assertIsNotNone(importlib.util.find_spec('file_bridge'),'Scoped file bridge is missing')
  from file_bridge import FileBridge
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'owned.txt';source.write_text('owned content')
   bridge=FileBridge(root/'state/jobs.sqlite3',directory=root/'shared',uid=None)
   try:
    first=bridge.prepare('owned_share_request',str(source),'text/plain')
    self.assertTrue(first['uri'].startswith('content://org.relaykite.runtime.files/'))
    self.assertEqual(bridge.prepare('owned_share_request',str(source),'text/plain'),first)
    self.assertEqual(source.read_text(),'owned content')
    shared=next((root/'shared').glob('*.txt'));self.assertEqual(shared.read_bytes(),source.read_bytes())
    self.assertEqual(first['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
    with self.assertRaises(ValueError):bridge.prepare('owned_share_request',str(source),'image/png')
   finally:bridge.close()
