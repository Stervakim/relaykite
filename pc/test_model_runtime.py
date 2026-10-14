import json,os,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
class ModelRuntimeTests(unittest.TestCase):
    def test_completed_input_cleanup_removes_duplicate_weights_and_keeps_other_files(self):
        import model_runtime
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCALAPPDATA':tmp}):
            root=Path(tmp)/'RelayKiteMemoryInputs';root.mkdir()
            weights=root/'Qwen3-0.6B-Q8_0.gguf';weights.write_bytes(b'fixture')
            (root/'keep.txt').write_text('retain')
            model_runtime.cleanup_inputs();self.assertTrue(weights.exists())
            (root/'install-status.json').write_text(json.dumps({'phase':'installed','explicit_choice':'yes','model_location':'pc'}))
            model_runtime.cleanup_inputs();self.assertFalse(weights.exists());self.assertTrue((root/'keep.txt').exists())
    def test_cleanup_refuses_missing_install_receipt(self):
        file=Path(__file__).with_name('model_runtime.py')
        self.assertTrue(file.exists(),'Owned model lifecycle implementation missing')
        import model_runtime
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'model';root.mkdir();(root/'unrelated.txt').write_text('retain')
            with self.assertRaises(ValueError):model_runtime.remove(root)
            self.assertTrue((root/'unrelated.txt').exists())
    def test_unknown_install_choice_cannot_enable_model(self):
        file=Path(__file__).with_name('model_runtime.py')
        self.assertTrue(file.exists(),'Owned model lifecycle implementation missing')
        import model_runtime
        with self.assertRaises(SystemExit):model_runtime.arguments(['install'])
