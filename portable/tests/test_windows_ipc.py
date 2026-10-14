import copy,json,tempfile,threading,time,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from portable.windows_sessions import WindowsSessions
from test_windows_sessions import Backend
try:from portable.windows_ipc import Boundary,LocalRPC,encoded_id
except ImportError:Boundary=LocalRPC=encoded_id=None

class WindowsIPCTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(Boundary,'Windows IPC is not implemented')
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.engine=WindowsSessions(Backend,self.root/'journal.sqlite3')
  self.boundary=Boundary(self.engine,self.root/'bridge.sqlite3')
  self.scope='11111111-1111-1111-1111-111111111111';self.other='22222222-2222-2222-2222-222222222222'
 def tearDown(self):
  if hasattr(self,'boundary'):self.boundary.close();self.engine.close();self.tmp.cleanup()
 def call(self,op,args,rid,scope=None):return self.boundary.execute({'scope':scope or self.scope,'op':op,'args':args,'request_id':rid})
 def start(self,target='1',scope=None):return self.call('session_start',{'target':target},'ipc_start_0001',scope)['session_id']
 def test_ids_are_namespaced_and_foreign_session_never_reaches_engine(self):
  a=self.start();b=self.start('2',self.other)
  self.assertNotEqual(a,b)
  r=self.call('observe',{'session_id':a},'ipc_observe_0001',self.other)
  self.assertEqual(r['code'],'SESSION_SCOPE');self.assertEqual(self.engine.sessions[a].backend.actions,[])
  diag=self.call('diagnostics',{},'ipc_diagnostics_1')
  self.assertEqual([x['session_id'] for x in diag['sessions']],[a])
  self.assertNotEqual(encoded_id(self.scope,'same_request_01'),encoded_id(self.other,'same_request_01'))
 def test_batch_child_result_and_reconcile_belong_to_original_scope(self):
  sid=self.start();o=self.call('observe',{'session_id':sid},'ipc_observe_0001');backend=self.engine.sessions[sid].backend
  def lost(action,observation):raise RuntimeError('lost receipt')
  backend.action=lost
  r=self.call('batch',{'session_id':sid,'observation_id':o['observation_id'],'steps':[{'action':{'kind':'click','selector':{'text':'Button'}}}]},'ipc_batch_0001')
  child=r['steps'][0]['request_id'];self.assertEqual(r['code'],'UNCERTAIN')
  self.assertEqual(self.call('result',{'request_id':child},'ipc_result_0001')['status'],'uncertain')
  self.assertEqual(self.call('result',{'request_id':child},'ipc_result_0001',self.other)['code'],'REQUEST_SCOPE')
  self.assertTrue(self.call('reconcile',{'request_id':child,'outcome':'not_applied','evidence':'No effect on owned test target'},'ipc_reconcile_01')['replayed'] is False)
 def test_duplicate_input_returns_original_receipt(self):
  sid=self.start();o=self.call('observe',{'session_id':sid},'ipc_observe_0001')
  args={'session_id':sid,'observation_id':o['observation_id'],'action':{'kind':'click','selector':{'text':'Button'}}}
  first=self.call('action',args,'ipc_action_0001');self.assertTrue(first['applied'])
  self.assertEqual(self.call('action',args,'ipc_action_0001'),first)
  self.assertEqual(len(self.engine.sessions[sid].backend.actions),1)
 def test_http_auth_and_main_thread_pump(self):
  rpc=LocalRPC(self.boundary,self.root/'endpoint.json',timeout=2).start();desc=json.loads((self.root/'endpoint.json').read_text())
  output=[];errors=[]
  def client(token):
   payload={'scope':self.scope,'op':'capabilities','args':{},'request_id':'ipc_http_caps01'}
   request=urllib.request.Request(desc['url'],data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(request,timeout=4) as response:output.append(json.load(response))
   except urllib.error.HTTPError as error:errors.append(error.code)
  try:
   worker=threading.Thread(target=client,args=('wrong',));worker.start();worker.join(2)
   self.assertEqual(errors,[403]);self.assertTrue(rpc.pending.empty())
   execution_threads=[];original=self.boundary.execute
   def tracked(request):execution_threads.append(threading.get_ident());return original(request)
   self.boundary.execute=tracked
   worker=threading.Thread(target=client,args=(desc['token'],));worker.start()
   deadline=time.monotonic()+2
   while worker.is_alive() and time.monotonic()<deadline:rpc.pump();time.sleep(.005)
   worker.join(1);self.assertEqual(execution_threads,[threading.get_ident()]);self.assertTrue(output[0]['batch'])
  finally:rpc.close()
 def test_expired_queued_rpc_does_not_execute_later(self):
  rpc=LocalRPC(self.boundary,self.root/'endpoint.json',timeout=.05).start();desc=json.loads((self.root/'endpoint.json').read_text());out=[]
  def client():
   req=urllib.request.Request(desc['url'],data=json.dumps({'scope':self.scope,'op':'session_start','args':{'target':'1'},'request_id':'ipc_expired_001'}).encode(),headers={'Authorization':'Bearer '+desc['token']})
   with urllib.request.urlopen(req,timeout=2) as response:out.append(json.load(response))
  try:
   thread=threading.Thread(target=client);thread.start();thread.join(1)
   self.assertFalse(thread.is_alive());self.assertEqual(out[0]['code'],'IPC_DEADLINE');rpc.pump();self.assertEqual(self.engine.sessions,{})
  finally:rpc.close()
 def test_result_limit_drops_image_but_retains_applied_receipt(self):
  from portable.windows_ipc import encode_receipt,RESULT_LIMIT
  data=json.loads(encode_receipt({'applied':True,'observation':{'screenshot':{'mime_type':'image/png','base64':'a'*RESULT_LIMIT}}}))
  self.assertTrue(data['applied']);self.assertIn('transport_warning',data);self.assertNotIn('screenshot',data['observation'])

if __name__=='__main__':unittest.main()
