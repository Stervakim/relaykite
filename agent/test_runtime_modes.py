import os,subprocess,unittest
from unittest.mock import patch
import native_phone as phone
from terminal_manager import android_backend

class RuntimeModesTests(unittest.TestCase):
    def test_app_worker_never_implicitly_requests_su(self):
        result=subprocess.CompletedProcess([],0,b'app-owned',b'')
        with patch.object(os,'geteuid',return_value=10515,create=True),patch.object(subprocess,'run',return_value=result) as run:
            with self.assertRaises(PermissionError):phone.run_android('id')
            run.assert_not_called()
            self.assertEqual(phone.run_android('id',require_root=False),'app-owned')
            self.assertEqual(run.call_args.args[0][:2],['/system/bin/sh','-c'])
    def test_app_terminal_retains_own_uid_and_does_not_use_termux(self):
        with patch.object(os,'geteuid',return_value=10515,create=True),patch('terminal_manager.Path.is_file',return_value=True):
            argv,env,uid=android_backend('app')
            self.assertEqual(argv,['/system/bin/sh']);self.assertIsNone(uid);self.assertNotIn('com.termux',str(env))
            with self.assertRaises(PermissionError):android_backend('root')
            with self.assertRaises(PermissionError):android_backend('system')
            with self.assertRaises(PermissionError):android_backend('termux')

if __name__=='__main__':unittest.main()
