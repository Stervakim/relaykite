import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc'))
from development.android_mcp import AndroidMcp, serve


class PeerFixture:
    def __init__(self): self.calls = []
    def __call__(self, operation, arguments, request_id):
        self.calls.append((operation, arguments, request_id))
        if operation == 'session_start': return {'session_id':'owned-session','target':'3'}
        if operation == 'observe':
            return {'session_id':arguments['session_id'],'observation_id':'fresh-observation',
                    'geometry':{'width':720,'height':1280}, 'windows':[{'title':'Settings','focused':True}],
                    'nodes':[{'node_id':str(n),'text':'secret' if n == 0 else 'Row '+str(n),
                              'password':n == 0,'description':'private' if n == 0 else '',
                              'checked':n==1,'selected':n==2,'focused':n==3,
                              'bounds':[0,0,10,10],'actions':['click']} for n in range(200)],
                    'screenshot':{'base64':'PRIVATE_IMAGE'}}
        if operation == 'action': return {'applied':True}
        if operation == 'session_stop': return {'stopped':True}
        if operation == 'result': return {'status':'completed','result':{'applied':True}}
        if operation == 'reconcile': return {'reconciled':arguments['request_id'],'replayed':False}
        return {'platform':'android','max_sessions':3}


class AndroidMcpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.peer=PeerFixture()
        self.adapter=AndroidMcp(self.root,'a'*32,peer=self.peer)
    def tearDown(self):
        self.adapter.close();self.temp.cleanup()
    def call(self, operation, arguments=None, request_id='request_0001', **kwargs):
        return self.adapter.call({'operation':operation,'arguments':arguments or {},'request_id':request_id,**kwargs})
    def value(self,result): return json.loads(result['content'][0]['text'])['result']
    def test_owned_session_observation_is_bounded_and_masks_protected_text(self):
        self.assertFalse(self.call('session_start')['isError'])
        response=self.call('observe',{'session_id':'owned-session'},'observe_0001')
        text=response['content'][0]['text'];value=self.value(response)
        self.assertLessEqual(len(text),24000)
        self.assertNotIn('PRIVATE_IMAGE',text);self.assertNotIn('secret',text)
        self.assertLess(len(value['nodes']),200);self.assertTrue(value['truncated'])
        self.assertEqual(value['observation_id'],'fresh-observation')
        page=self.value(self.call('observe',{'session_id':'owned-session'},'observe_0001',view={'offset':150,'limit':10}))
        self.assertEqual(page['nodes'][0]['node_id'],'150')

    def test_native_control_state_reaches_the_model(self):
        self.call('session_start')
        value=self.value(self.call('observe',{'session_id':'owned-session'},'states_0001'))
        self.assertTrue(value['nodes'][1]['checked'])
        self.assertTrue(value['nodes'][2]['selected'])
        self.assertTrue(value['nodes'][3]['focused'])
    def test_foreign_sessions_and_screenshot_inputs_are_rejected_without_ipc(self):
        for op,args in (('observe',{'session_id':'foreign'}),('action',{'session_id':'foreign'}),
                        ('session_stop',{'session_id':'foreign'}),('observe',{'session_id':'foreign','screenshot':True})):
            self.assertTrue(self.call(op,args,op+'_foreign')['isError'])
        self.assertEqual(self.peer.calls,[])
    def test_completed_mutations_are_not_replayed_after_restart(self):
        first=self.call('session_start');self.adapter.close()
        self.adapter=AndroidMcp(self.root,'a'*32,peer=self.peer)
        self.assertEqual(self.call('session_start'),first)
        self.assertEqual(len(self.peer.calls),1)
        self.assertFalse(self.call('observe',{'session_id':'owned-session'},'observe_0002')['isError'])
    def test_changed_request_and_different_run_state_are_rejected(self):
        self.call('session_start')
        self.assertTrue(self.call('session_start',{'lease_seconds':120})['isError'])
        with self.assertRaises(ValueError): AndroidMcp(self.root,'b'*32,peer=self.peer)
    def test_unknown_action_is_not_replayed_and_read_only_receipt_can_reconcile(self):
        self.call('session_start')
        original=self.peer
        def lost(op,args,rid):
            if op=='action': original(op,args,rid); raise OSError('IPC outcome unknown')
            return original(op,args,rid)
        self.adapter.peer=lost
        action={'session_id':'owned-session','observation_id':'fresh','action':{'kind':'click'}}
        self.assertTrue(self.call('action',action,'action_0001')['isError'])
        self.assertTrue(self.call('action',action,'action_0001')['isError'])
        self.assertEqual(sum(op=='action' for op,_,_ in self.peer.calls),1)
        result=self.call('result',{'request_id':'action_0001'},'result_0001')
        self.assertFalse(result['isError'])
        mapped=self.peer.calls[-1][1]['request_id']
        self.assertEqual(mapped,self.peer.calls[1][2])
        self.assertFalse(self.call('action',action,'action_0001')['isError'])
        self.assertEqual(sum(op=='action' for op,_,_ in self.peer.calls),1)
    def test_receipt_requests_cannot_address_another_runs_native_request(self):
        self.assertTrue(self.call('result',{'request_id':'not-owned'},'result_0001')['isError'])
        self.assertTrue(self.call('reconcile',{'request_id':'not-owned','outcome':'applied','evidence':'checked'},'reconcile_0001')['isError'])
        self.assertEqual(self.peer.calls,[])
    def test_invalid_view_is_a_tool_error_without_dispatch_or_protocol_failure(self):
        for view in ({'offset':'wrong'},{'limit':0},{'contains':[]},{'unknown':True}):
            self.assertTrue(self.call('capabilities',view=view)['isError'])
        self.assertEqual(self.peer.calls,[])
    def test_diagnostics_do_not_expose_another_sessions_state_or_receipts(self):
        self.call('session_start')
        self.adapter.peer=lambda *_:{'sessions':[{'session_id':'owned-session','target':'3'},
            {'session_id':'other-owner','private':'OTHER_OWNER_DATA'}],
            'uncertain_requests':[{'request_id':'other-request','error':'OTHER_REQUEST_DATA'}]}
        result=self.call('diagnostics',request_id='diagnostics_001')
        text=result['content'][0]['text']
        self.assertNotIn('OTHER_OWNER_DATA',text);self.assertNotIn('OTHER_REQUEST_DATA',text)
        self.assertIn('owned-session',text)
    def test_stdio_protocol_handles_notifications_and_tools_without_external_runtime(self):
        frames=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}},
                {'jsonrpc':'2.0','method':'notifications/initialized'},
                {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'android_use','arguments':{
                    'operation':'session_start','arguments':{},'request_id':'stdio_start'}}},
                {'jsonrpc':'2.0','id':4,'method':'ping'}]
        script='from development.android_mcp import AndroidMcp,serve;import sys;\n'\
               'peer=lambda op,args,rid:{"session_id":"stdio-owned","target":"5"};\n'\
               'adapter=AndroidMcp(sys.argv[1],sys.argv[2],peer=peer);serve(sys.stdin,sys.stdout,adapter);adapter.close()'
        env=os.environ.copy();env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'pc')
        result=subprocess.run([sys.executable,'-c',script,str(self.root/'stdio'),'c'*32],
            input='\n'.join(json.dumps(frame) for frame in frames)+'\n',capture_output=True,text=True,env=env,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        replies=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r['id'] for r in replies],[1,2,3,4])
        self.assertEqual([t['name'] for t in replies[1]['result']['tools']],['android_use'])
        self.assertFalse(replies[2]['result']['isError'])


if __name__=='__main__': unittest.main()
