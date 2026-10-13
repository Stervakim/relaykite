import copy, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from portable.engine import Engine, UseError
try:
    from portable.windows_native import WindowsBackend, key_sequence
except ImportError:
    WindowsBackend = None


class Value:
    CurrentValue = 'actual Ю value'
    CurrentIsReadOnly = False
    def SetValue(self, value): self.CurrentValue = value


class Control:
    def __init__(self, rid, name, role, rect, parent=None, password=False):
        self.handle = 7 if parent is None else 0
        element = Obj(CurrentIsPassword=password, CurrentHasKeyboardFocus=False)
        self.element_info = Obj(runtime_id=rid, name=name, control_type=role, automation_id='field' if role=='Edit' else '',
                                process_id=11, element=element)
        self.rect = Obj(left=rect[0], top=rect[1], right=rect[2], bottom=rect[3])
        self.child_controls = []
        if parent: parent.child_controls.append(self)
        self.calls = []
    def children(self): return list(self.child_controls)
    def rectangle(self): return self.rect
    def is_visible(self): return True
    def is_enabled(self): return True
    def set_focus(self): self.calls.append('focus')
    def __getattr__(self, name):
        if name.startswith('iface_'): raise RuntimeError('No pattern')
        raise AttributeError(name)


class Driver:
    def __init__(self):
        self.window = Control([1,7], 'Example', 'Window', [100,200,600,600])
        self.edit = Control([1,8], 'Search label', 'Edit', [120,220,350,250], self.window)
        self.edit.iface_value = Value()
        self.items = [self.window]; self.foreground_id = 7; self.hit_id = 7
        self.input = []; self.fail_input = False; self.image = b'PNG one'
    def windows(self): return list(self.items)
    def identity(self, window): return ('C:\\Example\\app.exe', 1000.0)
    def foreground(self): return self.foreground_id
    def hit(self, coords): return self.hit_id
    def image_png(self, window): return self.image
    def click(self, coords, button):
        self.input.append(('click',coords,button))
        if self.fail_input: raise OSError('lost native receipt')
    def keys(self, keys): self.input.append(('key',keys))
    def press(self, coords): self.input.append(('press',coords))
    def move(self, coords): self.input.append(('move',coords))
    def release(self, coords): self.input.append(('release',coords))
    def scroll(self, coords, distance): self.input.append(('scroll',coords,distance))
    def launch(self, path): self.input.append(('launch',path))


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(WindowsBackend, 'Standalone Windows backend is missing')
        self.d = Driver(); self.b = WindowsBackend(driver=self.d)
        self.tmp = tempfile.TemporaryDirectory(); self.e = Engine(self.b, Path(self.tmp.name)/'journal.db')
        self.seq = 0; self.sid = self.call('session_start', {'target':'7'})['session_id']
    def tearDown(self):
        if hasattr(self,'e'): self.e.close(); self.tmp.cleanup()
    def call(self, op, args, rid=None):
        self.seq += 1
        return self.e.execute(op,args,rid or 'native_request_%04d'%self.seq)
    def observe(self, screenshot=False): return self.call('observe',{'session_id':self.sid,'screenshot':screenshot})
    def action(self, obs, action, rid=None):
        return self.call('action',{'session_id':self.sid,'observation_id':obs['observation_id'],'action':action},rid)
    def test_exact_native_value_drives_append_insert_and_empty_replace(self):
        o=self.observe(); n=next(n for n in o['nodes'] if n['role']=='Edit')
        self.assertEqual(n['text'],'actual Ю value'); self.assertNotEqual(n['text'],'Search label')
        self.action(o,{'kind':'set_text','selector':{'node_id':n['node_id']},'mode':'append','text':'!'})
        self.assertEqual(self.d.edit.iface_value.CurrentValue,'actual Ю value!')
        self.action(self.observe(),{'kind':'set_text','selector':{'resource_id':'field'},'mode':'insert','start':7,'end':8,'text':'★'})
        self.assertEqual(self.d.edit.iface_value.CurrentValue,'actual ★ value!')
        self.action(self.observe(),{'kind':'set_text','selector':{'resource_id':'field'},'text':''})
        self.assertEqual(self.d.edit.iface_value.CurrentValue,'')
    def test_stable_runtime_id_survives_reenumeration(self):
        first=self.observe(); second=self.observe()
        self.assertEqual(first['nodes'][1]['node_id'],second['nodes'][1]['node_id'])
        self.assertEqual(second['nodes'][1]['parent_id'],second['nodes'][0]['node_id'])
    def test_handle_reuse_by_different_process_is_rejected(self):
        o=self.observe();self.d.window.element_info.process_id=99
        with self.assertRaises(UseError): self.action(o,{'kind':'key','key':'Return'})
        self.assertEqual(self.d.input,[])
    def test_changed_value_stales_before_any_input(self):
        o=self.observe();self.d.edit.iface_value.CurrentValue='new value'
        with self.assertRaises(UseError):self.action(o,{'kind':'set_text','selector':{'resource_id':'field'},'text':'oops'})
        self.assertEqual(self.d.edit.iface_value.CurrentValue,'new value')
    def test_coordinate_requires_screenshot_and_translates_window_origin(self):
        with self.assertRaises(UseError): self.action(self.observe(),{'kind':'click','x':10,'y':20})
        self.action(self.observe(True),{'kind':'click','x':10,'y':20})
        self.assertEqual(self.d.input,[('click',(110,220),'left')])
    def test_foreground_loss_or_foreign_hit_blocks_coordinates(self):
        o=self.observe(True);self.d.foreground_id=9
        with self.assertRaises(UseError):self.action(o,{'kind':'click','x':10,'y':20})
        self.d.foreground_id=7;o=self.observe(True);self.d.hit_id=9
        with self.assertRaises(UseError):self.action(o,{'kind':'click','x':10,'y':20})
        self.assertEqual(self.d.input,[])
    def test_changed_pixels_stale_coordinate_observation(self):
        o=self.observe(True);self.d.image=b'PNG two'
        with self.assertRaises(UseError):self.action(o,{'kind':'click','x':10,'y':20})
        self.assertEqual(self.d.input,[])
    def test_password_has_no_native_value_or_name_in_result(self):
        self.d.edit.element_info.element.CurrentIsPassword=True
        self.d.edit.element_info.name='SECRET label';self.d.edit.iface_value.CurrentValue='SECRET value'
        o=self.observe();self.assertNotIn('SECRET',str(o));self.assertTrue(o['nodes'][1]['password'])
        with self.assertRaises(UseError):self.action(o,{'kind':'set_text','selector':{'resource_id':'field'},'text':'x'})
    def test_privacy_query_failure_fails_closed(self):
        self.d.edit.element_info.element=Obj(CurrentHasKeyboardFocus=False)
        self.assertTrue(self.observe()['nodes'][1]['password'])
    def test_lost_native_receipt_is_uncertain_and_duplicate_never_replays(self):
        o=self.observe(True);self.d.fail_input=True;a={'kind':'click','x':10,'y':20}
        with self.assertRaises(UseError) as c:self.action(o,a,'native_lost_request')
        self.assertEqual(c.exception.code,'UNCERTAIN')
        with self.assertRaises(UseError):self.action(o,a,'native_lost_request')
        self.assertEqual(len(self.d.input),1)
        self.assertTrue(self.call('diagnostics',{})['blocked'])
    def test_stop_releases_binding_without_closing_window(self):
        self.call('session_stop',{'session_id':self.sid})
        self.assertEqual(self.d.items,[self.d.window]);self.assertEqual(self.d.input,[])
    def test_key_chords_are_validated_not_raw_macro_text(self):
        self.action(self.observe(),{'kind':'key','key':'Control_L+Shift_L+Left'})
        self.assertEqual(self.d.input,[('key','^+{LEFT}')])
        with self.assertRaises(UseError):key_sequence('{ENTER 50}')
    def test_readonly_value_does_not_advertise_text_write(self):
        self.d.edit.iface_value.CurrentIsReadOnly=True
        self.assertNotIn('set_text',self.observe()['nodes'][1]['actions'])
    def test_binding_can_select_discovered_app_path_and_apps_publish_window(self):
        apps=self.b.apps();self.assertEqual(apps[0]['app_id'],'C:\\Example\\app.exe')
        self.assertEqual(apps[0]['windows'][0]['window_id'],'7')
        self.b.stop();self.assertEqual(self.b.start(target=apps[0]['app_id'])['target'],'7')
    def test_drag_release_runs_even_if_pointer_move_fails(self):
        def fail(coords): raise OSError('native move failed')
        self.d.move=fail
        with self.assertRaises(UseError) as c:self.action(self.observe(True),{'kind':'drag','from_x':10,'from_y':20,'to_x':50,'to_y':70})
        self.assertEqual(c.exception.code,'UNCERTAIN')
        self.assertEqual(self.d.input[0][0],'press');self.assertEqual(self.d.input[-1][0],'release')


if __name__=='__main__':unittest.main()
