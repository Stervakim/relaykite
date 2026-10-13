import unittest,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from memory_service import child_command,enabled,is_owned_node

class ServiceTests(unittest.TestCase):
 def test_child_is_unprivileged_termux_and_fixed_node(self):
  cmd,env=child_command(10480)
  self.assertEqual(cmd[0],'/data/data/com.termux/files/usr/bin/node')
  self.assertEqual(cmd[2],'/data/data/com.termux/files/usr/var/lib/codaki-memory/service.json')
  self.assertNotIn('Bearer',str(cmd));self.assertEqual(env['LD_LIBRARY_PATH'],'/data/data/com.termux/files/usr/lib')
 def test_disabled_module_stops_memory(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);base=p/'base';mod=p/'mod';base.mkdir();mod.mkdir()
   self.assertFalse(enabled(base,mod));(base/'enabled').touch();self.assertTrue(enabled(base,mod))
   (mod/'disable').touch();self.assertFalse(enabled(base,mod))
 def test_reject_system_uid(self):
  with self.assertRaises(ValueError):child_command(0)
 def test_orphan_cleanup_matches_exact_uid_and_command(self):
  cmd,_=child_command(10480);args=[x.encode() for x in cmd]
  self.assertTrue(is_owned_node(args,10480,10480,cmd))
  self.assertFalse(is_owned_node(args,0,10480,cmd))
  self.assertFalse(is_owned_node([*args[:2],b'/another/config'],10480,10480,cmd))

if __name__=='__main__':unittest.main()
