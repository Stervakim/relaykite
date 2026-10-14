import importlib.util,json,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('memory_summary_test',ROOT/'pc/memory_summary.py');summary=importlib.util.module_from_spec(spec);spec.loader.exec_module(summary)
class SummaryTests(unittest.TestCase):
    def test_no_config_or_invalid_sources_cannot_make_a_model_request(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(summary.urllib.request,'build_opener') as opening:
            events=[{'id':'a'*64,'version':1,'title':'Owned','content':'verified source'}]
            self.assertEqual(summary.summarize(events,tmp)['reason'],'not_configured');opening.assert_not_called()
            with self.assertRaises(ValueError):summary.summarize([dict(events[0],command='id')],tmp)
    def test_failure_is_cached_and_cannot_interrupt_original_job_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'summary.json').write_text(json.dumps({'enabled':True,'url':summary.URL,'model':summary.MODEL,'key':'k'*40}))
            with closing(sqlite3.connect(base/'journal.sqlite')) as db:db.execute('CREATE TABLE jobs(id TEXT)');db.execute("INSERT INTO jobs VALUES('preserved')");db.commit()
            events=[{'id':'a'*64,'version':1,'title':'Owned','content':'verified source'}]
            with patch.object(summary.urllib.request,'build_opener') as opening:
                opening.return_value.open.side_effect=TimeoutError('quota or offline')
                out=summary.summarize(events,base);self.assertFalse(out['available']);self.assertEqual(summary.summarize(events,base),out);self.assertEqual(opening.call_count,1)
            with closing(sqlite3.connect(base/'journal.sqlite')) as db:self.assertEqual(db.execute('SELECT id FROM jobs').fetchone()[0],'preserved')
    def test_unselected_external_route_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'summary.json').write_text(json.dumps({'enabled':True,'url':'https://unselected.example','model':summary.MODEL,'key':'k'*40}))
            with self.assertRaises(ValueError):summary.summarize([{'id':'a'*64,'version':1,'title':'Owned','content':'source'}],base)
    def test_fixed_direct_pc_route_accepts_no_tools_or_arbitrary_model(self):
        self.assertTrue(hasattr(summary,'DIRECT_URL'),'Direct PC model route missing')
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'summary.json').write_text(json.dumps({'enabled':True,'url':summary.DIRECT_URL,'model':'unselected','key':'k'*40}))
            with self.assertRaises(ValueError):summary.summarize([{'id':'a'*64,'version':1,'title':'Owned','content':'source'}],base)
if __name__=='__main__':unittest.main()
