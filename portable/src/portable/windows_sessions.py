"""Independent Windows window leases, sharing one serialized input journal.

The desktop remains shared. Each window owns its observation and backend binding;
the manager's RLock and journal prevent concurrent physical input and replay.
"""
import threading
import time
from .engine import Engine, UseError

class WindowsSessions(Engine):
    def __init__(self, backend_factory, journal_path, clock=time.monotonic, max_sessions=8):
        self.backend_factory=backend_factory
        self.sessions={}
        self.max_sessions=max_sessions
        self.closed=False
        super().__init__(backend_factory(),journal_path,clock)

    def expire(self):
        with self.lock:
            for sid,child in list(self.sessions.items()):
                child.expire()
                if child.session is None:
                    self._release(sid)
            if self.session and self.session['session_id'] not in self.sessions:
                self.session=None

    def _release(self,sid):
        child=self.sessions.pop(sid)
        if hasattr(child.backend,'close'): child.backend.close()

    def _current_observation(self,session_id):
        self.expire()
        child=self.sessions.get(session_id)
        if child is None:raise UseError('Missing, expired or different session','SESSION_EXPIRED')
        child.require_session({'session_id':session_id})
        return child.observation

    def _run_batch(self,args,parent_id):
        self._current_observation(args.get('session_id'))
        supported=set(self.sessions[args['session_id']].backend.capabilities().get('actions',[]))
        validator=getattr(self.sessions[args['session_id']].backend,'validate_batch_action',None)
        for step in args.get('steps',[]) if isinstance(args.get('steps'),list) else []:
            action=step.get('action') if isinstance(step,dict) else None
            if isinstance(action,dict) and action.get('kind') not in supported:
                raise UseError('Batch action is unsupported by this backend','UNSUPPORTED')
            if validator and isinstance(action,dict):validator(action)
        return super()._run_batch(args,parent_id)

    def _run(self,op,args):
        self.expire()
        if op=='capabilities':
            return {**self.backend.capabilities(),'parallel_sessions':True,
                    'batch':True,'max_batch_steps':12,'max_batch_timeout_ms':30000,
                    'max_sessions':self.max_sessions,'session_scope':'window',
                    'input_serialized':True,'desktop_isolation':False}
        if op=='diagnostics':
            return {'blocked':bool(self.journal.uncertain()),
                    'uncertain_requests':self.journal.uncertain(),
                    'sessions':[dict(c.session) for c in self.sessions.values()],
                    'backend':self.backend.diagnostics()}
        if op in ('apps','result','reconcile'):
            result=super()._run(op,args)
            if op=='reconcile':
                for child in self.sessions.values(): child.observation=None
            return result
        if op=='session_start':
            if len(self.sessions)>=self.max_sessions: raise UseError('Windows session limit reached')
            # Child state uses the manager journal. Only the manager executes
            # journaled operations; child _run handles window-local UI state.
            child=Engine.__new__(Engine)
            child.backend=self.backend_factory(); child.clock=self.clock
            child.journal=self.journal; child.session=None; child.observation=None
            child.lock=threading.RLock()
            try:
                result=child._run(op,args)
                if any(c.session['target']==result['target'] for c in self.sessions.values()):
                    child.backend.stop()
                    raise UseError('This window already has a session; extend or close it')
            except Exception:
                if hasattr(child.backend,'close'): child.backend.close()
                raise
            self.sessions[result['session_id']]=child
            self.session=child.session
            return result
        sid=args.get('session_id')
        child=self.sessions.get(sid)
        if child is None: raise UseError('Missing, expired or different session','SESSION_EXPIRED')
        try:
            result=child._run(op,args)
        finally:
            if op in ('action','launch','file_open'):
                # Physical input or application launch may change the desktop
                # foreground. Keep independent leases, but require a fresh
                # observation before the next action in every other window.
                # Invalidate even when a native outcome is unknown or fails.
                for other_sid,other in self.sessions.items():
                    if other_sid != sid:
                        other.observation=None
        self.session=child.session
        if op=='session_stop': self._release(sid)
        return result

    def close(self):
        with self.lock:
            if self.closed: return
            for sid,child in list(self.sessions.items()):
                child.backend.stop(); self._release(sid)
            self.session=None
            if hasattr(self.backend,'close'): self.backend.close()
            super().close(); self.closed=True
