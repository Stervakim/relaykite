import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
card = load('pc_release_card_test', ROOT/'pc/chatgpt/package_card.py')
builder = load('pc_release_builder_test', ROOT/'pc/package_release.py')


class PCReleaseTests(unittest.TestCase):
    def test_public_pc_card_and_upgrade_preserve_the_correct_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = card.build_card(ROOT/'pc', Path(tmp)/'public')
            self.assertEqual(public.read_bytes(), (ROOT/'pc/chatgpt'/public.name).read_bytes())
            with zipfile.ZipFile(public) as archive:
                self.assertEqual(json.loads(archive.read('.app.json')), {'apps': {}})
                self.assertEqual(json.loads(archive.read('plugin.json'))['version'], '0.2.4')
                self.assertIn('skills/pc-control/SKILL.md', archive.namelist())
            private = card.build_card(ROOT/'pc', Path(tmp)/'private', 'asdk_app_fixture')
            self.assertEqual(card.previous_app_id(private, 'codaki-mini-codex-pc'), 'asdk_app_fixture')
            with self.assertRaises(ValueError): card.previous_app_id(private, 'codaki-mini-codex')

    def test_installer_contains_card_relay_migration_and_only_public_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)/'repo'; staged.mkdir()
            shutil.copytree(ROOT/'pc', staged/'pc', ignore=shutil.ignore_patterns('__pycache__'))
            relay = staged/'relay'
            for name in json.loads((ROOT/'pc/relay-files.json').read_text()):
                path=relay/name; path.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/'relay'/name,path)
            (staged/'pc/config.json').write_text('{"token":"DO_NOT_BUNDLE"}')
            target = builder.build(staged); first=target.read_bytes()
            self.assertEqual(first,builder.build(staged).read_bytes())
            with zipfile.ZipFile(target) as archive:
                self.assertIn('relay/drizzle/0001_hesitant_raza.sql',archive.namelist())
                self.assertIn('mini_codex_pc.py',archive.namelist())
                self.assertNotIn('config.json',archive.namelist())
                nested='chatgpt/codaki-mini-codex-pc-chatgpt-0.2.4.zip'
                self.assertEqual(archive.read(nested),(ROOT/'pc/chatgpt'/Path(nested).name).read_bytes())
                self.assertNotIn(b'DO_NOT_BUNDLE',b''.join(archive.read(p) for p in archive.namelist()))
            for line in (staged/'dist/SHA256SUMS').read_text().splitlines():
                digest,name=line.split('  ',1)
                self.assertEqual(digest,hashlib.sha256((staged/'dist'/name).read_bytes()).hexdigest())


if __name__=='__main__': unittest.main()
