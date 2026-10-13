import copy, tempfile, unittest
from pathlib import Path
try:
    from portable.engine import Engine, UseError
except ImportError:
    Engine = None
    class UseError(Exception): pass

class Backend:
    def __init__(self):
        self.active=False; self.actions=[]
        self.tree={'target':'7','geometry':{'width':720,'height':1280},'windows':[{'window_id':'7','title':'form'}],
        'nodes':[{'node_id':'7/0','parent_id':None,'window_id':'7','resource_id':'query','text':'abc','role':'EditText','enabled':True,'visible':True,'focused':True,'editable':True,'password':False,'bounds':[5,5,300,50],'actions':['set_text','focus']},
                 {'node_id':'7/1','parent_id':None,'window_id':'7','text':'Open','enabled':True,'visible':True,'bounds':[5,60,100,110],'actions':['click']},
                 {'node_id':'7/2','parent_id':None,'window_id':'7','text':'Open','enabled':True,'visible':True,'bounds':[5,120,100,170],'actions':['click']}]}
    def capabilities(self): return {'platform':'test','actions':['click','set_text','key','gesture']}
    def apps(self): return [{'app_id':'calc','name':'Calculator'}]
    def start(self,**kwargs): self.active=True; return {'target':'7'}
    def stop(self): self.active=False; return {'stopped':True}
    def extend(self,seconds): return {'extended':seconds}
    def snapshot(self,screenshot=False): return copy.deepcopy(self.tree)
    def action(self,action,observation):
        self.actions.append(copy.deepcopy(action))
        if action['kind']=='set_text': self.tree['nodes'][0]['text']=action['text']
        if getattr(self,'fail',False): raise RuntimeError('lost receipt')
        return {'applied':True}
    def launch(self,app_id): return {'launched':app_id}
    def diagnostics(self): return {'active':self.active}

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Engine,'Portable Engine is not implemented')
        self.tmp=tempfile.TemporaryDirectory();self.b=Backend();self.time=100
        self.e=Engine(self.b,Path(self.tmp.name)/'state.sqlite3',clock=lambda:self.time)
        self.session=self.call('session_start',{'lease_seconds':120})['session_id']
    def tearDown(self):
        if hasattr(self,'e'): self.e.close()
        if hasattr(self,'tmp'): self.tmp.cleanup()
    def call(self,op,args,rid=None):
        self.seq=getattr(self,'seq',0)+1
        return self.e.execute(op,args,rid or ('request_%08d'%self.seq))
    def observe(self): return self.call('observe',{'session_id':self.session})
    def act(self,obs,action,rid=None): return self.call('action',{'session_id':self.session,'observation_id':obs['observation_id'],'action':action},rid)
    def test_duplicate_returns_receipt_without_second_input(self):
        o=self.observe();a={'kind':'click','selector':{'node_id':'7/1'}}
        first=self.act(o,a,'same_request_01');second=self.act(o,a,'same_request_01')
        self.assertEqual(first,second);self.assertEqual(len(self.b.actions),1)
    def test_action_returns_updated_observation_usable_for_next_action(self):
        o=self.observe()
        receipt=self.act(o,{'kind':'set_text','selector':{'resource_id':'query'},'text':'новое'})
        fresh=receipt['observation']
        self.assertNotEqual(fresh['observation_id'],o['observation_id'])
        self.assertEqual(fresh['nodes'][0]['text'],'новое')
        self.act(fresh,{'kind':'click','selector':{'node_id':'7/1'}})
        self.assertEqual(len(self.b.actions),2)
    def test_post_action_read_failure_preserves_applied_receipt_and_dedup(self):
        o=self.observe();original=self.b.action
        def act_then_fail_read(action,observation):
            receipt=original(action,observation)
            self.b.snapshot=lambda **kw: (_ for _ in ()).throw(RuntimeError('private screen text'))
            return receipt
        self.b.action=act_then_fail_read
        a={'kind':'click','selector':{'node_id':'7/1'}}
        receipt=self.act(o,a,'post_read_failed_01')
        self.assertTrue(receipt['applied'])
        self.assertEqual(receipt['observation_error']['code'],'BACKEND_FAILED')
        self.assertNotIn('private screen text',str(receipt))
        self.assertEqual(self.act(o,a,'post_read_failed_01'),receipt)
        self.assertFalse(self.call('diagnostics',{})['blocked'])
        self.assertEqual(len(self.b.actions),1)
    def test_crash_during_post_read_keeps_confirmed_input_durable(self):
        o=self.observe();original=self.b.action
        def act_then_exit_during_read(action,observation):
            result=original(action,observation)
            self.b.snapshot=lambda **kw: (_ for _ in ()).throw(SystemExit())
            return result
        self.b.action=act_then_exit_during_read
        a={'kind':'click','selector':{'node_id':'7/1'}}
        with self.assertRaises(SystemExit):self.act(o,a,'post_read_crash_01')
        self.e.close();self.e=Engine(self.b,Path(self.tmp.name)/'state.sqlite3',clock=lambda:self.time)
        receipt=self.act(o,a,'post_read_crash_01')
        self.assertTrue(receipt['applied'])
        self.assertFalse(self.call('diagnostics',{})['blocked'])
        self.assertEqual(len(self.b.actions),1)
    def test_changed_arguments_rejected_for_same_request(self):
        self.call('apps',{},'repeat_request_01')
        with self.assertRaises(UseError): self.call('capabilities',{},'repeat_request_01')
    def test_changed_interface_rejects_old_snapshot_before_action(self):
        o=self.observe();self.b.tree['nodes'][1]['text']='Changed'
        with self.assertRaises(UseError):self.act(o,{'kind':'click','selector':{'node_id':'7/1'}})
        self.assertEqual(self.b.actions,[])
    def test_duplicate_text_needs_occurrence_or_id(self):
        o=self.observe()
        with self.assertRaises(UseError):self.act(o,{'kind':'click','selector':{'text':'Open'}})
        o=self.observe();self.act(o,{'kind':'click','selector':{'text':'Open','occurrence':1}})
        self.assertEqual(self.b.actions[0]['node_id'],'7/2')
    def test_empty_text_clears_field(self):
        o=self.observe();self.act(o,{'kind':'set_text','selector':{'resource_id':'query'},'text':''})
        self.assertEqual(self.b.tree['nodes'][0]['text'],'')
    def test_append_and_insert_preserve_existing_text(self):
        o=self.observe();self.act(o,{'kind':'set_text','selector':{'resource_id':'query'},'text':'Ю','mode':'append'})
        self.assertEqual(self.b.tree['nodes'][0]['text'],'abcЮ')
        o=self.observe();self.act(o,{'kind':'set_text','selector':{'resource_id':'query'},'text':'!','mode':'insert','start':1,'end':2})
        self.assertEqual(self.b.tree['nodes'][0]['text'],'a!cЮ')
    def test_coordinate_must_fit_actual_screen(self):
        o=self.observe()
        with self.assertRaises(UseError):self.act(o,{'kind':'click','x':720,'y':40})
        self.assertEqual(self.b.actions,[])
    def test_append_rejects_unknown_native_value(self):
        self.b.tree['nodes'][0]['text_value_known']=False
        o=self.observe()
        with self.assertRaises(UseError):self.act(o,{'kind':'set_text','selector':{'node_id':'7/0'},'mode':'append','text':'!'})
        self.assertEqual(self.b.actions,[])
    def test_disabled_element_not_clicked(self):
        self.b.tree['nodes'][1]['enabled']=False;o=self.observe()
        with self.assertRaises(UseError): self.act(o,{'kind':'click','selector':{'node_id':'7/1'}})
        self.assertEqual(self.b.actions,[])
    def test_snapshot_consumed_after_action(self):
        o=self.observe();self.act(o,{'kind':'click','selector':{'node_id':'7/1'}})
        with self.assertRaises(UseError):self.act(o,{'kind':'click','selector':{'node_id':'7/2'}})
    def test_expired_lease_closes_owned_session(self):
        self.time=221
        with self.assertRaises(UseError):self.observe()
        self.assertFalse(self.b.active)
    def test_extend_preserves_session(self):
        self.time=210;self.call('session_extend',{'session_id':self.session,'lease_seconds':120})
        self.time=250;self.assertIn('observation_id',self.observe())
    def test_password_never_exposed_or_targeted(self):
        self.b.tree['nodes'][0]['password']=True;o=self.observe()
        self.assertEqual(o['nodes'][0]['text'],'')
        with self.assertRaises(UseError):self.act(o,{'kind':'set_text','selector':{'node_id':'7/0'},'text':'secret'})
    def test_password_removes_raw_accessibility_echo(self):
        self.b.tree['nodes'][0]['password']=True
        self.b.tree['raw_tree']='password secret'
        self.b.tree['accessibility']={'tree':'password secret','document_text':'secret'}
        o=self.observe()
        self.assertNotIn('raw_tree',o);self.assertNotIn('accessibility',o)
    def test_uncertain_blocks_input_but_allows_diagnostics(self):
        o=self.observe()
        self.b.fail=True
        with self.assertRaises(UseError):self.act(o,{'kind':'click','selector':{'node_id':'7/1'}},'lost_request_01')
        self.assertTrue(self.call('diagnostics',{})['blocked'])
        self.call('reconcile',{'request_id':'lost_request_01','outcome':'applied','evidence':'owner checked result'})
        self.assertFalse(self.call('diagnostics',{})['blocked']);self.assertEqual(len(self.b.actions),1)
    def test_semantic_failure_reports_reason_without_replaying_input(self):
        from portable.engine import BackendOutcomeUnknown
        o=self.observe()
        def decline(action,observation):raise BackendOutcomeUnknown('SEMANTIC_NOT_CONFIRMED')
        self.b.action=decline
        with self.assertRaises(UseError) as err:self.act(o,{'kind':'click','selector':{'node_id':'7/1'}},'semantic_declined_01')
        self.assertEqual(err.exception.code,'UNCERTAIN')
        self.assertIn('SEMANTIC_NOT_CONFIRMED',str(err.exception))
        self.assertTrue(self.call('diagnostics',{})['blocked'])
    def test_crash_started_record_is_not_replayed(self):
        self.e.journal.begin('crashed_request_01','action',{'x':1})
        self.e.close();self.e=Engine(self.b,Path(self.tmp.name)/'state.sqlite3',clock=lambda:self.time)
        self.assertTrue(self.call('diagnostics',{})['blocked'])
    def test_launch_only_accepts_discovered_app(self):
        self.call('launch',{'session_id':self.session,'app_id':'calc'})
        with self.assertRaises(UseError):self.call('launch',{'session_id':self.session,'app_id':'shell:rm'})

if __name__=='__main__': unittest.main()
