"""Standalone Windows UIA backend; injectable driver keeps OS effects testable."""
import base64, io, os, re, subprocess
from collections import deque
from .engine import UseError
from .journal import digest
from . import __version__

def key_sequence(key):
    parts=key.split('+');modifiers={'Control_L':'^','Ctrl':'^','Control':'^','Shift_L':'+','Shift':'+','Alt_L':'%','Alt':'%'}
    prefix=''
    for part in parts[:-1]:
        if part not in modifiers:raise UseError('Unsupported modifier')
        prefix+=modifiers[part]
    last=parts[-1];named={'Return':'ENTER','Enter':'ENTER','Tab':'TAB','Escape':'ESC','BackSpace':'BACKSPACE','Delete':'DELETE','Left':'LEFT','Right':'RIGHT','Up':'UP','Down':'DOWN','Home':'HOME','End':'END','Page_Up':'PGUP','Page_Down':'PGDN','space':'SPACE'}
    if last in named:return prefix+'{'+named[last]+'}'
    if re.fullmatch(r'[A-Za-z0-9]',last):return prefix+last
    if re.fullmatch(r'F(?:[1-9]|1[0-2])',last):return prefix+'{'+last+'}'
    raise UseError('Unsupported key; raw macros are not accepted')

def pattern(node,name):
    try:return getattr(node,'iface_'+name)
    except Exception:return None

class NativeDriver:
    def __init__(self):
        if os.name!='nt':raise UseError('Windows backend requires Windows')
        try:
            from pywinauto import Desktop,mouse,keyboard
            import psutil,ctypes
        except ImportError as e:raise UseError('Install requirements-windows.txt') from e
        self.desktop=Desktop(backend='uia');self.mouse=mouse;self.keyboard=keyboard;self.psutil=psutil
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        from ctypes import wintypes
        self.user.GetForegroundWindow.restype=wintypes.HWND
        self.user.WindowFromPoint.argtypes=[wintypes.POINT];self.user.WindowFromPoint.restype=wintypes.HWND
        self.user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];self.user.GetAncestor.restype=wintypes.HWND
        self.point=wintypes.POINT
        # Align UIA screen coordinates and screenshots on scaled desktops.
        try:self.user.SetProcessDpiAwarenessContext(-4)
        except Exception:pass
    def windows(self):return self.desktop.windows(visible_only=True)
    def identity(self,w):
        p=self.psutil.Process(w.element_info.process_id);return p.exe(),p.create_time()
    def foreground(self):return self.user.GetForegroundWindow()
    def hit(self,coords):return self.user.GetAncestor(self.user.WindowFromPoint(self.point(*coords)),2)
    def image_png(self,w):
        image=w.capture_as_image()
        if image is None:raise UseError('Screenshot unavailable')
        out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()
    def click(self,coords,button):self.mouse.click(coords=coords,button=button)
    def keys(self,keys):self.keyboard.send_keys(keys,pause=.05)
    def press(self,coords):self.mouse.press(coords=coords)
    def move(self,coords):self.mouse.move(coords=coords)
    def release(self,coords):self.mouse.release(coords=coords)
    def scroll(self,coords,distance):self.mouse.scroll(coords=coords,wheel_dist=distance)
    def launch(self,path):subprocess.Popen([path])

