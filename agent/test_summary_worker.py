import io,json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
from summary_worker import SummaryPump
class SummaryWorkerTests(unittest.TestCase):
    def test_cancelled_or_expired_summary_receipt_does_not_block_new_sources(self):
        for terminal in ('cancelled','expired'):
            with self.subTest(terminal=terminal),tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);(base/'state').mkdir();(base/'summary-route.json').write_text(json.dumps({'enabled':True,'connection_id':'a'*36}))
                memory=Mock();record={'id':'b'*64,'version':1,'title':'RelayKite source','content':'Verified'};memory.search.return_value={'notes':[record]}
                end={'job_id':'old-job','status':'cancelled'} if terminal=='cancelled' else urllib.error.HTTPError('http://owned/bridge/api',403,'expired',{},io.BytesIO(json.dumps({'error':'Job not found or expired; inspect PC state before retrying'}).encode()))
                relay=Mock();relay.request.side_effect=[{'job_id':'old-job','status':'queued'},end,{'job_id':'new-job','status':'queued'}]
                with patch('memory_bridge.MemoryBridge',return_value=memory),patch('summary_worker.phone_state',return_value={'enabled':True,'battery':90}):
                    pump=SummaryPump(relay,base);self.assertEqual(pump.tick()['status'],'pending');self.assertEqual(pump.tick()['status'],'unavailable')
                    self.assertEqual(pump.tick()['status'],'unavailable');self.assertEqual(relay.request.call_count,2)
                    memory.search.return_value={'notes':[dict(record,version=2)]};self.assertEqual(pump.tick()['status'],'pending')
                self.assertEqual(relay.request.call_args.args[1]['operation'],'call');memory.save.assert_not_called()
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
