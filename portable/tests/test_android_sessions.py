import copy,tempfile,unittest,threading,time
from pathlib import Path
from unittest.mock import patch
from portable.engine import UseError

class Fake:
    seq=0
    def __init__(self,*args,**kwargs):
        self.target=None;self.actions=[];self.inspector=kwargs.get('inspector');self.stopped=False
    def capabilities(self):return {'platform':'android','actions':['click','key']}
    def apps(self):return [{'app_id':'owned.app/Main','name':'Owned app'}, {'app_id':'owned.app/Other','name':'Other activity'}]
    def start(self,target=None,lease_seconds=300):
        if target is not None:raise UseError('No external target')
        Fake.seq+=1;self.target=str(Fake.seq);return {'target':self.target}
    def stop(self):self.stopped=True;self.target=None;return {'stopped':True}
    def extend(self,n):pass
    def _lease(self,n):pass
    def stop_inspector(self):self.stopped=True
    def diagnostics(self):return {'display':self.target}
    def snapshot(self,screenshot=False):
        return {'target':self.target,'geometry':{'width':720,'height':1280},'windows':[{'window_id':self.target}],
                'nodes':[{'node_id':self.target+'/1','window_id':self.target,'text':'Own Button','role':'Button','enabled':True,'visible':True,'bounds':[0,0,30,30],'actions':['click']}]}
    def action(self,a,obs):self.actions.append(copy.deepcopy(a));return {'applied':True,'display':self.target}
    def launch(self,app):return {'requested':app}
    def open_file(self,app,uri,mime_type):return {'requested':app,'uri':uri,'mime_type':mime_type,'display':self.target}

