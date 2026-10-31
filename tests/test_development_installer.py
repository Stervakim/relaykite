"""Pinned installer failures must not activate code or overwrite owner state."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
import development_install as installer


def package(entries):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:xz') as archive:
        for name,data,link in entries:
            member=tarfile.TarInfo(name)
            if link is not None:
                member.type=tarfile.SYMTYPE;member.linkname=link
                archive.addfile(member)
            else:
                member.size=len(data);archive.addfile(member,io.BytesIO(data))
    raw=stream.getvalue()
    header=('data.tar.xz/'.ljust(16)+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(raw)).ljust(10)+'`\n').encode()
    return b'!<arch>\n'+header+raw+(b'\n' if len(raw)%2 else b'')


class EngineInstallerTests(unittest.TestCase):
    def test_release_lock_pins_only_official_https_sources(self):
        lock=installer.load_lock()
        self.assertEqual(lock['codex']['version'],'0.165.0')
        self.assertEqual(lock['codex']['sha256'],'6522e056d0be7f531da915c9a81ae05bc70811b782542499cc0a9776d3abf5d3')
        self.assertEqual(lock['codex']['binary_sha256'],'b32ece31af06440da980b733fb8fefdd1f193439595fda84096f1caaceec543f')
        self.assertTrue({'git','ripgrep','ca-certificates'}<={p['name'] for p in lock['packages']})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lock.json'
            for address in ('http://github.com/openai/codex/releases/download/x',
                            'https://github.com/other/repo/releases/download/x',
                            'https://packages-cf.termux.dev.evil.example/apt/termux-main/pool/x'):
                lock['codex']['url']=address;path.write_text(json.dumps(lock),encoding='utf8')
                with self.subTest(address=address),self.assertRaises(ValueError):installer.load_lock(path)

    def test_package_links_resolve_without_extracting_files(self):
        raw=package([(installer.PREFIX+'bin/git',b'owned bytes',None),
                     (installer.PREFIX+'libexec/git-core/git-add',b'','../../bin/git')])
        files,links,resolve=installer.package_files(raw)
        self.assertEqual(resolve('libexec/git-core/git-add'),b'owned bytes')
        self.assertEqual(set(files),{'bin/git'})

    def test_traversal_absolute_links_cycles_and_duplicates_are_rejected(self):
        fixtures=[
            [('../outside',b'effect',None)],
            [(installer.PREFIX+'bin/x',b'','/data/adb/private')],
            [(installer.PREFIX+'bin/x',b'','../../../../outside')],
            [(installer.PREFIX+'bin/x',b'a',None),(installer.PREFIX+'bin/x',b'b',None)],
        ]
        for fixture in fixtures:
            with self.subTest(fixture=fixture),self.assertRaises(ValueError):installer.package_files(package(fixture))
        _,_,resolve=installer.package_files(package([(installer.PREFIX+'bin/x',b'','x')]))
        with self.assertRaises(ValueError):resolve('bin/x')

    def test_bad_download_never_becomes_a_cached_input(self):
        class Response(io.BytesIO):url='https://github.com/official'
        with tempfile.TemporaryDirectory() as directory:
            entry={'url':'https://github.com/official','sha256':'0'*64,'size':4}
            with self.assertRaises(ValueError):installer.fetch(entry,directory,opener=lambda *a,**k:Response(b'evil'))
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_verified_cached_input_is_not_downloaded_again(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=b'verified archive';checksum=hashlib.sha256(raw).hexdigest()
            path=Path(directory)/checksum;path.write_bytes(raw)
            with patch.object(installer.urllib.request,'urlopen',side_effect=AssertionError('must not download')):
                self.assertEqual(installer.fetch({'sha256':checksum},directory),path)

    def test_existing_engine_and_policy_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);engine=base/'development-engine';engine.mkdir()
            (engine/'owned').write_text('preserved');policy=base/'development-policy.json';policy.write_text('owner policy')
            with patch.object(installer,'installation_lock',return_value=contextlib.nullcontext()),self.assertRaises(FileExistsError):
                installer.install(base,base/'runtime',inputs={},execute=False)
            self.assertEqual((engine/'owned').read_text(),'preserved');self.assertEqual(policy.read_text(),'owner policy')

    def test_failed_build_is_not_activated_and_does_not_create_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            def fail(lock,inputs,target,runtime):
                target.mkdir();(target/'partial').write_text('not executable');raise ValueError('incomplete dependency closure')
            with patch.object(installer,'installation_lock',return_value=contextlib.nullcontext()),patch.object(installer,'build_engine',side_effect=fail),self.assertRaises(ValueError):
                installer.install(base,base/'runtime',inputs={},execute=False)
            self.assertFalse((base/'development-engine').exists());self.assertFalse((base/'development-policy.json').exists())
            self.assertEqual(list(base.iterdir()),[])

    def test_policy_creation_without_hardlink_keeps_owner_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            def build(lock, inputs, target, runtime):
                target.mkdir()
                (target/'manifest.json').write_text('staged')
                return {'codex_version':lock['codex']['version']}
            with patch.object(installer,'installation_lock',return_value=contextlib.nullcontext()):
                with patch.object(installer,'build_engine',side_effect=build):
                    with patch.object(installer.os,'link',side_effect=NotImplementedError('Android embedded Python'),create=True):
                        result=installer.install(base,base/'runtime',inputs={},execute=False)
            self.assertEqual(result['state'],'installed')
            policy=base/'development-policy.json'
            self.assertEqual(json.loads(policy.read_text()),{'workspace_roots':[str(base/'projects')]})
            self.assertEqual(policy.stat().st_mode & 0o777,0o600)

    def test_policy_preparation_failure_keeps_installation_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);original=installer.private_directory
            def build(lock,inputs,target,runtime):
                target.mkdir();(target/'manifest.json').write_text('staged')
                return {'codex_version':'0.165.0'}
            def blocked(path):
                if Path(path)==base/'projects':raise PermissionError('injected project-storage failure')
                return original(path)
            with patch.object(installer,'installation_lock',return_value=contextlib.nullcontext()),patch.object(installer,'build_engine',side_effect=build):
                with patch.object(installer,'private_directory',side_effect=blocked),self.assertRaises(PermissionError):
                    installer.install(base,base/'runtime',inputs={},execute=False)
                self.assertFalse((base/'development-engine').exists(),'Failed setup published a non-retryable engine')
                self.assertFalse((base/'development-policy.json').exists())
                result=installer.install(base,base/'runtime',inputs={},execute=False)
                self.assertEqual(result['state'],'installed')
                self.assertTrue((base/'development-policy.json').is_file())


if __name__=='__main__':unittest.main()
