"""Phone-local root tools. Python standard library only; no PC, ADB or model SDK."""
from __future__ import annotations
import base64
import hashlib
import gzip
import hmac
import inspect
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import stat
import subprocess
import tempfile
import threading
import time
import urllib.request
import urllib.parse
import uuid
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parent
from runtime_paths import BASE as SUPPORT_BASE,identity as runtime_identity
LOCK=threading.RLock()
TOTAL_STORAGE_BYTES=5*1024*1024*1024
AGENT_STORAGE_RESERVE_BYTES=32*1024*1024
MAX_MEMORY_BYTES=TOTAL_STORAGE_BYTES-AGENT_STORAGE_RESERVE_BYTES
_RECOVERED_MEMORY_DATABASES=set()

from portable_tools import OPERATIONS as PORTABLE_OPERATIONS,wrapper as portable_wrapper
for _portable_operation in PORTABLE_OPERATIONS:
    globals()['phone_use_'+_portable_operation]=portable_wrapper(_portable_operation)
from managed_tools import OPERATIONS as MANAGED_OPERATIONS, wrapper as managed_wrapper
for _managed_operation in MANAGED_OPERATIONS:
    globals()[_managed_operation]=managed_wrapper(_managed_operation)


def adb(*args: str, timeout: int=30, binary: bool=False):
    """Implement the existing tool backend using local su, not an ADB connection."""
    with LOCK:
        if args == ('get-state',):
            return 'local-android'
        if len(args) == 2 and args[0] == 'shell':
            command = args[1]
            if command.startswith('su -c '):
                parts = shlex.split(command)
                if len(parts) != 3:
                    raise ValueError('Malformed root command wrapper')
                command = parts[2]
            return run_android(command, timeout=timeout, binary=binary,require_root=args[1].startswith('su -c '))
        if args and args[0] == 'exec-out':
            if len(args) == 2 and args[1].startswith('su -c '):
                parts = shlex.split(args[1])
                if len(parts) != 3:
                    raise ValueError('Malformed root command wrapper')
                command = parts[2]
            else:
                command = shlex.join(args[1:])
            return run_android(command, timeout=timeout, binary=binary)
        if len(args) == 3 and args[0] == 'push':
            source, destination = args[1:]
            if not Path(source).is_file():
                raise ValueError('Local phone runtime file does not exist')
            run_android('cp -- ' + shlex.quote(source) + ' ' + phone_path(destination), timeout=timeout)
            return 'Copied locally on Android'
        raise ValueError('Unsupported local Android backend operation')

def run_android(command: str, *, timeout: int=30, binary: bool=False,require_root:bool=True):
    is_root = getattr(os, 'geteuid', lambda: -1)() == 0
    if require_root and not is_root:
        raise PermissionError('This operation requires explicitly selected root mode; app mode never requests su')
    full_command = 'export PATH=/system/bin:/system/xbin; ' + command
    environment = os.environ.copy()
    environment.pop('LD_PRELOAD', None)
    environment.pop('LD_LIBRARY_PATH', None)
    try:
        argv = ['/system/bin/sh', '-c', full_command]
        result = subprocess.run(argv, capture_output=True, timeout=timeout, env=environment)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Android root command timed out') from exc
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace')[:2000])
    return result.stdout if binary else result.stdout.decode('utf-8', 'replace').strip()

def shell(command: str, root: bool=True, timeout: int=30):
    return adb('shell', 'su -c ' + shlex.quote(command) if root else command, timeout=timeout)

def phone_path(path: str) -> str:
    if not path.startswith('/') or '\x00' in path or '\n' in path:
        raise ValueError('Specify an absolute Android path without nulls/newlines')
    return shlex.quote(path)

def coordinate(value: int) -> int:
    if not 0 <= value <= 16384:
        raise ValueError('Coordinate must be between 0 and 16384')
    return value

def wake_phone() -> None:
    """Wake without changing timeouts or bypassing a secure lock screen."""
    shell('input keyevent 224')
    time.sleep(0.25)
    if os.environ.get('ANDROID_MCP_DISMISS_INSECURE_KEYGUARD') == '1':
        shell('wm dismiss-keyguard')

def redact_ui_text(value: str) -> str:
    return re.sub('(?:https?|vless|vmess|trojan|ss|ssr|hysteria2?|hy2|tuic)://[^\\s<>\\"\']+', '[private URL]', value, flags=re.I)

