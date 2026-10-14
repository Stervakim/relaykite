import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('chatgpt_card_test_builder',ROOT/'chatgpt/package_card.py')
card=importlib.util.module_from_spec(spec)
spec.loader.exec_module(card)

class ChatGPTCardTests(unittest.TestCase):
    def test_public_card_has_workflows_and_no_device_or_owner_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=card.build_card(ROOT,tmp)
            raw=target.read_bytes()
            self.assertEqual(raw,card.build_card(ROOT,tmp).read_bytes())
            self.assertEqual(raw,(ROOT/'chatgpt'/target.name).read_bytes())
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(set(archive.namelist()),set(card.FILES)|{'LICENSE'})
                self.assertEqual(json.loads(archive.read('.app.json')),{'apps':{}})
                manifest=json.loads(archive.read('plugin.json'))
                extension=manifest['extensions']['com.openai']
                for path in [extension['apps'],extension['onboardingSkill'],extension['interface']['composerIcon']]:
                    self.assertIn(path.removeprefix('./'),archive.namelist())
                self.assertTrue(archive.read('assets/icon.png').startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertNotIn('mcp.json',archive.namelist())
                self.assertNotIn('config.json',archive.namelist())

    def test_private_card_changes_only_app_reference_and_leaves_template_intact(self):
        original=(ROOT/'chatgpt/plugin/.app.json').read_bytes()
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            with zipfile.ZipFile(card.build_card(ROOT,a)) as public,zipfile.ZipFile(card.build_card(ROOT,b,'asdk_app_fixture')) as private:
                manifest=json.loads(private.read('plugin.json'))
                self.assertEqual(json.loads(private.read('.app.json')),{'apps':{manifest['name']:{'id':'asdk_app_fixture','required':True}}})
                for name in public.namelist():
                    if name!='.app.json':self.assertEqual(public.read(name),private.read(name))
        self.assertEqual(original,(ROOT/'chatgpt/plugin/.app.json').read_bytes())

    def test_invalid_identifiers_are_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'new'
            for value in ('plugin_example','https://example.com','Bearer secret','asdk_app_','asdk_app_x/../../secret'):
                with self.subTest(value=value),self.assertRaises(ValueError):card.build_card(ROOT,output,value)
            self.assertFalse(output.exists())

    def test_cli_refuses_owner_card_in_public_repo(self):
        result=subprocess.run([sys.executable,str(ROOT/'chatgpt/package_card.py'),'--app-id','asdk_app_fixture','--output',str(ROOT/'chatgpt')],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)

    def test_installer_contains_identical_nested_card_and_checksums(self):
        packager_path=ROOT/'scripts/build_release.py'
        spec=importlib.util.spec_from_file_location('installer_with_card_test',packager_path)
        package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
        with tempfile.TemporaryDirectory() as tmp:
            import shutil
            staged=Path(tmp)/'repo';staged.mkdir()
            for name in ('agent','magisk','chatgpt'):shutil.copytree(ROOT/name,staged/name)
            for source in package.EXTRA_AGENT_INPUTS.values():
                (staged/source).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/source,staged/source)
            provenance=staged/'device-runtime/artifacts';provenance.mkdir(parents=True)
            shutil.copyfile(ROOT/'device-runtime/artifacts/provider-manifest.json',provenance/'provider-manifest.json')
            shutil.copyfile(ROOT/'LICENSE',staged/'LICENSE')
            installer=package.build(staged)
            checksum_path=staged/'dist/SHA256SUMS'
            lines=checksum_path.read_text().splitlines()
            for line in lines:
                digest,name=line.split('  ',1)
                self.assertEqual(digest,hashlib.sha256((checksum_path.parent/name).read_bytes()).hexdigest())
            with zipfile.ZipFile(installer) as archive:
                nested=next(name for name in archive.namelist() if '/chatgpt-' in name or (name.startswith('chatgpt/') and name.endswith('.zip')) or ('/chatgpt/' in name and name.endswith('.zip')))
                public=ROOT/'chatgpt'/Path(nested).name
                self.assertEqual(archive.read(nested),public.read_bytes())
                with zipfile.ZipFile(io.BytesIO(archive.read(nested))) as inner:
                    self.assertEqual(json.loads(inner.read('.app.json')),{'apps':{}})

    def test_update_retains_prior_connection_in_new_card(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            previous=card.build_card(ROOT,a,'asdk_app_fixture')
            expected=json.loads((ROOT/'chatgpt/plugin/plugin.json').read_text(encoding='utf-8'))['name']
            app_id=card.previous_app_id(previous,expected)
            import shutil
            newer=Path(b)/'new-source';newer.mkdir()
            shutil.copytree(ROOT/'chatgpt',newer/'chatgpt')
            shutil.copyfile(ROOT/'LICENSE',newer/'LICENSE')
            manifest_path=newer/'chatgpt/plugin/plugin.json'
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'));manifest['version']='99.0.0'
            manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
            updated=card.build_card(newer,Path(b)/'output',app_id)
            with zipfile.ZipFile(updated) as archive:
                self.assertEqual(json.loads(archive.read('.app.json'))['apps'][expected]['id'],'asdk_app_fixture')
                self.assertEqual(json.loads(archive.read('plugin.json'))['version'],'99.0.0')
                self.assertIn('skills/update/SKILL.md',archive.namelist())
            with self.assertRaises(ValueError):card.previous_app_id(previous,'another-plugin')

    def test_previous_card_with_duplicate_mapping_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'duplicate.zip'
            expected=json.loads((ROOT/'chatgpt/plugin/plugin.json').read_text(encoding='utf-8'))['name']
            with zipfile.ZipFile(target,'w') as archive:
                archive.writestr('plugin.json',json.dumps({'name':expected}))
                archive.writestr('.app.json','{"apps":{}}')
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    archive.writestr('.app.json','{"apps":{}}')
            with self.assertRaises(ValueError):card.previous_app_id(target,expected)
