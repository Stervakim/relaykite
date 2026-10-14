import json,os,sqlite3,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
import root_supervisor as root

class RootSupervisorTests(unittest.TestCase):
    def test_frozen_app_cleanup_requires_exact_owned_uid_runtime_and_executable(self):
        args=['/owned/librelaykite_python.so',str(root.APPFILES/('runtime-'+'a'*24)/'agent/app_worker.py')]
        self.assertTrue(root.owned_app_worker(10515,args,10515))
        self.assertFalse(root.owned_app_worker(2000,args,10515))
        self.assertFalse(root.owned_app_worker(10515,['/owned/unrelated',args[1]],10515))
        self.assertFalse(root.owned_app_worker(10515,[args[0],'/unrelated/runtime-'+('a'*24)+'/agent/app_worker.py'],10515))
        self.assertFalse(root.owned_app_worker(10515,args+['extra'],10515))
    @unittest.skipIf(os.name=='nt','Kernel UNIX peer identity is checked on Android/POSIX')
    def test_readiness_requires_recorded_live_peer_and_selected_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'app';(base/'state').mkdir(parents=True)
            script=Path(tmp)/'agent/app_worker.py';script.parent.mkdir()
            script.write_text("import os,socket,time\nfrom pathlib import Path\nb=Path(os.environ['RELAYKITE_BASE'])\ns=socket.socket(socket.AF_UNIX);s.bind(str(b/'state/managed.sock'));s.listen(4)\n(b/'agent.pid').write_text(str(os.getpid()))\nwhile True:\n c,_=s.accept();c.close()\n")
            env=os.environ.copy();env.update(RELAYKITE_BASE=str(base),RELAYKITE_MODE='app')
            child=subprocess.Popen([sys.executable,str(script)],env=env)
            try:
                until=time.monotonic()+5
                while not (base/'agent.pid').exists() and time.monotonic()<until:time.sleep(.01)
                with patch.object(root,'APP',base),patch.object(root,'ROOT',base):
                    backend=root.Backend(Path(tmp),os.getuid())
                    self.assertTrue(backend.ready('app'))
                    self.assertFalse(backend.ready('root'),'Same socket must not certify the wrong mode')
                    (base/'agent.pid').write_text(str(os.getpid()))
                    self.assertFalse(backend.ready('app'),'A live socket with a different recorded worker is stale')
            finally:child.terminate();child.wait(timeout=5)

    def installation(self,base):
        base.mkdir();(base/'state').mkdir();(base/'memory-service/data').mkdir(parents=True)
        for path in (base/'state/jobs.sqlite3',base/'memory-service/data/vectors.db'):
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE owned(id TEXT,version INTEGER)');db.execute("INSERT INTO owned VALUES('original-owner',3)");db.commit()
        config={'relay_url':'https://owned.example','agent_token':'k'*48,'state_dir':str(base/'state'),'memory_dir':str(base/'memory'),'disable_file':str(base/'disable')}
        node={'scope':'codaki-owner-phone','key':'m'*48,'data_dir':str(base/'memory-service/data'),'port':8420}
        bridge={'url':'http://127.0.0.1:8420','key':node['key'],'data_dir':node['data_dir'],'accounting_roots':[str(base)]}
        for name,data in (('config.json',config),('memory-node.json',node),('memory-service.json',bridge)):(base/name).write_text(json.dumps(data))
        return config
    def test_actual_snapshot_preserves_owner_receipts_and_memory_while_remapping_only_runtime_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Path(tmp)/'app';target=Path(tmp)/'root';original=self.installation(app)
            with patch.object(root,'ROOT',target),patch.object(root,'APP',app),patch.object(root,'MODULE',Path(tmp)/'module'),patch.object(root.os,'chown',create=True):
                backend=root.Backend(Path(tmp)/'runtime',10515);backend.preflight('app','root');backend.prepare('app','root','owned_transition_1')
            copied=json.loads((target/'config.json').read_text())
            self.assertEqual(copied['agent_token'],original['agent_token']);self.assertEqual(copied['state_dir'],str(target/'state'))
            self.assertEqual(json.loads((app/'config.json').read_text()),original)
            for path in ('state/jobs.sqlite3','memory-service/data/vectors.db'):
                with closing(sqlite3.connect(target/path)) as db:self.assertEqual(db.execute('SELECT * FROM owned').fetchall(),[('original-owner',3)])
            self.assertFalse((target/'enabled').exists(),'Preparing a copy must not activate a worker')
    def test_other_owner_configuration_is_rejected_before_stop_or_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Path(tmp)/'app';target=Path(tmp)/'root';self.installation(app);self.installation(target)
            value=json.loads((target/'config.json').read_text());value['agent_token']='x'*48;(target/'config.json').write_text(json.dumps(value))
            with patch.object(root,'ROOT',target),patch.object(root,'APP',app):
                backend=root.Backend(Path(tmp)/'runtime',10515)
                with self.assertRaises(PermissionError):backend.preflight('app','root')
            self.assertFalse((target/'mode-backups').exists())

if __name__=='__main__':unittest.main()
