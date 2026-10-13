"""Real durable scheduling: concurrency, resource exclusion and no replay."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.find_spec('job_scheduler')
        self.assertIsNotNone(spec,'Durable job_scheduler is not implemented')
        from job_scheduler import Scheduler
        self.Scheduler=Scheduler
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'jobs.sqlite3'
        self.release=threading.Event();self.started=threading.Event();self.calls=[]
        def execute(op,args):
            self.calls.append(args['value'])
            if args.get('wait'):
                self.started.set();self.release.wait(3)
            return {'value':args['value']}
        self.scheduler=Scheduler(self.path,execute,workers=2,max_pending=2,max_output_bytes=256)
    def tearDown(self):
        self.release.set()
        if hasattr(self,'scheduler'):self.scheduler.close()
        if hasattr(self,'temp'):self.temp.cleanup()
    def wait(self,ident):
        until=time.monotonic()+3
        while time.monotonic()<until:
            out=self.scheduler.status(ident)
            if out['status'] not in ('queued','running'):return out
            time.sleep(.01)
        self.fail('Task did not finish')
    def submit(self,ident,value,wait=False,resources=(),timeout=30):
        return self.scheduler.submit(ident,'owned_test',{'value':value,'wait':wait},resources=resources,timeout_seconds=timeout)
    def test_independent_task_and_status_are_responsive_during_long_job(self):
        self.submit('long_job_1',1,True);self.assertTrue(self.started.wait(1))
        start=time.monotonic();self.submit('short_job_2',2)
        self.assertEqual(self.wait('short_job_2')['result'],{'value':2})
        self.assertEqual(self.scheduler.status('long_job_1')['status'],'running')
        self.assertLess(time.monotonic()-start,1)
    def test_resource_conflict_waits_but_independent_work_runs(self):
        self.submit('path_job_1',1,True,['path:/owned/a']);self.assertTrue(self.started.wait(1))
        self.submit('path_job_2',2,resources=['path:/owned/a']);self.submit('path_job_3',3,resources=['path:/owned/b'])
        self.assertEqual(self.wait('path_job_3')['result'],{'value':3})
        self.assertNotIn(2,self.calls)
        self.release.set();self.assertEqual(self.wait('path_job_2')['result'],{'value':2})
    def test_stable_receipt_rejects_id_reuse_and_never_reexecutes(self):
        self.submit('same_job_1',1);self.wait('same_job_1')
        self.assertEqual(self.submit('same_job_1',1)['result'],{'value':1})
        with self.assertRaises(ValueError):self.submit('same_job_1',2)
        self.assertEqual(self.calls,[1])
    def test_queued_cancel_and_backpressure_do_not_execute_work(self):
        self.submit('held_job_1',1,True,['ui']);self.assertTrue(self.started.wait(1))
        self.submit('queue_job_2',2,resources=['ui']);self.submit('queue_job_3',3,resources=['ui'])
        with self.assertRaises(RuntimeError):self.submit('queue_job_4',4,resources=['ui'])
        self.assertEqual(self.scheduler.cancel('queue_job_2')['status'],'cancelled')
        self.assertFalse(self.scheduler.cancel('held_job_1')['cancelled'])
        self.release.set();self.wait('queue_job_3');self.assertNotIn(2,self.calls)
    def test_restart_preserves_results_and_marks_inflight_uncertain(self):
        self.submit('finished_1',1);self.wait('finished_1');self.scheduler.close()
        db=sqlite3.connect(self.path)
        db.execute("UPDATE managed_tasks SET status='running' WHERE id='finished_1'");db.commit();db.close()
        self.scheduler=self.Scheduler(self.path,lambda *_:self.fail('Restart must not replay'))
        self.assertEqual(self.scheduler.status('finished_1')['status'],'uncertain')
        self.assertEqual(self.submit('finished_1',1)['status'],'uncertain')
    def test_expired_waiting_task_never_starts(self):
        self.submit('held_expiry',1,True,['ui']);self.assertTrue(self.started.wait(1))
        self.submit('expires_soon',2,resources=['ui'],timeout=1)
        time.sleep(1.05);self.release.set()
        self.assertEqual(self.wait('expires_soon')['status'],'expired');self.assertNotIn(2,self.calls)
    def test_oversized_result_is_explicit_and_does_not_repeat_effect(self):
        self.submit('large_result','x'*300);out=self.wait('large_result')
        self.assertEqual(out['status'],'completed')
        self.assertTrue(out['result']['truncated'])
        self.submit('large_result','x'*300);self.assertEqual(len(self.calls),1)
    def test_completed_argument_payload_is_discarded_but_receipt_still_prevents_replay(self):
        self.submit('payload_receipt','private-argument');self.wait('payload_receipt')
        db=sqlite3.connect(self.path)
        stored=db.execute("SELECT arguments FROM managed_tasks WHERE id='payload_receipt'").fetchone()[0];db.close()
        self.assertEqual(stored,'{}')
        self.submit('payload_receipt','private-argument');self.assertEqual(self.calls,['private-argument'])

if __name__=='__main__':unittest.main()
