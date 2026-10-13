"""Owner-local POSIX PTYs with bounded binary output and durable stdin IDs."""
from __future__ import annotations
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import sqlite3
import struct
import subprocess
import sys
import threading
import time

def android_backend(mode):
    if mode not in ('app','system','root','termux'):raise ValueError('Unknown shell mode')
    if not Path('/system/bin/sh').is_file():raise RuntimeError('Android backend unavailable')
    env={'PATH':'/system/bin:/system/xbin','TERM':'xterm-256color','LANG':'C.UTF-8','HOME':'/data/local/tmp','TMPDIR':'/data/local/tmp'}
    env.update({key:value for key,value in os.environ.items() if key in ('ANDROID_ROOT','ANDROID_DATA','ANDROID_RUNTIME_ROOT','ANDROID_ART_ROOT','ANDROID_TZDATA_ROOT','ANDROID_I18N_ROOT','BOOTCLASSPATH','DEX2OATBOOTCLASSPATH','SYSTEMSERVERCLASSPATH')})
    own_uid=os.geteuid()
    if mode!='app' and own_uid!=0:raise PermissionError('Selected shell requires explicitly selected root mode')
    uid=own_uid if mode=='app' else 2000 if mode=='system' else 0
    if mode=='app':env.update(HOME=os.environ.get('RELAYKITE_BASE',os.environ.get('HOME','/data/local/tmp')),TMPDIR=os.environ.get('TMPDIR','/data/local/tmp'))
    shell='/system/bin/sh'
    if mode=='termux':
        from runtime_paths import MODE
        if MODE!='root-termux':raise PermissionError('Termux backend requires root+Termux installation mode')
        prefix=Path('/data/data/com.termux/files/usr')
        if not (prefix/'bin/bash').is_file():raise RuntimeError('Termux backend unavailable')
        uid=Path('/data/data/com.termux').stat().st_uid
        shell=str(prefix/'bin/bash')
        env.update(PATH=str(prefix/'bin')+':/system/bin',LD_LIBRARY_PATH=str(prefix/'lib'),HOME='/data/data/com.termux/files/home',TMPDIR=str(prefix/'tmp'))
    if os.geteuid()!=0 and os.geteuid()!=uid:raise PermissionError('Selected UID requires the authorized root executor')
    return [shell],env,uid if os.geteuid()==0 else None

def generation(pid):
    try:return int((Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19])
    except (OSError,IndexError,ValueError):return None

