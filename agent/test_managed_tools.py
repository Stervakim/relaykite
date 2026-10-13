import importlib.util
import base64
import os
from pathlib import Path
import tempfile
import time
import unittest

class ManagedToolsTests(unittest.TestCase):
    def test_registered_managed_tools_validate_before_any_effect(self):
        import native_phone as phone
        names={t['name'] for t in phone.tool_definitions()}
        self.assertIn('phone_task_start',names,'Managed tools are absent from the owner-bound registry')
        self.assertIn('phone_terminal_write',names)
        self.assertTrue(phone.dispatch('phone_task_start',{'request_id':'valid_rid_1','tool':'root_shell','arguments':{'command':'id'},'timeout_seconds':True})['isError'])
        self.assertTrue(phone.dispatch('phone_terminal_write',{'terminal_id':'no_terminal','request_id':'valid_rid_2','base64':'%%%','other':True})['isError'])

    @unittest.skipIf(os.name=='nt','PTY runtime is Android/POSIX')
    def test_same_runtime_hosts_terminal_and_scheduler_without_replay(self):
        self.assertIsNotNone(importlib.util.find_spec('managed_tools'),'Managed runtime not implemented')
        from managed_tools import Runtime
        shell='/system/bin/sh' if Path('/system/bin/sh').exists() else '/bin/sh'
        backend=lambda mode:([shell],{'PATH':'/system/bin:/usr/bin:/bin'},None)
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Runtime(Path(tmp),lambda tool,args:{'echo':args['command']},backend=backend)
            try:
                args={'request_id':'managed_job_1','tool':'root_shell','arguments':{'command':'owned'},'timeout_seconds':30}
                runtime.invoke('phone_task_start',args)
                until=time.monotonic()+2
                while runtime.invoke('phone_task_status',{'task_id':'managed_job_1'})['status'] in ('running','queued') and time.monotonic()<until:time.sleep(.01)
                out=runtime.invoke('phone_task_result',{'task_id':'managed_job_1'})
                self.assertEqual(out['result'],{'echo':'owned'})
                self.assertEqual(runtime.invoke('phone_task_start',args)['result'],out['result'])
                terminal=runtime.invoke('phone_command_start',{'request_id':'managed_cmd_1','command':'printf managed-ok','mode':'system','cwd':tmp,'timeout_seconds':10})
                tid=terminal['terminal_id'];until=time.monotonic()+2
                while time.monotonic()<until:
                    out=runtime.invoke('phone_command_result',{'terminal_id':tid,'cursor':0})
                    if out['eof']:break
                    time.sleep(.01)
                self.assertIn(b'managed-ok',base64.b64decode(out['base64']))
            finally:runtime.close()

if __name__=='__main__':unittest.main()
