import base64,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import native_phone as n
import portable_tools as p

class PortableToolsTests(unittest.TestCase):
 def test_every_installed_operation_forwards_once_with_original_id(self):
  for op in p.OPERATIONS:
   arguments={'request_id':'fixture_request_001'}
   if op in ('result','reconcile'):arguments['target_request_id']='original_child_001'
   with patch('portable_peer.call',return_value={'ok':True}) as call:
    result=p.invoke(op,arguments)
    self.assertFalse(result['isError']);call.assert_called_once()
    self.assertEqual(call.call_args.args[0],op);self.assertEqual(call.call_args.args[2],'fixture_request_001')
    if op in ('result','reconcile'):self.assertEqual(call.call_args.args[1]['request_id'],'original_child_001')
 def test_nested_batch_image_is_a_real_mcp_image_not_base64_text(self):
  image={'base64':base64.b64encode(b'fixture-image').decode(),'mime_type':'image/png'}
  with patch('portable_peer.call',return_value={'status':'stopped','completed':1,'observation':{'screenshot':image,'nodes':[]}}):
   result=p.invoke('batch',{'request_id':'fixture_request_002'})
  self.assertTrue(result['isError']);self.assertEqual(result['content'][1],{'type':'image','data':image['base64'],'mimeType':'image/png'})
  self.assertNotIn(image['base64'],result['content'][0]['text'])
 def test_bad_request_identity_never_reaches_ipc(self):
  with patch('portable_peer.call') as call:
   with self.assertRaises(ValueError):p.invoke('action',{'request_id':'../../evil'})
   call.assert_not_called()
 def test_dispatch_preserves_portable_envelope_and_status(self):
  with patch('portable_peer.call',return_value={'error':'inspect outcome','code':'UNCERTAIN'}),patch.object(n,'operational_memory_context',return_value={'state':'ready','notes':[]}):
   result=n.dispatch('phone_use_capabilities',{'request_id':'fixture_request_003'})
  self.assertTrue(result['isError']);self.assertEqual(result['structuredContent']['code'],'UNCERTAIN')
 def test_empty_batch_rejected_before_ipc(self):
  with patch('portable_peer.call') as call:
   result=n.dispatch('phone_use_batch',{'request_id':'fixture_request_004','session_id':'s','observation_id':'o','steps':[]})
   self.assertTrue(result['isError']);call.assert_not_called()
 def test_bad_screenshot_does_not_hide_confirmed_input(self):
  with patch('portable_peer.call',return_value={'applied':True,'observation':{'screenshot':{'mime_type':'bad','base64':'invalid'}}}):
   r=p.invoke('action',{'request_id':'fixture_request_005'})
  self.assertTrue(r['structuredContent']['applied']);self.assertIn('screenshot_warning',r['structuredContent']['observation'])
 def test_transport_failure_discloses_no_replay_requirement(self):
  with patch('portable_peer.call',side_effect=TimeoutError):
   r=p.invoke('action',{'request_id':'fixture_request_006'})
  self.assertTrue(r['isError']);self.assertEqual(r['structuredContent']['code'],'IPC_FAILED')

if __name__=='__main__':unittest.main()
