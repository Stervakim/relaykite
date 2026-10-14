import importlib.util,struct,unittest
from pathlib import Path
import test_runtime_relocation

class ApkRuntimeTests(unittest.TestCase):
    def module(self):
        path=Path(__file__).resolve().parents[1]/'scripts/pack_apk_runtime.py'
        self.assertTrue(path.exists(),'APK runtime packer missing')
        spec=importlib.util.spec_from_file_location('apk_runtime',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_dependency_and_soname_aliases_are_patched_without_code_changes(self):
        m=self.module();raw=bytearray(test_runtime_relocation.RelocationTests().fixture())
        struct.pack_into('<Q',raw,120+32,96)
        pairs=((5,0x1180),(10,128),(29,1),(1,60),(14,60),(0,0))
        for i,pair in enumerate(pairs):struct.pack_into('<qQ',raw,256+i*16,*pair)
        raw[444:456]=b'libz.so.1\0\0\0'
        raw[500:504]=b'CODE'
        out=m.apk_elf(bytes(raw),{'libz.so.1':'libz.so'})
        self.assertEqual(out[444:454],b'libz.so\0\0\0');self.assertEqual(out[500:504],b'CODE')
        self.assertEqual(len(out),len(raw));self.assertEqual(out[385:393],b'$ORIGIN\0')
    def test_alias_growth_is_refused(self):
        m=self.module();raw=bytearray(test_runtime_relocation.RelocationTests().fixture());struct.pack_into('<qQ',raw,288,1,60);raw[444:454]=b'libz.so.1\0'
        with self.assertRaises(ValueError):m.apk_elf(bytes(raw),{'libz.so.1':'lib_growing_alias.so'})
    def test_versioned_dependencies_extract_as_apk_libraries(self):
        m=self.module();self.assertEqual(m.library_name('libssl.so.3'),'libssl.so')
        self.assertEqual(m.library_name('libc++_shared.so'),'libc++_shared.so')

if __name__=='__main__':unittest.main()
