"""Phone support reference loader and metadata-only inventory; standard library."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import sys,shlex
from runtime_paths import BASE,MODE

PATHS = {
    'mini_codex': '/data/adb/mini-codex',
    'boot_service': '/data/adb/modules/mini_codex/service.sh',
    'job_log': '/data/adb/mini-codex/state/agent.log',
    'job_journal': '/data/adb/mini-codex/state/jobs.sqlite3',
    'memory': '/data/adb/mini-codex/memory',
    'tencent_memory': '/data/data/com.termux/files/usr/var/lib/codaki-memory/data',
    'memory_supervisor': '/data/adb/modules/mini_codex/agent/memory_service.py',
    'project_graph': '/data/adb/mini-codex/project-graph',
    'node': '/data/data/com.termux/files/usr/bin/node',
    'python': '/data/data/com.termux/files/usr/bin/python',
    'modules': '/data/adb/modules',
    'network_proxy': '/data/adb/gpt-vless',
    'network_boot': '/data/adb/modules/gpt_vless_router/service.sh',
    'downloads': '/sdcard/Download',
    'temporary_files': '/data/local/tmp',
    'lsposed': '/data/adb/lspd',
}
KEY_PACKAGES = ('com.termux', 'com.openai.chatgpt', 'com.topjohnwu.magisk',
                'io.github.mekhontsev.magicdesk', 'su.happ.proxyutility',
                'com.sevtinge.hyperceiler', 'org.lsposed.corepatch')

def runtime_paths(base):
    paths=PATHS.copy();runtime=Path(__file__).resolve().parent
    paths.update(mini_codex=str(base),job_log=str(base/'state/agent.log'),job_journal=str(base/'state/jobs.sqlite3'),memory=str(base/'memory'),project_graph=str(base/'project-graph'),python=sys.executable)
    if os.environ.get('RELAYKITE_NATIVE'):
        paths.update(node=str(Path(os.environ['RELAYKITE_NATIVE'])/'librelaykite_node.so'),tencent_memory=str(base/'memory-service/data'),memory_supervisor=str(runtime/'app_worker.py'))
    if MODE=='app':
        paths={k:v for k,v in paths.items() if k not in ('modules','network_proxy','network_boot','lsposed','boot_service')}
    return paths


def read_owned(path: Path, limit: int) -> str:
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('Support references must be regular files')
    with path.open('rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Support reference is not a file')
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Support reference exceeds the context limit')
    return data.decode('utf-8')


def get_context(base: Path) -> dict:
    directory = base / 'support'
    references = directory if (directory/'SKILL.md').exists() else Path(__file__).resolve().parent/'support'
    result = {'state': 'partial', 'skill_path': str(references/'SKILL.md'),
              'passport_path': str(directory/'passport.json'),
              'service_reference': str(references/'services.md'),
              'refresh_command': shlex.quote(sys.executable)+' '+shlex.quote(str(Path(__file__).resolve()))+' refresh',
              'memory_query': 'mini-codex-support', 'passport_stale': True}
    try:
        result['instructions'] = read_owned(references/'SKILL.md', 16384)
    except (OSError, ValueError, UnicodeError):
        result['skill_unavailable'] = True
    try:
        passport = json.loads(read_owned(directory/'passport.json', 512*1024))
        if passport.get('schema_version') != 1:
            raise ValueError('Unsupported passport schema')
        epoch = passport['verified_epoch']
        if type(epoch) not in (int, float) or not math.isfinite(epoch):
            raise ValueError('Invalid passport timestamp')
        packages = passport.get('packages', [])
        result['passport'] = {
            'verified_at': passport['verified_at'],
            'device': passport.get('device', {}),
            'python_version': passport.get('python_version'),
            'package_count': len(packages),
            'third_party_count': sum(bool(p.get('third_party')) for p in packages),
            'key_packages': [p for p in packages if p.get('package') in KEY_PACKAGES],
            'modules': passport.get('modules', []),
            'paths': passport.get('paths', {}),
        }
        age = time.time() - epoch
        result['passport_stale'] = age < 0 or age > 24*60*60
        if 'instructions' in result:
            result['state'] = 'ready'
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, AttributeError, OverflowError):
        result.pop('passport', None)
    return result


def refresh(base: Path, run) -> dict:
    """Capture only OS/package/path metadata; never read app or agent configs."""
    props = run('getprop ro.product.model; getprop ro.product.device; getprop ro.product.manufacturer; getprop ro.build.version.release; getprop ro.build.version.incremental').splitlines()
    if len(props) != 5:
        raise RuntimeError('Incomplete device properties; existing passport retained')
    identity = run('id')
    user_packages = {line[8:] for line in run('pm list packages -3').splitlines() if line.startswith('package:')}
    packages = []
    for line in run('pm list packages -f').splitlines():
        if not line.startswith('package:') or '=' not in line:
            continue
        apk, package = line[8:].rsplit('=', 1)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', package):
            continue
        packages.append({'package': package, 'apk_path': apk, 'third_party': package in user_packages})
    if not packages:
        raise RuntimeError('Package inventory empty; existing passport retained')
    modules = []
    module_root = base.parent/'modules'
    if module_root.is_dir() and not module_root.is_symlink():
        for directory in sorted(module_root.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                continue
            metadata = {}
            try:
                for line in read_owned(directory/'module.prop', 8192).splitlines():
                    key, sep, value = line.partition('=')
                    if sep and key in ('name', 'version', 'versionCode'):
                        metadata[key] = value[:200]
            except (OSError, ValueError, UnicodeError):
                pass
            modules.append({'id': directory.name, **metadata, 'path': str(directory),
                            'disabled': (directory/'disable').exists(), 'remove_pending': (directory/'remove').exists()})
    epoch = time.time()
    passport = {
        'schema_version': 1, 'verified_at': datetime.fromtimestamp(epoch, timezone.utc).isoformat(), 'verified_epoch': epoch,
        'source': 'phone-local OS properties, package manager, module metadata and path existence',
        'device': dict(zip(('model','codename','manufacturer','android','build'), props), root_identity=identity),
        'python_version': 'Python '+sys.version.split()[0],
        'packages': sorted(packages, key=lambda p:p['package']), 'modules': modules,
        'paths': {name:{'path':path,'exists':Path(path).exists()} for name,path in runtime_paths(base).items()},
        'limitations': ['Snapshot: recheck affected paths/packages before changing them.',
                        'Module enable markers are configuration metadata, not proof of a running process.',
                        'Credentials, private application files, accounts and file contents are not inventoried.'],
    }
    directory = base/'support'
    if directory.is_symlink():
        raise ValueError('Support directory must not be a symlink')
    directory.mkdir(mode=0o700, exist_ok=True)
    target = directory/'passport.json'
    if target.is_symlink():
        raise ValueError('Passport must not be a symlink')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=directory,prefix='.passport-',delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(passport, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary,0o600)
        os.replace(temporary,target)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return {'updated':True,'verified_at':passport['verified_at'],'package_count':len(packages),
            'third_party_count':len(user_packages),'module_count':len(modules),'passport_path':str(target)}


if __name__ == '__main__':
    import sys
    import native_phone
    from configure import BASE
    base = BASE
    if sys.argv[1:] == ['refresh']:
        result = refresh(base, native_phone.shell)
    elif sys.argv[1:] == ['summary']:
        result = get_context(base)
    else:
        raise SystemExit('Use support_runtime.py refresh|summary')
    print(json.dumps(result, ensure_ascii=False))
