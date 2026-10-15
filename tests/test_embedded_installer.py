import hashlib,importlib.util,io,json,tempfile,unittest,zipfile
from pathlib import Path

class EmbeddedInstallerTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('embedded_installer',Path(__file__).resolve().parents[1]/'scripts/install_embedded_runtime.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    def apk(self,path,entry='agent/owned.py',corrupt=False,extra=False):
        payload=b'owned source';native=b'owned executable';digest=lambda b:hashlib.sha256(b).hexdigest()
        manifest={'version':'0.3.0','architecture':'arm64-v8a','files':{entry:digest(payload)},'native':{'libowned.so':{'sha256':digest(native)}},'links':{'lib/python/lib-dynload/owned.so':'libowned.so'}}
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr(entry,b'changed' if corrupt else payload);z.writestr('runtime-manifest.json',json.dumps(manifest))
            if extra:z.writestr('unlisted.py','effect')
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('assets/runtime.zip',buf.getvalue());z.writestr('assets/runtime-manifest.json',json.dumps(manifest));z.writestr('lib/arm64-v8a/libowned.so',native)
        return digest(path.read_bytes())
    def test_accepts_only_the_expected_apk_and_inventory(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            apk=Path(tmp)/'owned.apk';digest=self.apk(apk)
            manifest,assets,native=m.read_package(apk,digest)
            self.assertEqual(assets,{'agent/owned.py':b'owned source'});self.assertEqual(native,{'libowned.so':b'owned executable'})
            with self.assertRaises(ValueError):m.read_package(apk,'0'*64)
    def test_rejects_traversal_corruption_and_unlisted_code_before_staging(self):
        m=self.module()
        for kw in ({'entry':'../escape.py'},{'corrupt':True},{'extra':True}):
            with self.subTest(kw=kw),tempfile.TemporaryDirectory() as tmp:
                apk=Path(tmp)/'owned.apk';digest=self.apk(apk,**kw);target=Path(tmp)/'versions'
                with self.assertRaises(ValueError):m.stage(apk,digest,target)
                self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
