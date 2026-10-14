import hashlib,json,unittest,zipfile
from pathlib import Path
class CoreManifestTests(unittest.TestCase):
    def test_source_and_dex_match_build_manifest_and_no_compile_stub_is_shipped(self):
        root=Path(__file__).resolve().parents[1];m=json.loads((root/'core/build-manifest.json').read_text())
        for name,digest in m['sources'].items():self.assertEqual(hashlib.sha256((root/'android/java'/name).read_bytes()).hexdigest(),digest)
        for name,digest in m['jars'].items():
            p=root/'core'/name;self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),digest)
            with zipfile.ZipFile(p) as z:
                raw=z.read('classes.dex');self.assertTrue(raw.startswith(b'dex\n'));self.assertNotIn(b'Lcom/android/uiautomator/testrunner/UiAutomatorTestCase;\x00',raw if name=='display-engine.jar' else b'')
