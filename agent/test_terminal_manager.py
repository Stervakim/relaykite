"""POSIX PTYs against real shell processes (also run on Android and CI)."""
import base64
import importlib.util
import os
import shlex
from pathlib import Path
import sys
import tempfile
import time
import unittest

@unittest.skipIf(os.name=='nt','Real PTY acceptance runs on Linux/Android, not pipes on Windows')
class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('terminal_manager'),'PTY manager is not implemented')
        from terminal_manager import TerminalManager
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'jobs.sqlite3'
        shell='/system/bin/sh' if Path('/system/bin/sh').exists() else '/bin/sh'
        self.factory=lambda mode:([shell],dict(PATH='/system/bin:/usr/bin:/bin',TERM='xterm-256color'),None)
        self.manager=TerminalManager(self.path,backend=self.factory,max_output_bytes=4096)
    def tearDown(self):
        if hasattr(self,'manager'):self.manager.close()
        if hasattr(self,'temp'):self.temp.cleanup()
    def read_until(self,sid,want=b'',eof=False):
        until=time.monotonic()+5
        while time.monotonic()<until:
            out=self.manager.read(sid,0,65536);raw=base64.b64decode(out['base64'])
            if want in raw and (not eof or out['eof']):return out,raw
            time.sleep(.02)
        self.fail('PTY output/EOF did not arrive')
    def open(self,ident,command=None):
        return self.manager.open(ident,mode='system',cwd=self.temp.name,command=command)['terminal_id']
    def test_interactive_input_unicode_resize_and_eof(self):
        sid=self.open('interactive_1')
        self.manager.resize(sid,40,100)
        self.manager.write(sid,'stdin_receipt_1',base64.b64encode('printf "Привет\\n"; stty size; exit 7\n'.encode()).decode())
        out,raw=self.read_until(sid,'Привет'.encode(),eof=True)
        self.assertIn(b'40 100',raw);self.assertEqual(out['exit_code'],7)
    def test_shell_has_a_controlling_terminal_for_interactive_programs(self):
        sid=self.open('controlling_tty_1','exec 3<>/dev/tty && printf controlling-tty-ok')
        self.assertIn(b'controlling-tty-ok',self.read_until(sid,b'controlling-tty-ok',eof=True)[1])
    def test_three_process_groups_and_targeted_close(self):
        long=self.open('long_process_1','sleep 20')
        interactive=self.open('interactive_2')
        short=self.open('short_process_3','printf short-ok')
        self.assertIn(b'short-ok',self.read_until(short,b'short-ok',eof=True)[1])
        self.manager.stop(long)
        self.manager.write(interactive,'alive_receipt_1',base64.b64encode(b'printf survivor-ok\n').decode())
        self.assertIn(b'survivor-ok',self.read_until(interactive,b'survivor-ok')[1])
        self.assertTrue(self.manager.read(long)['eof'])
    def test_open_and_stdin_receipts_block_duplicate_effects(self):
        sid=self.open('replay_open_1')
        self.assertEqual(self.open('replay_open_1'),sid)
        target=Path(self.temp.name)/'effect.txt'
        command='printf X >> '+shlex.quote(str(target))+'; printf effect-done\n'
        payload=base64.b64encode(command.encode()).decode()
        receipt=self.manager.write(sid,'replay_input_1',payload)
        self.assertEqual(self.manager.write(sid,'replay_input_1',payload),receipt)
        with self.assertRaises(ValueError):self.manager.write(sid,'replay_input_1',base64.b64encode(b'exit\n').decode())
        self.read_until(sid,b'effect-done')
        until=time.monotonic()+2
        while not target.exists() and time.monotonic()<until:time.sleep(.02)
        time.sleep(.1)
        self.assertEqual(target.read_bytes(),b'X')
    def test_bounded_buffer_reports_cursor_gap_instead_of_losing_output_silently(self):
        sid=self.open('large_output_1',"head -c 12000 /dev/zero | tr '\\000' x")
        out,_=self.read_until(sid,b'x',eof=True)
        self.assertGreater(out['oldest_cursor'],0);self.assertTrue(out['gap'])
        self.assertLessEqual(len(base64.b64decode(out['base64'])),4096)
        self.assertEqual(self.manager.read(sid,out['next_cursor'])['base64'],'')
    def test_restart_never_reopens_old_process(self):
        sid=self.open('restart_open_1','printf persisted')
        self.read_until(sid,b'persisted',eof=True)
        self.manager.close()
        from terminal_manager import TerminalManager
        self.manager=TerminalManager(self.path,backend=self.factory)
        result=self.manager.open('restart_open_1',mode='system',cwd=self.temp.name,command='printf persisted')
        self.assertEqual(result['terminal_id'],sid)
        self.assertIn(result['status'],('exited','closed','uncertain'))
        self.assertFalse(self.manager.list()[0]['running'])

if __name__=='__main__':unittest.main()
