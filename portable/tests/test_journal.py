import tempfile,unittest,time
from pathlib import Path
from portable.journal import Journal
from portable.engine import Engine,UseError

class JournalTests(unittest.TestCase):
    def test_compaction_keeps_id_but_never_replays_input(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal.sqlite3';j=Journal(p)
            j.begin('old_request_01','apps',{});j.finish('old_request_01','completed',{'apps':[]})
            j.db.execute('UPDATE requests SET created=?',(time.time()-86401,));j.db.commit()
            j.compact();self.assertEqual(j.get('old_request_01')[1],'compacted');j.close()
            class Backend:
                def apps(self):raise AssertionError('Expired input replayed')
            e=Engine(Backend(),p)
            try:
                with self.assertRaises(UseError) as raised:e.execute('apps',{},'old_request_01')
                self.assertEqual(raised.exception.code,'RESULT_EXPIRED')
            finally:e.close()
    def test_byte_budget_drops_completed_payloads_but_retains_uncertain(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'j.db')
            j.begin('result_request_01','apps',{});j.finish('result_request_01','completed',{'blob':'😀'*30})
            j.begin('result_request_02','action',{});j.finish('result_request_02','uncertain',{'code':'UNCERTAIN'})
            j.compact(max_bytes=64)
            self.assertEqual(j.get('result_request_01')[1],'compacted')
            self.assertEqual(j.uncertain(),['result_request_02']);j.close()
