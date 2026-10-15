"""Durable local runs; restarting never replays an interrupted side effect."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import uuid


TERMINAL = frozenset({'completed', 'failed', 'cancelled'})
_TRANSITIONS = {
    'queued': {'running', 'waiting_model', 'waiting_user', 'paused', 'cancelled', 'failed'},
    'running': {'waiting_model', 'waiting_user', 'paused', 'recovering', 'uncertain',
                'completed', 'failed', 'cancelled'},
    'waiting_model': {'running', 'waiting_user', 'paused', 'uncertain', 'failed', 'cancelled'},
    'waiting_user': {'running', 'waiting_model', 'paused', 'uncertain', 'failed', 'cancelled'},
    'paused': {'running', 'waiting_user', 'waiting_model', 'uncertain', 'failed', 'cancelled'},
    'recovering': {'running', 'waiting_model', 'waiting_user', 'paused', 'uncertain', 'failed', 'cancelled'},
    'uncertain': {'paused', 'failed', 'cancelled'},
    'completed': set(), 'failed': set(), 'cancelled': set(),
}
_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)


def _json(value, max_bytes=1_048_576):
    result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(result.encode('utf-8')) > max_bytes:
        raise ValueError('Payload exceeds storage limit; save large output as an artifact')
    return result


def _page_limit(value, maximum):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError('Page limit must be a positive integer')
    return min(value, maximum)


class RunStore:
    """SQLite WAL storage safe for threads and cooperating local service instances.

    Public dictionaries are detached JSON values. Request identities are immutable;
    a reused key with different arguments fails instead of silently starting work.
    """

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.root / 'runs.sqlite3'), timeout=30, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute('PRAGMA synchronous=FULL')
        self._db.execute('PRAGMA foreign_keys=ON')
        self._db.executescript('''
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
                prompt TEXT NOT NULL, workspace TEXT NOT NULL, status TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, limits TEXT NOT NULL,
                mode TEXT NOT NULL, error TEXT, checkpoint TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
                type TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_run_cursor ON events(run_id,id);
            CREATE TABLE IF NOT EXISTS artifacts (
                run_id TEXT NOT NULL REFERENCES runs(id), name TEXT NOT NULL,
                size INTEGER NOT NULL, media_type TEXT NOT NULL,
                PRIMARY KEY(run_id,name)
            );
        ''')

    def close(self):
        """Release the database connection; repeated close calls are harmless."""
        with self._lock:
            self._db.close()

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield
            except BaseException:
                self._db.rollback()
                raise
            else:
                self._db.commit()

    def _row(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise KeyError(run_id)
        row = self._db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return row

    @staticmethod
    def _run(row):
        fields = ('id', 'prompt', 'workspace', 'status', 'created_at', 'updated_at', 'mode', 'error')
        result = {name: row[name] for name in fields}
        result['limits'] = json.loads(row['limits'])
        result['checkpoint'] = json.loads(row['checkpoint']) if row['checkpoint'] else None
        return result

    def _event(self, run_id, kind, data, now):
        encoded = _json(data)
        cursor = self._db.execute('INSERT INTO events(run_id,type,data,created_at) VALUES(?,?,?,?)',
                                  (run_id, kind, encoded, now))
        return {'id': cursor.lastrowid, 'run_id': run_id, 'type': kind,
                'data': json.loads(encoded), 'created_at': now}

    def create(self, prompt, workspace, request_id, limits=None, mode='live'):
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 1_048_576:
            raise ValueError('Prompt must be nonempty and at most 1048576 characters')
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256:
            raise ValueError('request_id must be nonempty and at most 256 characters')
        if not isinstance(workspace, (str, os.PathLike)) or not Path(workspace).is_absolute():
            raise ValueError('Workspace must be an absolute path')
        workspace = str(Path(workspace).expanduser().resolve())
        if mode not in ('live', 'test'):
            raise ValueError('Mode must be live or test')
        if limits is None:
            limits = {}
        if not isinstance(limits, dict):
            raise ValueError('Limits must be a JSON object')
        encoded_limits = _json(limits, 65_536)
        fingerprint = hashlib.sha256(_json([prompt, workspace, limits, mode], 4_194_304).encode()).hexdigest()
        with self._transaction():
            old = self._db.execute('SELECT * FROM runs WHERE request_id=?', (request_id,)).fetchone()
            if old is not None:
                if old['fingerprint'] != fingerprint:
                    raise ValueError('request_id already exists with different arguments')
                return self._run(old)
            run_id, now = uuid.uuid4().hex, time.time()
            self._db.execute('''INSERT INTO runs
                (id,request_id,fingerprint,prompt,workspace,status,created_at,updated_at,limits,mode)
                VALUES(?,?,?,?,?,'queued',?,?,?,?)''',
                (run_id, request_id, fingerprint, prompt, workspace, now, now, encoded_limits, mode))
            self._event(run_id, 'status', {'status': 'queued'}, now)
            return self._run(self._row(run_id))

    def get(self, run_id):
        with self._lock:
            return self._run(self._row(run_id))

    def list_runs(self, limit=100):
        limit = _page_limit(limit, 100)
        with self._lock:
            return [self._run(row) for row in self._db.execute(
                'SELECT * FROM runs ORDER BY created_at DESC,rowid DESC LIMIT ?', (limit,))]

    def transition(self, run_id, status, detail=None):
        if not isinstance(status, str) or status not in _TRANSITIONS:
            raise ValueError('Unknown run status')
        if detail is not None and (not isinstance(detail, str) or len(detail) > 65_536):
            raise ValueError('Transition detail must be a string of at most 65536 characters')
        with self._transaction():
            old = self._row(run_id)
            if status == old['status']:
                return self._run(old)
            if status not in _TRANSITIONS[old['status']]:
                raise ValueError(f'Illegal run transition: {old["status"]} -> {status}')
            now = time.time()
            error = detail if status in ('failed', 'uncertain') else None
            self._db.execute('UPDATE runs SET status=?,updated_at=?,error=? WHERE id=?',
                             (status, now, error, run_id))
            self._event(run_id, 'status', {'status': status, 'detail': detail}, now)
            return self._run(self._row(run_id))

    def append_event(self, run_id, type, data):
        if not isinstance(type, str) or not type or len(type) > 128:
            raise ValueError('Event type must be a nonempty string of at most 128 characters')
        with self._transaction():
            self._row(run_id)
            now = time.time()
            event = self._event(run_id, type, data, now)
            self._db.execute('UPDATE runs SET updated_at=? WHERE id=?', (now, run_id))
            return event

    def events(self, run_id, after=0, limit=200):
        if not isinstance(after, int) or isinstance(after, bool) or after < 0 or after > 2**63 - 1:
            raise ValueError('Event cursor must be a nonnegative signed 64-bit integer')
        limit = _page_limit(limit, 200)
        with self._lock:
            self._row(run_id)
            rows = self._db.execute('SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id LIMIT ?',
                                    (run_id, after, limit)).fetchall()
            return [{'id': r['id'], 'run_id': r['run_id'], 'type': r['type'],
                     'data': json.loads(r['data']), 'created_at': r['created_at']} for r in rows]

    def checkpoint(self, run_id, payload):
        if not isinstance(payload, dict):
            raise ValueError('Checkpoint must be a JSON object')
        encoded = _json(payload)
        with self._transaction():
            self._row(run_id)
            self._db.execute('UPDATE runs SET checkpoint=?,updated_at=? WHERE id=?',
                             (encoded, time.time(), run_id))
            return json.loads(encoded)

    @staticmethod
    def _name(name):
        if (not isinstance(name, str) or not name or len(name) > 180 or name in ('.', '..')
                or name[-1] in '. ' or any(ord(c) < 32 or c in '/\\:<>"|?*' for c in name)
                or _RESERVED.match(name)):
            raise ValueError('Artifact name must be a portable filename without path components')
        return name

    def _artifact_path(self, run_id, name, create=False):
        self._row(run_id)
        self._name(name)
        directory = self.root / 'artifacts' / run_id
        # Resolve all ancestors and the leaf before trusting an existing directory or symlink.
        if directory.resolve() != directory:
            raise ValueError('Artifact directory is redirected by a symlink or junction')
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        target = directory / name
        if not target.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Artifact path escapes its run directory')
        if target.is_symlink():
            raise ValueError('Artifact symlinks are not supported')
        return target

    def artifact(self, run_id, name, content, media_type='text/plain'):
        if isinstance(content, str):
            content = content.encode('utf-8')
        if not isinstance(content, bytes):
            raise ValueError('Artifact content must be bytes or a string')
        if (not isinstance(media_type, str) or not media_type or len(media_type) > 256
                or any(ord(c) < 32 for c in media_type)):
            raise ValueError('Invalid artifact media type')
        with self._transaction():
            target = self._artifact_path(run_id, name, create=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.artifact-', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Recheck after writing: an existing symlink must never redirect the output.
                self._artifact_path(run_id, name)
                os.replace(temporary, target)
                self._db.execute('''INSERT INTO artifacts(run_id,name,size,media_type) VALUES(?,?,?,?)
                    ON CONFLICT(run_id,name) DO UPDATE SET size=excluded.size,media_type=excluded.media_type''',
                    (run_id, name, len(content), media_type))
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return {'name': name, 'size': len(content), 'media_type': media_type}

    def artifact_path(self, run_id, name):
        """Return a validated path only for a registered artifact that still exists."""
        with self._lock:
            target = self._artifact_path(run_id, name)
            known = self._db.execute('SELECT 1 FROM artifacts WHERE run_id=? AND name=?', (run_id, name)).fetchone()
            if known is None or not target.is_file():
                raise KeyError(name)
            return target

    def artifacts(self, run_id):
        with self._lock:
            self._row(run_id)
            return [dict(row) for row in self._db.execute(
                'SELECT name,size,media_type FROM artifacts WHERE run_id=? ORDER BY name', (run_id,))]

    def recover(self):
        """Mark interrupted execution uncertain. This method never schedules work."""
        with self._transaction():
            rows = self._db.execute("SELECT id FROM runs WHERE status IN ('running','waiting_model','recovering')").fetchall()
            result = []
            for row in rows:
                run_id, now = row['id'], time.time()
                detail = 'Execution was interrupted; inspect receipts and workspace before explicit resume'
                self._db.execute("UPDATE runs SET status='uncertain',error=?,updated_at=? WHERE id=?",
                                 (detail, now, run_id))
                self._event(run_id, 'recovery', {'status': 'uncertain', 'detail': detail}, now)
                result.append(self._run(self._row(run_id)))
            return result
