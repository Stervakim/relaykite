import importlib.util,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'pc'))
spec=importlib.util.spec_from_file_location('pc_portable_test_worker',ROOT/'pc/mini_codex_pc.py');pc=importlib.util.module_from_spec(spec);spec.loader.exec_module(pc)
try:import portable_client as client
except ImportError:client=None

class PCPortableTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(client,'Mini PC Portable client not implemented')
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.scope='11111111-1111-1111-1111-111111111111';self.config={'capabilities':['terminal'],'roots':[str(self.base)]}
 def tearDown(self):
  if hasattr(self,'tmp'):self.tmp.cleanup()
 def test_all_twelve_operations_forward_once_and_translate_target_identity(self):
  for op in client.OPERATIONS:
   args={'request_id':'mini_pc_fixture01'}
   if op in ('result','reconcile'):args['target_request_id']='original_request01'
   # Use transport seam independently of schema-valid invocation fixtures.
   with patch.object(client,'request',return_value={'ok':True}) as call,patch.object(client,'validate'):
    out=pc.execute('pc_use_'+op,args,self.config,self.base,scope=self.scope)
    self.assertFalse(out['isError']);call.assert_called_once()
    payload=call.call_args.args[0];self.assertEqual(payload['scope'],self.scope);self.assertEqual(payload['request_id'],'mini_pc_fixture01')
    if op in ('result','reconcile'):self.assertEqual(payload['args']['request_id'],'original_request01')
 def test_missing_grant_is_rejected_before_transport(self):
  with patch.object(client,'request') as request:
   with self.assertRaises(PermissionError):pc.execute('pc_use_capabilities',{'request_id':'mini_pc_caps001'},{'capabilities':[]},self.base,scope=self.scope)
   request.assert_not_called()
 def test_nested_batch_image_preserves_receipt_and_engine_error(self):
  receipt={'status':'stopped','completed':1,'observation':{'screenshot':{'mime_type':'image/png','base64':'eA=='}}}
  args={'request_id':'mini_pc_batch01','session_id':'owned','observation_id':'fresh','steps':[{'action':{'kind':'key','key':'Tab'}}]}
  with patch.object(client,'request',return_value=receipt):out=pc.execute('pc_use_batch',args,self.config,self.base,scope=self.scope)
  self.assertTrue(out['isError']);self.assertEqual(out['content'][1]['type'],'image');self.assertNotIn('base64',out['content'][0]['text']);self.assertEqual(out['structuredContent']['completed'],1)
 def test_invalid_id_and_empty_batch_never_reach_transport(self):
  with patch.object(client,'request') as request:
   for args in ({'request_id':'bad id!!!'},{'request_id':'valid_request01','session_id':'owned','observation_id':'fresh','steps':[]}):
    with self.assertRaises(ValueError):pc.execute('pc_use_batch',args,self.config,self.base,scope=self.scope)
   request.assert_not_called()
 def test_journal_reuses_original_envelope_and_marks_unknown_transport(self):
  journal=pc.Journal(self.base)
  job={'id':'12345678-1234-1234-1234-123456789abc','tool':'pc_use_capabilities','arguments':{'request_id':'mini_pc_caps001'},'expires_at':time.time()+120}
  try:
   with patch.object(client,'request',side_effect=OSError('lost response')) as request:
    first=journal.execute_job(self.scope,job,self.config,self.base);second=journal.execute_job(self.scope,job,self.config,self.base)
   request.assert_called_once();self.assertEqual(first,second);self.assertEqual(first[0],'uncertain')
  finally:journal.db.close()
 def test_endpoint_rejects_remote_address_and_never_uses_environment_proxy(self):
  fake=self.base/'CodakiPortableUseIPC';fake.mkdir();path=fake/'endpoint.json'
  with patch.dict('os.environ',{'LOCALAPPDATA':str(self.base)}):
   for url in ('http://example.com/rpc','http://127.0.0.1:1234/rpc?secret=x','http://x:y@127.0.0.1:1234/rpc'):
    path.write_text(json.dumps({'version':1,'url':url,'token':'a'*64}))
    with self.assertRaises(ValueError):client.descriptor()
   path.write_text(json.dumps({'version':1,'url':'http://127.0.0.1:1234/rpc','token':'a'*64}))
   with patch.object(client.urllib.request,'build_opener') as build:
    build.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"ok":true}'
    self.assertTrue(client.request({'test':True})['ok'])
   self.assertEqual(build.call_args.args[0].proxies,{})
 def test_oversized_image_is_disclosed_without_erasing_applied_receipt(self):
  out=client.envelope({'applied':True,'observation':{'screenshot':{'base64':'a'*client.LIMIT,'mime_type':'image/png'}}})
  self.assertTrue(out['structuredContent']['applied'])
  self.assertEqual([x['type'] for x in out['content']],['text'])
  self.assertIn('transport_warning',out['structuredContent'])
  self.assertLessEqual(len(json.dumps(out).encode()),client.LIMIT)
 def test_status_does_not_advertise_ui_when_effective_grant_is_absent(self):
  with patch.object(client,'descriptor',return_value={}):
   denied=pc.execute('pc_status',{}, {'capabilities':[]},self.base)['portable_use']
   self.assertEqual(denied['operations'],[]);self.assertFalse(denied['available'])
   allowed=pc.execute('pc_status',{},self.config,self.base)['portable_use']
   self.assertEqual(len(allowed['operations']),12);self.assertTrue(allowed['grant_enabled'])

if __name__=='__main__':unittest.main()
