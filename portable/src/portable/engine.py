import copy, re, secrets, threading, time
from .journal import Journal, digest

class UseError(Exception):
    def __init__(self,message,code='REJECTED'):super().__init__(message);self.code=code

class BackendOutcomeUnknown(RuntimeError):
    def __init__(self,reason):
        self.reason=reason if reason=='SEMANTIC_NOT_CONFIRMED' else 'RECEIPT_NOT_CONFIRMED'
        super().__init__(self.reason)

READ_ONLY={'apps','capabilities','observe','diagnostics','result'}
FIELDS={
 'apps':set(),'capabilities':set(),'diagnostics':set(),
 'session_start':{'lease_seconds','target'},'session_extend':{'session_id','lease_seconds'},
 'session_stop':{'session_id'},'observe':{'session_id','screenshot'},
 'launch':{'session_id','app_id'},'action':{'session_id','observation_id','action'},
 'batch':{'session_id','observation_id','steps','timeout_ms'},
 'result':{'request_id'},'reconcile':{'request_id','outcome','evidence'}}
SELECTOR_FIELDS={'node_id','resource_id','text','description','role','parent_id','window_id','occurrence'}

def sanitize(snapshot):
    protected=False
    for node in snapshot.get('nodes',[]):
        if node.get('password'):
            node['text']='';node['description']='';protected=True
    if protected:
        snapshot.pop('raw_tree',None);snapshot.pop('accessibility',None)
    return snapshot

def fingerprint(snapshot):
    value={k:v for k,v in snapshot.items() if k not in ('screenshot','fingerprint','observation_id','session_id','expires_at')}
    if snapshot.get('screenshot'):value['visual_digest']=digest(snapshot['screenshot'])
    return digest(value)

def select(nodes,selector):
    if not isinstance(selector,dict) or not selector or set(selector)-SELECTOR_FIELDS:raise UseError('Invalid selector')
    index=selector.get('occurrence')
    filters={k:v for k,v in selector.items() if k!='occurrence'}
    if not filters:raise UseError('Selector requires an identifying field')
    matches=[n for n in nodes if all(n.get(k)==v for k,v in filters.items())]
    if index is not None:
        if type(index)!=int or not 0<=index<len(matches):raise UseError('Invalid occurrence (zero-based)')
        return matches[index]
    if len(matches)!=1:raise UseError('Selector matched %d elements; refine it'%len(matches),'AMBIGUOUS')
    return matches[0]

def stable_action_target(previous, current, requested):
    """Allow unrelated UI updates, never a changed/ambiguous input target.

    Atomic native fingerprint protection remains enforced using the *current*
    native snapshot. This check only authorizes rebasing a known action onto it.
    """
    if previous.get('geometry') != current.get('geometry'):
        return False
    def foreground(state):
        return [(w.get('window_id'), w.get('title'), w.get('focused'))
                for w in state.get('windows', []) if w.get('focused')]
    if foreground(previous) != foreground(current):
        return False
    kind=requested.get('kind')
    # Navigation keys cannot submit messages. Permit them when the focused
    # window remains identical, even if its internal text updated.
    if kind=='key' and requested.get('key') in ('BACK','HOME'):
        return True
    if kind not in ('click','long_click','focus','set_text','selection','select','scroll','secondary'):
        return False
    def same(a,b):
        fields=('role','resource_id','text','description','bounds','enabled',
                'visible','password','window_id','editable')
        return all(a.get(f)==b.get(f) for f in fields)
    selector=requested.get('selector')
    if selector:
        try:
            a=select(previous.get('nodes',[]),selector)
            b=select(current.get('nodes',[]),selector)
        except UseError:
            return False
        if not same(a,b):
            return False
        # Node IDs in UI Automator are positional; rebase a non-node selector
        # only if it identifies exactly one unchanged target.
        if 'node_id' in selector and a.get('node_id')!=b.get('node_id'):
            return False
        if kind in ('set_text','selection') and not a.get('editable',False):
            return False
        if kind=='scroll' and not a.get('scrollable',False):
            return False
        return True
    if kind not in ('click','long_click','focus','scroll'):
        return False
    x,y=requested.get('x'),requested.get('y')
    if type(x)!=int or type(y)!=int:
        return False
    def hit(snapshot):
        candidates=[]
        for n in snapshot.get('nodes',[]):
            b=n.get('bounds')
            if not isinstance(b,list) or len(b)!=4 or not (b[0]<=x<b[2] and b[1]<=y<b[3]):
                continue
            if not n.get('visible',True) or not n.get('enabled',False):
                continue
            acts=n.get('actions',[])
            if kind=='scroll':
                useful=n.get('scrollable',False)
            else:
                useful=kind in acts
            if useful:
                candidates.append(n)
        if not candidates:
            return None
        candidates.sort(key=lambda n: ((n['bounds'][2]-n['bounds'][0])*(n['bounds'][3]-n['bounds'][1]),n['node_id']))
        return candidates[0]
    a,b=hit(previous),hit(current)
    if a is None or b is None or a.get('node_id')!=b.get('node_id'):
        return False
    # An anonymous generic container is not a safe semantic anchor.
    if not any(a.get(k) for k in ('text','description','resource_id')):
        return False
    return same(a,b)


