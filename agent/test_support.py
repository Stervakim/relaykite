import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import native_phone as phone


class SupportTests(unittest.TestCase):
    def runtime(self):
        self.assertIsNotNone(importlib.util.find_spec('support_runtime'), 'Phone support loader is not implemented')
        import support_runtime
        return support_runtime

    def test_status_delivers_support_without_changing_device_status(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base/'support').mkdir()
            (base/'support'/'SKILL.md').write_text('Owner phone support guide', encoding='utf-8')
            (base/'support'/'passport.json').write_text(json.dumps({'schema_version':1,'verified_at':'2026-10-10T00:00:00Z','verified_epoch':time.time(),'device':{'model':'24069PC21G'},'packages':[],'modules':[],'paths':{}}), encoding='utf-8')
            def shell(command, **kwargs):
                if command.startswith('getprop'): return '24069PC21G\n16\nOS3.0.303.0.WNPMIXM'
                if command == 'dumpsys battery': return 'level: 32'
                if command == 'id': return 'uid=0(root)'
                raise AssertionError('Unexpected device action: '+command)
            with patch.object(phone,'SUPPORT_BASE',base), patch.object(phone,'shell',shell),patch.object(phone,'runtime_identity',return_value={'mode':'root','root_active':True}):
                result = phone.phone_status()
            self.assertEqual(result['battery_percent'],32)
            self.assertEqual(result['root_identity'],'uid=0(root)')
            self.assertIn('support',result,'phone_status must deliver the installed support guide')
            self.assertEqual(result['support']['instructions'],'Owner phone support guide')
            self.assertEqual(result['support']['passport']['device']['model'],'24069PC21G')

    def test_missing_or_corrupt_passport_does_not_hide_status(self):
        runtime=self.runtime()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); (base/'support').mkdir()
            (base/'support'/'SKILL.md').write_text('Guide',encoding='utf-8')
            (base/'support'/'passport.json').write_text('{broken',encoding='utf-8')
            result=runtime.get_context(base)
            self.assertEqual(result['state'],'partial')
            self.assertTrue(result['passport_stale'])
            self.assertEqual(result['instructions'],'Guide')
            self.assertNotIn('passport',result)

    def test_refresh_replaces_old_facts_and_never_reads_private_configuration(self):
        runtime=self.runtime()
        fixture={
            'getprop ro.product.model; getprop ro.product.device; getprop ro.product.manufacturer; getprop ro.build.version.release; getprop ro.build.version.incremental':'24069PC21G\nperidot\nXiaomi\n16\nOS3.0.303.0.WNPMIXM',
            'id':'uid=0(root)',
            'pm list packages -f':'package:/data/app/com.termux/base.apk=com.termux\npackage:/system/app/Foo/base.apk=com.android.foo',
            'pm list packages -3':'package:com.termux',
            '/data/data/com.termux/files/usr/bin/python --version':'Python 3.14.6',
        }
        def runner(command, **kwargs):
            if command not in fixture: raise AssertionError('Unexpected inventory command: '+command)
            return fixture[command]
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)/'mini-codex'; base.mkdir()
            modules=base.parent/'modules'; modules.mkdir()
            module=modules/'mini_codex'; module.mkdir()
            (module/'module.prop').write_text('id=mini_codex\nname=Mini Codex\nversion=1.0\n',encoding='utf-8')
            (module/'disable').touch()
            (base/'config.json').write_text('PRIVATE-CONFIGURATION-DO-NOT-READ',encoding='utf-8')
            (base/'support').mkdir()
            (base/'support'/'passport.json').write_text(json.dumps({'device':{'model':'OLD'},'packages':[{'package':'old.package'}]}),encoding='utf-8')
            report=runtime.refresh(base,runner)
            data=json.loads((base/'support'/'passport.json').read_text(encoding='utf-8'))
            self.assertEqual(report['package_count'],2)
            self.assertEqual(data['device']['codename'],'peridot')
            self.assertEqual(data['python_version'],'Python 3.14.6')
            self.assertEqual(data['packages'][0]['package'],'com.android.foo')
            self.assertTrue(next(p for p in data['packages'] if p['package']=='com.termux')['third_party'])
            self.assertTrue(data['modules'][0]['disabled'])
            self.assertNotIn('PRIVATE-CONFIGURATION',json.dumps(data))
            self.assertNotIn('old.package',json.dumps(data))
            self.assertTrue(runtime.get_context(base)['passport_stale'] is False)

    def test_symlink_support_file_is_not_loaded_as_instructions(self):
        runtime=self.runtime()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); (base/'support').mkdir()
            external=base/'private.txt'; external.write_text('PRIVATE',encoding='utf-8')
            link=base/'support'/'SKILL.md'
            try: link.symlink_to(external)
            except OSError: self.skipTest('Host disallows symlink creation')
            result=runtime.get_context(base)
            self.assertNotIn('PRIVATE',json.dumps(result))

    def test_invalid_timestamp_cannot_break_status_or_claim_freshness(self):
        runtime=self.runtime()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); (base/'support').mkdir()
            (base/'support'/'SKILL.md').write_text('Guide',encoding='utf-8')
            for epoch in (10**400, float('nan'), float('inf'), True, '0'):
                with self.subTest(epoch=str(epoch)[:30]):
                    (base/'support'/'passport.json').write_text(json.dumps({'schema_version':1,'verified_at':'2026-10-10','verified_epoch':epoch,'packages':[]}),encoding='utf-8')
                    result=runtime.get_context(base)
                    self.assertTrue(result['passport_stale'])
                    self.assertEqual(result['state'],'partial')
                    self.assertNotIn('passport',result)

    def test_existing_memory_is_searchable_by_support_tag(self):
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ',{'PHONE_MEMORY_DIR':d}):
            phone.phone_memory_save('Связь восстановлена','Проверено: агент снова отвечает; решение относится к телефонному прокси.',['mini-codex-support','network'])
            notes=phone.phone_memory_search('mini-codex-support')['notes']
            self.assertEqual(len(notes),1)
            self.assertIn('агент снова отвечает',notes[0]['content'])

    def test_packaged_guides_are_available_before_first_inventory(self):
        runtime=self.runtime()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)/'private'
            result=runtime.get_context(base)
            self.assertIn('instructions',result)
            self.assertTrue(Path(result['skill_path']).is_file())
            self.assertTrue(Path(result['service_reference']).is_file())
            self.assertEqual(result['passport_path'],str(base/'support'/'passport.json'))
            self.assertIn(str(Path(runtime.__file__).resolve()),result['refresh_command'])

    def test_cli_inventory_uses_private_storage_not_module_sources(self):
        import shutil
        runtime=self.runtime()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); module=root/'module'; module.mkdir()
            base=root/'private'; base.mkdir()
            shutil.copyfile(runtime.__file__,module/'support_runtime.py')
            (module/'configure.py').write_text('from pathlib import Path\nBASE=Path('+repr(str(base))+')\n',encoding='utf-8')
            (module/'native_phone.py').write_text(
                'from pathlib import Path\nBASE=Path('+repr(str(base))+')\n'
                'def shell(command):\n'
                '    if command.startswith("getprop"): return "TEST\\nTEST\\nTEST\\n16\\nTEST"\n'
                '    if command == "id": return "uid=0(root)"\n'
                '    if command == "pm list packages -f": return "package:/system/app/TEST/base.apk=com.example.test"\n'
                '    return "Python TEST" if command.endswith("--version") else ""\n',encoding='utf-8')
            result=subprocess.run([sys.executable,str(module/'support_runtime.py'),'refresh'],
                                  cwd=module,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertTrue(data['updated'])
            self.assertTrue((base/'support'/'passport.json').is_file())
            self.assertFalse((module/'support'/'passport.json').exists())

if __name__=='__main__': unittest.main()
