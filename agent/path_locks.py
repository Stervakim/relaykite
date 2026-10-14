"""Canonical in-process file resource locks shared by dispatch and transfers."""
from contextlib import contextmanager
from pathlib import Path
import threading
import weakref

_guard=threading.RLock();_locks=weakref.WeakValueDictionary()

@contextmanager
def hold(paths):
    keys=sorted({str(Path(p).resolve()) for p in paths})
    with _guard:
        locks=[]
        for key in keys:
            lock=_locks.get(key)
            if lock is None:lock=threading.RLock();_locks[key]=lock
            locks.append(lock)
    for lock in locks:lock.acquire()
    try:yield
    finally:
        for lock in reversed(locks):lock.release()
