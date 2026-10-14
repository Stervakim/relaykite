import json,socket,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from portable.local import LocalServer,LockedEngine,call,receive

@unittest.skipUnless(hasattr(socket,'AF_UNIX'),'Unix sockets required')
class AndroidIPCTests(unittest.TestCase):
    def test_independent_socket_read_is_not_held_behind_a_waiting_client(self):
        class Engine:
            def __init__(self):self.lock=threading.RLock();self.waiting=threading.Event();self.condition=threading.Condition(self.lock)
            def execute(self,op,args,rid):
                with self.lock:
                    if op=='batch':self.waiting.set();self.condition.wait(timeout=1)
                    return {'result':rid}
            def expire(self):pass
        engine=Engine();stop=threading.Event()
        def listener(path):
            s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(str(path));Path(path).chmod(0o600);s.listen();s.settimeout(.1)
            d=Path(path).stat();return s,Path(path),(d.st_dev,d.st_ino)
        with tempfile.TemporaryDirectory() as tmp,patch('portable.local._prepare_listener',side_effect=listener),patch('portable.local._peer_uid',return_value=0):
            server=LocalServer(LockedEngine(engine),stop,str(Path(tmp)/'ipc.sock')).start()
            def request(op,rid):
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
                    c.connect(str(server.path));c.sendall((json.dumps({'op':op,'args':{},'request_id':rid})+'\n').encode())
                    return receive(c)
            thread=threading.Thread(target=lambda:request('batch','waiting_client_1'));thread.start()
            try:
                self.assertTrue(engine.waiting.wait(1));start=time.monotonic();out=request('diagnostics','independent_client_2')
                self.assertLess(time.monotonic()-start,.5);self.assertEqual(out['result'],'independent_client_2')
            finally:thread.join(2);server.close()
    def test_agent_and_ipc_share_the_same_lock_and_stop_partial_read(self):
        class Engine:
            def __init__(self):self.lock=threading.RLock();self.reads=0
            def execute(self,op,args,rid):self.reads+=1;return {'result':rid}
            def expire(self):pass
        engine=Engine();stop=threading.Event()
        with tempfile.TemporaryDirectory() as tmp,patch('portable.local._require_root'),patch('portable.local._peer_uid',return_value=0),patch('portable.local.os.geteuid',return_value=0):
            # Windows filesystem owner IDs are unavailable; listener creation
            # is separately covered by device root-only connection tests.
            from portable import local
            original=local._prepare_listener
            def listener(path):
                s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(str(path));Path(path).chmod(0o600);s.listen();s.settimeout(.1)
                d=Path(path).stat();return s,Path(path),(d.st_dev,d.st_ino)
            with patch('portable.local._prepare_listener',side_effect=listener):
                server=LocalServer(LockedEngine(engine),stop,str(Path(tmp)/'ipc.sock')).start()
                try:
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
                        c.connect(str(server.path));c.sendall(b'{"op":"capabilities","args":{},"request_id":"ipc_test_once"}\n')
                        self.assertEqual(receive(c)['result'],'ipc_test_once')
                    self.assertEqual(engine.reads,1)
                    c=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);c.connect(str(server.path));c.sendall(b'{')
                    time.sleep(.05);server.close();c.close();self.assertFalse(server.thread.is_alive())
                finally:server.close()
    def test_framing_rejects_trailing_request(self):
        class C:
            def settimeout(self,n):pass
            def recv(self,n):return b'{}\n{}\n'
        with self.assertRaises(ValueError):receive(C())
