import tempfile, unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
try:from .test_engine import Backend
except ImportError:from test_engine import Backend
from portable.engine import Engine
try:
    from portable.agent import Agent
except ImportError:Agent=None

class Relay:
    def __init__(self):self.results=[];self.fail_upload=True
    def request(self,path,data):
        if path=='/agent/claim':return {'claimed':True}
        if path=='/agent/result':
            if self.fail_upload:self.fail_upload=False;raise OSError('reply lost')
            self.results.append(data);return {'saved':True}
        return {'job':None}

class AgentTests(unittest.TestCase):
    def test_route_switch_closes_the_old_tls_connection_before_next_request(self):
        from portable.agent import Relay as HttpRelay
        connections=[MagicMock(),MagicMock()]
        for connection in connections:
            reply=connection.getresponse.return_value;reply.status=200;reply.read.return_value=b'{"job":null}'
        with patch('portable.agent.choose_proxy',side_effect=['http://127.0.0.1:17890','']),patch('portable.agent.http.client.HTTPSConnection',side_effect=connections) as factory:
            relay=HttpRelay({'relay_url':'https://private.test','agent_token':'d'*48,'device_id':'phone','proxy_url':'http://127.0.0.1:17890'})
            relay.request('/agent/next',{});relay.request('/agent/next',{})
            connections[0].set_tunnel.assert_called_once_with('private.test',443)
            connections[0].close.assert_called_once()
            connections[1].set_tunnel.assert_not_called()
            self.assertEqual(factory.call_args.args[0],'private.test')
    def test_private_site_access_is_sent_only_as_dispatch_header(self):
        from portable.agent import Relay as HttpRelay
        connection=MagicMock();reply=connection.getresponse.return_value;reply.status=200;reply.read.return_value=b'{"job":null}'
        with patch('portable.agent.http.client.HTTPSConnection',return_value=connection):
            relay=HttpRelay({'relay_url':'https://private.test','agent_token':'d'*48,'site_access_token':'private-dispatch-key','device_id':'phone'})
            relay.request('/agent/next',{})
            headers=connection.request.call_args.kwargs['headers']
            self.assertEqual(headers['OAI-Sites-Authorization'],'Bearer private-dispatch-key')
            self.assertEqual(headers['Authorization'],'Bearer '+'d'*48)
            self.assertNotIn('private-dispatch-key',connection.request.call_args.args[1])
    def setUp(self):
        self.assertIsNotNone(Agent,'Outbound agent missing');self.t=tempfile.TemporaryDirectory();self.b=Backend();self.e=Engine(self.b,Path(self.t.name)/'state.db');self.r=Relay();self.a=Agent(self.e,self.r,Path(self.t.name)/'outbox.db')
    def tearDown(self):
        if hasattr(self,'a'):self.a.close();self.e.close();self.t.cleanup()
    def test_lost_result_upload_retries_receipt_without_repeating_input(self):
        session=self.e.execute('session_start',{},'session_request01')['session_id'];o=self.e.execute('observe',{'session_id':session},'observe_request01')
        job={'id':'j1','request_id':'input_request01','op':'action','args':{'session_id':session,'observation_id':o['observation_id'],'action':{'kind':'click','selector':{'node_id':'7/1'}}}}
        self.a.process(job);self.assertEqual(len(self.b.actions),1)
        self.a.process(job);self.assertEqual(len(self.b.actions),1);self.a.flush()
        self.assertTrue(self.r.results)
    def test_restart_delivers_outbox_receipt_before_new_work(self):
        self.a.process({'id':'j1','request_id':'read_request01','op':'apps','args':{}});self.a.close()
        self.a=Agent(self.e,self.r,Path(self.t.name)/'outbox.db');self.a.flush();self.assertEqual(self.r.results[0]['job_id'],'j1')

if __name__=='__main__':unittest.main()
