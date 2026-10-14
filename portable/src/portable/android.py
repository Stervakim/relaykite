import json, os, re, subprocess, tempfile, time, socket, struct, signal
from pathlib import Path
from .engine import UseError, BackendOutcomeUnknown
from . import __version__

ROOT=Path(__file__).resolve().parents[1]
def parse_apps(raw):
    apps=[]
    for line in raw.splitlines():
        m=re.fullmatch(r'([A-Za-z_][\w.]*)/(\.?[A-Za-z_][\w.$]*)',line.strip())
        if not m:continue
        package,activity=m.groups()
        if activity.startswith('.'):activity=package+activity
        value={'app_id':package+'/'+activity,'name':package}
        if value not in apps:apps.append(value)
    return apps

class AndroidBackend:
    def __init__(self,legacy=None,inspector=None):
        from . import legacy_display
        self.legacy=legacy if legacy is not None else legacy_display
        self.inspector=inspector
        self._persistent=True
        if os.geteuid()!=0:raise UseError('Android backend requires preinstalled authorized root')
    def capabilities(self):
        return {'platform':'android','version':__version__,'display_isolation':True,'physical_display':False,
                'actions':['click','long_click','focus','set_text','selection','select','scroll','key','gesture','drag'],
                'max_text':65536,'max_fingers':5,'unicode':True,'persistent_inspector':True}
    def validate_batch_action(self,action):
        if action.get('kind')=='key':
            chord=action.get('key')
            if not isinstance(chord,str):raise UseError('Android key requires a name')
            parts=chord.upper().split('+');key=parts[-1]
            aliases={'BACKSPACE':'DEL','DELETE':'FORWARD_DEL','ESC':'ESCAPE'};key=aliases.get(key,key)
            allowed={'BACK','ENTER','TAB','DPAD_UP','DPAD_DOWN','DPAD_LEFT','DPAD_RIGHT','DEL','FORWARD_DEL','ESCAPE','MOVE_HOME','MOVE_END','SPACE','PAGE_UP','PAGE_DOWN'}
            if any(x not in {'CTRL','SHIFT','ALT'} for x in parts[:-1]) or (key not in allowed and not re.fullmatch('[A-Z0-9]',key)):
                raise UseError('Unsupported Android key','UNSUPPORTED')
        if action.get('kind') in ('click','long_click') and action.get('button','left')!='left':
            raise UseError('Android supports touch; secondary mouse button is unsupported','UNSUPPORTED')
    def verified_display(self):
        did=self.legacy.find_display()
        if type(did)!=int or did<=0:raise UseError('Physical display is never a valid target')
        return did
    def apps(self):return parse_apps(self.legacy.run('cmd','package','query-activities','--brief','-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER'))
    def _lease(self,seconds):
        for parent in (self.legacy.HOME,*self.legacy.HOME.parents):
            if parent.is_symlink():raise UseError('Owned core directory symlink rejected')
        self.legacy.HOME.mkdir(parents=True,exist_ok=True)
        self.legacy.HOME.chmod(0o700)
        p=self.legacy.HOME/'lease-deadline';temp=p.with_suffix('.tmp')
        temp.write_text(str(int((time.time()+seconds)*1000)),encoding='ascii');temp.chmod(0o600);temp.replace(p)
        if getattr(self,'inspector',None) is not None:
            shared=self.inspector.legacy.HOME/'lease-deadline'
            deadline=int(shared.read_text()) if shared.is_file() else 0
            self.inspector._lease(max(seconds,(deadline/1000-time.time())))
    def start(self,target=None,lease_seconds=300):
        if target is not None:raise UseError('Android creates its own display; target must be omitted')
        self._lease(lease_seconds)
        try:data=self.legacy.start_engine()
        except Exception as e:raise RuntimeError('Display start outcome unknown') from e
        return {'target':str(data['display'])}
    def extend(self,seconds):self.verified_display();self._lease(seconds);return {'extended':seconds}
    def stop(self):
        if getattr(self,'_persistent',False) and getattr(self,'inspector',None) is None:self.stop_inspector()
        try:result=self.legacy.stop_engine()
        except Exception as e:raise RuntimeError('Owned display stop outcome unknown') from e
        (self.legacy.HOME/'lease-deadline').unlink(missing_ok=True)
        return result
    def close(self):
        if getattr(self,'inspector',None) is None:
            self.stop_inspector();return
        # Manager cleanup is idempotent and also releases partial starts. PID
        # generation and exact owner argv are checked before any signal.
        pid=self.legacy.engine_pid()
        if not pid:return
        try:self.verified_display()
        except Exception:
            os.kill(pid,signal.SIGTERM)
            (self.legacy.HOME/'lease-deadline').unlink(missing_ok=True)
        else:self.stop()
    def launch(self,app_id):
        did=self.verified_display()
        raw=self.legacy.run('am','start','--display',str(did),'-f','0x18800000','-n',app_id)
        if 'Error:' in raw or 'Exception' in raw:raise UseError('Android refused launch')
        return {'requested':app_id,'display':did,'verify_with_observe':True}
    def open_file(self,app_id,uri,mime_type):
        import re
        if not isinstance(uri,str) or not re.fullmatch(r'content://org\.relaykite\.runtime\.files/[a-f0-9]{32}\.[a-z0-9]{1,12}',uri):raise UseError('Expected an owned scoped file URI')
        if not isinstance(mime_type,str) or not re.fullmatch('[a-z0-9.+-]+/[a-z0-9.+-]+',mime_type):raise UseError('Invalid MIME type')
        did=self.verified_display()
        raw=self.legacy.run('am','start','--display',str(did),'-a','android.intent.action.VIEW','-d',uri,'-t',mime_type,'-f','0x18800000','--grant-read-uri-permission','-n','org.relaykite.runtime/.FileLaunchActivity','--es','target',app_id)
        if 'Error:' in raw or 'Exception' in raw:raise UseError('Android refused scoped file open')
        return {'requested':app_id,'display':did,'uri':uri,'mime_type':mime_type,'verify_with_observe':True}
    def request(self,data):
        did=self.verified_display();data=dict(data,display=did)
        packed=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(packed)>524288:raise UseError('UI request exceeds byte limit')
        if getattr(self,'_persistent',False):return self.persistent_request(did,packed)
        jar=self.legacy.HOME/'ui-v2.jar'
        if not jar.is_file():raise UseError('ui-v2.jar is not installed')
        # A single Unicode text argument can exceed Linux MAX_ARG_STRLEN.
        # Keep input in an exclusive mode-0600 file in the owned core directory.
        fd,name=tempfile.mkstemp(prefix='request-',suffix='.json',dir=self.legacy.HOME)
        path=Path(name)
        try:
            with os.fdopen(fd,'wb') as stream:
                if hasattr(os,'fchmod'):os.fchmod(stream.fileno(),0o600)
                else:path.chmod(0o600)
                stream.write(packed)
            args=['/system/bin/uiautomator','runtest',str(jar),'-c','com.oai.androiduse.PortableUiTest#testRequest','-e','display',str(did),'-e','request_file',path.name,'-s']
            env={k:v for k,v in os.environ.items() if not k.startswith('LD_')};env['PATH']='/system/bin:/system/xbin:/vendor/bin'
            try:r=subprocess.run(args,capture_output=True,text=True,timeout=30,env=env)
            except subprocess.TimeoutExpired:raise RuntimeError('UI operation outcome unknown')
        finally:path.unlink(missing_ok=True)
        lines=[line.split('PORTABLE_USE\t',1)[1] for line in r.stdout.splitlines() if 'PORTABLE_USE\t' in line]
        if len(lines)!=1:raise RuntimeError('Missing Java operation receipt')
        result=json.loads(lines[0])
        if result.get('display')!=did:raise RuntimeError('Receipt display mismatch')
        if result.get('ok') is not True:
            if result.get('applied') is False:raise UseError(result.get('error','UI action rejected'),result.get('code','REJECTED'))
            raise BackendOutcomeUnknown(result.get('code'))
        return result
    def inspector_pid(self):
        record=self.legacy.HOME/'inspector.pid'
        if not record.exists():return None
        metadata=json.loads(record.read_text());pid=metadata['pid'];cmd=Path('/proc')/str(pid)/'cmdline'
        if not cmd.exists():record.unlink(missing_ok=True);return None
        start=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        status=Path('/proc',str(pid),'status').read_text()
        if start!=metadata['start_ticks'] or not re.search(r'^Uid:\s+0\s+0\s+0\s+0\s*$',status,re.M):raise RuntimeError('Inspector PID ownership mismatch')
        if 'app_process' not in os.readlink(str(Path('/proc',str(pid),'exe'))):raise RuntimeError('Inspector executable mismatch')
        return pid
    def stop_inspector(self):
        pid=self.inspector_pid()
        if pid:
            os.kill(pid,signal.SIGTERM)
            for _ in range(40):
                try:os.waitpid(pid,os.WNOHANG)
                except ChildProcessError:pass
                if not Path('/proc',str(pid)).exists():break
                time.sleep(.1)
            else:raise RuntimeError('Inspector has not stopped')
        (self.legacy.HOME/'inspector.pid').unlink(missing_ok=True)
        (self.legacy.HOME/'inspector.sock').unlink(missing_ok=True)
    def persistent_request(self,did,packed):
        if getattr(self,'inspector',None) is not None:return self.inspector.persistent_request(did,packed)
        path=self.legacy.HOME/'inspector.sock'
        if not self.inspector_pid():
            path.unlink(missing_ok=True)
            jar=self.legacy.HOME/'ui-v2.jar'
            if not jar.is_file():raise UseError('ui-v2.jar is not installed')
            argv=['/system/bin/uiautomator','runtest',str(jar),'-c','com.oai.androiduse.PortableUiTest#testServe','-e','display',str(did),'-s']
            with (self.legacy.HOME/'inspector.log').open('w') as log:
                proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=self.legacy.system_env(),start_new_session=True)
            start=Path('/proc',str(proc.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
            record=self.legacy.HOME/'inspector.pid';record.write_text(json.dumps({'pid':proc.pid,'start_ticks':start}));record.chmod(0o600)
            for _ in range(100):
                if path.exists():break
                if proc.poll() is not None:raise RuntimeError('Persistent inspector failed; inspect its local log')
                time.sleep(.05)
            else:raise RuntimeError('Inspector did not become ready')
        def read_exact(connection,size):
            out=bytearray()
            while len(out)<size:
                part=connection.recv(size-len(out))
                if not part:raise RuntimeError('Inspector receipt lost')
                out.extend(part)
            return bytes(out)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(30);connection.connect(str(path));connection.sendall(struct.pack('!I',len(packed))+packed)
            size=struct.unpack('!I',read_exact(connection,4))[0]
            if not 0<size<=4*1024*1024:raise RuntimeError('Invalid inspector receipt size')
            result=json.loads(read_exact(connection,size))
        if result.get('display')!=did:raise RuntimeError('Receipt display mismatch')
        if result.get('ok') is not True:
            if result.get('applied') is False:raise UseError(result.get('error','UI rejected'),result.get('code','REJECTED'))
            raise BackendOutcomeUnknown(result.get('code'))
        return result
    def snapshot(self,screenshot=False):
        data=self.request({'op':'observe'})['snapshot']
        if screenshot:
            image=self.legacy.capture_virtual();data['screenshot']={'mime_type':'image/png','base64':image['png']}
        return data
    def action(self,action,observation):
        if action.get('kind')=='selection':
            action=dict(action);node=next(n for n in observation['nodes'] if n['node_id']==action['node_id'])
            for key in ('start','end'):action[key]=len(node.get('text','')[:action[key]].encode('utf-16-le'))//2
        return self.request({'op':'action','action':action,'expected':observation.get('native_fingerprint')})
    def diagnostics(self):
        installed=(self.legacy.HOME/'ui-v2.jar').is_file()
        try:display=self.verified_display();state='active'
        except UseError:display=None;state='idle'
        except Exception:display=None;state='display_unavailable' if (self.legacy.HOME/'engine.pid').exists() else 'idle'
        return {'display':display,'core_installed':installed,'session_display_ready':display is not None,
                'state':state,'core_ready':display is not None,
                'instruction':'core_ready is a legacy display-presence flag. An idle session has no display; this does not mean the installed core is broken.'}
