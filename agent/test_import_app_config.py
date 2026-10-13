import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import import_app_config as importer

class ConfigImportTests(unittest.TestCase):
    def test_first_import_preserves_relay_owner_and_remaps_private_runtime_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'owned';source=Path(tmp)/'selected.json'
            old={'relay_url':'https://owned.example','agent_token':'k'*48,'state_dir':'/old/state','memory_dir':'/old/memory','disable_file':'/old/disable'}
            source.write_text(json.dumps(old))
            with patch.object(importer,'BASE',base),patch.object(importer,'MODE','app'),patch.object(os,'geteuid',return_value=10515,create=True):
                result=importer.first_import(source)
                self.assertTrue(result['imported']);actual=json.loads((base/'config.json').read_text())
                self.assertEqual(actual['agent_token'],old['agent_token']);self.assertEqual(actual['state_dir'],str(base/'state'))
                self.assertEqual(actual['disable_file'],str(base/'disable'));self.assertTrue((base/'enabled').is_file())
                before=(base/'config.json').read_bytes()
                with self.assertRaises(ValueError):importer.first_import(source)
                self.assertEqual((base/'config.json').read_bytes(),before)
    def test_invalid_config_never_creates_an_enabled_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'owned';source=Path(tmp)/'selected.json';source.write_text('{"relay_url":"http://unsafe.example"}')
            with patch.object(importer,'BASE',base),patch.object(importer,'MODE','app'),patch.object(os,'geteuid',return_value=10515,create=True):
                with self.assertRaises(ValueError):importer.first_import(source)
            self.assertFalse((base/'enabled').exists());self.assertFalse((base/'config.json').exists())

if __name__=='__main__':unittest.main()
