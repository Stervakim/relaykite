import json,socket,tempfile,unittest
from pathlib import Path
from portable.local import receive,dispatch
from portable.engine import Engine
try:from .test_engine import Backend
except ImportError:from test_engine import Backend
class LocalTests(unittest.TestCase):
    def test_stream_framing_and_size_limit(self):
        a,b=socket.socketpair()
        try:
            a.sendall(b'{"op":"apps"}\n');self.assertEqual(receive(b),{'op':'apps'})
            a.sendall(b'0123456789\n')
            with self.assertRaises(ValueError):receive(b,8)
        finally:a.close();b.close()
    def test_dispatch_uses_same_durable_dedup_as_mcp(self):
        with tempfile.TemporaryDirectory() as d:
            backend=Backend();e=Engine(backend,Path(d)/'journal.db')
            try:
                q={'op':'session_start','args':{},'request_id':'local_start_01'}
                first=dispatch(e,q);self.assertEqual(first,dispatch(e,q))
                self.assertEqual(dispatch(e,dict(q,args={'lease_seconds':60}))['code'],'REJECTED')
                self.assertEqual(dispatch(e,dict(q,command='shell'))['code'],'REJECTED')
            finally:e.close()
