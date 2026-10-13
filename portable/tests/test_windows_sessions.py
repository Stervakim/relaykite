import copy, tempfile, unittest
from pathlib import Path
from portable.engine import UseError
from portable.windows_sessions import WindowsSessions

class Backend:
    def __init__(self): self.target=None; self.actions=[]
    def capabilities(self): return {'platform':'windows','actions':['click']}
    def apps(self): return [{'app_id':'test','windows':[{'window_id':'1'},{'window_id':'2'}]}]
    def start(self,target=None,lease_seconds=300): self.target=str(target); return {'target':self.target}
    def stop(self): self.target=None; return {'stopped':True,'windows_closed':False}
    def extend(self,n): pass
    def diagnostics(self): return {'target':self.target}
    def snapshot(self,screenshot=False):
        return {'target':self.target,'geometry':{'width':100,'height':100},'windows':[{'window_id':self.target}],
                'nodes':[{'node_id':self.target+'/0','window_id':self.target,'text':'Button','role':'Button','enabled':True,'visible':True,'bounds':[0,0,20,20],'actions':['click']}]}
    def launch(self,app): return {'requested':app,'verify_with_observe':True}
    def action(self,action,observation): self.actions.append(copy.deepcopy(action)); return {'applied':True,'window_id':self.target}

class SessionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.now=0; self.seq=0
        self.manager=WindowsSessions(Backend,Path(self.tmp.name)/'journal.sqlite3',clock=lambda:self.now)
    def tearDown(self): self.manager.close(); self.tmp.cleanup()
    def call(self,op,args,rid=None):
        self.seq+=1; return self.manager.execute(op,args,rid or 'parallel_%08d'%self.seq)
    def start(self,target,lease=300): return self.call('session_start',{'target':target,'lease_seconds':lease})['session_id']
    def observe(self,sid): return self.call('observe',{'session_id':sid})
    def test_two_windows_keep_independent_observations_and_stop(self):
        a=self.start('1'); b=self.start('2'); oa=self.observe(a); ob=self.observe(b)
        result=self.call('action',{'session_id':a,'observation_id':oa['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}},'parallel_action_1')
        self.assertEqual(result['observation']['session_id'],a)
        with self.assertRaises(UseError): self.call('action',{'session_id':b,'observation_id':oa['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}})
        self.call('session_stop',{'session_id':a}); self.assertEqual(self.observe(b)['target'],'2')
        self.assertEqual(len(self.call('diagnostics',{})['sessions']),1)
    def test_duplicate_window_rejected_and_lease_expires_independently(self):
        a=self.start('1',30); b=self.start('2',90)
        with self.assertRaises(UseError): self.start('1')
        self.now=31; self.manager.expire()
        with self.assertRaises(UseError): self.observe(a)
        self.assertEqual(self.observe(b)['target'],'2'); self.start('1')
    def test_request_ids_are_global_and_inputs_never_replay(self):
        a=self.start('1'); b=self.start('2'); obs=self.observe(a)
        args={'session_id':a,'observation_id':obs['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}}
        receipt=self.call('action',args,'parallel_replay_1'); self.assertEqual(self.call('action',args,'parallel_replay_1'),receipt)
        self.assertEqual(len(self.manager.sessions[a].backend.actions),1)
        with self.assertRaises(UseError): self.call('action',{**args,'session_id':b},'parallel_replay_1')
        self.assertEqual(self.call('result',{'request_id':'parallel_replay_1'})['status'],'completed')
    def test_close_releases_all_windows_without_closing_apps(self):
        a=self.start('1'); b=self.start('2'); backends=[self.manager.sessions[s].backend for s in (a,b)]
        self.manager.close(); self.assertTrue(all(x.target is None for x in backends)); self.manager=None
    def test_action_in_one_session_preserves_other_lease_but_expires_observation(self):
        a=self.start('1'); b=self.start('2'); oa=self.observe(a); ob=self.observe(b)
        first=self.call('action',{'session_id':a,'observation_id':oa['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}})
        self.assertEqual(first['window_id'],'1')
        self.assertIn(b,self.manager.sessions)
        with self.assertRaises(UseError) as exc:
            self.call('action',{'session_id':b,'observation_id':ob['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}})
        self.assertEqual(exc.exception.code,'STALE')
        fresh=self.observe(b)
        result=self.call('action',{'session_id':b,'observation_id':fresh['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}})
        self.assertEqual(result['window_id'],'2')
    def test_capacity_is_reclaimed_on_stop(self):
        self.manager.max_sessions=2; a=self.start('1'); self.start('2')
        with self.assertRaises(UseError): self.start('3')
        self.call('session_stop',{'session_id':a}); self.start('3')
    def test_uncertain_input_blocks_every_session_until_checked_reconciliation(self):
        a=self.start('1'); b=self.start('2'); oa=self.observe(a)
        def lost(action,observation): raise RuntimeError('lost receipt')
        self.manager.sessions[a].backend.action=lost
        with self.assertRaises(UseError) as error:
            self.call('action',{'session_id':a,'observation_id':oa['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}},'parallel_lost_01')
        self.assertEqual(error.exception.code,'UNCERTAIN')
        with self.assertRaises(UseError) as error: self.call('session_extend',{'session_id':b})
        self.assertEqual(error.exception.code,'BLOCKED')
        self.assertEqual(self.observe(b)['target'],'2')
        self.call('reconcile',{'request_id':'parallel_lost_01','outcome':'not_applied','evidence':'Verified test backend failed before applying'})
        self.call('session_extend',{'session_id':b})

    def test_repeated_session_stop_returns_original_receipt(self):
        """An acknowledgement retry must not stop the wrong next session."""
        a=self.start('1'); b=self.start('2')
        args={'session_id':a}
        first=self.call('session_stop',args,'parallel_stop_receipt_1')
        second=self.call('session_stop',args,'parallel_stop_receipt_1')
        self.assertEqual(first,second)
        self.assertTrue(first['stopped'])
        self.assertEqual(self.observe(b)['target'],'2')
        self.assertEqual(len(self.manager.sessions),1)

    def test_two_threads_never_overlap_physical_input(self):
        """Windows has one mouse/keyboard even with multiple window leases."""
        import threading, time
        a=self.start('1'); b=self.start('2')
        oa=self.observe(a); ob=self.observe(b)
        guard=threading.Lock()
        active=[0]; peak=[0]; applied=[]; errors=[]
        for sid in (a,b):
            backend=self.manager.sessions[sid].backend
            original=backend.action
            def tracked(action,observation,original=original,sid=sid):
                with guard:
                    active[0]+=1
                    peak[0]=max(peak[0],active[0])
                try:
                    time.sleep(0.03)
                    applied.append(sid)
                    return original(action,observation)
                finally:
                    with guard: active[0]-=1
            backend.action=tracked
        start=threading.Barrier(3)
        def run(sid,observation,rid):
            try:
                start.wait(timeout=2)
                self.manager.execute('action',
                    {'session_id':sid,'observation_id':observation['observation_id'],
                     'action':{'kind':'click','selector':{'text':'Button'}}},rid)
            except Exception as error: errors.append(error)
        workers=[
            threading.Thread(target=run,args=(a,oa,'parallel_thread_a')),
            threading.Thread(target=run,args=(b,ob,'parallel_thread_b')),
        ]
        for thread in workers:thread.start()
        start.wait(timeout=2)
        for thread in workers:thread.join(timeout=4)
        self.assertFalse(any(thread.is_alive() for thread in workers))
        # One request wins the shared input lock. The other must refresh
        # its observation before retrying; no stale input reaches the desktop.
        self.assertEqual(len(applied),1)
        self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],UseError)
        self.assertEqual(errors[0].code,'STALE')
        sid=next(s for s in (a,b) if s not in applied)
        refreshed=self.observe(sid)
        self.call('action',{'session_id':sid,'observation_id':refreshed['observation_id'],
             'action':{'kind':'click','selector':{'text':'Button'}}})
        self.assertEqual(len(applied),2)
        self.assertEqual(peak[0],1)

    def test_closed_window_can_be_released_without_disrupting_other_session(self):
        """A stale or closed HWND must not trap an unrelated valid window."""
        a=self.start('1'); b=self.start('2')
        broken=self.manager.sessions[a].backend
        def closed(screenshot=False):
            raise UseError('Window closed or handle was reused','SESSION_EXPIRED')
        broken.snapshot=closed
        with self.assertRaises(UseError):
            self.observe(a)
        receipt=self.call('session_stop',{'session_id':a})
        self.assertTrue(receipt['stopped'])
        self.assertNotIn(a,self.manager.sessions)
        self.assertEqual(self.observe(b)['target'],'2')

    def test_launch_expires_other_window_observation(self):
        a=self.start('1'); b=self.start('2')
        stale=self.observe(b)
        self.call('launch',{'session_id':a,'app_id':'test'})
        with self.assertRaises(UseError) as exc:
            self.call('action',{'session_id':b,'observation_id':stale['observation_id'],
                'action':{'kind':'click','selector':{'text':'Button'}}})
        self.assertEqual(exc.exception.code,'STALE')
        self.assertEqual(self.observe(b)['target'],'2')

    def tearDown(self):
        if self.manager: self.manager.close()
        self.tmp.cleanup()
