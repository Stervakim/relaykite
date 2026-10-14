import tempfile,unittest
from pathlib import Path
from mode_coordinator import Coordinator

class Backend:
    def __init__(self):self.calls=[];self.fail=None
    def effect(self,name,*args):
        self.calls.append((name,*args))
        if self.fail==name:raise RuntimeError('Owned fixture interruption')
    def preflight(self,*args):self.effect('preflight',*args)
    def stop(self,*args):self.effect('stop',*args)
    def prepare(self,*args):self.effect('prepare',*args)
    def start(self,*args):self.effect('start',*args)
    def reconcile(self,*args):self.effect('reconcile',*args)

class CoordinatorTests(unittest.TestCase):
    def test_explicit_three_modes_and_duplicate_request_never_repeat_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=Backend();c=Coordinator(Path(tmp)/'mode.sqlite3',backend)
            try:
                for i,mode in enumerate(('app','root-termux','root')):
                    ident='owned_mode_'+str(i);out=c.change(ident,mode);self.assertEqual(out['status'],'completed');self.assertEqual(c.state()['mode'],mode)
                    count=len(backend.calls);self.assertEqual(c.change(ident,mode),out);self.assertEqual(len(backend.calls),count)
                self.assertEqual(c.state()['epoch'],3)
                with self.assertRaises(ValueError):c.change('owned_mode_0','root')
            finally:c.close()
    def test_failed_start_commits_new_authority_and_requires_reconcile_instead_of_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=Backend();backend.fail='start';path=Path(tmp)/'mode.sqlite3';c=Coordinator(path,backend)
            out=c.change('owned_failed_start','app');self.assertEqual(out['status'],'uncertain');self.assertEqual(out['committed'],1);self.assertEqual(c.state()['mode'],'app');c.close()
            c=Coordinator(path,backend)
            try:
                count=len(backend.calls);self.assertEqual(c.change('owned_failed_start','app')['status'],'uncertain');self.assertEqual(len(backend.calls),count)
                with self.assertRaises(RuntimeError):c.change('owned_next_change','root')
                backend.fail=None;c.reconcile('owned_failed_start');self.assertIsNone(c.state()['uncertain_request'])
                self.assertEqual(backend.calls[-1],('reconcile','app'))
            finally:c.close()
    def test_copy_failure_retains_original_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=Backend();backend.fail='prepare';c=Coordinator(Path(tmp)/'mode.sqlite3',backend)
            try:
                out=c.change('owned_failed_copy','app');self.assertEqual(out['status'],'uncertain');self.assertEqual(out['committed'],0);self.assertEqual(c.state()['mode'],'root')
                self.assertNotIn(('start','app'),backend.calls)
            finally:c.close()
    def test_owner_stop_survives_reopen_and_does_not_start_a_worker_during_reconcile(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=Backend();path=Path(tmp)/'mode.sqlite3';c=Coordinator(path,backend)
            out=c.stop('owned_stop_request');self.assertEqual(out['status'],'completed');self.assertFalse(c.state()['enabled']);c.close()
            c=Coordinator(path,backend)
            try:
                self.assertFalse(c.state()['enabled']);count=len(backend.calls);self.assertEqual(c.stop('owned_stop_request'),out);self.assertEqual(count,len(backend.calls))
                self.assertEqual(c.change('owned_resume_request','root')['status'],'completed');self.assertTrue(c.state()['enabled'])
            finally:c.close()

if __name__=='__main__':unittest.main()