def phone_status() -> dict:
    """Read connection, model, Android/build version, battery and root availability."""
    state = adb('get-state')
    props = shell('getprop ro.product.model; getprop ro.build.version.release; getprop ro.build.version.incremental', root=False).splitlines()
    active=runtime_identity()
    battery = shell('dumpsys battery', root=False) if active['root_active'] else ''
    level = re.search('level:\\s*(\\d+)', battery)
    result = {'state': state, 'observed_at': time.time(), 'model': props[0] if props else '', 'android': props[1] if len(props) > 1 else '', 'build': props[2] if len(props) > 2 else '', 'battery_percent': int(level[1]) if level else None, 'root_identity': shell('id',root=active['root_active']),'runtime':active}
    try:
        from support_runtime import get_context
        result['support'] = get_context(SUPPORT_BASE)
    except (ImportError, OSError, ValueError):
        result['support'] = {'state': 'unavailable', 'skill_path': str(SUPPORT_BASE/'support'/'SKILL.md')}
    result['operation_statistics']=operation_statistics()
    # Report discovery only; socket presence is not a responsiveness check.
    try:
        portable=Path('/data/adb/codaki-portable-use/state/portable.sock').lstat()
        private=stat.S_ISSOCK(portable.st_mode) and portable.st_uid==0 and not portable.st_mode & 0o077
    except OSError:
        private=False
    result['portable_use']={'state':'socket-present' if private else 'unavailable',
        'entrypoint':str(BASE/'portable_peer.py'),
        'instruction':'Use portable_peer capabilities, then session_start and observe on its owned nonzero display. Stable request IDs prevent replay. A batch stops on its first failure; completed steps are not rolled back.'}
    return result


def operation_statistics() -> dict:
    """Read bounded aggregate timings; no job inputs, output bodies or secrets."""
    path=SUPPORT_BASE/'state'/'jobs.sqlite3'
    if not path.is_file() or path.is_symlink():
        return {'state':'unavailable','tools':[]}
    try:
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=0.1)
        try:
            rows=db.execute('SELECT tool,calls,errors,total_ms,max_ms,first_at,last_at FROM tool_metrics ORDER BY total_ms DESC LIMIT 30').fetchall()
            queue=db.execute("SELECT COUNT(*),MIN(updated),COALESCE(SUM(status='uncertain'),0) FROM jobs WHERE status IN ('completed','uncertain') AND id NOT IN (SELECT id FROM delivered)").fetchone()
            started=db.execute("SELECT COUNT(*) FROM jobs WHERE status='started'").fetchone()[0]
        finally:
            db.close()
    except (OSError,sqlite3.Error):
        return {'state':'unavailable','tools':[]}
    observed=time.time()
    age=max(0,round(observed-queue[1],2)) if queue[1] is not None else None
    findings=[]
    if queue[0] and age is not None and age>30:
        findings.append('Result delivery has been pending over 30 seconds. Check connectivity; do not repeat the Android action.')
    if queue[2]:
        findings.append('Some pending outcomes are uncertain. Inspect the actual phone state before deciding on a retry.')
    return {'state':'ready','observed_at':observed,
            'journal':{'pending_delivery':queue[0],'oldest_pending_seconds':age,'pending_uncertain':queue[2],'in_progress':started},
            'findings':findings,
            'scope':'Local executor time only; excludes relay/network/model latency. Counts since instrumentation was enabled.',
            'tools':[{'tool':r[0],'calls':r[1],'errors':r[2],'average_ms':round(r[3]/r[1],2) if r[1] else 0,
                      'max_ms':round(r[4],2),'first_at':r[5],'last_at':r[6]} for r in rows]}


def read_ui(limit: int=120) -> dict:
    """Read fresh visible Android UI nodes with bounds; password/private identifiers are redacted."""
    if not 1 <= limit <= 500:
        raise ValueError('limit must be 1..500')
    tree = None
    with LOCK:
        wake_phone()
        for attempt in range(3):
            remote = '/data/local/tmp/owner-mcp-ui-' + uuid.uuid4().hex + '.xml'
            try:
                result = shell('uiautomator dump --compressed ' + shlex.quote(remote), timeout=20)
                if 'ERROR:' in result or 'could not get idle state' in result.lower():
                    raise RuntimeError('Android UI hierarchy is not idle')
                tree = ET.fromstring(shell('cat ' + shlex.quote(remote)))
                break
            except (RuntimeError, ET.ParseError):
                if attempt < 2:
                    time.sleep(0.4)
            finally:
                try:
                    shell('rm -f ' + shlex.quote(remote))
                except RuntimeError:
                    pass
    if tree is None:
        return {'nodes': [], 'error': 'UI hierarchy unavailable after 3 attempts; use screenshot for animated screens. If locked, the owner must unlock the phone.'}
    nodes = []
    for node in tree.iter('node'):
        attrs = node.attrib
        text, desc = (attrs.get('text', ''), attrs.get('content-desc', ''))
        if not (text or desc or attrs.get('clickable') == 'true'):
            continue
        ident = attrs.get('resource-id', '')
        private = attrs.get('password') == 'true' or bool(re.search('password|secret|token|account_name|email|phone_number', ident, re.I))
        nodes.append({'text': '[private]' if private else redact_ui_text(text)[:500], 'description': '[private]' if private else redact_ui_text(desc)[:500], 'id': redact_ui_text(ident), 'bounds': attrs.get('bounds'), 'clickable': attrs.get('clickable') == 'true', 'enabled': attrs.get('enabled') == 'true'})
        if len(nodes) >= limit:
            break
    return {'nodes': nodes, 'rotation': tree.attrib.get('rotation')}

