"""Independent Android virtual-display leases and one serialized inspector."""
import importlib.util,re,secrets,time,threading
from .android import AndroidBackend
from .engine import UseError
from .windows_sessions import WindowsSessions

def make_owner(token):
    from . import legacy_display
    if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('Invalid owned display token')
    # Each trusted module instance has its own function globals. Never change
    # the singleton used by the separately installed Android Use component.
    spec=importlib.util.spec_from_file_location(__name__+'_owner_'+token,legacy_display.__file__)
    owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
    owner.HOME=legacy_display.HOME/'sessions'/token
    owner.NAME='CodakiPortableUse_'+token
    owner.SOCK=owner.HOME/'core.sock'
    owner.ENGINE_PID=owner.HOME/'engine.pid';owner.ENGINE_LOG=owner.HOME/'engine.log'
    owner.ENGINE_JAR=legacy_display.ENGINE_JAR
    return owner

class AndroidSessions(WindowsSessions):
    def __init__(self,journal_path,clock=time.monotonic,max_sessions=3,backend_class=AndroidBackend,owner_factory=make_owner):
        self.package_owners={}
        self.busy_sessions={}
        self.inspector=backend_class()
        if backend_class is AndroidBackend:
            # CLI owns the existing single-agent flock before constructing us.
            # Sessions cannot survive its journal restart. Release only verified
            # namespace owners; never adopt orphan UI or another project's core.
            self.inspector.stop_inspector()
            from .legacy_display import HOME
            for directory in sorted((HOME/'sessions').glob('*')):
                if directory.is_symlink():raise RuntimeError('Owned display directory symlink')
                if not re.fullmatch('[a-f0-9]{32}',directory.name):continue
                backend_class(legacy=owner_factory(directory.name),inspector=self.inspector).close()
        super().__init__(lambda:backend_class(legacy=owner_factory(secrets.token_hex(16)),inspector=self.inspector),journal_path,clock,max_sessions)
        self.batch_condition=threading.Condition(self.lock)
    def _batch_pause(self,seconds):
        # Condition.wait releases all recursive acquisitions, including the
        # agent boundary's lock, then restores them before inspecting/input.
        self.batch_condition.wait(timeout=seconds)
    def _run_batch(self,args,parent_id):
        sid=args.get('session_id')
        if sid in self.busy_sessions:raise UseError('Session already has a running batch','RESOURCE_CONFLICT')
        self.busy_sessions[sid]=threading.get_ident()
        try:return super()._run_batch(args,parent_id)
        finally:self.busy_sessions.pop(sid,None)
    def _release(self,sid):
        super()._release(sid)
        self.package_owners={package:owner for package,owner in self.package_owners.items() if owner!=sid}
        if not self.sessions:self.inspector.stop_inspector()
    def _run(self,op,args):
        sid=args.get('session_id')
        owner=self.busy_sessions.get(sid)
        if owner is not None and owner!=threading.get_ident():
            raise UseError('Session has an active batch; inspect its original result','RESOURCE_CONFLICT')
        if op=='launch':
            self.expire()
            sid=args.get('session_id');app=args.get('app_id')
            if sid not in self.sessions:raise UseError('Missing or expired session','SESSION_EXPIRED')
            if app not in {item['app_id'] for item in self.sessions[sid].backend.apps()}:
                raise UseError('App must be returned by apps')
            package=app.split('/',1)[0]
            owner=self.package_owners.get(package)
            if owner is not None and owner!=sid:
                raise UseError('Package already belongs to another display lease; stop that session first','RESOURCE_CONFLICT')
            # Retain the claim even on an uncertain launch. Android may have
            # moved its singleton activity before reporting the failure.
            self.package_owners[package]=sid
        if op=='capabilities':
            return {**self.backend.capabilities(),'parallel_sessions':True,'batch':True,'max_batch_steps':12,
                    'max_batch_timeout_ms':30000,'max_sessions':self.max_sessions,'session_scope':'virtual_display',
                    'input_serialized':True,'desktop_isolation':True,'application_data_isolation':False}
        if op=='diagnostics':
            self.expire()
            return {'blocked':bool(self.journal.uncertain()),'uncertain_requests':self.journal.uncertain(),
                    'sessions':[dict(c.session) for c in self.sessions.values()],
                    'backends':[c.backend.diagnostics() for c in self.sessions.values()],
                    'backend':self.inspector.diagnostics()}
        return super()._run(op,args)
    def close(self):
        try:super().close()
        finally:self.inspector.stop_inspector()
