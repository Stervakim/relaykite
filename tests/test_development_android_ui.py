import json
import hashlib
import re
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc'))
from development.android_ui import AndroidDriver, DriverStop, json_answer


def node(ident, text='', description='', actions=(), parent=None, editable=False, bounds=None):
    return dict(node_id=ident, text=text, description=description, actions=list(actions), parent_id=parent,
                editable=editable, enabled=True, visible=True, bounds=bounds or [0, 0, 50, 50])


class PhoneFixture:
    def __init__(self):
        self.stage = 'home'; self.calls = []; self.prompt = ''; self.answer = '{"message":"done"}'; self.replies = 0
        self.latest_only=False;self.freeze_answer=False
    def __call__(self, operation, args, request_id):
        self.calls.append((operation, args, request_id))
        if operation == 'capabilities': return {'platform':'android', 'max_text':65536, 'display_isolation':True}
        if operation == 'session_start': return {'session_id':'owned', 'target':'2'}
        if operation in ('launch', 'session_stop', 'session_extend'): return {'ok':True}
        if operation == 'observe':
            controls = [node('menu_parent', actions=['click']), node('menu', description='Меню', parent='menu_parent')]
            if self.stage == 'drawer': controls.append(node('new', description='Новый чат', actions=['click']))
            else:
                controls += [node('composer'), node('composer/edit', text=self.prompt, actions=['set_text'], parent='composer/editor', editable=True, bounds=[20,1000,680,1150]),
                             node('composer/send', actions=['click','long_click'], parent='composer', bounds=[590,1160,690,1260])]
                if self.stage == 'answer':
                    replies=[node('reply-latest',text=self.answer)] if self.latest_only else [node('reply-'+str(i),text=self.answer) for i in range(self.replies)]
                    controls += replies+[node('copy', description='Копировать', actions=['click'])]
            return {'observation_id':'obs-' + str(len(self.calls)), 'geometry':{'width':720,'height':1280},
                    'windows':[{'title':'ChatGPT','focused':True}], 'nodes':controls, 'truncated':False}
        if operation == 'action':
            action = args['action']; ident = action.get('selector',{}).get('node_id')
            if ident == 'menu_parent': self.stage = 'drawer'
            elif ident == 'new': self.stage = 'home'; self.prompt = ''; self.replies = 0
            elif ident == 'composer/edit': self.prompt = action['text']
            elif ident == 'composer/send':
                nonce=re.search(r'RELAYKITE_REPLY_BINDING: ([a-f0-9]{32})',self.prompt)
                if nonce and not self.freeze_answer:
                    answer=json.loads(self.answer);answer['_relaykite_request_id']=nonce[1]
                    self.answer=json.dumps(answer,separators=(',',':'))
                self.stage = 'answer'; self.prompt = ''; self.replies += 1
            return {'ok':True,'applied':True}
        raise AssertionError(operation)


class AndroidUiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.phone = PhoneFixture()
        self.driver = AndroidDriver(Path(self.temp.name), peer=self.phone, sleep=lambda _:None)
    def tearDown(self): self.temp.cleanup()
    def request(self, **kwargs):
        return {'operation':'generate','run_id':'a'*32,'request_id':'ui_probe','fingerprint':'b'*64,'prompt':'Reply JSON only.', 'images':[], **kwargs}
    def test_saved_normal_chat_and_sequential_continuation(self):
        self.assertEqual(self.driver.run(self.request())['status'],'completed')
        self.assertEqual(self.driver.run(self.request(request_id='ui_second'))['status'],'completed')
        actions=[a['action'] for op,a,_ in self.phone.calls if op=='action']
        self.assertEqual(sum(a.get('selector',{}).get('node_id')=='new' for a in actions),1)
        self.assertEqual(sum(a.get('selector',{}).get('node_id')=='composer/send' for a in actions),2)
        self.assertNotIn('Временный',json.dumps(actions,ensure_ascii=False))
        self.assertTrue(all(a.get('observation_id') for op,a,_ in self.phone.calls if op=='action'))
    def test_large_prompt_rejected_before_ui(self):
        result=self.driver.run(self.request(prompt='🙂'*33000))
        self.assertEqual(result['status'],'waiting_user'); self.assertFalse(result['sent']); self.assertEqual(self.phone.calls,[])

    def test_identical_logical_reply_completes_when_only_latest_turn_is_visible(self):
        self.phone.latest_only=True;self.driver.timeout=.1
        first=self.driver.run(self.request())
        self.assertEqual(first['status'],'completed')
        second=self.driver.run(self.request(request_id='ui_virtualized_second'))
        self.assertEqual(second['status'],'completed')
        self.assertEqual(first['text'],second['text'])
        self.assertNotIn('_relaykite_request_id',second['text'])
        self.assertEqual(sum(op=='action' and a['action'].get('selector',{}).get('node_id')=='composer/send' for op,a,_ in self.phone.calls),2)

    def test_new_visible_copy_of_old_answer_cannot_complete_a_new_request(self):
        self.driver.timeout=.1
        self.assertEqual(self.driver.run(self.request())['status'],'completed')
        self.phone.freeze_answer=True
        result=self.driver.run(self.request(request_id='ui_stale_reply_second'))
        self.assertEqual(result['status'],'uncertain')
        self.assertTrue(result['sent'])

    def test_launch_focus_transition_retries_reads_without_replaying_launch(self):
        original=self.phone.__call__; observations=0
        def transitioning(op,args,rid):
            nonlocal observations
            result=original(op,args,rid)
            if op=='observe':
                observations+=1
                if observations<=2:result['windows']=[]
            return result
        self.driver.peer=transitioning
        self.assertEqual(self.driver.run(self.request())['status'],'completed')
        self.assertEqual(sum(op=='launch' for op,_,_ in self.phone.calls),1)
    def test_images_not_claimed_supported(self):
        result=self.driver.run(self.request(images=[{'mime_type':'image/png'}]))
        self.assertFalse(result['sent']); self.assertEqual(result['status'],'waiting_user')

    def test_changing_layout_stops_before_any_input_action(self):
        original=self.phone.__call__; counter=0
        def animation(op,args,rid):
            nonlocal counter
            result=original(op,args,rid)
            if op=='observe':
                counter+=1;result['nodes'][0]['bounds']=[counter,0,50,50]
            return result
        self.driver.peer=animation
        self.assertEqual(self.driver.run(self.request())['status'],'waiting_user')
        self.assertFalse(any(op=='action' for op,_,_ in self.phone.calls))
    def test_pending_action_is_never_replayed(self):
        self.driver.state={'pending':{'operation':'action','request_id':'old'}}; self.driver.save()
        result=self.driver.run(self.request())
        self.assertEqual(result['status'],'uncertain'); self.assertEqual(self.phone.calls,[])
    def test_probe_rejection_cannot_erase_an_unresolved_action_receipt(self):
        pending={'operation':'action','request_id':'old'}
        self.driver.state={'pending':pending}; self.driver.save()
        self.driver.peer=lambda *_:{'error':'IPC outcome unknown','code':'UNCERTAIN'}
        self.driver.run({'operation':'probe'})
        self.assertEqual(json.loads(self.driver.path.read_text('utf-8'))['pending'],pending)
    def test_unconfirmed_action_keeps_original_receipt_and_blocks_next_mutation(self):
        self.driver.peer=lambda *_:{'error':'Backend outcome unknown','code':'UNCERTAIN'}
        with self.assertRaises(DriverStop):
            self.driver.op('action',session_id='owned',observation_id='fresh',action={'kind':'click'})
        pending=json.loads(self.driver.path.read_text('utf-8')).get('pending')
        self.assertIsNotNone(pending)
        self.driver.peer=lambda *_:{'ok':True,'applied':True}
        with self.assertRaises(DriverStop):
            self.driver.op('action',session_id='owned',observation_id='new',action={'kind':'click'})
        self.assertEqual(json.loads(self.driver.path.read_text('utf-8'))['pending'],pending)
    def test_confirmed_send_followed_by_failed_observation_cannot_be_sent_again(self):
        original=self.phone.__call__
        def interrupted(op,args,rid):
            if op=='observe' and self.phone.stage=='answer':raise OSError('driver died after send')
            return original(op,args,rid)
        self.driver.peer=interrupted
        self.assertEqual(self.driver.run(self.request())['status'],'uncertain')
        before=len(self.phone.calls)
        restarted=AndroidDriver(Path(self.temp.name),peer=self.phone,sleep=lambda _:None)
        result=restarted.run(self.request(request_id='next_request'))
        self.assertEqual(result['status'],'uncertain')
        self.assertTrue(result['sent'])
        self.assertEqual(len(self.phone.calls),before)
    def test_completed_same_request_reuses_response_without_another_send(self):
        first=self.driver.run(self.request())
        before=len(self.phone.calls)
        restarted=AndroidDriver(Path(self.temp.name),peer=self.phone,sleep=lambda _:None)
        second=restarted.run(self.request())
        self.assertEqual(second['status'],'completed')
        self.assertEqual(second['text'],first['text'])
        self.assertEqual(len(self.phone.calls),before)
    def test_same_request_id_with_changed_prompt_is_rejected(self):
        self.assertEqual(self.driver.run(self.request())['status'],'completed')
        before=len(self.phone.calls)
        result=self.driver.run(self.request(prompt='A changed request'))
        self.assertEqual(result['status'],'waiting_user')
        self.assertEqual(len(self.phone.calls),before)
    def test_partially_created_session_receipt_is_not_discarded(self):
        self.driver.peer=lambda *_:{'session_id':'partial'}
        with self.assertRaises(DriverStop):
            self.driver.op('session_start',lease_seconds=1800)
        self.assertEqual(self.driver.state.get('pending',{}).get('operation'),'session_start')
    def test_two_driver_processes_cannot_own_the_same_session_state(self):
        second=AndroidDriver(Path(self.temp.name),peer=self.phone,sleep=lambda _:None)
        with self.driver.exclusive():
            result=second.run({'operation':'probe'})
        self.assertEqual(result['status'],'waiting_user')
        self.assertEqual(self.phone.calls,[])
    def test_state_is_reloaded_after_exclusive_ownership_is_acquired(self):
        stale=AndroidDriver(Path(self.temp.name),peer=self.phone,sleep=lambda _:None)
        self.driver.state={'pending':{'operation':'action','request_id':'other-process'}};self.driver.save()
        result=stale.run(self.request())
        self.assertEqual(result['status'],'uncertain')
        self.assertEqual(self.phone.calls,[])
    def test_truncated_tree_cannot_be_mistaken_for_complete_reply(self):
        original=self.phone.__call__
        def truncated(op,args,rid):
            result=original(op,args,rid)
            if op=='observe' and self.phone.stage=='answer': result['truncated']=True
            return result
        self.driver.peer=truncated; self.driver.timeout=.01
        result=self.driver.run(self.request()); self.assertEqual(result['status'],'uncertain')
    def test_json_extraction_is_strict_and_does_not_extract_echoed_prompt(self):
        self.assertEqual(json_answer('```json\n{"message":"ok"}\n```'),'{"message":"ok"}')
        self.assertIsNone(json_answer('Please return {"message":"ok"}'))
        self.assertIsNone(json_answer('{"a":1} then prose'))

    def test_confirmed_package_conflict_is_waiting_without_unsent_receipt(self):
        self.driver.peer=lambda op,args,rid: {'status':'failed','result':{'code':'RESOURCE_CONFLICT'}}
        with self.assertRaises(DriverStop) as result:
            self.driver.op('launch',session_id='owned',app_id='com.openai.chatgpt/com.openai.chatgpt.MainActivity')
        self.assertEqual(result.exception.state,'waiting_user')
        self.assertNotIn('pending',self.driver.state)

    def test_plain_json_reply_finishes_with_confirmed_idle_voice_composer(self):
        original=self.phone.__call__
        def without_toolbar(op,args,rid):
            result=original(op,args,rid)
            if op=='observe' and self.phone.stage=='answer':
                result['nodes']=[n for n in result['nodes'] if n.get('description')!='Копировать']
                result['nodes'].append(node('voice',description='Начать голосовой разговор',actions=['click']))
            return result
        self.driver.peer=without_toolbar
        self.assertEqual(self.driver.run(self.request())['status'],'completed')

    def test_recovery_reads_inspected_answer_without_repeating_ui_input(self):
        self.assertEqual(self.driver.run(self.request())['status'],'completed')
        self.driver.state['generation']['stage']='awaiting_reply';self.driver.save();self.phone.calls.clear()
        result=self.driver.run({'operation':'recover','confirm_response_sha256':hashlib.sha256(self.phone.answer.encode()).hexdigest()})
        self.assertEqual(result['status'],'completed');self.assertTrue(result['reconciled'])
        self.assertTrue(all(op=='observe' for op,_,_ in self.phone.calls))

    def test_recovery_wrong_digest_preserves_uncertainty(self):
        self.assertEqual(self.driver.run(self.request())['status'],'completed')
        self.driver.state['generation']['stage']='awaiting_reply';self.driver.save();self.phone.calls.clear()
        result=self.driver.run({'operation':'recover','confirm_response_sha256':'a'*64})
        self.assertEqual(result['status'],'uncertain')
        self.assertEqual(self.driver.state['generation']['stage'],'awaiting_reply')

    def test_recovery_of_old_nonce_is_rejected_even_with_explicit_matching_hash(self):
        self.assertEqual(self.driver.run(self.request())['status'],'completed')
        old=self.phone.answer
        self.driver.state['generation'].update(stage='awaiting_reply',reply_nonce='f'*32)
        self.driver.save();self.phone.calls.clear()
        result=self.driver.run({'operation':'recover','confirm_response_sha256':hashlib.sha256(old.encode()).hexdigest()})
        self.assertEqual(result['status'],'uncertain')
        self.assertTrue(all(op=='observe' for op,_,_ in self.phone.calls))
        self.assertEqual(self.driver.state['generation']['stage'],'awaiting_reply')

    def test_binding_overhead_is_checked_before_opening_or_changing_chat(self):
        result=self.driver.run(self.request(prompt='x'*64999))
        self.assertEqual(result['status'],'waiting_user')
        self.assertFalse(result['sent']);self.assertEqual(self.phone.calls,[])

    def test_definitely_expired_stop_does_not_block_a_new_owned_session(self):
        self.driver.peer=lambda op,args,rid:{'error':'expired','code':'SESSION_EXPIRED'}
        self.assertTrue(self.driver.op('session_stop',session_id='owned')['already_expired'])
        self.assertNotIn('pending',self.driver.state)


if __name__=='__main__': unittest.main()
