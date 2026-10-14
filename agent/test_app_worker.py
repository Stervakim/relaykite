import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app_worker

class AppWorkerTests(unittest.TestCase):
    def test_memory_child_uses_embedded_node_and_original_adapter_with_owner_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);cfg={'key':'k'*48,'scope':'codaki-owner-phone','data_dir':str(base/'memory-service/data'),'port':8420}
            (base/'memory-node.json').write_text(json.dumps(cfg))
            with patch.object(app_worker,'BASE',base),patch.object(app_worker,'MODE','app'),patch.object(os,'geteuid',return_value=10515,create=True),patch.dict(os.environ,{'RELAYKITE_NATIVE':'/data/app/owned/lib/arm64'}):
                command,value=app_worker.memory_command()
                self.assertEqual(Path(command[0]),Path('/data/app/owned/lib/arm64/librelaykite_node.so'));self.assertTrue(command[1].replace('\\','/').endswith('memory-runtime/codaki-external.mjs'))
                self.assertEqual(value,cfg)
                cfg['scope']='another-owner';(base/'memory-node.json').write_text(json.dumps(cfg))
                with self.assertRaises(ValueError):app_worker.memory_command()
    def test_app_entry_rejects_root_even_before_private_config_read(self):
        with patch.object(app_worker,'MODE','app'),patch.object(os,'geteuid',return_value=0,create=True):
            with self.assertRaises(PermissionError):app_worker.main()
    def test_root_entry_rejects_app_uid_and_accepts_root_in_both_explicit_modes(self):
        for mode in ('root','root-termux'):
            with patch.object(app_worker,'MODE',mode),patch.object(os,'geteuid',return_value=10515,create=True):
                with self.assertRaises(PermissionError):app_worker.verify_mode()
            with patch.object(app_worker,'MODE',mode),patch.object(os,'geteuid',return_value=0,create=True):
                app_worker.verify_mode()
    def test_orphan_reaper_requires_owner_generation_and_exact_command(self):
        receipt={'pid':123,'generation':19,'uid':10515,'argv':['/owned/node','/owned/adapter','/owned/config']}
        with patch.object(os,'geteuid',return_value=10515,create=True):
            self.assertTrue(app_worker.owned_child(receipt,10515,19,receipt['argv'],123))
            for uid,born,args,pgid in ((0,19,receipt['argv'],123),(10515,20,receipt['argv'],123),(10515,19,['other'],123),(10515,19,receipt['argv'],122)):
                self.assertFalse(app_worker.owned_child(receipt,uid,born,args,pgid))
    def test_memory_health_alone_cannot_replace_the_child_startup_receipt(self):
        self.assertEqual(app_worker.validate_memory_ready(b'{"ready":true,"port":8420,"engine":"tencentdb-original-external"}',8420)['port'],8420)
        for value in (b'{"engine":"tencentdb-original-external"}',b'{"ready":true,"port":9999,"engine":"tencentdb-original-external"}',b'{"ready":false,"port":8420,"engine":"tencentdb-original-external"}'):
            with self.assertRaises(ValueError):app_worker.validate_memory_ready(value,8420)

if __name__=='__main__':unittest.main()
