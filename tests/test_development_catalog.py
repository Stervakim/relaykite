"""The Free UI descriptor must select real Codex tools without model claims."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pc.development.catalog import write_catalog


class DevelopmentCatalogTests(unittest.TestCase):
    def test_descriptor_enables_native_patch_and_sequential_text_transport(self):
        with tempfile.TemporaryDirectory() as root:
            path = write_catalog(root)
            self.assertIsInstance(path, Path)
            self.assertTrue(path.is_absolute())
            self.assertTrue(path.is_relative_to(Path(root).resolve()))
            descriptor = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(descriptor['models']), 1)
            model = descriptor['models'][0]
            self.assertEqual(model['slug'], 'chatgpt-free')
            self.assertIn('ChatGPT', model['display_name'])
            self.assertEqual(model['apply_patch_tool_type'], 'freeform')
            self.assertFalse(model['supports_parallel_tool_calls'])
            self.assertEqual(model['input_modalities'], ['text'])
            self.assertFalse(model['prefer_websockets'])
            self.assertFalse(model['use_responses_lite'])
            self.assertEqual(model['tool_mode'], 'direct')
            self.assertLess(model['auto_compact_token_limit'], model['context_window'])
            self.assertTrue(model.get('base_instructions') or
                            model.get('model_messages', {}).get('instructions_template'))

    def test_repeated_catalog_is_deterministic_and_replaces_obsolete_settings(self):
        with tempfile.TemporaryDirectory() as root:
            path = write_catalog(root)
            expected = path.read_bytes()
            path.write_text('{"obsolete": true}', encoding='utf-8')
            self.assertEqual(write_catalog(root), path)
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(list(Path(root).iterdir()), [path])

    def test_interrupted_replace_keeps_previous_valid_catalog_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = write_catalog(root)
            expected = path.read_bytes()
            with patch('pc.development.catalog.os.replace', side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):
                    write_catalog(root)
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(list(Path(root).iterdir()), [path])

    def test_nested_new_state_directory_is_created_without_global_config(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / 'isolated' / 'runtime'
            path = write_catalog(state)
            self.assertEqual(path.parent, state.resolve())
            self.assertFalse((Path(root) / 'config.toml').exists())
            self.assertFalse((state / 'config.toml').exists())


if __name__ == '__main__':
    unittest.main()
