"""Host-only configuration and release tests; never touch Android or live storage."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
import configure
from phone_agent import BoundedStartupWriter
spec=importlib.util.spec_from_file_location('release_builder',ROOT/'scripts'/'build_release.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)/'private'
        self.module=Path(self.temp.name)/'module'
        self.values={'relay_url':'https://relay.example.com','agent_token':'x'*40}

    def tearDown(self): self.temp.cleanup()

    def test_bad_urls_and_credentials_refused_without_storage(self):
        for url in ('http://relay.example.com','https://a:b@relay.example.com','https://relay.example.com/?token=x',
                    'https://relay.example.com/#secret','https://127.0.0.1','https://localhost',
                    'https://relay.example.com:99999','https://bad_host.example.com','https://relay.example.com\n'):
            with self.subTest(url=url),self.assertRaises(ValueError):
                configure.install_config({**self.values,'relay_url':url},self.base,self.module)
        for token in ('short','x'*32,'x'*40+'\n'):
            with self.assertRaises(ValueError):
                configure.install_config({**self.values,'agent_token':token},self.base,self.module)
        self.assertFalse(self.base.exists())

    def test_interactive_credentials_use_hidden_input(self):
        hidden=Mock(side_effect=['x'*40,'optional-secret'])
        values=configure.interactive_values(prompt=Mock(return_value='https://relay.example.com'),hidden=hidden)
        self.assertEqual(hidden.call_count,2)
        self.assertEqual(values['agent_token'],'x'*40)

    def test_startup_diagnostics_have_shared_utf8_byte_limit(self):
        output=io.StringIO()
        budget=[64*1024]
        stdout=BoundedStartupWriter(output,budget)
        stderr=BoundedStartupWriter(output,budget)
        stdout.write('я'*20000)
        stderr.write('e'*50000)
        stderr.write('must-not-grow')
        self.assertEqual(len(output.getvalue().encode('utf-8')),64*1024)
        self.assertEqual(budget[0],0)

    def test_import_enables_private_config_and_preserves_upgrade_state(self):
        configure.install_config(self.values,self.base,self.module)
        state=self.base/'state'/'preserved.dat'
        state.write_bytes(b'previous-action-history')
        memory=self.base/'memory'/'preserved.dat'
        memory.write_bytes(b'old-summary')
        previous=(self.base/'config.json').read_bytes()
        with self.assertRaises(ValueError):
            configure.install_config({**self.values,'agent_token':'y'*40},self.base,self.module,confirm=lambda _: 'no')
        self.assertEqual((self.base/'config.json').read_bytes(),previous)
        configure.install_config({**self.values,'agent_token':'y'*40},self.base,self.module,confirm=lambda _: 'REPLACE')
        self.assertEqual(state.read_bytes(),b'previous-action-history')
        self.assertEqual(memory.read_bytes(),b'old-summary')
        self.assertTrue((self.base/'enabled').is_file())
        result=configure.read_config(self.base/'config.json',self.base,self.module)
        self.assertEqual(result['state_dir'],str(self.base/'state'))
        if os.name!='nt':
            self.assertEqual(stat.S_IMODE((self.base/'config.json').stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(self.base.stat().st_mode),0o700)

    def test_refuses_symlink_storage_without_touching_target(self):
        real=Path(self.temp.name)/'outside'
        real.mkdir()
        try:
            self.base.symlink_to(real,target_is_directory=True)
        except OSError:
            # Exercise the same refusal branch where Windows link privilege is absent.
            original=Path.is_symlink
            with patch.object(Path,'is_symlink',lambda p:p==self.base or original(p)):
                with self.assertRaises(ValueError):
                    configure.install_config(self.values,self.base,self.module)
        else:
            with self.assertRaises(ValueError):
                configure.install_config(self.values,self.base,self.module)
        self.assertEqual(list(real.iterdir()),[])

    def test_foreign_runtime_paths_and_unknown_fields_refused(self):
        for extra in ({'memory_dir':'/some/other/path'},{'state_dir':'/tmp'},{'unexpected':'anything'}):
            with self.assertRaises(ValueError): configure.validate({**self.values,**extra},self.base,self.module)

    def test_release_allowlist_reproducible_and_no_owner_config(self):
        target=Path(self.temp.name)/'repo'
        target.mkdir()
        for folder in ('agent','magisk','chatgpt'):
            shutil.copytree(ROOT/folder,target/folder)
        for source in builder.EXTRA_AGENT_INPUTS.values():
            (target/source).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/source,target/source)
        provenance=target/'device-runtime/artifacts';provenance.mkdir(parents=True)
        shutil.copyfile(ROOT/'device-runtime/artifacts/provider-manifest.json',provenance/'provider-manifest.json')
        shutil.copyfile(ROOT/'LICENSE',target/'LICENSE')
        # Even local secret-looking files and host tests must never enter release ZIP.
        (target/'agent'/'config.json').write_text('{"agent_token":"DO_NOT_BUNDLE"}')
        artifact=builder.build(target)
        first=artifact.read_bytes()
        self.assertEqual(first,builder.build(target).read_bytes())
        with zipfile.ZipFile(artifact) as archive:
            expected=set(builder.MODULE_FILES)|{'agent/'+n for n in builder.AGENT_FILES}|{'LICENSE'}
            expected|={'agent/'+n for n in builder.EXTRA_AGENT_INPUTS}|set(builder.GENERATED_FILES)
            expected|={'chatgpt/package_card.py','chatgpt/README.md'}|{'chatgpt/plugin/'+n for n in builder.card_builder.FILES}
            expected.add('chatgpt/codaki-mini-codex-chatgpt-'+builder.VERSION+'.zip')
            self.assertEqual(set(archive.namelist()),expected)
            self.assertNotIn(b'DO_NOT_BUNDLE',b''.join(archive.read(n) for n in archive.namelist()))
            for name in archive.namelist():
                if not name.endswith(('.png','.zip')):
                    self.assertNotIn(b'\r',archive.read(name))
                if name.endswith('.sh'):
                    self.assertEqual((archive.getinfo(name).external_attr>>16)&0o777,0o755)
        self.assertEqual((target/'dist'/'SHA256SUMS').read_text().split()[0],hashlib.sha256(first).hexdigest())

    def test_magisk_scripts_scope_and_configuration_gate(self):
        service=(ROOT/'magisk'/'service.sh').read_text()
        customize=(ROOT/'magisk'/'customize.sh').read_text()
        self.assertLess(service.index('[ -f "$BASE/enabled" ]'),service.index('phone_agent.py'))
        self.assertLess(service.index('--validate'),service.index('phone_agent.py'))
        self.assertNotIn('touch "$BASE/enabled"',customize)
        for path in (ROOT/'magisk').glob('*.sh'):
            text=path.read_text()
            self.assertNotIn('rm -rf',text)
            self.assertNotIn('pkill',text)
        uninstall=(ROOT/'magisk'/'uninstall.sh').read_text()
        self.assertIn('stop.sh',uninstall)
        self.assertNotIn('rm ',uninstall)

    def test_shell_syntax_and_mock_installer_preserve_existing_storage(self):
        shell=shutil.which('sh')
        if not shell:
            candidate=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/usr/bin/sh.exe'
            if candidate.is_file(): shell=str(candidate)
        if not shell: self.skipTest('POSIX shell unavailable on this host')
        for script in (ROOT/'magisk').glob('*.sh'):
            check=subprocess.run([shell,'-n',str(script)],capture_output=True,text=True)
            self.assertEqual(check.returncode,0,check.stderr)
        # Replace fixed Android paths in a temporary test copy ONLY. The real
        # installer and current device/storage are never executed or modified.
        self.base.mkdir()
        (self.base/'config.json').write_bytes(b'existing-private-config')
        (self.base/'enabled').write_bytes(b'')
        (self.base/'memory').mkdir()
        (self.base/'memory'/'old-note').write_bytes(b'preserved')
        runtime=Path(self.temp.name)/'python-mock'
        runtime.write_text('#!/bin/sh\nexit 0\n')
        os.chmod(runtime,0o755)
        script=(ROOT/'magisk'/'customize.sh').read_text()
        # Git sh expects /C/... POSIX paths; cygpath is unnecessary for Unix hosts.
        def posix_path(path):
            value=Path(path).absolute().as_posix()
            return '/'+value[0].lower()+value[2:] if len(value)>1 and value[1]==':' else value
        script=script.replace('/data/data/com.termux/files/usr/bin/python',posix_path(runtime))
        script=script.replace('"/system/bin/sh" "$MODPATH/install-runtime.sh" "$MODPATH"','"'+posix_path(runtime)+'"')
        script=script.replace('/data/adb/mini-codex',posix_path(self.base))
        script=script.replace('/data/adb',posix_path(Path(self.temp.name)))
        script=script.replace('for path in /data ', 'for path in '+posix_path(Path(self.temp.name))+' ')
        mock_script=Path(self.temp.name)/'customize-mock.sh'
        mock_script.write_text(script)
        self.module.mkdir()
        harness='abort(){ echo "$1" >&2; exit 2; }; ui_print(){ :; }; set_perm(){ :; }; set_perm_recursive(){ :; }; mkdir(){ :; }; chmod(){ :; }; BOOTMODE=true; MODPATH="$1"; . "$2"'
        result=subprocess.run([shell,'-c',harness,'mock',posix_path(self.module),posix_path(mock_script)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.base/'config.json').read_bytes(),b'existing-private-config')
        self.assertEqual((self.base/'memory'/'old-note').read_bytes(),b'preserved')
        self.assertTrue((self.base/'enabled').exists())


if __name__=='__main__': unittest.main()
