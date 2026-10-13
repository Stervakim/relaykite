"""Build reproducible Magisk-app ZIPs without phone access or credentials."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import zipfile

VERSION='0.2.4'
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mini_codex_card',ROOT/'chatgpt'/'package_card.py')
card_builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(card_builder)
MODULE_FILES=('module.prop','skip_mount','customize.sh','service.sh','stop.sh','uninstall.sh','configure.sh','INSTALL_WITH_CODEX.md')
AGENT_FILES=('native_phone.py','phone_agent.py','network_route.py','pc_peer.py','portable_peer.py','tool-definitions.json','configure.py','support_runtime.py','support/SKILL.md','support/services.md',
             'job_scheduler.py','terminal_manager.py','_pty_exec.py','managed_tools.py','file_ops.py','path_locks.py',
             'memory_bridge.py','memory_service.py','project_graph.py','graph-runtime.zip','portable_tools.py',
             'memory-runtime/codaki-external.mjs','memory-runtime/LICENSE.Tencent','memory-runtime/LICENSE.Graphify','memory-runtime/LICENSE.NetworkX',
             'memory-runtime/external.ts','memory-runtime/external.test.ts','memory-runtime/tencent-external.patch','memory-runtime/versions.json','memory-runtime/README.md')


def build(root=ROOT):
    root=Path(root)
    output=root/'dist'
    output.mkdir(exist_ok=True)
    card=card_builder.build_card(root,output)
    target=output/f'mini-codex-magisk-{VERSION}.zip'
    entries=[(root/'magisk'/name,name) for name in MODULE_FILES]
    entries += [(root/'agent'/name,'agent/'+name) for name in AGENT_FILES]
    entries.append((root/'LICENSE','LICENSE'))
    entries += [(root/'chatgpt'/name,'chatgpt/'+name) for name in ('package_card.py','README.md')]
    entries += [(root/'chatgpt'/'plugin'/name,'chatgpt/plugin/'+name) for name in card_builder.FILES]
    entries.append((card,'chatgpt/'+card.name))
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for source,name in sorted(entries,key=lambda item:item[1]):
            if source.is_symlink() or not source.is_file():
                raise ValueError('Release inputs must be regular files')
            data=source.read_bytes()
            if source.suffix not in ('.png','.zip'):
                data=data.replace(b'\r\n',b'\n')
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0))
            info.create_system=3
            info.external_attr=(0o100755 if name.endswith('.sh') else 0o100644)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    agent_output=output/'agent'
    agent_output.mkdir(exist_ok=True)
    for name in AGENT_FILES:
        (agent_output/name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/'agent'/name,agent_output/name)
    (output/'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n' for path in (target,card)),encoding='ascii',newline='\n')
    return target


if __name__=='__main__':
    print(build())