def tap(x: int, y: int) -> str:
    """Tap a coordinate derived from a fresh screenshot or read_ui bounds."""
    command = f'input tap {coordinate(x)} {coordinate(y)}'
    wake_phone()
    shell(command)
    return 'Tapped'

def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int=300) -> str:
    """Swipe the phone screen using fresh coordinates."""
    if not 50 <= duration_ms <= 10000:
        raise ValueError('duration_ms must be 50..10000')
    command = f'input swipe {coordinate(x1)} {coordinate(y1)} {coordinate(x2)} {coordinate(y2)} {duration_ms}'
    wake_phone()
    shell(command)
    return 'Swiped'

def keypress(key: str) -> str:
    """Send HOME, BACK, ENTER, POWER, WAKEUP, volume, menu or recent-apps key."""
    keys = {'HOME': 3, 'BACK': 4, 'ENTER': 66, 'POWER': 26, 'WAKEUP': 224, 'VOLUME_UP': 24, 'VOLUME_DOWN': 25, 'MENU': 82, 'APP_SWITCH': 187}
    if key.upper() not in keys:
        raise ValueError('Unsupported key')
    wake_phone()
    shell(f'input keyevent {keys[key.upper()]}')
    return 'Key sent'

def launch_app(package: str) -> str:
    """Open an installed Android package. Does not grant permissions or sign in."""
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z0-9_]+)+', package):
        raise ValueError('Invalid package name')
    wake_phone()
    return shell('monkey -p ' + package + ' -c android.intent.category.LAUNCHER 1')

def root_shell(command: str, timeout_seconds: int=30) -> dict:
    """Execute an owner-authorized Android root shell command, including advanced device management. May alter/delete any device data. Not a Windows shell."""
    if not command.strip() or '\x00' in command:
        raise ValueError('Command is empty or contains a null byte')
    if not 1 <= timeout_seconds <= 120:
        raise ValueError('timeout_seconds must be 1..120')
    # Shell jobs run in their own process; a long command must not hold the
    # UI inspector/input lock and delay independent reads or PTYs.
    result = run_android(command, timeout=timeout_seconds)
    return {'output': result[:60000], 'truncated': len(result) > 60000}

def phone_list_files(directory: str, include_hidden: bool=False) -> dict:
    """List an owner-requested Android directory with root, including app/private folders when explicitly requested."""
    result = shell('ls ' + ('-la ' if include_hidden else '-l ') + '-- ' + phone_path(directory))
    return {'directory': directory, 'listing': result[:60000], 'truncated': len(result) > 60000}

def phone_read_file(path: str, encoding: str='utf-8', max_bytes: int=262144) -> dict:
    """Read an explicitly requested phone file as UTF-8 or base64. Never extract credentials or tokens."""
    if encoding not in ('utf-8', 'base64') or not 1 <= max_bytes <= 8 * 1024 * 1024:
        raise ValueError('encoding must be utf-8/base64; max_bytes must be 1..8388608')
    quoted = phone_path(path)
    raw = adb('exec-out', 'su -c ' + shlex.quote(f'head -c {max_bytes + 1} -- {quoted}'), binary=True)
    return {'path': path, 'encoding': encoding, 'content': base64.b64encode(raw[:max_bytes]).decode() if encoding == 'base64' else raw[:max_bytes].decode('utf-8', 'replace'), 'truncated': len(raw) > max_bytes}