class TerminalManager:
    def __init__(self,path,*,backend=android_backend,max_output_bytes=1024*1024,max_sessions=8):
        if os.name=='nt':raise RuntimeError('POSIX PTY backend unavailable on Windows')
        if type(max_output_bytes)!=int or not 1024<=max_output_bytes<=1024*1024:raise ValueError('Invalid output cap')
        if type(max_sessions)!=int or not 1<=max_sessions<=8:raise ValueError('Invalid terminal limit')
        path=Path(path).absolute()
        if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Journal symlink rejected')
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        import fcntl
        self.instance=(path.parent/'terminal-manager.lock').open('a+b')
        try:fcntl.flock(self.instance.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:self.instance.close();raise RuntimeError('Another PTY manager owns this state') from None
        self.backend=backend;self.cap=min(max_output_bytes,128*1024);self.limit=max_sessions;self.lock=threading.RLock();self.active={};self.closed=False
        self.db=sqlite3.connect(path,check_same_thread=False,timeout=10);os.chmod(path,0o600)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS terminal_sessions (id TEXT PRIMARY KEY,request_id TEXT UNIQUE,fingerprint TEXT,status TEXT,pid INTEGER,generation INTEGER,output BLOB,total INTEGER,exit_code INTEGER)')
        self.db.execute('CREATE TABLE IF NOT EXISTS terminal_inputs (id TEXT PRIMARY KEY,terminal TEXT,fingerprint TEXT,status TEXT,written INTEGER)')
        for pid,born in self.db.execute("SELECT pid,generation FROM terminal_sessions WHERE status='running'").fetchall():
            if pid is None or born is None or generation(pid)!=born:continue
            try:
                if os.getpgid(pid)!=pid:continue
                os.killpg(pid,signal.SIGTERM)
                until=time.monotonic()+2
                while generation(pid)==born and time.monotonic()<until:
                    state=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[0]
                    if state=='Z':break
                    time.sleep(.05)
                if generation(pid)==born:
                    state=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[0]
                    if state!='Z' and os.getpgid(pid)==pid:os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError:pass
        # Preserve old receipts and never reopen a command after restart.
        self.db.execute("UPDATE terminal_sessions SET status='uncertain' WHERE status IN ('starting','running')")
        self.db.execute("UPDATE terminal_inputs SET status='uncertain' WHERE status='started'");self.db.commit()

    def open(self,request_id,*,mode='system',cwd=None,command=None,timeout_seconds=1800):
        if not isinstance(request_id,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',request_id):raise ValueError('Stable request ID required')
        if mode not in ('app','system','root','termux'):raise ValueError('Unknown shell mode')
        if cwd is None:cwd=os.environ.get('RELAYKITE_BASE',os.environ.get('HOME','/data/local/tmp')) if mode=='app' else '/data/local/tmp'
        if not isinstance(cwd,str) or not Path(cwd).is_absolute() or '\0' in cwd:raise ValueError('Absolute cwd required')
        if command is not None and (not isinstance(command,str) or not command.strip() or len(command)>65536 or '\0' in command):raise ValueError('Invalid command')
        if type(timeout_seconds)!=int or not 1<=timeout_seconds<=3600:raise ValueError('Timeout must be 1..3600')
        fingerprint=hashlib.sha256(json.dumps([mode,cwd,command,timeout_seconds]).encode()).hexdigest()
        sid=hashlib.sha256(request_id.encode()).hexdigest()[:32]
        with self.lock:
            old=self.db.execute('SELECT fingerprint FROM terminal_sessions WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old[0]!=fingerprint:raise ValueError('Request ID reused with different arguments')
                return self._info(sid)
            if self.closed:raise RuntimeError('Terminal manager is closed')
            if len(self.active)>=self.limit:raise RuntimeError('Terminal capacity reached')
            if self.db.execute('SELECT count(*) FROM terminal_sessions').fetchone()[0]>=1000:raise RuntimeError('Receipt capacity reached')
            argv,env,uid=self.backend(mode)
            if command is None:argv=argv+['-i']
            else:argv=argv+['-c',command+'\nrelaykite_exit=$?; wait; exit "$relaykite_exit"']
            self.db.execute("INSERT INTO terminal_sessions VALUES(?,?,?,'starting',NULL,NULL,?,0,NULL)",(sid,request_id,fingerprint,b''));self.db.commit()
            master,slave=os.openpty()
            try:
                if uid is not None:os.fchown(slave,uid,uid)
                bootstrap_env={key:value for key,value in os.environ.items() if key in ('PATH','LD_LIBRARY_PATH','PYTHONHOME','TMPDIR','HOME','SSL_CERT_FILE')}
                bootstrap_env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='')
                # The terminal session is independent from RPC descriptors.
                launcher=[sys.executable,str(Path(__file__).with_name('_pty_exec.py')),json.dumps([argv,env,uid])]
                proc=subprocess.Popen(launcher,stdin=slave,stdout=slave,stderr=slave,cwd=cwd,env=bootstrap_env,start_new_session=True,close_fds=True)
            except Exception:
                os.close(master);self.db.execute("UPDATE terminal_sessions SET status='failed' WHERE id=?",(sid,));self.db.commit();raise
            finally:os.close(slave)
            born=generation(proc.pid)
            self.db.execute("UPDATE terminal_sessions SET status='running',pid=?,generation=? WHERE id=?",(proc.pid,born,sid));self.db.commit()
            item={'process':proc,'fd':master,'generation':born,'deadline':time.monotonic()+timeout_seconds,'stopped':False}
            self.active[sid]=item
            item['thread']=threading.Thread(target=self._collect,args=(sid,item),name='relaykite-pty-'+sid[:8],daemon=True)
            item['thread'].start()
            return self._info(sid)

    def _info(self,sid):
        row=self.db.execute('SELECT status,pid,exit_code,total FROM terminal_sessions WHERE id=?',(sid,)).fetchone()
        if not row:raise ValueError('Terminal not found')
        return {'terminal_id':sid,'status':row[0],'pid':row[1],'running':row[0]=='running','exit_code':row[2],'next_cursor':row[3]}

    def list(self):
        with self.lock:return [self._info(row[0]) for row in self.db.execute('SELECT id FROM terminal_sessions ORDER BY rowid DESC LIMIT 100').fetchall()]

    def _append(self,sid,data):
        with self.lock:
            raw,total=self.db.execute('SELECT output,total FROM terminal_sessions WHERE id=?',(sid,)).fetchone()
            self.db.execute('UPDATE terminal_sessions SET output=?,total=? WHERE id=?',((raw+data)[-self.cap:],total+len(data),sid));self.db.commit()
            retained=0
            for old_sid,size in self.db.execute('SELECT id,length(output) FROM terminal_sessions ORDER BY rowid DESC').fetchall():
                retained+=size or 0
                if retained>1024*1024:self.db.execute('UPDATE terminal_sessions SET output=? WHERE id=?',(b'',old_sid))
            self.db.commit()

    def _signal(self,item,sig):
        proc=item['process']
        if proc.poll() is not None:return
        if item['generation'] is None or generation(proc.pid)!=item['generation'] or os.getpgid(proc.pid)!=proc.pid:
            raise RuntimeError('Process generation/group mismatch; signal refused')
        os.killpg(proc.pid,sig)

    def _collect(self,sid,item):
        proc=item['process'];fd=item['fd'];timed_out=False
        try:
            while True:
                if time.monotonic()>=item['deadline'] and proc.poll() is None:
                    timed_out=True
                    self._signal(item,signal.SIGKILL)
                ready,_,_=select.select([fd],[],[],.1)
                if ready:
                    try:data=os.read(fd,65536)
                    except OSError as exc:
                        if exc.errno==errno.EIO:break
                        raise
                    if not data:break
                    self._append(sid,data)
                elif proc.poll() is not None:break
            code=proc.wait(timeout=5)
            with self.lock:
                state='terminated' if timed_out or item['stopped'] else 'exited'
                self.db.execute('UPDATE terminal_sessions SET status=?,exit_code=? WHERE id=?',(state,code,sid));self.db.commit()
        except Exception:
            try:self._signal(item,signal.SIGKILL);proc.wait(timeout=5)
            except (OSError,RuntimeError,subprocess.TimeoutExpired):pass
            with self.lock:self.db.execute("UPDATE terminal_sessions SET status='uncertain' WHERE id=?",(sid,));self.db.commit()
        finally:
            with self.lock:
                os.close(fd);self.active.pop(sid,None)

    def read(self,sid,cursor=0,max_bytes=65536):
        if type(cursor)!=int or cursor<0 or type(max_bytes)!=int or not 1<=max_bytes<=65536:raise ValueError('Invalid read cursor/limit')
        with self.lock:
            out=self._info(sid)
            raw,total=self.db.execute('SELECT output,total FROM terminal_sessions WHERE id=?',(sid,)).fetchone()
            if cursor>total:raise ValueError('Cursor is beyond produced output')
            oldest=total-len(raw);start=max(cursor,oldest);chunk=raw[start-oldest:start-oldest+max_bytes]
            return {**out,'base64':base64.b64encode(chunk).decode(),'text':chunk.decode('utf-8','replace'),'oldest_cursor':oldest,'next_cursor':start+len(chunk),'gap':cursor<oldest,'eof':sid not in self.active}

    def write(self,sid,request_id,payload):
        if not isinstance(request_id,str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}',request_id):raise ValueError('Stable stdin request ID required')
        data=base64.b64decode(payload,validate=True)
        if not 1<=len(data)<=65536:raise ValueError('stdin must be 1..65536 bytes')
        fingerprint=hashlib.sha256(data).hexdigest()
        with self.lock:
            row=self.db.execute('SELECT terminal,fingerprint,status,written FROM terminal_inputs WHERE id=?',(request_id,)).fetchone()
            if row:
                if row[:2]!=(sid,fingerprint):raise ValueError('stdin ID reused with different input')
                return {'request_id':request_id,'status':row[2],'written':row[3]}
            item=self.active.get(sid)
            if item is None or item['process'].poll() is not None:raise ValueError('Terminal is not running')
            if self.db.execute('SELECT count(*) FROM terminal_inputs').fetchone()[0]>=10000:raise RuntimeError('stdin receipt capacity reached')
            self.db.execute("INSERT INTO terminal_inputs VALUES(?,?,?,'started',0)",(request_id,sid,fingerprint));self.db.commit()
            count=0;status='completed'
            try:
                while count<len(data):
                    _,ready,_=select.select([],[item['fd']],[],1)
                    if not ready:raise TimeoutError('PTY input blocked')
                    count+=os.write(item['fd'],data[count:])
            except Exception:status='uncertain'
            self.db.execute('UPDATE terminal_inputs SET status=?,written=? WHERE id=?',(status,count,request_id));self.db.commit()
            return {'request_id':request_id,'status':status,'written':count}

    def resize(self,sid,rows,columns):
        if type(rows)!=int or type(columns)!=int or not 1<=rows<=300 or not 1<=columns<=500:raise ValueError('Invalid terminal dimensions')
        import fcntl,termios
        with self.lock:
            item=self.active.get(sid)
            if item is None:raise ValueError('Terminal is not running')
            fcntl.ioctl(item['fd'],termios.TIOCSWINSZ,struct.pack('HHHH',rows,columns,0,0))
            return {'terminal_id':sid,'rows':rows,'columns':columns}

    def stop(self,sid):
        with self.lock:
            item=self.active.get(sid)
            if item is None:return self._info(sid)
            item['stopped']=True;self._signal(item,signal.SIGTERM)
            thread=item['thread']
        thread.join(2)
        if thread.is_alive():
            with self.lock:
                if sid in self.active:self._signal(item,signal.SIGKILL)
            thread.join(5)
        if thread.is_alive():raise RuntimeError('Terminal outcome is uncertain; cleanup not confirmed')
        with self.lock:return self._info(sid)

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True;ids=list(self.active)
        for sid in ids:self.stop(sid)
        self.db.close();self.instance.close()
