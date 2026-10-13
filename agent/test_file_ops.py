import base64
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

class FileOpsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('file_ops'),'Atomic file/transfer manager is not implemented')
        from file_ops import FileStore
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=FileStore(self.root/'state/jobs.sqlite3')
    def tearDown(self):
        if hasattr(self,'store'):self.store.close()
        if hasattr(self,'temp'):self.temp.cleanup()
    def test_copy_move_checksum_and_delete_have_stable_effect_receipts(self):
        a=self.root/'a';b=self.root/'b';c=self.root/'c';a.write_bytes(b'Unicode: \xd0\xaf');a.chmod(0o640)
        result=self.store.operate('copy_receipt_1','copy',str(a),str(b))
        self.assertEqual(b.read_bytes(),a.read_bytes());self.assertEqual(self.store.checksum(str(b))['sha256'],hashlib.sha256(a.read_bytes()).hexdigest())
        self.assertEqual(self.store.operate('copy_receipt_1','copy',str(a),str(b)),result)
        self.store.operate('move_receipt_2','move',str(b),str(c));self.assertFalse(b.exists());self.assertTrue(c.exists())
        self.store.operate('delete_receipt_3','delete',str(c));self.assertFalse(c.exists())
        self.assertEqual(self.store.operate('delete_receipt_3','delete',str(c))['deleted'],True)
    def test_refuses_overwrite_and_hash_mismatch_without_changing_destination(self):
        a=self.root/'a';b=self.root/'b';a.write_bytes(b'new');b.write_bytes(b'old')
        with self.assertRaises(FileExistsError):self.store.operate('no_overwrite_1','copy',str(a),str(b))
        with self.assertRaises(ValueError):self.store.operate('bad_source_hash','copy',str(a),str(b),overwrite=True,expected_sha256='0'*64)
        self.assertEqual(b.read_bytes(),b'old')
    def test_symlink_paths_and_directory_delete_are_rejected(self):
        a=self.root/'a';a.write_bytes(b'owned')
        link=self.root/'link'
        try:link.symlink_to(a)
        except OSError:self.skipTest('Host cannot create symbolic links')
        with self.assertRaises(ValueError):self.store.operate('link_delete_1','delete',str(link))
        with self.assertRaises(ValueError):self.store.operate('directory_delete','delete',str(self.root))
        self.assertEqual(a.read_bytes(),b'owned')
    def test_resumable_chunks_verify_hash_and_publish_only_at_commit(self):
        target=self.root/'large';data=b'abcd'*2000;digest=hashlib.sha256(data).hexdigest()
        transfer=self.store.start_transfer('transfer_start_1',str(target),len(data),digest)['transfer_id']
        first=data[:3000];part=base64.b64encode(first).decode();chunk_hash=hashlib.sha256(first).hexdigest()
        self.store.write_chunk(transfer,0,part,chunk_hash)
        self.assertFalse(target.exists())
        self.store.close()
        from file_ops import FileStore
        self.store=FileStore(self.root/'state/jobs.sqlite3')
        self.assertEqual(self.store.transfer_status(transfer)['offset'],3000)
        self.assertFalse(self.store.write_chunk(transfer,0,part,chunk_hash)['written'])
        remaining=data[3000:]
        self.store.write_chunk(transfer,3000,base64.b64encode(remaining).decode(),hashlib.sha256(remaining).hexdigest())
        self.assertEqual(self.store.commit_transfer(transfer)['sha256'],digest)
        self.assertEqual(target.read_bytes(),data)
        self.assertEqual(self.store.commit_transfer(transfer)['sha256'],digest)
    def test_mismatched_chunk_and_changed_target_do_not_publish(self):
        target=self.root/'target';target.write_bytes(b'original');data=b'payload'
        transfer=self.store.start_transfer('transfer_conflict',str(target),len(data),hashlib.sha256(data).hexdigest(),overwrite=True)['transfer_id']
        with self.assertRaises(ValueError):self.store.write_chunk(transfer,0,base64.b64encode(data).decode(),'0'*64)
        self.store.write_chunk(transfer,0,base64.b64encode(data).decode(),hashlib.sha256(data).hexdigest())
        target.write_bytes(b'external-change')
        with self.assertRaises(RuntimeError):self.store.commit_transfer(transfer)
        self.assertEqual(target.read_bytes(),b'external-change')
    def test_wrong_final_hash_preserves_destination(self):
        target=self.root/'target';target.write_bytes(b'original');data=b'payload'
        transfer=self.store.start_transfer('transfer_bad_final',str(target),len(data),'0'*64,overwrite=True)['transfer_id']
        self.store.write_chunk(transfer,0,base64.b64encode(data).decode(),hashlib.sha256(data).hexdigest())
        with self.assertRaises(ValueError):self.store.commit_transfer(transfer)
        self.assertEqual(target.read_bytes(),b'original')
    def test_transfer_lease_blocks_conflicting_file_operation_until_abort(self):
        target=self.root/'target';source=self.root/'source';source.write_bytes(b'new')
        transfer=self.store.start_transfer('file_lease_transfer',str(target),3,hashlib.sha256(b'new').hexdigest())['transfer_id']
        with self.assertRaises(RuntimeError):self.store.operate('conflicting_copy','copy',str(source),str(target))
        self.assertFalse(target.exists())
        self.store.abort_transfer(transfer)
        self.store.operate('copy_after_abort','copy',str(source),str(target));self.assertEqual(target.read_bytes(),b'new')

if __name__=='__main__':unittest.main()
