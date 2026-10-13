"""ELF fixture with independently placed dynamic table and string payload."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
class RelocationTests(unittest.TestCase):
    def module(self):
        path=ROOT/'scripts/relocate_elf.py'
        self.assertTrue(path.exists(),'Relocatable Android runtime builder is missing')
        spec=importlib.util.spec_from_file_location('runtime_relocator',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    def fixture(self):
        raw=bytearray(768);raw[:16]=b'\x7fELF\x02\x01\x01'+b'\x00'*9
        struct.pack_into('<HHIQQQIHHHHHH',raw,16,3,183,1,0,64,0,0,64,56,2,0,0,0)
        struct.pack_into('<IIQQQQQQ',raw,64,1,5,0,0x1000,0,768,768,4096)
        struct.pack_into('<IIQQQQQQ',raw,120,2,6,256,0x1100,0,64,64,8)
        for index,pair in enumerate(((5,0x1180),(10,128),(29,1),(0,0))):struct.pack_into('<qQ',raw,256+index*16,*pair)
        original=b'/data/data/com.termux/files/usr/lib'
        raw[384:384+len(original)+2]=b'\0'+original+b'\0';raw[450:454]=b'KEEP'
        return bytes(raw)
    def test_rewrites_only_declared_runpath_and_preserves_other_bytes(self):
        module=self.module();original=self.fixture();out,changed=module.relocate_bytes(original,'$ORIGIN/../lib')
        self.assertTrue(changed);self.assertEqual(out[385:400],b'$ORIGIN/../lib\0')
        self.assertEqual(out[450:454],b'KEEP');self.assertEqual(out[:384],original[:384]);self.assertEqual(len(out),len(original))
        self.assertNotIn(b'/data/data/com.termux/files/usr/lib',out)
    def test_refuses_oversized_path_or_wrong_architecture_without_modifying_input(self):
        module=self.module();original=self.fixture()
        with self.assertRaises(ValueError):module.relocate_bytes(original,'x'*200)
        bad=bytearray(original);struct.pack_into('<H',bad,18,62)
        with self.assertRaises(ValueError):module.relocate_bytes(bytes(bad),'$ORIGIN')
    def test_relocatable_object_without_program_headers_is_unchanged(self):
        module=self.module();raw=bytearray(self.fixture());struct.pack_into('<H',raw,16,1);struct.pack_into('<HH',raw,54,0,0)
        out,changed=module.relocate_bytes(bytes(raw),'$ORIGIN')
        self.assertFalse(changed);self.assertEqual(out,bytes(raw))

if __name__=='__main__':unittest.main()
