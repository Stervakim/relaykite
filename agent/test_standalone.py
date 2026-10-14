"""Meaningful host tests; no phone UI/root action, secret or network connection."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch
from unittest.mock import Mock

import native_phone as phone
from phone_agent import Journal, Relay, execute_job, acquire_instance_lock


def make_job(ident='test-job',**extra):
    return {'id':ident,'tool':'root_shell','arguments':{'command':'id'},'expires_at':time.time()+120,**extra}


class StandaloneTests(unittest.TestCase):
    def test_tool_dispatch_validation_does_not_execute_bad_input(self):
        with patch.object(phone,'tap') as tap:
            self.assertTrue(phone.dispatch('tap',{'x':True,'y':5})['isError'])
            self.assertTrue(phone.dispatch('tap',{'x':5,'y':5,'other':'bad'})['isError'])
            tap.assert_not_called()
        self.assertTrue(phone.dispatch('adb',{})['isError'])

    def test_root_process_uses_system_shell_without_su(self):
        result=subprocess.CompletedProcess([],0,b'uid=0(root)',b'')
        with patch.object(os,'geteuid',return_value=0,create=True), patch.object(subprocess,'run',return_value=result) as run:
            self.assertEqual(phone.run_android('id'),'uid=0(root)')
        self.assertEqual(run.call_args.args[0][:2],['/system/bin/sh','-c'])

    def test_memory_redacts_secrets_and_upserts(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'PHONE_MEMORY_DIR':directory}):
            result=phone.phone_memory_save('example task','Authorization: Bearer fixture-private-token\nhttps://host/sub/key\npassword=fixture\nmail@example.com\n123456',['test'])
            note=phone.phone_memory_search('example')['notes'][0]
            for secret in ('fixture-private-token','host/sub/key','password=fixture','mail@example.com','123456'):
                self.assertNotIn(secret,note['content'])
            self.assertTrue(result['redacted'])
            result=phone.phone_memory_save('example task','Confirmed: installed package',['test'])
            self.assertEqual(result['notes_count'],1)
            self.assertEqual(result['archive_count'],1)
            self.assertEqual(result['max_bytes']+result['agent_reserve_bytes'],5*1024**3)
            self.assertEqual(result['agent_reserve_bytes'],32*1024*1024)
            self.assertLess(result['bytes'],1024*1024)

    def test_memory_hot_limit_and_bounded_archive_search(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'PHONE_MEMORY_DIR':directory}):
            for i in range(203): result=phone.phone_memory_save(f'entry-{i:03}','Confirmed short task note',[])
            self.assertEqual(result['notes_count'],200)
            self.assertEqual(result['archive_count'],3)
            archived=phone.phone_memory_search('entry-000',limit=1)['notes']
            self.assertEqual(len(archived),1)
            self.assertTrue(archived[0]['archived'])
            self.assertLessEqual(len(archived[0]['content']),384)
            self.assertEqual(len(list((Path(directory)/'archives').glob('*.json.gz'))),3)

    def test_memory_rejects_binary_and_oversized_notes(self):
        with self.assertRaises(ValueError): phone.phone_memory_save('too long','я'*4096)
        with self.assertRaises(ValueError): phone.phone_memory_save('image','data:image/png;base64,'+'A'*2000)

    def test_duplicate_job_returns_cache_not_second_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=Journal(Path(directory))
            job=make_job()
            calls=[]
            executor=lambda *_: calls.append(1) or {'content':[{'type':'text','text':'ok'}],'isError':False}
            first=execute_job(job,journal,executor)
            second=execute_job(job,journal,executor)
            self.assertEqual(first,second)
            self.assertEqual(len(calls),1)
            journal.db.close()

    def test_restart_tombstone_blocks_uncertain_action(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=Journal(Path(directory))
            job=make_job('interrupted')
            fingerprint=hashlib.sha256(json.dumps({'tool':job['tool'],'arguments':job['arguments']},sort_keys=True,separators=(',',':')).encode()).hexdigest()
            journal.start(job['id'],job['expires_at'],fingerprint)
            journal.db.close()
            journal=Journal(Path(directory))
            with patch('native_phone.dispatch') as executor:
                result=execute_job(job,journal,executor)
                executor.assert_not_called()
            self.assertEqual(result[2],'uncertain')
            journal.db.close()

    def test_compaction_keeps_live_job_tombstone(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=Journal(Path(directory))
            counter=[]
            executor=lambda *_: counter.append(1) or {'content':[{'type':'text','text':'done'}],'isError':False}
            original=make_job('oldest-live')
            execute_job(original,journal,executor)
            for i in range(105): execute_job(make_job(f'new-{i}'),journal,executor)
            result=execute_job(original,journal,executor)
            self.assertEqual(len(counter),106)
            self.assertEqual(result[2],'uncertain')
            self.assertIsNotNone(journal.get(original['id']))
            journal.db.close()

    def test_expired_or_disabled_jobs_never_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=Journal(Path(directory))
            with patch('native_phone.dispatch') as executor:
                self.assertEqual(execute_job(make_job(expires_at=time.time()-1),journal,executor)[2],'uncertain')
                with self.assertRaises(InterruptedError): execute_job(make_job('disabled-job'),journal,executor,disabled=lambda:True)
                executor.assert_not_called()
            journal.db.close()

    def test_transport_refuses_insecure_or_credential_urls(self):
        for url in ('http://example.com','https://user:pass@example.com','https://example.com?token=x'):
            with self.assertRaises(ValueError): Relay({'relay_url':url,'agent_token':'x'*40})

    def test_lock_is_nonblocking_exclusive_and_failed_handle_is_closed(self):
        lock_calls=[]
        def flock(fd,mode):
            lock_calls.append((fd,mode))
            if len(lock_calls)>1: raise BlockingIOError('fixture contention')
        fake_fcntl=types.SimpleNamespace(LOCK_EX=2,LOCK_NB=4,flock=flock)
        with tempfile.TemporaryDirectory() as directory, patch.dict('sys.modules',{'fcntl':fake_fcntl}):
            held=acquire_instance_lock(Path(directory))
            self.assertFalse(held.closed)
            with self.assertRaises(RuntimeError): acquire_instance_lock(Path(directory))
            self.assertTrue((Path(directory)/'agent.lock').exists())
            self.assertEqual(lock_calls[0][1],6)
            held.close()

    def test_memory_budget_counts_allocated_blocks_not_compressed_length(self):
        path=Mock()
        path.stat.return_value=types.SimpleNamespace(st_mode=stat.S_IFREG,st_blocks=16,st_size=12)
        self.assertEqual(phone.allocated_disk_bytes(path),8192)
        path.stat.return_value=types.SimpleNamespace(st_mode=stat.S_IFREG,st_size=4097)
        self.assertEqual(phone.allocated_disk_bytes(path),8192)
        path.stat.return_value=types.SimpleNamespace(st_mode=stat.S_IFREG,st_size=10)
        self.assertEqual(phone.allocated_disk_bytes(path),4096)
        path.stat.return_value=types.SimpleNamespace(st_mode=stat.S_IFLNK,st_size=10)
        with self.assertRaises(RuntimeError): phone.allocated_disk_bytes(path)

    def test_restart_recovers_owned_orphan_and_migrates_old_byte_accounting(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'PHONE_MEMORY_DIR':directory}):
            phone.phone_memory_save('task','first')
            phone.phone_memory_save('task','second')
            base=Path(directory)
            dbpath=base/'notes.sqlite3'
            db=sqlite3.connect(dbpath)
            name=db.execute('SELECT file FROM archives').fetchone()[0]
            db.execute('UPDATE archives SET bytes=1')
            db.commit()
            db.close()
            orphan=base/'archives'/('a'*32+'.json.gz')
            orphan.write_bytes(b'uncommitted fixture')
            unrelated=base/'archives'/'user-file.gz'
            unrelated.write_bytes(b'keep')
            phone._RECOVERED_MEMORY_DATABASES.discard(str(dbpath.resolve()))
            with patch.object(phone.os,'scandir',wraps=os.scandir) as scan:
                db=phone.memory_database()
                self.assertEqual(db.execute('SELECT bytes FROM archives WHERE file=?',(name,)).fetchone()[0],phone.allocated_disk_bytes(base/'archives'/name))
                db.close()
                db=phone.memory_database()
                db.close()
                self.assertEqual(scan.call_count,1)
            self.assertFalse(orphan.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue((base/'archives'/name).exists())

    def test_orphan_recovery_never_follows_symlink_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            outside=base/'outside.txt'
            outside.write_text('protected fixture',encoding='utf-8')
            entry=Mock(name='symlink-entry')
            entry.name='b'*32+'.json.gz'
            entry.path=str(outside)
            entry.is_file.return_value=False
            scan=Mock()
            scan.__enter__=Mock(return_value=iter([entry]))
            scan.__exit__=Mock(return_value=False)
            with patch.dict(os.environ,{'PHONE_MEMORY_DIR':str(base/'memory')}),patch.object(phone.os,'scandir',return_value=scan):
                db=phone.memory_database()
                db.close()
            entry.is_file.assert_called_once_with(follow_symlinks=False)
            self.assertEqual(outside.read_text(encoding='utf-8'),'protected fixture')


if __name__=='__main__':
    unittest.main()