class WindowsBackend:
    def __init__(self,driver=None):self.driver=driver or NativeDriver();self.binding=None;self.handles={}
    def capabilities(self):return {'platform':'windows','version':__version__,'backend':'pywinauto-uia','standalone':True,'actions':['click','focus','set_text','select','key','drag','scroll'],'unicode':True,'multitouch':False,'apps_scope':'running windows','screenshot_requires_foreground':True,'secure_desktop':False}
    def validate_batch_action(self,action):
        # Static native constraints are known before any preceding batch input.
        kind=action.get('kind')
        if kind=='key':
            if not isinstance(action.get('key'),str):raise UseError('key requires a native key name')
            key_sequence(action['key'])
        if kind=='scroll':raise UseError('Native batch does not support semantic scroll; coordinate scroll needs an observed screenshot','UNSUPPORTED')
        if kind=='click' and action.get('button','left')!='left':raise UseError('Native semantic batch click supports only Invoke/left button','UNSUPPORTED')
    def apps(self):
        apps={}
        for w in self.driver.windows():
            try:path,_=self.driver.identity(w)
            except Exception:continue
            app=apps.setdefault(path,{'app_id':path,'name':os.path.basename(path),'windows':[]})
            app['windows'].append({'window_id':str(w.handle),'title':w.element_info.name})
        return list(apps.values())
    def start(self,target=None,lease_seconds=300):
        candidates=[]
        for w in self.driver.windows():
            try:identity=self.driver.identity(w)
            except Exception:continue
            if target is None or str(w.handle)==str(target) or identity[0]==target:candidates.append((w,identity))
        if len(candidates)!=1:raise UseError('Select exactly one returned window target')
        w,identity=candidates[0];self.binding=(w.handle,w.element_info.process_id,identity);return {'target':str(w.handle)}
    def current(self):
        if not self.binding:raise UseError('No selected window','SESSION_EXPIRED')
        hwnd,pid,identity=self.binding
        for w in self.driver.windows():
            if w.handle==hwnd and w.element_info.process_id==pid and self.driver.identity(w)==identity:return w
        raise UseError('Window closed or handle was reused','SESSION_EXPIRED')
    def stop(self):self.binding=None;self.handles={};return {'stopped':True,'windows_closed':False}
    def extend(self,seconds):self.current();return {'extended':seconds}
    def launch(self,app):
        if app not in {a['app_id'] for a in self.apps()}:raise UseError('Discover application first')
        self.driver.launch(app);return {'requested':app,'verify_with_observe':True}
    def snapshot(self,screenshot=False):
        w=self.current();rect=w.rectangle();wid=str(w.handle);nodes=[];self.handles={};q=deque([(w,None,0)]);seen=set()
        while q and len(nodes)<2000:
            c,parent,depth=q.popleft();info=c.element_info
            rid=tuple(info.runtime_id or ())
            if not rid:continue
            nid=wid+'/'+'.'.join(map(str,rid))
            if nid in seen:continue
            seen.add(nid)
            try:protected=bool(info.element.CurrentIsPassword)
            except Exception:protected=True
            value=pattern(c,'value') if not protected else None
            known=False;text='';actions=[]
            if not protected:
                actions.append('focus');text=info.name or ''
                if value is not None:
                    try:
                        text=str(value.CurrentValue);known=True
                        if not value.CurrentIsReadOnly:actions.append('set_text')
                    except Exception:pass
                if pattern(c,'invoke') is not None:actions.append('click')
                if pattern(c,'selection_item') is not None:actions.append('select')
            r=c.rectangle()
            try:focused=bool(info.element.CurrentHasKeyboardFocus)
            except Exception:focused=False
            nodes.append({'node_id':nid,'parent_id':parent,'window_id':wid,'resource_id':info.automation_id or '', 'role':info.control_type,'text':text,'text_value_known':known,'description':'' if protected else info.name or '', 'password':protected,'focused':focused,'editable':'set_text' in actions,'scrollable':False,'enabled':c.is_enabled(),'visible':c.is_visible(),'actions':actions,'bounds':[r.left-rect.left,r.top-rect.top,r.right-rect.left,r.bottom-rect.top]})
            self.handles[nid]=c
            if depth<40:
                for child in c.children():q.append((child,nid,depth+1))
        state={'target':wid,'geometry':{'width':rect.right-rect.left,'height':rect.bottom-rect.top},'origin':[rect.left,rect.top],'windows':[{'window_id':wid,'title':w.element_info.name,'app':self.binding[2][0]}],'nodes':nodes,'truncated':bool(q)}
        if state['geometry']['width']<=0 or state['geometry']['height']<=0:raise UseError('Window geometry unavailable')
        state['native_fingerprint']=digest(state)
        if screenshot:
            if self.driver.foreground()!=w.handle:raise UseError('Bring selected window to foreground before screenshot')
            state['screenshot']={'mime_type':'image/png','base64':base64.b64encode(self.driver.image_png(w)).decode()}
        return state
    def action(self,a,observation):
        from .engine import fingerprint,sanitize
        fresh=self.snapshot(bool(observation.get('screenshot')))
        if fingerprint(sanitize(fresh))!=observation['fingerprint']:raise UseError('Interface changed','STALE')
        w=self.current();kind=a['kind'];c=self.handles.get(a.get('node_id'));coords=None
        def point(x,y):
            if not observation.get('screenshot'):raise UseError('Coordinates require a screenshot')
            if self.driver.foreground()!=w.handle:raise UseError('Selected window is not foreground')
            p=(fresh['origin'][0]+x,fresh['origin'][1]+y)
            if self.driver.hit(p)!=w.handle:raise UseError('Coordinate is covered by another window')
            return p
        if kind=='key':
            keys=key_sequence(a['key'])
            if self.driver.foreground()!=w.handle:raise UseError('Selected window is not foreground')
        elif kind=='drag':
            first=point(a['from_x'],a['from_y']);last=point(a['to_x'],a['to_y'])
        elif c is None and kind in ('click','focus','scroll'):coords=point(a['x'],a['y'])
        elif c is None:raise UseError('Unsupported action','UNSUPPORTED')
        if kind=='click' and a.get('button','left') not in ('left','right','middle'):raise UseError('Unsupported button')
        if kind=='scroll' and (c is not None or a.get('scroll_x',0)):raise UseError('Only coordinate vertical scroll supported','UNSUPPORTED')
        if kind not in self.capabilities()['actions']:raise UseError('Unsupported action','UNSUPPORTED')
        # Native exceptions after this boundary are UNKNOWN, never replayable.
        if kind=='set_text':c.iface_value.SetValue(a['text'])
        elif kind=='select':c.iface_selection_item.Select()
        elif kind=='focus':c.set_focus() if c is not None else self.driver.click(coords,'left')
        elif kind=='key':self.driver.keys(keys)
        elif kind=='click':
            for _ in range(a.get('click_count',1)):
                if c is not None:c.iface_invoke.Invoke()
                else:self.driver.click(point(a['x'],a['y']),a.get('button','left'))
        elif kind=='scroll':self.driver.scroll(coords,a.get('scroll_y',0))
        elif kind=='drag':
            try:self.driver.press(first);self.driver.move(last)
            finally:self.driver.release(last)
        return {'applied':True,'window_id':str(w.handle)}
    def diagnostics(self):return {'binding':self.binding,'windows':self.apps()}
