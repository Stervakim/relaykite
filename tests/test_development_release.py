"""Development runtime release inputs are explicit, shared and contain no state."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


class DevelopmentReleaseTests(unittest.TestCase):
    def test_development_manifest_is_an_explicit_source_only_allowlist(self):
        path = ROOT / 'pc/development/release-files.json'
        self.assertTrue(path.is_file(), 'Development runtime release allowlist is missing')
        names = json.loads(path.read_text('utf8'))
        self.assertEqual(len(names), len(set(names)))
        for required in ('__main__.py','server.py','client.py','supervisor.py','android_ui.py','android_mcp.py','web/index.html','release-files.json'):
            self.assertIn(required, names)
        for name in names:
            self.assertTrue((ROOT / 'pc/development' / name).is_file(), name)
            self.assertFalse(Path(name).is_absolute())
            self.assertNotIn('..', Path(name).parts)
            self.assertFalse(any(part in ('node_modules','browser-profile','__pycache__','provider') for part in Path(name).parts))
            self.assertNotIn(Path(name).suffix, ('.sqlite3','.db','.pyc','.log'))

    def test_phone_package_maps_the_shared_runtime_into_agent_namespace(self):
        builder = load('phone_development_release', 'scripts/build_release.py')
        self.assertIn('development_tools.py', builder.AGENT_FILES)
        self.assertEqual(builder.EXTRA_AGENT_INPUTS.get('development/server.py'), 'pc/development/server.py')
        self.assertEqual(builder.EXTRA_AGENT_INPUTS.get('development/android_ui.py'), 'pc/development/android_ui.py')
        names = [name for name in builder.EXTRA_AGENT_INPUTS if name.startswith('development/')]
        manifest = ROOT / 'pc/development/release-files.json'
        self.assertTrue(manifest.is_file())
        self.assertEqual(set(names), {'development/' + name for name in json.loads(manifest.read_text('utf8'))})

    def test_pc_package_contains_the_same_allowlisted_runtime(self):
        builder = load('pc_development_release', 'pc/package_release.py')
        self.assertIn('development/server.py', builder.PC_FILES)
        manifest = ROOT / 'pc/development/release-files.json'
        self.assertTrue(manifest.is_file())
        self.assertEqual({name for name in builder.PC_FILES if name.startswith('development/')},
                         {'development/' + name for name in json.loads(manifest.read_text('utf8'))})


if __name__ == '__main__': unittest.main()