class Engine:
    def __init__(self,backend,journal_path,clock=time.monotonic):
        self.backend=backend;self.clock=clock;self.journal=Journal(journal_path)
        self.session=None;self.observation=None;self.lock=threading.RLock()
    def close(self):self.journal.close()
    def lease(self,args):
        n=args.get('lease_seconds',300)
        if type(n)!=int or not 30<=n<=1800:raise UseError('Lease must be 30..1800 seconds')
        return n
    def expire(self):
        with self.lock:
            if self.session and self.clock()>=self.session['expires_at']:
                self.backend.stop();self.session=None;self.observation=None
    def require_session(self,args):
        self.expire()
        if not self.session or args.get('session_id')!=self.session['session_id']:raise UseError('Missing, expired or different session','SESSION_EXPIRED')
    def execute(self,op,args,request_id):
        with self.lock:
            if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',request_id):raise UseError('Invalid request_id')
            if op not in FIELDS or not isinstance(args,dict) or set(args)-FIELDS[op]:raise UseError('Unknown operation or arguments')
            prior=self.journal.get(request_id)
            if prior:
                if prior[0]!=digest([op,args]):raise UseError('request_id was already used with different arguments')
                if prior[1] in ('failed','uncertain','started','compacted'):raise UseError((prior[2] or {}).get('error','Outcome unknown'),(prior[2] or {}).get('code','UNCERTAIN'))
                return prior[2]
            if self.journal.uncertain() and op not in READ_ONLY|{'reconcile','session_stop'}:raise UseError('Uncertain operation blocks new inputs; inspect and reconcile','BLOCKED')
            try:self.journal.begin(request_id,op,args)
            except RuntimeError as e:raise UseError(str(e),'JOURNAL_FULL') from e
            try:
                result=self._run_batch(copy.deepcopy(args),request_id) if op=='batch' else self._run(op,copy.deepcopy(args))
            except UseError as e:
                self.journal.finish(request_id,'failed',{'error':str(e),'code':e.code});raise
            except Exception as e:
                status='failed' if op in READ_ONLY else 'uncertain'
                result={'error':'Backend operation did not produce a verified receipt','code':'BACKEND_FAILED' if status=='failed' else 'UNCERTAIN'}
                if isinstance(e,BackendOutcomeUnknown):
                    result['backend_reason']=e.reason
                    result['error']+=' ('+e.reason+'). Inspect the screen and reconcile the checked outcome; do not replay input.'
                self.journal.finish(request_id,status,result);raise UseError(result['error'],result['code']) from e
            # Persist confirmed input before any optional follow-up read. A
            # crash during that read must retain the original applied receipt.
            self.journal.finish(request_id,'completed',result)
            if op=='action' and result.get('applied') is True:
                result=copy.deepcopy(result)
                try:result['observation']=self._run('observe',{'session_id':self.session['session_id'],'screenshot':False})
                except Exception:
                    self.observation=None
                    result['observation_error']={'code':'BACKEND_FAILED','instruction':'Input was applied. Observe again; do not repeat the action.'}
                else:result['instruction']='Use the returned observation for verification and the next action; refresh if the interface is still changing.'
                self.journal.finish(request_id,'completed',result)
            return result
    def _current_observation(self,session_id):
        self.require_session({'session_id':session_id})
        return self.observation
    def _run_batch(self,args,parent_id):
        from .mcp import TOOLS, validate
        schema=next(t['inputSchema'] for t in TOOLS if t['name']=='use_batch')
        validate(schema,{**args,'device_id':'local','request_id':parent_id})
        # Validate the entire recipe before its first input. Selectors describe
        # semantics across screens; positional IDs/coordinates cannot be reused.
        steps=args.get('steps');timeout=args.get('timeout_ms',15000)
        if not isinstance(steps,list) or not 1<=len(steps)<=12:raise UseError('Batch needs 1..12 steps')
        if type(timeout)!=int or not 1<=timeout<=30000:raise UseError('timeout_ms must be 1..30000')
        stable={'resource_id','text','description','role','occurrence'}
        allowed={'click','long_click','focus','set_text','selection','select','scroll','key'}
        for step in steps:
            if not isinstance(step,dict) or set(step)-{'action','wait_for','wait_timeout_ms'}:raise UseError('Invalid batch step')
            action=step.get('action')
            if not isinstance(action,dict) or action.get('kind') not in allowed:raise UseError('Unsupported batch action')
            if set(action)&{'x','y','paths','from_x','from_y','to_x','to_y'}:raise UseError('Batch requires semantic targets')
            kind=action['kind']
            if kind in ('click','long_click') and not 1<=action.get('click_count',1)<=3:raise UseError('click_count must be 1..3')
            if kind=='set_text':
                if not isinstance(action.get('text'),str):raise UseError('set_text requires text')
                mode=action.get('mode','replace')
                if mode not in ('replace','append','insert'):raise UseError('Unknown text mode')
                if mode=='insert':
                    start=action.get('start');end=action.get('end',start)
                    if type(start)!=int or type(end)!=int or not 0<=start<=end:raise UseError('Invalid replacement range')
            if kind=='selection':
                start=action.get('start');end=action.get('end')
                if type(start)!=int or type(end)!=int or not 0<=start<=end:raise UseError('Invalid selection range')
            if kind=='key' and not isinstance(action.get('key'),str):raise UseError('key requires key name')
            if kind=='key' and not 1<=len(action['key'])<=100:raise UseError('Invalid key')
            if kind=='scroll' and 'direction' in action and not action['direction']:raise UseError('Invalid scroll direction')
            selectors=[action.get('selector')]
            if action['kind']=='key' and 'selector' not in action:selectors=[]
            if 'wait_for' in step:selectors.append(step['wait_for'])
            for selector in selectors:
                if not isinstance(selector,dict) or not selector or set(selector)-stable or not set(selector)-{'occurrence'}:raise UseError('Batch requires stable selectors')
            delay=step.get('wait_timeout_ms',2000)
            if type(delay)!=int or not 0<=delay<=5000:raise UseError('wait_timeout_ms must be 0..5000')
        sid=args.get('session_id');obs=self._current_observation(sid)
        if not obs or args.get('observation_id')!=obs['observation_id'] or self.clock()>=obs['expires_at']:raise UseError('Observation expired or already consumed','STALE')
        deadline=self.clock()+timeout/1000
        result={'status':'running','completed':0,'total':len(steps),'steps':[]}
        def checkpoint():self.journal.finish(parent_id,'started',result)
        def stop(index,code,error):
            result.update(status='stopped',stopped_at=index,code=code,error=error)
            result.pop('inflight_request_id',None)
            if obs is not None:result['observation']=copy.deepcopy(obs)
            return result
        checkpoint()
        for index,step in enumerate(steps):
            if self.clock()>=deadline:return stop(index,'TIMEOUT','Batch deadline reached; later steps were not started')
            if 'wait_for' in step:
                until=min(deadline,self.clock()+step.get('wait_timeout_ms',2000)/1000)
                while True:
                    try:
                        obs=self._run('observe',{'session_id':sid,'screenshot':False})
                        # An ambiguous match is a stop, not permission to pick.
                        selector=step['wait_for']
                        matches=[n for n in obs.get('nodes',[]) if all(n.get(k)==v for k,v in selector.items() if k!='occurrence')]
                        if matches:
                            select(obs.get('nodes',[]),selector)
                            break
                    except UseError as error:return stop(index,error.code,str(error))
                    except Exception:return stop(index,'BACKEND_FAILED','Could not observe the awaited target')
                    remaining=until-self.clock()
                    if remaining<=0:return stop(index,'TIMEOUT','Awaited target did not appear uniquely')
                    time.sleep(min(.1,remaining))
            if self.clock()>=deadline:return stop(index,'TIMEOUT','Batch deadline reached; later steps were not started')
            child_id='batch_'+digest(parent_id)[:48]+'_%02d'%index
            result['inflight_request_id']=child_id
            checkpoint()  # Crash recovery retains identity before any input.
            entry={'index':index,'request_id':child_id,'applied':False,'status':'not_started'}
            try:
                receipt=self.execute('action',{'session_id':sid,'observation_id':obs['observation_id'],'action':step['action']},child_id)
            except UseError as error:
                saved=self.journal.get(child_id)
                entry['status']=saved[1] if saved else 'not_started'
                entry.update(code=error.code,error=str(error))
                result['steps'].append(entry)
                try:obs=self._current_observation(sid)
                except UseError:obs=None
                return stop(index,error.code,str(error))
            entry.update(applied=receipt.get('applied') is True,status='completed')
            result['steps'].append(entry)
            if entry['applied']:result['completed']+=1
            result.pop('inflight_request_id',None)
            checkpoint()
            obs=receipt.get('observation')
            if not entry['applied']:return stop(index,'RECEIPT_NOT_CONFIRMED','Step did not confirm applied input')
            if obs is None:return stop(index,'OBSERVATION_FAILED','Input was applied; observe again before further input')
        result['status']='completed'
        result['observation']=copy.deepcopy(obs)
        return result
    def _run(self,op,args):
        if op=='capabilities':return {**self.backend.capabilities(),'batch':True,'max_batch_steps':12,'max_batch_timeout_ms':30000}
        if op=='apps':return {'apps':self.backend.apps()}
        if op=='diagnostics':return {'blocked':bool(self.journal.uncertain()),'uncertain_requests':self.journal.uncertain(),'session':self.session,'backend':self.backend.diagnostics()}
        if op=='result':
            r=self.journal.get(args.get('request_id'))
            if r is None:raise UseError('Request not found')
            return {'status':r[1],'result':r[2]}
        if op=='reconcile':
            rid=args.get('request_id');r=self.journal.get(rid)
            if r is None or r[1]!='uncertain':raise UseError('Only an uncertain request may be reconciled')
            outcome=args.get('outcome');evidence=args.get('evidence')
            if outcome not in ('applied','not_applied') or not isinstance(evidence,str) or not 1<=len(evidence)<=2000:raise UseError('Explicit checked outcome and evidence required')
            self.journal.finish(rid,'reconciled',{'outcome':outcome,'evidence':evidence});self.observation=None
            return {'reconciled':rid,'replayed':False}
        if op=='session_start':
            self.expire()
            if self.session:raise UseError('A session already exists; extend or close it')
            n=self.lease(args);started=self.backend.start(target=args.get('target'),lease_seconds=n)
            self.session={'session_id':secrets.token_hex(16),'expires_at':self.clock()+n,'target':started['target']}
            return dict(self.session)
        self.require_session(args)
        if op=='session_stop':
            result=self.backend.stop();self.session=None;self.observation=None;return result
        if op=='session_extend':
            n=self.lease(args);self.backend.extend(n);self.session['expires_at']=self.clock()+n;return dict(self.session)
        if op=='launch':
            app=args.get('app_id')
            if app not in {a['app_id'] for a in self.backend.apps()}:raise UseError('App must be returned by apps')
            self.observation=None;return self.backend.launch(app)
        if op=='observe':
            if type(args.get('screenshot',False))!=bool:raise UseError('screenshot must be boolean')
            data=self.backend.snapshot(screenshot=args.get('screenshot',False))
            data=sanitize(copy.deepcopy(data))
            data['fingerprint']=fingerprint(data)
            data.update({'session_id':self.session['session_id'],'observation_id':secrets.token_hex(16),'expires_at':min(self.session['expires_at'],self.clock()+90)})
            self.observation=data;return copy.deepcopy(data)
        if op=='action':
            obs=self.observation;self.observation=None
            if not obs or args.get('observation_id')!=obs['observation_id'] or self.clock()>=obs['expires_at']:raise UseError('Observation expired or already consumed','STALE')
            requested=args.get('action')
            # A UI screenshot can be very expensive, and image bytes are not
            # needed to verify a semantic target. Read the native tree only.
            # Windows coordinate actions require a current screenshot and a
            # verified fingerprint; Android semantic reads stay tree-only.
            coordinate_input=isinstance(requested,dict) and not requested.get('selector') and requested.get('kind') in ('click','long_click','focus','scroll','drag','gesture')
            visual=bool(obs.get('screenshot')) and coordinate_input and self.backend.capabilities().get('platform')=='windows'
            current=sanitize(self.backend.snapshot(screenshot=visual))
            current['fingerprint']=fingerprint(current)
            unchanged=(current['fingerprint']==obs['fingerprint'])
            if not unchanged and not stable_action_target(obs,current,requested if isinstance(requested,dict) else {}):
                raise UseError('Input target or foreground changed; observe again','STALE')
            # Bind the action to the verified *current* node tree and to the
            # current native fingerprint for a second, atomic Java-side check.
            action=self.validate_action(requested,current)
            return self.backend.action(action,current)
        raise UseError('Unsupported operation')
    def validate_action(self,a,obs):
        if not isinstance(a,dict):raise UseError('action must be an object')
        a=copy.deepcopy(a);kind=a.get('kind')
        allowed={'click','long_click','focus','set_text','selection','select','scroll','key','gesture','secondary','drag'}
        if kind not in allowed:raise UseError('Unknown action')
        if kind in ('click','long_click'):
            count=a.get('click_count',1)
            if type(count)!=int or not 1<=count<=3:raise UseError('click_count must be 1..3')
        fields={'kind','selector','x','y','text','mode','start','end','key','paths','duration_ms','direction','scroll_x','scroll_y','button','click_count','from_x','from_y','to_x','to_y','action'}
        if set(a)-fields:raise UseError('Unknown action field')
        node=None
        if 'selector' in a:
            node=select(obs.get('nodes',[]),a.pop('selector'))
            if node.get('password') or not node.get('enabled',False) or not node.get('visible',True):raise UseError('Element is protected, disabled or invisible')
            if kind not in node.get('actions',[]) and kind not in ('secondary',):raise UseError('Element does not expose '+kind,'UNSUPPORTED')
            a['node_id']=node['node_id'];a['window_id']=node['window_id']
        w,h=obs['geometry']['width'],obs['geometry']['height']
        def point(x,y):
            if type(x)!=int or type(y)!=int or not 0<=x<w or not 0<=y<h:raise UseError('Point outside observed geometry')
        if kind in ('click','long_click','focus') and node is None:point(a.get('x'),a.get('y'))
        if kind in ('set_text','selection','select','secondary') and node is None:raise UseError('This action requires a selector')
        if kind=='set_text':
            text=a.get('text')
            if not isinstance(text,str) or '\0' in text or len(text)>65536:raise UseError('Invalid input text')
            mode=a.pop('mode','replace');old=node.get('text','')
            if mode in ('append','insert') and node.get('text_value_known') is False:raise UseError('Native field value unavailable; use explicit replacement','UNSUPPORTED')
            if mode=='append':text=old+text
            elif mode=='insert':
                start=a.get('start');end=a.get('end',start)
                if type(start)!=int or type(end)!=int or not 0<=start<=end<=len(old):raise UseError('Invalid replacement range')
                text=old[:start]+text+old[end:]
            elif mode!='replace':raise UseError('Unknown text mode')
            if len(text)>65536:raise UseError('Text too long')
            a['text']=text
        if kind=='selection':
            start=a.get('start');end=a.get('end')
            if type(start)!=int or type(end)!=int or not 0<=start<=end<=len(node.get('text','')):raise UseError('Invalid selection range')
        if kind=='key':
            if not isinstance(a.get('key'),str) or len(a['key'])>100:raise UseError('Invalid key')
        if kind=='gesture':
            paths=a.get('paths');duration=a.get('duration_ms',500)
            if not isinstance(paths,list) or not 1<=len(paths)<=5 or type(duration)!=int or not 80<=duration<=5000:raise UseError('Invalid gesture')
            count=None
            for path in paths:
                if not isinstance(path,list) or not 2<=len(path)<=120:raise UseError('Gesture path needs 2..120 points')
                if count is None:count=len(path)
                if len(path)!=count:raise UseError('All fingers need equal point counts')
                for p in path:
                    if not isinstance(p,list) or len(p)!=2:raise UseError('Invalid point')
                    point(*p)
        if kind=='drag':point(a.get('from_x'),a.get('from_y'));point(a.get('to_x'),a.get('to_y'))
        if kind=='scroll' and node is None:point(a.get('x'),a.get('y'))
        return a
