import tempfile, unittest
from pathlib import Path
from test_engine import Backend
try:
    from portable.mcp import handle
    from portable.engine import Engine
except ImportError:
    handle=None

class MCPTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(handle,'MCP dispatcher not implemented');self.tmp=tempfile.TemporaryDirectory();self.e=Engine(Backend(),Path(self.tmp.name)/'state.db')
    def tearDown(self):
        if hasattr(self,'e'):self.e.close();self.tmp.cleanup()
    def test_tool_list_and_observation_use_shared_contract(self):
        out=handle(self.e,{'jsonrpc':'2.0','id':1,'method':'tools/list'})
        self.assertIn('use_action',[x['name'] for x in out['result']['tools']])
        self.assertIsNotNone(handle(self.e,{'jsonrpc':'2.0','id':2,'method':'initialize'})['result']['serverInfo'])
    def test_tools_call_requires_request_id(self):
        out=handle(self.e,{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'use_apps','arguments':{}}})
        self.assertTrue(out['result']['isError'])
    def test_image_is_returned_as_mcp_image_content(self):
        from portable.mcp import content
        out=content({'screenshot':{'mime_type':'image/png','base64':'eA=='},'nodes':[]})
        self.assertEqual(out['content'][1],{'type':'image','data':'eA==','mimeType':'image/png'})

if __name__=='__main__':unittest.main()
