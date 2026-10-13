import copy,json,tempfile,unittest
from pathlib import Path
from portable.windows_sessions import WindowsSessions
from portable.engine import UseError
from portable.journal import digest
from portable.mcp import handle,TOOLS
from test_windows_sessions import Backend

class WindowsBatchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'journal.sqlite3';self.now=0;self.seq=0
  self.m=WindowsSessions(Backend,self.path,clock=lambda:self.now)
  self.a=self.call('session_start',{'target':'1'})['session_id'];self.b=self.call('session_start',{'target':'2'})['session_id']
 def tearDown(self):self.m.close();self.tmp.cleanup()
 def call(self,op,args,rid=None):
  self.seq+=1;return self.m.execute(op,args,rid or 'winbatch_%08d'%self.seq)
 def observe(self,sid):return self.call('observe',{'session_id':sid})
 def recipe(self,steps=None,observation=None):
  obs=observation or self.observe(self.a)
  return {'session_id':self.a,'observation_id':obs['observation_id'],'steps':steps or [{'action':{'kind':'click','selector':{'text':'Button'}}}]*2}
 def test_scoped_batch_preserves_other_lease_and_never_replays(self):
  other=self.observe(self.b);args=self.recipe();result=self.call('batch',args,'winbatch_stable_01')
  self.assertEqual((result['status'],result['completed']),('completed',2))
  self.assertEqual(result['observation']['session_id'],self.a)
  self.assertEqual(len(self.m.sessions[self.a].backend.actions),2)
  self.assertEqual(self.call('batch',args,'winbatch_stable_01'),result)
  self.assertEqual(len(self.m.sessions[self.a].backend.actions),2)
  self.assertIn(self.b,self.m.sessions)
  with self.assertRaises(UseError) as e:self.call('action',{'session_id':self.b,'observation_id':other['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}})
  self.assertEqual(e.exception.code,'STALE')
  self.call('session_stop',{'session_id':self.a});self.assertEqual(self.observe(self.b)['target'],'2')
 def test_cross_session_observation_rejected_before_input(self):
  args=self.recipe(observation=self.observe(self.b))
  with self.assertRaises(UseError) as e:self.call('batch',args)
  self.assertEqual(e.exception.code,'STALE');self.assertEqual(self.m.sessions[self.a].backend.actions,[])
 def test_entire_recipe_validation_precedes_first_step(self):
  args=self.recipe([{'action':{'kind':'click','selector':{'text':'Button'}}},{'action':{'kind':'click','selector':{'node_id':'1/0'}}}])
  with self.assertRaises(UseError):self.call('batch',args)
  self.assertEqual(self.m.sessions[self.a].backend.actions,[])
 def test_ambiguity_stops_without_choosing_target_or_running_later_steps(self):
  backend=self.m.sessions[self.a].backend;original=backend.snapshot
  def duplicate(screenshot=False):
   data=original(screenshot);data['nodes'].append({**data['nodes'][0],'node_id':'1/1'});return data
  backend.snapshot=duplicate
  r=self.call('batch',self.recipe())
  self.assertEqual((r['status'],r['completed'],r['code']),('stopped',0,'AMBIGUOUS'));self.assertEqual(backend.actions,[])
 def test_unknown_second_step_keeps_first_and_reconciles_child_only(self):
  backend=self.m.sessions[self.a].backend;original=backend.action
  def lost(action,observation):
   if len(backend.actions)==1:backend.actions.append(copy.deepcopy(action));raise RuntimeError('lost receipt')
   return original(action,observation)
  backend.action=lost;args=self.recipe([{'action':{'kind':'click','selector':{'text':'Button'}}}]*3)
  r=self.call('batch',args,'winbatch_uncertain_01')
  self.assertEqual((r['status'],r['completed'],r['code']),('stopped',1,'UNCERTAIN'));self.assertEqual(len(backend.actions),2)
  child=r['steps'][1]['request_id'];self.assertEqual(self.call('result',{'request_id':child})['status'],'uncertain')
  self.assertEqual(self.call('batch',args,'winbatch_uncertain_01'),r);self.assertEqual(len(backend.actions),2)
  self.call('reconcile',{'request_id':child,'outcome':'applied','evidence':'Observed test click effect'})
  self.assertEqual(self.call('diagnostics',{})['uncertain_requests'],[])
 def test_deadline_retains_applied_step_and_never_starts_the_next(self):
  backend=self.m.sessions[self.a].backend;original=backend.action
  def slow(action,observation):r=original(action,observation);self.now+=1;return r
  backend.action=slow;r=self.call('batch',{**self.recipe(),'timeout_ms':500})
  self.assertEqual((r['status'],r['completed'],r['code']),('stopped',1,'TIMEOUT'));self.assertEqual(len(backend.actions),1)
 def test_restart_keeps_parent_progress_and_inflight_identity(self):
  backend=self.m.sessions[self.a].backend;original=backend.action
  def crash(action,observation):
   if len(backend.actions)==1:raise KeyboardInterrupt('simulated crash')
   return original(action,observation)
  backend.action=crash;args=self.recipe()
  with self.assertRaises(KeyboardInterrupt):self.call('batch',args,'winbatch_crash_01')
  self.m.close();self.m=WindowsSessions(Backend,self.path,clock=lambda:self.now)
  parent=self.call('result',{'request_id':'winbatch_crash_01'})
  self.assertEqual(parent['status'],'uncertain');self.assertEqual(parent['result']['completed'],1)
  child=parent['result']['inflight_request_id'];self.assertEqual(self.call('result',{'request_id':child})['status'],'uncertain')
  with self.assertRaises(UseError):self.call('batch',args,'winbatch_crash_01')
 def test_capability_and_mcp_expose_batch_and_nested_image(self):
  caps=self.call('capabilities',{});self.assertTrue(caps['batch']);self.assertEqual(caps['max_batch_steps'],12)
  self.assertIn('use_batch',{t['name'] for t in TOOLS})
  raw={'status':'completed','observation':{'screenshot':{'base64':'aGVsbG8=','mime_type':'image/png'}}}
  from portable.mcp import content
  result=content(raw);self.assertEqual(result['content'][1]['type'],'image');self.assertNotIn('base64',result['content'][0]['text'])
 def test_native_impossible_later_step_is_rejected_before_first_input(self):
  from portable.windows_native import WindowsBackend
  from test_windows_native import Driver
  manager=WindowsSessions(lambda:WindowsBackend(Driver()),Path(self.tmp.name)/'native-preflight.sqlite3')
  try:
   for index,bad in enumerate(({'kind':'key','key':'{ENTER}'},{'kind':'scroll','selector':{'resource_id':'field'},'scroll_y':-1},{'kind':'click','selector':{'resource_id':'field'},'button':'right'})):
    sid=manager.execute('session_start',{'target':'7'},'native_start_%04d'%index)['session_id']
    obs=manager.execute('observe',{'session_id':sid},'native_observe_%04d'%index)
    value=manager.sessions[sid].backend.driver.edit.iface_value;old=value.CurrentValue
    recipe={'session_id':sid,'observation_id':obs['observation_id'],'steps':[{'action':{'kind':'set_text','selector':{'resource_id':'field'},'text':'changed'}},{'action':bad}]}
    with self.assertRaises(UseError):manager.execute('batch',recipe,'native_batch_%04d'%index)
    self.assertEqual(value.CurrentValue,old)
    manager.execute('session_stop',{'session_id':sid},'native_stop_%04d'%index)
  finally:manager.close()
 def test_semantic_batch_survives_caret_image_changes_and_reports_editability(self):
  from portable.windows_native import WindowsBackend
  from test_windows_native import Driver
  manager=WindowsSessions(lambda:WindowsBackend(Driver()),Path(self.tmp.name)/'caret.sqlite3')
  try:
   sid=manager.execute('session_start',{'target':'7'},'caret_start_0001')['session_id']
   obs=manager.execute('observe',{'session_id':sid,'screenshot':True},'caret_observe01')
   field=next(n for n in obs['nodes'] if n['resource_id']=='field');self.assertTrue(field.get('editable'))
   manager.sessions[sid].backend.driver.image=b'PNG caret blink changed'
   result=manager.execute('batch',{'session_id':sid,'observation_id':obs['observation_id'],'steps':[{'action':{'kind':'set_text','selector':{'resource_id':'field'},'text':'semantic input'}}]},'caret_batch0001')
   self.assertEqual(result['completed'],1);self.assertEqual(manager.sessions[sid].backend.driver.edit.iface_value.CurrentValue,'semantic input')
  finally:manager.close()

if __name__=='__main__':unittest.main()