def phone_write_file(path: str, content: str, encoding: str='utf-8') -> dict:
    """Write a user-requested phone file atomically with root; existing file metadata is preserved when possible. Can overwrite any writable device file."""
    destination = phone_path(path)
    if encoding not in ('utf-8', 'base64'):
        raise ValueError('encoding must be utf-8/base64')
    data = base64.b64decode(content, validate=True) if encoding == 'base64' else content.encode('utf-8')
    if len(data) > 8 * 1024 * 1024:
        raise ValueError('Maximum write size is 8 MiB; use root_shell for larger files')
    remote = '/data/local/tmp/owner-mcp-write-' + uuid.uuid4().hex
    staged = path + '.owner-mcp-' + uuid.uuid4().hex
    staged_q = phone_path(staged)
    with LOCK, tempfile.TemporaryDirectory(prefix='owner-mcp-') as folder:
        local = Path(folder) / 'payload.bin'
        local.write_bytes(data)
        try:
            adb('push', str(local), remote)
            shell(f'set -e; if [ -e {destination} ]; then cp -p -- {destination} {staged_q}; else umask 077; touch -- {staged_q}; fi; cat {shlex.quote(remote)} > {staged_q}; mv -f -- {staged_q} {destination}')
        finally:
            shell('rm -f -- ' + shlex.quote(remote) + ' ' + staged_q)
    return {'path': path, 'bytes_written': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

class HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != 'https':
            raise ValueError('Redirect to non-HTTPS URL rejected')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def phone_download_url(url: str, destination: str, expected_sha256: str='') -> dict:
    """Download an owner-approved public HTTPS file with verified TLS on this PC, then save it to the phone. Does not install it automatically. Up to 1 GiB."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Only HTTPS URLs without embedded credentials are supported')
    if expected_sha256 and (not re.fullmatch('[a-fA-F0-9]{64}', expected_sha256)):
        raise ValueError('Invalid SHA-256')
    dest = phone_path(destination)
    digest = hashlib.sha256()
    total = 0
    remote = '/data/local/tmp/owner-mcp-download-' + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='owner-mcp-download-') as folder:
        local = Path(folder) / 'download.bin'
        opener = urllib.request.build_opener(HttpsOnlyRedirect())
        request = urllib.request.Request(url, headers={'User-Agent': 'OwnerAndroidBridge/1.0'})
        with opener.open(request, timeout=30) as response, local.open('wb') as out:
            while (block := response.read(1024 * 1024)):
                total += len(block)
                if total > 1024 * 1024 * 1024:
                    raise ValueError('Download exceeds 1 GiB')
                digest.update(block)
                out.write(block)
        actual = digest.hexdigest()
        if expected_sha256 and (not hmac.compare_digest(actual, expected_sha256.lower())):
            raise ValueError('Downloaded file SHA-256 does not match')
        with LOCK:
            try:
                adb('push', str(local), remote, timeout=120)
                shell('cp -- ' + shlex.quote(remote) + ' ' + dest)
            finally:
                shell('rm -f -- ' + shlex.quote(remote))
    return {'destination': destination, 'bytes': total, 'sha256': actual}

def phone_install_apk(path: str, replace: bool=True) -> str:
    """Install a user-approved APK already stored on the phone with root pm, without Fastboot."""
    if not path.lower().endswith('.apk'):
        raise ValueError('Specify an APK path')
    return shell('pm install ' + ('-r ' if replace else '') + phone_path(path), timeout=120)

def screenshot() -> dict:
    wake_phone()
    data=adb('exec-out','screencap','-p',binary=True)
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('Android did not return a PNG')
    if len(data)>2*1024*1024:
        raise ValueError('Screenshot exceeds the 2 MiB transport limit; use read_ui for this screen')
    return {'content':[{'type':'image','mimeType':'image/png','data':base64.b64encode(data).decode('ascii')}]}


def redact_memory(value: str) -> str:
    value=redact_ui_text(value)
    value=re.sub(r'(?i)(?:authorization|cookie|set-cookie)\s*[:=][^\n]+','[secret]',value)
    value=re.sub(r'(?i)bearer\s+[^\s,;]+','[secret]',value)
    value=re.sub(r'(?i)otpauth://[^\s<>\"\']+','[secret]',value)
    value=re.sub(r'(?i)\b(?:password|passwd|pwd|secret|token|api[_ -]?key|пароль|токен|otp|totp|pin)\s*[:=]\s*[^\s,;]+','[secret]',value)
    value=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{10,})\b','[secret]',value)
    value=re.sub(r'\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b','[secret]',value)
    value=re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','[private address]',value)
    value=re.sub(r'(?<!\w)\+?\d[\d\s()-]{8,}\d(?!\w)','[private number]',value)
    value=re.sub(r'(?<!\d)\d{6}(?!\d)','[private code]',value)
    return value


def allocated_disk_bytes(path: Path) -> int:
    info=path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError('Memory artifact is not a regular owned file')
    blocks=getattr(info,'st_blocks',None)
    if blocks is not None:
        # Keep a conservative block for inline data/inode storage as well.
        return max(4096,blocks*512)
    return max(4096,((info.st_size+4095)//4096)*4096)


def owned_archive_directory(db: sqlite3.Connection) -> Path:
    directory=Path(db.execute('PRAGMA database_list').fetchone()[2]).parent/'archives'
    directory.mkdir(exist_ok=True,mode=0o700)
    if not stat.S_ISDIR(directory.stat(follow_symlinks=False).st_mode):
        raise RuntimeError('Memory archive directory must not be a symlink')
    os.chmod(directory,0o700)
    return directory


def recover_memory_archives(db: sqlite3.Connection) -> bool:
    dbpath=Path(db.execute('PRAGMA database_list').fetchone()[2])
    identity=str(dbpath.resolve())
    if identity in _RECOVERED_MEMORY_DATABASES: return False
    directory=owned_archive_directory(db)
    # Stream this private directory once per process, never recurse or follow
    # symlinks. Strict filenames are exclusively generated by archive_note.
    with os.scandir(directory) as entries:
        for entry in entries:
            if not re.fullmatch(r'[0-9a-f]{32}\.json\.gz',entry.name) or not entry.is_file(follow_symlinks=False):
                continue
            record=db.execute('SELECT id FROM archives WHERE file=?',(entry.name,)).fetchone()
            if record is None:
                Path(entry.path).unlink()
            else:
                db.execute('UPDATE archives SET bytes=? WHERE id=?',(allocated_disk_bytes(Path(entry.path)),record[0]))
    # Remove stale index rows for missing/nonregular files. Never delete their
    # path or anything outside the private archive directory. Iterate in pages.
    last_id=0
    while True:
        rows=db.execute('SELECT id,file FROM archives WHERE id>? ORDER BY id LIMIT 500',(last_id,)).fetchall()
        if not rows: break
        for ident,name in rows:
            last_id=ident
            valid=bool(re.fullmatch(r'[0-9a-f]{32}\.json\.gz',name))
            if valid:
                try: valid=stat.S_ISREG((directory/name).stat(follow_symlinks=False).st_mode)
                except FileNotFoundError: valid=False
            if not valid: db.execute('DELETE FROM archives WHERE id=?',(ident,))
    db.commit()
    _RECOVERED_MEMORY_DATABASES.add(identity)
    return True


def memory_database() -> sqlite3.Connection:
    directory=Path(os.environ.get('PHONE_MEMORY_DIR',str(Path.home()/'.mini-codex'/'memory')))
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(directory,0o700)
    dbpath=directory/'notes.sqlite3'
    if dbpath.is_symlink(): raise RuntimeError('Memory database must not be a symlink')
    connection=sqlite3.connect(dbpath)
    os.chmod(dbpath,0o600)
    connection.execute('PRAGMA journal_mode=DELETE')
    connection.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY,title TEXT UNIQUE,content TEXT,tags TEXT,updated REAL)')
    connection.execute('CREATE TABLE IF NOT EXISTS archives (id INTEGER PRIMARY KEY,file TEXT UNIQUE,title TEXT,summary TEXT,tags TEXT,updated REAL,bytes INTEGER)')
    connection.commit()
    try:
        recovered=recover_memory_archives(connection)
        if recovered:
            archive_bytes=connection.execute('SELECT COALESCE(sum(bytes),0) FROM archives').fetchone()[0]
            if allocated_disk_bytes(dbpath)+archive_bytes>MAX_MEMORY_BYTES:
                compact_memory(connection)
    except Exception:
        connection.close()
        raise
    return connection


def archive_note(db: sqlite3.Connection, row: tuple) -> None:
    title,content,tags,updated=row
    directory=owned_archive_directory(db)
    name=uuid.uuid4().hex+'.json.gz'
    data=gzip.compress(json.dumps({'title':title,'content':content,'tags':json.loads(tags),'updated':updated},ensure_ascii=False).encode('utf-8'))
    destination=directory/name
    try:
        with destination.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(destination,0o600)
        db.execute('INSERT INTO archives(file,title,summary,tags,updated,bytes) VALUES(?,?,?,?,?,?)',(name,title,content[:384],tags,updated,allocated_disk_bytes(destination)))
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def compact_memory(db: sqlite3.Connection) -> int:
    dbpath=Path(db.execute('PRAGMA database_list').fetchone()[2])
    cap=MAX_MEMORY_BYTES
    db.commit()
    db.execute('VACUUM')
    while True:
        archived=db.execute('SELECT COALESCE(sum(bytes),0) FROM archives').fetchone()[0]
        total=allocated_disk_bytes(dbpath)+archived
        if total<=cap: return total
        oldest=db.execute('SELECT id,file FROM archives ORDER BY updated ASC LIMIT 50').fetchall()
        if not oldest: raise RuntimeError('Memory exceeds its cap after reserving agent journal/log storage')
        for ident,name in oldest:
            if not re.fullmatch(r'[0-9a-f]{32}\.json\.gz',name): raise RuntimeError('Invalid owned archive filename')
            path=owned_archive_directory(db)/name
            try:
                if stat.S_ISREG(path.stat(follow_symlinks=False).st_mode): path.unlink()
            except FileNotFoundError:
                pass
            db.execute('DELETE FROM archives WHERE id=?',(ident,))
        db.commit()
        db.execute('VACUUM')


def _legacy_phone_memory_save(title: str, content: str, tags: list[str] | None=None) -> dict:
    if not isinstance(title,str) or not title.strip() or len(title)>160:
        raise ValueError('Title must be 1..160 characters')
    if not isinstance(content,str) or not content.strip() or len(content.encode('utf-8'))>6144:
        raise ValueError('Memory content must be a short note/script of at most 6 KiB')
    tags=[] if tags is None else tags
    if not isinstance(tags,list) or len(tags)>20 or any(not isinstance(t,str) or len(t)>50 for t in tags):
        raise ValueError('Invalid memory tags')
    # Do not accept full images/APKs/base64 exports as automatic memory.
    if 'data:image/' in content.lower() or re.search(r'[A-Za-z0-9+/]{1024,}={0,2}',content):
        raise ValueError('Store short summaries/scripts, not screenshots or binary/base64 exports')
    clean_title=redact_memory(title.strip())
    clean_content=redact_memory(content.strip())
    clean_tags=[redact_memory(t) for t in tags]
    with LOCK:
        db=memory_database()
        try:
            previous=db.execute('SELECT title,content,tags,updated FROM notes WHERE title=?',(clean_title,)).fetchone()
            if previous and (previous[1]!=clean_content or previous[2]!=json.dumps(clean_tags,ensure_ascii=False)):
                archive_note(db,previous)
            db.execute('INSERT INTO notes(title,content,tags,updated) VALUES(?,?,?,?) ON CONFLICT(title) DO UPDATE SET content=excluded.content,tags=excluded.tags,updated=excluded.updated',
                       (clean_title,clean_content,json.dumps(clean_tags,ensure_ascii=False),time.time()))
            overflow=db.execute('SELECT title,content,tags,updated FROM notes ORDER BY updated DESC LIMIT -1 OFFSET 200').fetchall()
            for row in overflow: archive_note(db,row)
            db.execute('DELETE FROM notes WHERE id NOT IN (SELECT id FROM notes ORDER BY updated DESC LIMIT 200)')
            size=compact_memory(db)
            count=db.execute('SELECT count(*) FROM notes').fetchone()[0]
            archive_count=db.execute('SELECT count(*) FROM archives').fetchone()[0]
        finally:
            db.close()
    return {'saved':True,'title':clean_title,'notes_count':count,'archive_count':archive_count,'bytes':size,'max_bytes':MAX_MEMORY_BYTES,'total_storage_cap_bytes':TOTAL_STORAGE_BYTES,'agent_reserve_bytes':AGENT_STORAGE_RESERVE_BYTES,'redacted':clean_title!=title.strip() or clean_content!=content.strip() or clean_tags!=tags}


def _legacy_phone_memory_search(query: str, limit: int=10) -> dict:
    if not isinstance(query,str) or len(query)>2000 or not 1<=limit<=30:
        raise ValueError('Invalid memory query/limit')
    # SQLite LIKE only folds ASCII by default. Fold Unicode explicitly and
    # treat punctuation literally, including SQL wildcard characters.
    phrase=redact_memory(query).strip().casefold()
    terms=tuple(dict.fromkeys(phrase.split()))
    def memory_rank(title,content,tags):
        fields=tuple((value or '').casefold() for value in (title,content,tags))
        if any(phrase in field for field in fields):
            return 2
        return int(all(any(term in field for field in fields) for term in terms))
    with LOCK:
        db=memory_database()
        try:
            db.create_function('memory_rank',3,memory_rank,deterministic=True)
            rows=db.execute('SELECT id,title,content,tags,updated,memory_rank(title,content,tags) AS relevance FROM notes WHERE relevance>0 ORDER BY relevance DESC,updated DESC LIMIT ?',(limit,)).fetchall()
            archive_rows=db.execute('SELECT id,title,summary,tags,updated,memory_rank(title,summary,tags) AS relevance FROM archives WHERE relevance>0 ORDER BY relevance DESC,updated DESC LIMIT ?',(limit-len(rows),)).fetchall()
        finally:
            db.close()
    return {'notes':[{'id':r[0],'title':r[1],'content':r[2],'tags':json.loads(r[3]),'updated':r[4],'archived':False} for r in rows]+[{'id':r[0],'title':r[1],'content':r[2],'tags':json.loads(r[3]),'updated':r[4],'archived':True} for r in archive_rows]}


def _memory_bridge():
    from memory_bridge import MemoryBridge
    return MemoryBridge()


def phone_memory_save(title: str, content: str, tags: list[str] | None=None, memory: dict | None=None) -> dict:
    from memory_bridge import MemoryUnavailable
    bridge=_memory_bridge()
    if not bridge.configured:
        if memory is not None: raise RuntimeError('Tencent memory is not configured; structured memory was not saved')
        return {**_legacy_phone_memory_save(title,content,tags),'engine':'legacy'}
    if not isinstance(title,str) or not title.strip() or len(title)>160: raise ValueError('Invalid memory title')
    if not isinstance(content,str) or not content.strip() or len(content.encode('utf-8'))>6144: raise ValueError('Memory content must be at most 6 KiB')
    tags=[] if tags is None else tags
    if not isinstance(tags,list) or len(tags)>20 or any(not isinstance(t,str) or len(t)>50 for t in tags): raise ValueError('Invalid memory tags')
    if 'data:image/' in content.lower() or re.search(r'[A-Za-z0-9+/]{1024,}={0,2}',content): raise ValueError('Store summaries, not binary exports')
    if memory is not None and not isinstance(memory,dict): raise ValueError('Invalid structured memory')
    clean_memory=None if memory is None else {k:redact_memory(v) if isinstance(v,str) else v for k,v in memory.items()}
    try:
        result=bridge.save(redact_memory(title.strip()),redact_memory(content.strip()),[redact_memory(t) for t in tags],clean_memory)
        return {**result,'redacted':redact_memory(content.strip())!=content.strip()}
    except MemoryUnavailable:
        if memory is not None: raise
        return {**_legacy_phone_memory_save(title,content,tags),'engine':'legacy-fallback','warning':'Tencent is unavailable; saved in original legacy memory'}


def phone_memory_search(query: str, limit: int=5, filters: dict | None=None) -> dict:
    from memory_bridge import MemoryUnavailable
    if not isinstance(query,str) or len(query)>2000 or isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=30: raise ValueError('Invalid memory query/limit')
    bridge=_memory_bridge()
    if not bridge.configured:
        if filters: raise RuntimeError('Tencent memory filters are not configured')
        return {**_legacy_phone_memory_search(query,limit),'engine':'legacy'}
    try:
        result=bridge.search(redact_memory(query),limit,filters)
        if filters:return result
        # Transitional read-only merge: outage writes in legacy remain visible.
        legacy=_legacy_phone_memory_search(query,limit)['notes']
        current=result.get('notes',[])
        def duplicate(old):
            source='legacy:'+('archives' if old.get('archived') else 'notes')+':'+str(old['id'])
            return any((x.get('memory',{}).get('source_id')==source and (old.get('archived') or
                       old.get('updated',0)<=x.get('updated',0) or
                       (x.get('truncated') and old.get('content','').startswith(x.get('content',''))))) or
                       (x.get('title')==old.get('title') and x.get('memory',{}).get('device')=='android' and
                        x.get('memory',{}).get('project') in ('','codaki') and old.get('updated',0)<=x.get('updated',0)) or
                       (x.get('title')==old.get('title') and x.get('content')==old.get('content') and x.get('tags')==old.get('tags')) for x in current)
        extra=[{**x,'engine':'legacy','memory':{'layer':'L0' if x.get('archived') else 'L1','status':'historical','source':'legacy SQLite; not reconciled'}} for x in legacy if not duplicate(x)]
        if not extra:return result
        result={**result,'engine':'tencentdb-original-external+legacy','warning':'Includes legacy evidence; reconcile newer legacy notes explicitly.',
                'notes':(extra+[{**x,'engine':'tencentdb-original-external'} for x in current])[:limit]}
        while len(json.dumps(result,ensure_ascii=False).encode())>6144 and len(result['notes'])>1:result['notes'].pop()
        if result['notes']:
            note=result['notes'][0]
            while len(json.dumps(result,ensure_ascii=False).encode())>6144 and note.get('content'):
                note['content']=note['content'][:-64];note['truncated']=True
        if len(json.dumps(result,ensure_ascii=False).encode())>6144:raise ValueError('Memory metadata exceeds response budget')
        return result
    except MemoryUnavailable:
        if filters: raise
        return {**_legacy_phone_memory_search(query,limit),'engine':'legacy-fallback','warning':'Tencent unavailable; searched original legacy memory'}


def phone_memory_read(record_id: str) -> dict:
    return _memory_bridge().read(record_id)


def phone_memory_health() -> dict:
    bridge=_memory_bridge()
    if not bridge.configured: return {'engine':'legacy','tencent_configured':False}
    result=bridge.health()
    try:
        from project_graph import ProjectGraph
        G,manifest,changed=ProjectGraph()._load()
        result['graph']={'engine':'graphify-original','nodes':len(G),'edges':G.number_of_edges(),'stale':bool(changed),'revision':manifest.get('revision')}
    except Exception as exc: result['graph']={'state':'unavailable','reason':type(exc).__name__}
    return result


def project_graph_query(question: str) -> dict:
    from project_graph import ProjectGraph
    return ProjectGraph().query(question)


def project_graph_node(label: str) -> dict:
    from project_graph import ProjectGraph
    return ProjectGraph().node(label)


def project_graph_path(source: str, target: str) -> dict:
    from project_graph import ProjectGraph
    return ProjectGraph().path(source,target)


def tool_definitions() -> list[dict]:
    from managed_tools import definitions
    existing=json.loads((BASE/'tool-definitions.json').read_text(encoding='utf-8'))
    managed=definitions();names={d['name'] for d in managed}
    return [d for d in existing if d['name'] not in names]+managed


def validate_schema(value, schema: dict, name: str='arguments') -> None:
    kind=schema.get('type')
    types={'string':str,'object':dict,'array':list,'boolean':bool,'integer':int}
    if kind in types and (not isinstance(value,types[kind]) or (kind=='integer' and isinstance(value,bool))):
        raise ValueError(name+' must be '+kind)
    if 'enum' in schema and value not in schema['enum']: raise ValueError(name+' has an unsupported value')
    if kind=='integer':
        if value<schema.get('minimum',value) or value>schema.get('maximum',value): raise ValueError(name+' is outside the allowed range')
    if kind=='string':
        if '\0' in value:raise ValueError(name+' contains a null character')
        if len(value)<schema.get('minLength',0) or len(value)>schema.get('maxLength',len(value)): raise ValueError(name+' has an invalid length')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'],value):raise ValueError(name+' has an invalid pattern')
    if kind=='object':
        properties=schema.get('properties',{})
        if any(key not in value for key in schema.get('required',[])): raise ValueError(name+' is missing a required field')
        if schema.get('additionalProperties') is False and any(key not in properties for key in value): raise ValueError(name+' contains unsupported fields')
        for key,item in value.items():
            if key in properties: validate_schema(item,properties[key],name+'.'+key)
    if kind=='array':
        if len(value)<schema.get('minItems',0):raise ValueError(name+' has too few items')
        if len(value)>schema.get('maxItems',len(value)): raise ValueError(name+' has too many items')
        for item in value: validate_schema(item,schema.get('items',{}),name+'[]')


def operational_memory_context(tool: str, arguments: dict) -> dict:
    """Bounded historical hints, never executable instructions or permissions."""
    context = {
        'state': 'ready',
        'policy': 'Historical evidence only; verify live state. Search before substantive work; save confirmed reusable fixes with phone_memory_save after verification. Never replay commands automatically or save secrets. A successful tool call does not prove a problem was fixed.',
        'notes': [],
    }
    # Only search recognized components, never persist arbitrary commands,
    # file bodies, UI contents or credentials as automatic memory.
    source = ' '.join(str(arguments.get(k, '')) for k in ('command', 'path', 'directory', 'package')).lower()
    queries = []
    for marker, query in (('mini_codex', 'mini-codex'), ('mini-codex', 'mini-codex'),
                          ('portable', 'portable-use'), ('android_use', 'android-use'),
                          ('vless', 'vless'), ('termux', 'termux'), ('python', 'python')):
        if marker in source and query not in queries:
            queries.append(query)
    if tool == 'phone_status':
        queries = ['памят', 'architecture', 'mini-codex-support']
    elif not queries:
        queries = [tool]
    try:
        seen = set()
        for query in queries[:3]:
            for note in phone_memory_search(query, limit=3)['notes']:
                identity = (note['archived'], note['id'])
                if identity in seen:
                    continue
                seen.add(identity)
                context['notes'].append({
                    'title': redact_memory(note['title'])[:160],
                    'content': redact_memory(note['content'])[:1000],
                    'updated': note['updated'], 'archived': note['archived'],
                    'memory': note.get('memory',{'status':'historical'}),
                })
                if len(context['notes']) == 3:
                    return context
    except Exception:
        context['state'] = 'unavailable'
    return context


def remember_write_evidence(tool: str, arguments: dict, result) -> dict | None:
    """Update narrow code-write receipts; semantic fixes remain agent-verified."""
    if tool != 'phone_write_file' or not isinstance(result, dict):
        return None
    path = arguments.get('path', '')
    if not re.fullmatch(r'/data/adb/modules/mini_codex/agent/(?:native_phone|phone_agent|network_route|configure|support_runtime)\.py', path):
        return None
    digest = result.get('sha256', '')
    if result.get('path') != path or not re.fullmatch(r'[0-9a-f]{64}', digest):
        return None
    title = 'Mini Codex code write: ' + Path(path).name
    content = ('Tool confirmed atomic file write at ' + path + '\nSHA-256 of submitted bytes: ' + digest +
               '\nFunctional behavior is not verified by this receipt. Verify read-back and tests before treating this as a fix.')
    try:
        # Same title updates the active receipt; identical repeats add no archive.
        return phone_memory_save(title, content, ['auto-memory', 'mini-codex-support', 'write-evidence'])
    except Exception:
        return {'saved': False, 'state': 'unavailable'}


def dispatch(tool: str, arguments: dict) -> dict:
    # Dispatch exclusively named tools; never eval code received from the relay.
    allowed={definition['name']:definition for definition in tool_definitions()}
    if tool not in allowed or not isinstance(arguments,dict):
        return {'content':[{'type':'text','text':'Unknown tool or invalid arguments'}],'isError':True}
    try:
        validate_schema(arguments,allowed[tool]['inputSchema'])
        function=globals()[tool]
        inspect.signature(function).bind(**arguments)
        context = None if tool.startswith('phone_memory_') or tool in MANAGED_OPERATIONS else operational_memory_context(tool, arguments)
        from path_locks import hold
        file_paths=[arguments[key] for key in ('path','source','destination') if isinstance(arguments.get(key),str)]
        with hold(file_paths):result=function(**arguments)
        if tool.startswith('phone_use_'):return result
        if context is not None:
            receipt = remember_write_evidence(tool, arguments, result)
            if receipt is not None:
                context['write_evidence'] = receipt
        if tool=='screenshot':
            return {**result, 'content': result['content'] + [{'type':'text','text':json.dumps({'memory_context':context},ensure_ascii=False)}], 'isError':False}
        result = result if isinstance(result,dict) else {'result':result}
        if context is not None:
            result = {**result, 'memory_context': context}
        return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}],
                'structuredContent':result,'isError':False}
    except Exception as exc:
        # A command error may contain an input URL; sanitize before transmission.
        blocks = [{'type':'text','text':redact_ui_text(str(exc))[:3000]}]
        if 'context' in locals() and context is not None:
            blocks.append({'type':'text','text':json.dumps({'memory_context':context},ensure_ascii=False)})
        return {'content':blocks,'isError':True}
