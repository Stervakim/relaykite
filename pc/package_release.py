"""Build the PC installer and portable PC card from explicit public inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.3.0'
PC_FILES = ('mini_codex_pc.py', 'memory_summary.py', 'model_runtime.py', 'prepare_model_inputs.py', 'portable_client.py', 'portable-tools.json', 'install-background.ps1', 'INSTALL_WITH_CODEX.md', 'README.md',
            'LICENSE', 'phone-tools.json', 'package_release.py', 'relay-files.json',
            'chatgpt/package_card.py', 'chatgpt/README.md')
DEVELOPMENT_FILES = tuple(json.loads((ROOT/'pc/development/release-files.json').read_text(encoding='utf-8')))
PC_FILES += tuple('development/'+name for name in DEVELOPMENT_FILES)


def build(root=ROOT):
    root = Path(root)
    spec = importlib.util.spec_from_file_location('pc_card_builder', root/'pc/chatgpt/package_card.py')
    card = importlib.util.module_from_spec(spec); spec.loader.exec_module(card)
    output = root/'dist'; output.mkdir(exist_ok=True)
    target_card = card.build_card(root/'pc', output)
    entries = [(root/'pc'/p, p) for p in PC_FILES]
    entries += [(root/'pc/chatgpt/plugin'/p, 'chatgpt/plugin/'+p) for p in card.FILES]
    entries += [(root/'relay'/p, 'relay/'+p) for p in json.loads((root/'pc/relay-files.json').read_text())]
    entries.append((target_card, 'chatgpt/'+target_card.name))
    target = output/f'mini-codex-pc-{VERSION}.zip'
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in sorted(entries, key=lambda p:p[1]):
            if path.is_symlink() or not path.is_file() or '..' in Path(name).parts: raise ValueError('Invalid public release input')
            data = path.read_bytes()
            if path.suffix not in ('.png', '.zip'): data = data.replace(b'\r\n', b'\n')
            info = zipfile.ZipInfo(name, (2026,10,10,0,0,0)); info.create_system=3
            info.external_attr = 0o100644 << 16; info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    # Merge with the phone package sums without silently dropping its assets.
    sums = output/'SHA256SUMS'
    previous = sums.read_text().splitlines() if sums.exists() else []
    names = {target.name, target_card.name}
    previous = [line for line in previous if line.split('  ',1)[-1] not in names]
    sums.write_text('\n'.join(previous+[hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in (target,target_card)])+'\n',encoding='ascii',newline='\n')
    return target


if __name__ == '__main__': print(build())
