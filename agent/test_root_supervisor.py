import json,os,sqlite3,stat,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing,contextmanager
from types import SimpleNamespace
import root_supervisor as root

class RootSupervisorTests(unittest.TestCase):
    def test_new_apk_files_directory_is_owned_by_app_before_control_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp)/'apk';parent.mkdir();files=parent/'files'
            with patch.object(root,'APPFILES',files),patch.object(root.os,'chown',create=True) as chown,patch.object(root.subprocess,'run') as restore:
                root.prepare_app_files(10515)
                self.assertTrue(files.is_dir())
                chown.assert_called_once_with(files,10515,10515)
                self.assertEqual(restore.call_args.args[0],['/system/bin/restorecon',str(files)])
    def test_apk_files_symlink_is_rejected_without_chown(self):
        with tempfile.TemporaryDirectory() as tmp:
            files=Path(tmp)/'files';files.mkdir()
            original=Path.is_symlink
            with patch.object(root,'APPFILES',files),patch.object(root.os,'chown',create=True) as chown,patch.object(Path,'is_symlink',lambda p: p==files or original(p)):
                with self.assertRaises(PermissionError):root.prepare_app_files(10515)
                chown.assert_not_called()
    @contextmanager
    def headless_installation(self,marker=True,marker_mode=0o600,control_mode=0o700,marker_uid=0,control_uid=0):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);base=home/'root';base.mkdir();(base/'state').mkdir()
            control=home/'control';control.mkdir();flag=control/'headless-root-enabled'
            if marker:flag.write_text('enabled\n')
            appfiles=home/'absent-apk/files';app=appfiles/'owner';module=home/'module';module.mkdir()
            original=Path.lstat
            def secure_stat(path,*args,**kwargs):
                value=original(path,*args,**kwargs)
                if path==control:return SimpleNamespace(st_mode=stat.S_IFDIR|control_mode,st_uid=control_uid)
                if path==flag:return SimpleNamespace(st_mode=stat.S_IFREG|marker_mode,st_uid=marker_uid)
                return value
            fcntl=SimpleNamespace(LOCK_EX=2,LOCK_NB=4,flock=lambda *_:None)
            with patch.object(root,'ROOT',base),patch.object(root,'APP',app),patch.object(root,'APPFILES',appfiles),patch.object(root,'CONTROL',control),patch.object(root,'MODULE',module),patch.object(Path,'lstat',secure_stat),patch.object(root.os,'geteuid',return_value=0,create=True),patch.object(root.os,'chown',create=True),patch.dict(sys.modules,{'fcntl':fcntl}),patch.object(root.signal,'signal'):
                yield base,control,flag,appfiles,module
    def test_explicit_headless_marker_starts_root_without_creating_apk_storage(self):
        with self.headless_installation() as (base,control,flag,appfiles,module):
            (base/'enabled').touch();journal=control/'mode.sqlite3';journal.write_bytes(b'preserved-mode-journal')
            (base/'config.json').write_text('{"agent_token":"original"}');(base/'memory').mkdir();(base/'memory/original').write_bytes(b'original-memory')
            calls=[]
            class Backend:
                def __init__(self,runtime,uid):calls.append(('uid',uid));self.child=None
                def reconcile(self,mode):calls.append(('reconcile',mode));self.child=SimpleNamespace(poll=lambda:None)
                def stop(self,mode):calls.append(('stop',mode));self.child=None
            with patch.object(root,'Backend',Backend),patch.object(root,'Coordinator',side_effect=AssertionError('Headless mode must preserve the mode journal')),patch.object(root.time,'sleep',side_effect=lambda _:flag.unlink(missing_ok=True)):
                try:root.main()
                except Exception as error:self.fail('Authorized root must run without APK: '+repr(error))
            self.assertIn(('uid',None),calls);self.assertIn(('reconcile','root'),calls);self.assertEqual(calls[-1],('stop','root'))
            self.assertFalse(appfiles.parent.exists(),'Headless startup created APK storage')
            self.assertEqual(journal.read_bytes(),b'preserved-mode-journal')
            self.assertEqual(json.loads((base/'config.json').read_text()),{'agent_token':'original'})
            self.assertEqual((base/'memory/original').read_bytes(),b'original-memory')
            self.assertFalse(json.loads((control/'root-control.json').read_text())['available'])
            self.assertEqual(json.loads((control/'mode-status.json').read_text())['mode'],'root')
    def test_absent_apk_requires_explicit_headless_marker(self):
        with self.headless_installation(marker=False) as (_,_,_,appfiles,_),patch.object(root,'Backend') as backend:
            with self.assertRaises(FileNotFoundError):root.main()
            backend.assert_not_called();self.assertFalse(appfiles.parent.exists())
    def test_headless_marker_and_control_must_be_private_and_root_owned(self):
        for values in ({'marker_mode':0o644},{'marker_uid':10515},{'control_mode':0o755},{'control_uid':10515}):
            with self.subTest(values=values),self.headless_installation(**values),patch.object(root,'Backend') as backend:
                with self.assertRaises(PermissionError):root.main()
                backend.assert_not_called()
    def test_headless_stop_does_not_contact_apk_or_touch_app_enable(self):
        with self.headless_installation() as (base,_,_,appfiles,_):
            app=appfiles/'owner';app.mkdir(parents=True);(app/'enabled').touch()
            with patch.object(root,'android',side_effect=AssertionError('Headless stop contacted APK')):
                try:root.Backend(base/'runtime',None).stop('root')
                except Exception as error:self.fail('Headless stop touched another mode: '+repr(error))
            self.assertTrue((app/'enabled').is_file())
    def test_normal_stop_still_stops_owned_apk_and_clears_app_enable(self):
        with self.headless_installation() as (base,_,_,appfiles,_):
            app=appfiles/'owner';app.mkdir(parents=True);(app/'enabled').touch()
            with patch.object(root,'android') as android:root.Backend(base/'runtime',10515).stop('root')
            android.assert_called_once_with('stopservice','-n','org.relaykite.runtime/.WorkerService')
            self.assertFalse((app/'enabled').exists())
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