class AndroidSessionsTests(unittest.TestCase):
    def setUp(self):
        from portable.android_sessions import AndroidSessions
        self.tmp=tempfile.TemporaryDirectory();self.now=0;self.seq=0
        self.manager=AndroidSessions(Path(self.tmp.name)/'journal.sqlite3',clock=lambda:self.now,backend_class=Fake,owner_factory=lambda token:token)
    def tearDown(self):self.manager.close();self.tmp.cleanup()
    def call(self,op,args={},rid=None):
        self.seq+=1;return self.manager.execute(op,args,rid or 'android_test_%08d'%self.seq)
    def test_two_displays_and_independent_stop(self):
        a=self.call('session_start');b=self.call('session_start')
        self.assertNotEqual(a['target'],b['target']);self.call('session_stop',{'session_id':a['session_id']})
        self.assertEqual(self.call('observe',{'session_id':b['session_id']})['target'],b['target'])
        self.assertFalse(self.manager.inspector.stopped)
        self.call('session_stop',{'session_id':b['session_id']});self.assertTrue(self.manager.inspector.stopped)
    def test_package_cannot_move_between_owned_displays_until_release(self):
        a=self.call('session_start')['session_id'];b=self.call('session_start')['session_id']
        self.call('launch',{'session_id':a,'app_id':'owned.app/Main'})
        with self.assertRaises(UseError) as conflict:
            self.call('launch',{'session_id':b,'app_id':'owned.app/Other'})
        self.assertEqual(conflict.exception.code,'RESOURCE_CONFLICT')
        self.assertEqual(self.call('observe',{'session_id':a})['session_id'],a)
        self.call('session_stop',{'session_id':a})
        self.assertEqual(self.call('launch',{'session_id':b,'app_id':'owned.app/Main'})['requested'],'owned.app/Main')
    def test_awaited_batch_does_not_hold_independent_display_read(self):
        self.manager.clock=time.monotonic
        a=self.call('session_start');b=self.call('session_start')
        obs=self.call('observe',{'session_id':a['session_id']})
        waiting=threading.Event();done=[];original=Fake.snapshot
        def snapshot(backend,screenshot=False):
            if backend.target==a['target']:waiting.set()
            return original(backend,screenshot)
        args={'session_id':a['session_id'],'observation_id':obs['observation_id'],
              'steps':[{'wait_for':{'text':'Not present'},'wait_timeout_ms':1200,'action':{'kind':'click','selector':{'text':'Own Button'}}}]}
        def batch():done.append(self.manager.execute('batch',args,'concurrent_android_batch'))
        with patch.object(Fake,'snapshot',snapshot):
            thread=threading.Thread(target=batch);thread.start();self.assertTrue(waiting.wait(1))
            start=time.monotonic();result=self.call('observe',{'session_id':b['session_id']});elapsed=time.monotonic()-start
            thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(result['target'],b['target'])
        self.assertLess(elapsed,.5,'Independent read was held by a wait in another batch')
        self.assertEqual(done[0]['status'],'stopped');self.assertEqual(done[0]['completed'],0)
    def test_scoped_file_open_is_journaled_and_conflicts_with_other_package_lease(self):
        a=self.call('session_start');b=self.call('session_start')
        args={'session_id':a['session_id'],'app_id':'owned.app/Main','uri':'content://org.relaykite.runtime.files/0123456789abcdef0123456789abcdef.txt','mime_type':'text/plain'}
        first=self.call('file_open',args,'file_open_receipt_1')
        self.assertEqual(self.call('file_open',args,'file_open_receipt_1'),first)
        self.assertEqual(first['display'],a['target'])
        with self.assertRaises(UseError) as conflict:self.call('file_open',{**args,'session_id':b['session_id']})
        self.assertEqual(conflict.exception.code,'RESOURCE_CONFLICT')
    def test_scoped_file_open_preserves_read_grant_in_final_intent_flags(self):
        from portable.android import AndroidBackend
        class AndroidIntentBoundary:
            flags=0
            def run(self,*args):
                self.argv=args
                for i,value in enumerate(args):
                    if value=='--grant-read-uri-permission':self.flags|=1
                    if value=='-f':self.flags=int(args[i+1],0)
                return 'Status: ok'
        backend=AndroidBackend.__new__(AndroidBackend);boundary=AndroidIntentBoundary();backend.legacy=boundary
        backend.verified_display=lambda:17
        result=backend.open_file('owned.app/Main','content://org.relaykite.runtime.files/0123456789abcdef0123456789abcdef.txt','text/plain')
        self.assertEqual(result['display'],17);self.assertEqual(boundary.flags&1,1,'The later -f argument erased the scoped URI grant')
        self.assertIn('org.relaykite.runtime/.FileLaunchActivity',boundary.argv)
        self.assertEqual(boundary.argv[-3:],('--es','target','owned.app/Main'))
    def test_independent_expiry_and_capacity(self):
        a=self.call('session_start',{'lease_seconds':30});b=self.call('session_start',{'lease_seconds':90});self.call('session_start')
        with self.assertRaises(UseError):self.call('session_start')
        self.now=31;self.manager.expire()
        with self.assertRaises(UseError):self.call('observe',{'session_id':a['session_id']})
        self.assertEqual(self.call('observe',{'session_id':b['session_id']})['target'],b['target'])
        self.call('session_start')
    def test_cross_observation_duplicate_batch_and_global_uncertainty(self):
        a=self.call('session_start')['session_id'];b=self.call('session_start')['session_id']
        oa=self.call('observe',{'session_id':a});ob=self.call('observe',{'session_id':b})
        with self.assertRaises(UseError):self.call('action',{'session_id':b,'observation_id':oa['observation_id'],'action':{'kind':'click','selector':{'text':'Own Button'}}})
        oa=self.call('observe',{'session_id':a})
        args={'session_id':a,'observation_id':oa['observation_id'],'steps':[{'action':{'kind':'click','selector':{'text':'Own Button'}}}]}
        r=self.call('batch',args,'android_batch_repeat');self.assertEqual(r['completed'],1)
        self.assertEqual(self.call('batch',args,'android_batch_repeat'),r);self.assertEqual(len(self.manager.sessions[a].backend.actions),1)
        ob=self.call('observe',{'session_id':b})
        def lost(*args):raise RuntimeError('lost')
        self.manager.sessions[b].backend.action=lost
        with self.assertRaises(UseError) as e:self.call('action',{'session_id':b,'observation_id':ob['observation_id'],'action':{'kind':'click','selector':{'text':'Own Button'}}},'android_unknown_01')
        self.assertEqual(e.exception.code,'UNCERTAIN')
        with self.assertRaises(UseError) as e:self.call('session_start')
        self.assertEqual(e.exception.code,'BLOCKED')
    def test_capabilities_and_diagnostics(self):
        c=self.call('capabilities');self.assertEqual(c['max_sessions'],3);self.assertTrue(c['parallel_sessions']);self.assertEqual(c['session_scope'],'virtual_display')
        self.call('session_start');self.assertEqual(len(self.call('diagnostics')['sessions']),1)
    def test_owners_do_not_mutate_global_legacy(self):
        from portable import legacy_display as legacy
        from portable.android_sessions import make_owner
        a=make_owner('a'*32);b=make_owner('b'*32)
        self.assertNotEqual(a.HOME,b.HOME);self.assertEqual(legacy.NAME,'CodakiPortableUse')
        self.assertEqual(a.ENGINE_JAR,legacy.ENGINE_JAR);self.assertNotEqual(a.ENGINE_PID,b.ENGINE_PID)
        with self.assertRaises(ValueError):make_owner('../bad')
    def test_process_record_rejects_reused_generation_and_other_owner(self):
        from portable.android_sessions import make_owner
        import json
        owner=make_owner('c'*32);owner.ENGINE_PID=Path(self.tmp.name)/'owner.pid'
        proc=Path(self.tmp.name)/'proc/55';proc.mkdir(parents=True)
        stat='55 (app process) '+' '.join(['0']*19+['12345'])
        (proc/'stat').write_text(stat);(proc/'status').write_text('Uid:\t0\t0\t0\t0\n')
        argv=['/system/bin/app_process',owner.ENGINE_CLASS,owner.NAME,str(owner.HOME/'lease-deadline')]
        (proc/'cmdline').write_bytes(b'\0'.join(x.encode() for x in argv)+b'\0')
        owner.ENGINE_PID.write_text(json.dumps({'pid':55,'start_ticks':'12345'}))
        real_path=Path
        def mapped(*parts):
            if parts and str(parts[0])=='/proc':return real_path(self.tmp.name)/'proc'/real_path(*parts[1:])
            return real_path(*parts)
        with patch.object(owner,'Path',side_effect=mapped):
            self.assertEqual(owner.engine_pid(),55)
            (proc/'stat').write_text(stat.replace('12345','12346'))
            with self.assertRaises(owner.Denied):owner.engine_pid()
            (proc/'stat').write_text(stat)
            (proc/'cmdline').write_bytes(b'\0'.join(x.encode() for x in argv[:-2]+['CodakiPortableUse_'+('d'*32),argv[-1]])+b'\0')
            with self.assertRaises(owner.Denied):owner.engine_pid()

if __name__=='__main__':unittest.main()
