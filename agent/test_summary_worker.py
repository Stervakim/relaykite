import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from summary_worker import SummaryPump
class SummaryWorkerTests(unittest.TestCase):
    def test_twenty_percent_pauses_only_background_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'summary-route.json').write_text(json.dumps({'enabled':True,'connection_id':'a'*36}))
            relay=Mock()
            with patch('summary_worker.phone_state',return_value={'enabled':True,'battery':20}):
                self.assertEqual(SummaryPump(relay,base).tick()['reason'],'battery_paused')
            relay.request.assert_not_called()
    def test_background_keeps_original_receipts_and_only_saves_proposed_with_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'state').mkdir();(base/'summary-route.json').write_text(json.dumps({'enabled':True,'connection_id':'a'*36}))
            relay=Mock();memory=Mock();events=[{'id':'b'*64,'version':2,'title':'RelayKite event','content':'Verified source'}]
            memory.search.return_value={'notes':events};memory.save.return_value={'saved':True,'id':'c'*64}
            relay.request.side_effect=[{'job_id':'owned-pc-job','status':'pending'},{'job_id':'owned-pc-job','status':'completed','result':{'available':True,'status':'proposed','summary':'Compact source summary','source_records':[{'id':'b'*64,'version':2}]}}]
            with patch('memory_bridge.MemoryBridge',return_value=memory),patch('summary_worker.phone_state',return_value={'enabled':True,'battery':90}):
                pump=SummaryPump(relay,base);self.assertEqual(pump.tick()['status'],'pending')
                self.assertEqual(pump.tick()['status'],'completed');self.assertEqual(pump.tick()['status'],'completed')
            self.assertEqual(relay.request.call_count,2);self.assertEqual(relay.request.call_args.args[1]['operation'],'result')
            self.assertEqual(relay.request.call_args.args[1]['job_id'],'owned-pc-job')
            saved=memory.save.call_args.args[3];self.assertEqual(saved['status'],'proposed');self.assertIn('bbbb',saved['source'])
    def test_model_unavailable_never_saves_or_replays_same_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'state').mkdir();(base/'summary-route.json').write_text(json.dumps({'enabled':True,'connection_id':'a'*36}))
            memory=Mock();memory.search.return_value={'notes':[{'id':'b'*64,'version':2,'title':'Source','content':'Verified source'}]}
            relay=Mock();relay.request.return_value={'job_id':'owned-job','status':'completed','result':{'available':False,'reason':'daily_budget'}}
            with patch('memory_bridge.MemoryBridge',return_value=memory),patch('summary_worker.phone_state',return_value={'enabled':True,'battery':90}):
                pump=SummaryPump(relay,base);self.assertEqual(pump.tick()['status'],'unavailable');self.assertEqual(pump.tick()['status'],'unavailable')
            memory.save.assert_not_called();self.assertEqual(relay.request.call_count,1)
if __name__=='__main__':unittest.main()
