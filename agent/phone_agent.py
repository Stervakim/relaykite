"""Private outbound queue worker. Standard-library only; no PC or model API key."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import native_phone
from network_route import choose_proxy

MAX_JOURNAL=5*1024*1024
MAX_RESULT=4*1024*1024-8192
RESULT_RETENTION_SECONDS=900


class BoundedStartupWriter:
    """Bound startup diagnostics shared by stdout/stderr, separate from job logs."""
    def __init__(self,stream,budget):
        self.stream=stream
        self.budget=budget

    def write(self,value):
        raw=value.encode('utf-8','replace')[:self.budget[0]]
        text=raw.decode('utf-8','ignore')
        self.budget[0]-=len(text.encode('utf-8'))
        if text: self.stream.write(text)
        return len(value)

    def flush(self): self.stream.flush()
    def isatty(self): return False
    @property
    def encoding(self): return 'utf-8'


def error_result(message: str) -> dict:
    return {'content':[{'type':'text','text':message}],'isError':True}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        # Never forward agent credentials to a redirect target.
        return None


class Relay:
    def __init__(self,config:dict):
        parsed=urllib.parse.urlparse(config['relay_url'])
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('relay_url must be an HTTPS base URL without credentials/query/fragment')
        token=config['agent_token']
        if not isinstance(token,str) or len(token)<32 or '\n' in token or '\r' in token:
            raise ValueError('A strong private agent credential of at least 32 characters is required')
        self.base=config['relay_url'].rstrip('/')
        self.headers={'Authorization':'Bearer '+token,'Accept':'application/json'}
        if config.get('sites_authorization'):
            self.headers['OAI-Sites-Authorization']=config['sites_authorization']
        self.configured_proxy=config.get('outbound_proxy','')
        proxy=choose_proxy(self.configured_proxy)
        self.selected_proxy=proxy
        # Explicit local VLESS HTTP proxy overrides ambient shell proxy settings.
        # A blank value preserves the default urllib environment behavior.
        proxy_handler=urllib.request.ProxyHandler({'https':proxy}) if proxy else urllib.request.ProxyHandler({} if self.configured_proxy else None)
        self.opener=urllib.request.build_opener(NoRedirect(),proxy_handler,
                                                 urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def request(self,path:str,body:dict|None=None):
        proxy=choose_proxy(self.configured_proxy)
        if proxy!=self.selected_proxy:
            proxy_handler=urllib.request.ProxyHandler({'https':proxy} if proxy else ({} if self.configured_proxy else None))
            self.opener=urllib.request.build_opener(NoRedirect(),proxy_handler,urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            self.selected_proxy=proxy
        headers=self.headers.copy()
        data=None if body is None else json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if data is not None:
            if len(data)>4*1024*1024: raise ValueError('Result exceeds the 4 MiB relay request limit')
            headers['Content-Type']='application/json'
        request=urllib.request.Request(self.base+path,data=data,headers=headers,method='GET' if body is None else 'POST')
        with self.opener.open(request,timeout=20) as response:
            if response.status==204: return None
            raw=response.read(16*1024*1024+1)
            if len(raw)>16*1024*1024: raise ValueError('Relay response is too large')
            return json.loads(raw) if raw else None

    def next_job(self):
        response=self.request('/agent/jobs/next')
        return None if response is None else response.get('job')

    def result(self,ident:str,result:dict,status:str):
        return self.request('/agent/jobs/'+urllib.parse.quote(ident,safe='')+'/result',{'result':result,'status':status})


class Journal:
    def __init__(self,directory:Path):
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(directory,0o700)
        self.path=directory/'jobs.sqlite3'
        self.db=sqlite3.connect(self.path)
        os.chmod(self.path,0o600)
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,expires REAL,args_hash TEXT,status TEXT,result TEXT,updated REAL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS delivered (id TEXT PRIMARY KEY)')
        self.db.execute('CREATE TABLE IF NOT EXISTS tool_metrics (tool TEXT PRIMARY KEY,calls INTEGER,errors INTEGER,total_ms REAL,max_ms REAL,first_at REAL,last_at REAL)')
        self.known_tools={definition['name'] for definition in native_phone.tool_definitions()}
        # The previous process might have performed an action before crashing.
        uncertain=json.dumps(error_result('Previous process stopped during this job. Outcome is uncertain; inspect the device before deciding what to do.'))
        self.db.execute("UPDATE jobs SET status='uncertain',result=? WHERE status='started'",(uncertain,))
        self.db.commit()
        self.compact()

    def compact(self):
        # Execution deadlines and result delivery are separate. Keep expired
        # outcomes for the relay's 15-minute recovery window, within the size
        # cap. Purged jobs still cannot run after their original deadline.
        now=time.time()
        self.db.execute('DELETE FROM jobs WHERE expires<? AND updated<?',
                        (now,now-RESULT_RETENTION_SECONDS))
        self.db.execute('DELETE FROM delivered WHERE id NOT IN (SELECT id FROM jobs)')
        tombstone=json.dumps(error_result('Cached output was compacted. This action already ran or has an uncertain outcome; automatic re-execution remains blocked.'))
        self.db.execute("UPDATE jobs SET result=?,status='uncertain' WHERE status!='started' AND id NOT IN (SELECT id FROM jobs ORDER BY updated DESC LIMIT 100) AND (status!='uncertain' OR length(result)>?)",(tombstone,len(tombstone)))
        self.db.commit()
        # Free pages can be reused by subsequent jobs. Rebuild only when the
        # file exceeds its budget; durable commits and replay protection stay
        # on every action's path.
        if self.path.stat().st_size>MAX_JOURNAL:
            self.db.execute('VACUUM')
        while self.path.stat().st_size>MAX_JOURNAL:
            row=self.db.execute("SELECT id FROM jobs WHERE status!='started' AND length(result)>? ORDER BY updated ASC LIMIT 1",(len(tombstone),)).fetchone()
            if not row: raise RuntimeError('Journal full; refusing to run an unjournaled action')
            self.db.execute("UPDATE jobs SET result=?,status='uncertain' WHERE id=?",(tombstone,row[0]))
            self.db.commit()
            self.db.execute('VACUUM')

    def get(self,ident):
        row=self.db.execute('SELECT args_hash,status,result FROM jobs WHERE id=?',(ident,)).fetchone()
        return None if row is None else {'args_hash':row[0],'status':row[1],'result':json.loads(row[2]) if row[2] else None}

    def start(self,ident,expires,fingerprint):
        self.db.execute("INSERT INTO jobs VALUES(?,?,?,'started',NULL,?)",(ident,expires,fingerprint,time.time()))
        self.db.commit()  # Must be durable before any Android command.

    def pending(self):
        return [(ident,json.loads(raw),status) for ident,raw,status in self.db.execute("SELECT id,result,status FROM jobs WHERE status IN ('completed','uncertain') AND result IS NOT NULL AND id NOT IN (SELECT id FROM delivered) ORDER BY updated")]

    def delivered(self,ident):
        self.db.execute('INSERT OR IGNORE INTO delivered VALUES (?)',(ident,))
        self.db.commit()

    def finish(self,ident,result,status='completed',tool=None,duration_ms=None):
        payload=json.dumps(result,ensure_ascii=False,separators=(',',':'))
        if len(payload.encode('utf-8'))>MAX_RESULT:
            result=error_result('Tool output exceeds transport/cache limits. Use a bounded read or read_ui instead of a large screenshot.')
            payload=json.dumps(result)
        self.db.execute('UPDATE jobs SET status=?,result=?,updated=? WHERE id=?',(status,payload,time.time(),ident))
        self.db.commit()
        # Aggregate only fixed tool names and timing, never arguments/results.
        # Optional observability must not invalidate a durably saved outcome.
        if tool in self.known_tools and duration_ms is not None:
            try:
                now=time.time()
                self.db.execute('INSERT INTO tool_metrics VALUES(?,1,?,?,?,?,?) ON CONFLICT(tool) DO UPDATE SET calls=calls+1,errors=errors+excluded.errors,total_ms=total_ms+excluded.total_ms,max_ms=max(max_ms,excluded.max_ms),last_at=excluded.last_at',
                                (tool,int(bool(result.get('isError')) or status=='uncertain'),duration_ms,duration_ms,now,now))
                self.db.commit()
            except sqlite3.Error:
                self.db.rollback()
        self.compact()
        return result


def execute_job(job:dict,journal:Journal,executor=native_phone.dispatch,disabled=lambda:False):
    ident=job.get('id')
    if not isinstance(ident,str) or not 1<=len(ident)<=100 or not all(c.isalnum() or c in '_-' for c in ident):
        raise ValueError('Invalid job id')
    tool=job.get('tool')
    arguments=job.get('arguments')
    expires=job.get('expires_at')
    if not isinstance(tool,str) or not isinstance(arguments,dict) or type(expires) not in (int,float) or not math.isfinite(expires):
        raise ValueError('Invalid job shape')
    fingerprint=hashlib.sha256(json.dumps({'tool':tool,'arguments':arguments},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    previous=journal.get(ident)
    if previous:
        if previous['args_hash']!=fingerprint:
            return ident,error_result('Job ID was reused with different arguments; action blocked.'),'uncertain'
        if previous['status']=='started':
            return ident,error_result('This job may already have executed; automatic re-execution is blocked.'),'uncertain'
        return ident,previous['result'],previous['status']
    now=time.time()
    if expires<=now or expires>now+300:
        # Persist the rejection too: the worker delivers from pending(), not
        # from this return value. This record represents no Android execution.
        journal.compact()
        journal.start(ident,now,fingerprint)
        result=error_result('Job expired or deadline is invalid; no action was executed.')
        return ident,journal.finish(ident,result,'uncertain'),'uncertain'
    if disabled(): raise InterruptedError('Phone agent is disabled')
    journal.compact()
    journal.start(ident,expires,fingerprint)
    started=time.monotonic()
    try:
        result=executor(tool,arguments)
    except Exception:
        result=error_result('Executor stopped unexpectedly. Outcome is uncertain; inspect the device before retrying.')
        return ident,journal.finish(ident,result,'uncertain',tool,(time.monotonic()-started)*1000),'uncertain'
    return ident,journal.finish(ident,result,tool=tool,duration_ms=(time.monotonic()-started)*1000),'completed'


def acquire_instance_lock(state:Path):
    # Linux/Android flock is released by the kernel when the process exits.
    # Keep the same lock file; unlinking it would permit a second inode/owner.
    import fcntl
    handle=(state/'agent.lock').open('a+b')
    try:
        os.chmod(state/'agent.lock',0o600)
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except Exception:
        handle.close()
        raise RuntimeError('Another phone agent owns this state directory; refusing a second worker') from None
    return handle


def flush_results(relay,journal):
    for ident,result,status in journal.pending():
        try:
            receipt=relay.result(ident,result,status)
        except urllib.error.HTTPError as exc:
            if exc.code not in (404,410):
                raise
            exc.close()
            journal.delivered(ident)
            continue
        if not isinstance(receipt,dict) or receipt.get('ok') is not True:
            raise ValueError('Relay did not acknowledge result persistence')
        journal.delivered(ident)


def run_agent(config:dict,state:Path):
    logger=logging.getLogger('phone-agent')
    logger.setLevel(logging.INFO)
    handler=RotatingFileHandler(state/'agent.log',maxBytes=1024*1024,backupCount=4,encoding='utf-8')
    logger.addHandler(handler)
    os.chmod(state/'agent.log',0o600)
    relay=Relay(config)
    journal=Journal(state)
    disable_file=Path(config['disable_file']) if config.get('disable_file') else None
    stop=False
    def terminate(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,terminate)
    signal.signal(signal.SIGINT,terminate)
    def disabled(): return stop or (disable_file is not None and disable_file.exists())
    delay=max(1,min(30,float(config.get('poll_seconds',3))))
    retry_delay=delay
    logger.info('Agent started; no network listener; authenticated outbound polling only')
    try:
        while not disabled():
            try:
                flush_results(relay,journal)
                job=relay.next_job()
                retry_delay=delay  # A successful poll restores normal responsiveness.
                if job and not disabled():
                    ident,result,status=execute_job(job,journal,disabled=disabled)
                    # Local result is cached first; if POST fails the next delivery
                    # resubmits the cache and never repeats the root action.
                    flush_results(relay,journal)
                    logger.info('Job %s: %s',ident,status)
                    continue
            except urllib.error.HTTPError as exc:
                logger.warning('Relay HTTP status %s',exc.code)
                exc.close()
                retry_delay=min(30,retry_delay*2)
            except InterruptedError:
                break
            except Exception as exc:
                logger.warning('Worker event: %s',type(exc).__name__)
                retry_delay=min(30,retry_delay*2)
            for _ in range(int(retry_delay*10)):
                if disabled(): break
                time.sleep(.1)
    finally:
        journal.db.close()
        logger.info('Agent stopped; no further jobs will execute')
        logger.removeHandler(handler)
        handler.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    os.umask(0o077)
    # The distribution validates fixed private paths and rejects symlink storage.
    from configure import BASE, inspect_storage, read_config
    inspect_storage(BASE)
    if args.config != BASE/'config.json':
        raise ValueError('Use the installation’s private configuration path')
    config=read_config(args.config)
    os.chmod(args.config,0o600)
    state=Path(config.get('state_dir',str(Path.home()/'.mini-codex'/'agent')))
    if config.get('memory_dir'): os.environ['PHONE_MEMORY_DIR']=config['memory_dir']
    state.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(state,0o700)
    # Acquire before opening the job journal or starting any queue operation.
    with acquire_instance_lock(state):
        pid_path=BASE/'agent.pid'
        pid_path.write_text(str(os.getpid())+'\n',encoding='ascii')
        os.chmod(pid_path,0o600)
        try:
            run_agent(config,state)
        finally:
            if not pid_path.is_symlink() and pid_path.read_text(encoding='ascii').strip()==str(os.getpid()):
                pid_path.unlink()


if __name__=='__main__':
    budget=[64*1024]
    sys.stdout=BoundedStartupWriter(sys.stdout,budget)
    sys.stderr=BoundedStartupWriter(sys.stderr,budget)
    try:
        main()
    except Exception as exc:
        # Configuration values and exception text can contain credentials.
        print('Agent failed: '+type(exc).__name__,file=sys.stderr)
        sys.exit(1)

