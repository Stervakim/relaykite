"""Native saved ChatGPT conversation over the owner's existing Portable IPC.

Runs on Android itself. No ADB, browser, credential extraction or model API.
Uncertain actions are journaled before input and never automatically replayed.
"""
from __future__ import annotations
from contextlib import contextmanager
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid


class DriverStop(RuntimeError):
    def __init__(self, reason, state='waiting_user'):
        self.state = state
        super().__init__(reason)


def json_answer(text):
    text = text.strip()
    if text.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', text, re.S)
        if not match: return None
        text = match[1].strip()
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return text if isinstance(value, dict) else None


def bound_answer(text, nonce):
    """A visible reply must prove it belongs to this confirmed send."""
    answer=json_answer(text)
    if answer is None:return None
    value=json.loads(answer)
    if value.pop('_relaykite_request_id',None)!=nonce:return None
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def installed_peer():
    # Fixed installed source, never a path supplied by model output.
    directory = Path('/data/adb/modules/mini_codex/agent')
    if os.name != 'posix' or os.geteuid() != 0 or not directory.is_dir():
        raise DriverStop('The native UI driver requires the installed Android root service')
    sys.path.insert(0, str(directory))
    from portable_peer import call
    return call


class AndroidDriver:
    def __init__(self, root, *, peer=None, clock=time.monotonic, sleep=time.sleep):
        self.root = Path(root)
        if self.root.is_symlink(): raise DriverStop('UI state symlink rejected')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / 'session.json'
        if self.path.is_symlink(): raise DriverStop('UI session symlink rejected')
        self.state = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}
        self.peer = peer
        self.clock = clock; self.sleep = sleep; self.timeout = 480
        self.sent = False

    @contextmanager
    def exclusive(self):
        """A crashed process releases ownership; a concurrent driver cannot send."""
        path = self.root / 'driver.lock'
        if path.is_symlink(): raise DriverStop('UI ownership symlink rejected')
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        stream = os.fdopen(fd, 'r+b')
        acquired = False
        try:
            try:
                if os.name == 'nt':
                    import msvcrt
                    if stream.seek(0, os.SEEK_END) == 0:
                        stream.write(b'\0'); stream.flush()
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as error:
                raise DriverStop('Another native driver owns this saved conversation') from error
            yield
        finally:
            if acquired:
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()

    def save(self):
        temporary = self.root / ('.session-' + uuid.uuid4().hex)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(self.state, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def op(self, operation, **arguments):
        request_id = 'rkui_' + uuid.uuid4().hex
        mutation = operation not in ('capabilities', 'observe', 'result')
        if mutation:
            if self.state.get('pending'):
                raise DriverStop('An earlier input receipt is unresolved; new input is blocked', 'uncertain')
            self.state['pending'] = {'operation': operation, 'request_id': request_id}
            self.save()
        try:
            result = self.peer(operation, arguments, request_id)
        except Exception as error:
            raise DriverStop('Portable IPC outcome unknown; inspect the saved request receipt', 'uncertain') from error
        if not isinstance(result, dict): raise DriverStop('Malformed Portable response', 'uncertain')
        if result.get('code') == 'SESSION_EXPIRED' and operation in ('session_stop','session_extend'):
            self.state.pop('pending', None); self.save()
            if operation == 'session_stop': return {'ok':True,'already_expired':True}
            raise DriverStop('The owned ChatGPT display lease expired; reopen the task conversation before resuming')
        if result.get('status') == 'failed' and result.get('result', {}).get('code') == 'RESOURCE_CONFLICT' and operation == 'launch':
            self.state.pop('pending', None); self.save()
            raise DriverStop('ChatGPT is already owned by another virtual session; close that session before continuing')
        if result.get('error'):
            # Keep the original receipt for reconciliation. An error can report
            # an unknown backend outcome, and a probe cannot resolve old input.
            raise DriverStop(str(result.get('error'))[:300], 'uncertain' if mutation or self.sent else 'waiting_user')
        if mutation:
            if result.get('status') in ('pending', 'running', 'uncertain', 'stopped'):
                raise DriverStop('Portable input has no final confirmed receipt', 'uncertain')
            if operation == 'action' and result.get('applied') is not True:
                raise DriverStop('Input was not confirmed; inspect the original request receipt', 'uncertain')
            if operation == 'session_start' and (not result.get('session_id') or result.get('target') is None
                                                or str(result.get('target')) == '0'):
                raise DriverStop('Virtual display creation was not confirmed; inspect its receipt', 'uncertain')
            self.state.pop('pending', None); self.save()
        return result

    def observe(self, *, wait_focus=False):
        # Launch acknowledgement precedes Android's window-focus transition.
        # Only fresh reads are retried here; no input action is replayed.
        for attempt in range(25 if wait_focus else 1):
            result = self.op('observe', session_id=self.state['session_id'])
            windows = [w for w in result.get('windows', []) if w.get('focused')]
            if windows and all(w.get('title') == 'ChatGPT' for w in windows):
                break
            if not wait_focus or attempt == 24:
                raise DriverStop('ChatGPT is not the focused app on the owned virtual display', 'uncertain' if self.sent else 'waiting_user')
            self.sleep(.2)
        if not result.get('observation_id') or not isinstance(result.get('nodes'), list):
            raise DriverStop('Native observation is incomplete', 'uncertain')
        return result

    def settled_observe(self, *, wait_focus=False):
        previous = None; repeats = 0
        for _ in range(25):
            state = self.observe(wait_focus=wait_focus)
            signature = json.dumps({key:state.get(key) for key in ('windows','nodes','geometry')}, sort_keys=True)
            repeats = repeats + 1 if signature == previous else 0
            if repeats >= 2: return state
            previous = signature
            self.sleep(.25)
        raise DriverStop('ChatGPT layout is still changing; no new input was sent', 'uncertain' if self.sent else 'waiting_user')

    def action(self, state, node, kind='click', **extra):
        if state.get('truncated'):
            raise DriverStop('The native tree is incomplete; fresh full UI evidence is required',
                             'uncertain' if self.sent else 'waiting_user')
        if node.get('password'): raise DriverStop('Protected field rejected')
        if kind == 'click':
            nodes = {n['node_id']: n for n in state['nodes']}
            visited = set()
            while kind not in node.get('actions', []):
                ident = node.get('node_id')
                if ident in visited: raise DriverStop('Cyclic accessibility ancestry rejected')
                visited.add(ident)
                node = nodes.get(node.get('parent_id'))
                if node is None: raise DriverStop('No accessible control for the observed label')
            if node.get('password') or not node.get('enabled', True) or not node.get('visible', True):
                raise DriverStop('The observed control is protected or unavailable')
        result = self.op('action', session_id=self.state['session_id'], observation_id=state['observation_id'],
                         action={'kind': kind, 'selector': {'node_id': node['node_id']}, **extra})
        if result.get('applied') is not True:
            raise DriverStop('Input was not confirmed; inspect the original request receipt', 'uncertain')

    @staticmethod
    def labeled(state, labels):
        matches = [n for n in state['nodes'] if n.get('visible', True) and (n.get('description') in labels or n.get('text') in labels)]
        if len(matches) != 1: raise DriverStop('Expected one ChatGPT control: ' + '/'.join(labels))
        return matches[0]

    @staticmethod
    def editor(state):
        matches = [n for n in state['nodes'] if n.get('editable') and n.get('visible', True) and not n.get('password')]
        if len(matches) != 1: raise DriverStop('ChatGPT composer is unavailable; open the signed-in native app')
        return matches[0]

    def start_chat(self, run_id):
        if self.state.get('session_id'):
            self.op('session_stop', session_id=self.state['session_id'])
        self.state = {'run_id': run_id}; self.save()
        session = self.op('session_start', lease_seconds=1800)
        if not session.get('session_id') or str(session.get('target', '0')) == '0':
            raise DriverStop('Owned nonzero virtual display was not created', 'uncertain')
        self.state['session_id'] = session['session_id']; self.save()
        self.op('launch', session_id=session['session_id'], app_id='com.openai.chatgpt/com.openai.chatgpt.MainActivity')
        state = self.settled_observe(wait_focus=True)
        self.action(state, self.labeled(state, ('Меню', 'Menu', 'Open navigation menu')))
        state = self.settled_observe()
        self.action(state, self.labeled(state, ('Новый чат', 'New chat')))
        state = self.settled_observe()
        if self.editor(state).get('text'): raise DriverStop('New conversation composer is not empty')
        if any(n.get('text') in ('Временный чат', 'Temporary chat') for n in state['nodes']):
            raise DriverStop('A normal saved conversation is required; temporary chats are disabled')
        self.state['conversation_ready'] = True; self.save()

    def generate(self, request):
        prompt = request.get('prompt')
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode('utf-16-le')) // 2 > 65000:
            raise DriverStop('Native composer accepts at most 65000 UTF-16 units; compact context before sending')
        if request.get('images'): raise DriverStop('Native attachment transport has not been verified')
        run_id = request.get('run_id')
        if not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id): raise DriverStop('A durable run identity is required')
        if self.state.get('pending'): raise DriverStop('Saved UI action outcome needs reconciliation before new input', 'uncertain')
        request_id = request.get('request_id')
        if not isinstance(request_id, str) or not re.fullmatch('[A-Za-z0-9_-]{8,80}', request_id):
            raise DriverStop('A stable native request identity is required')
        digest = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
        previous = self.state.get('generation') or {}
        if previous and previous.get('stage') != 'completed':
            self.sent = previous.get('stage') in ('send_pending', 'awaiting_reply')
            raise DriverStop('A saved generation is incomplete; inspect its existing conversation before further input', 'uncertain')
        if previous.get('request_id') == request_id:
            if (previous.get('prompt_sha256') != digest or previous.get('run_id') != run_id
                    or previous.get('fingerprint') != request.get('fingerprint')):
                raise DriverStop('Native request identity was reused with different input')
            cached = previous.get('result')
            if not isinstance(cached, dict):
                raise DriverStop('Completed native receipt is incomplete; do not replay input', 'uncertain')
            self.sent = True
            return dict(cached)
        nonce=uuid.uuid4().hex
        wire_prompt=(prompt+'\n\nRELAYKITE_REPLY_BINDING: '+nonce+
                     '\nFor reply tracking, include the additional root JSON field '
                     '"_relaykite_request_id":"'+nonce+'" in this response. '
                     'Keep the requested output schema otherwise unchanged. This field is removed by the local transport.')
        if len(wire_prompt.encode('utf-16-le'))//2>65000:
            raise DriverStop('Native request plus reply binding exceeds 65000 UTF-16 units; compact context before sending')
        self.peer = self.peer or installed_peer()
        if self.state.get('run_id') != run_id or not self.state.get('conversation_ready'):
            self.start_chat(run_id)
        else:
            self.op('session_extend', session_id=self.state['session_id'], lease_seconds=1800)
        state = self.settled_observe(); editor = self.editor(state)
        if editor.get('text'): raise DriverStop('Composer contains unsent text; inspect it before continuing')
        self.state['generation'] = {'request_id': request_id, 'fingerprint': request.get('fingerprint'),
            'prompt_sha256': digest, 'reply_nonce':nonce, 'run_id': run_id, 'stage': 'composing'}
        self.save()
        self.action(state, editor, 'set_text', text=wire_prompt)
        state = self.settled_observe(); editor = self.editor(state)
        if editor.get('text') != wire_prompt: raise DriverStop('Composer text was changed or truncated; message was not sent')
        send = [n for n in state['nodes'] if n.get('visible', True) and n.get('enabled', True)
                and not n.get('password') and n.get('description') in ('Отправить', 'Отправить сообщение', 'Send', 'Send message')]
        if not send:
            # Native ChatGPT's inspected send button is unlabelled. Restrict the
            # structural match to the editor's composer subtree and geometry.
            prefix = editor.get('parent_id', '').rsplit('/', 1)[0] + '/'
            right = state['geometry']['width']; bottom = state['geometry']['height']
            send = [n for n in state['nodes'] if n['node_id'].startswith(prefix) and 'click' in n.get('actions', [])
                    and 'long_click' in n.get('actions', []) and not n.get('editable') and n.get('enabled')
                    and n.get('bounds', [0,0,0,0])[0] > right * .75 and n['bounds'][1] > bottom * .75]
        if len(send) != 1: raise DriverStop('Native send control changed; inspect the composer before sending')
        self.sent = True
        self.state['last_request_id'] = request_id
        self.state['generation']['stage'] = 'send_pending'; self.save()
        self.action(state, send[0])
        self.state['generation']['stage'] = 'awaiting_reply'; self.save()
        deadline = self.clock() + self.timeout; stable = None; repeats = 0
        while self.clock() < deadline:
            self.sleep(1)
            state = self.observe()
            if state.get('truncated'):
                continue  # Never mistake an omitted stop/answer control for completion.
            nodes = state['nodes']
            generating = any(re.search(r'^(stop|остановить)', n.get('description', ''), re.I) for n in nodes)
            candidates = [parsed for n in nodes if not n.get('editable') and n.get('visible',True)
                          and (parsed:=bound_answer(n.get('text',''),nonce)) is not None]
            toolbar = any(re.search(r'copy|копир|read aloud|прочитать вслух|плохой ответ|bad response', n.get('description', ''), re.I) for n in nodes)
            idle_composer = any(re.search(r'^(начать голосовой разговор|start voice|start advanced voice)', n.get('description', ''), re.I)
                                and n.get('enabled', True) and n.get('visible', True) for n in nodes)
            candidate = candidates[-1] if candidates else None
            if candidate and candidate == stable and not generating and (toolbar or idle_composer):
                repeats += 1
                if repeats >= 2:
                    result = {'status':'completed', 'text':candidate, 'sent':True, 'transport':'android-native-ui'}
                    self.state['generation'].update(stage='completed', result=result)
                    self.save()
                    return result
            else:
                stable = candidate; repeats = 0
        raise DriverStop('No complete JSON response was confirmed; inspect the saved ChatGPT conversation', 'uncertain')

    def recover(self, request):
        """Read-only operator reconciliation of an explicitly inspected answer."""
        expected=request.get('confirm_response_sha256')
        generation=self.state.get('generation') or {}
        if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected):
            raise DriverStop('Recovery requires the SHA-256 of the explicitly inspected JSON response')
        if self.state.get('pending') or generation.get('stage')!='awaiting_reply':
            raise DriverStop('Only a confirmed send awaiting its reply can be reconciled', 'uncertain')
        self.peer=self.peer or installed_peer();self.sent=True
        candidate=None
        for _ in range(3):
            state=self.observe();nodes=state['nodes']
            if state.get('truncated') or any(re.search(r'^(stop|остановить)',n.get('description',''),re.I) for n in nodes):
                raise DriverStop('Response is not confirmed complete','uncertain')
            found=[answer for n in nodes if not n.get('editable') and (answer:=json_answer(n.get('text',''))) is not None
                   and hashlib.sha256(answer.encode('utf-8')).hexdigest()==expected]
            idle=any(re.search(r'copy|копир|read aloud|прочитать вслух|^(начать голосовой разговор|start voice|start advanced voice)',n.get('description',''),re.I) for n in nodes)
            if len(found)!=1 or not idle or (candidate is not None and candidate!=found[0]):
                raise DriverStop('Inspected response changed or completion control is unavailable','uncertain')
            candidate=found[0];self.sleep(1)
        # Pre-binding receipts remain recoverable only through explicit operator
        # evidence. New receipts additionally require the persisted request nonce.
        if generation.get('reply_nonce'):
            candidate=bound_answer(candidate,generation['reply_nonce'])
            if candidate is None:raise DriverStop('Inspected reply belongs to another request','uncertain')
        result={'status':'completed','text':candidate,'sent':True,'transport':'android-native-ui','reconciled':True}
        generation.update(stage='completed',result=result,recovery_evidence_sha256=expected);self.save()
        return result

    def run(self, request):
        self.sent = False
        try:
            with self.exclusive():
                if self.path.is_symlink(): raise DriverStop('UI session symlink rejected')
                self.state = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}
                if not isinstance(self.state, dict): raise DriverStop('UI session state is malformed')
                if request.get('operation') == 'probe':
                    self.peer = self.peer or installed_peer(); self.op('capabilities')
                    return {'status':'ready', 'reason':'Android Portable IPC available; native ChatGPT session is checked when a task starts',
                            'transport':'android-native-ui', 'image_input':False, 'live_verified':False, 'max_prompt_utf16':65000}
                if request.get('operation') == 'recover': return self.recover(request)
                if request.get('operation') != 'generate': raise DriverStop('Unsupported native driver operation')
                return self.generate(request)
        except DriverStop as error:
            return {'status':error.state,'reason':str(error),'sent':self.sent}
        except Exception:
            return {'status':'uncertain' if self.sent or self.state.get('pending') else 'waiting_user',
                    'reason':'Native UI failed; inspect the saved action receipt and existing conversation','sent':self.sent}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--state',type=Path,required=True); args=parser.parse_args()
    try:
        raw=sys.stdin.buffer.read(8*1024*1024+1)
        if len(raw)>8*1024*1024: raise ValueError('oversized input')
        request=json.loads(raw); result=AndroidDriver(args.state).run(request)
    except Exception:
        result={'status':'waiting_user','reason':'Native driver input or private state is invalid','sent':False}
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
