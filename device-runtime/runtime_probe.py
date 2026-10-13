"""Owned APK acceptance: run under the actual app UID/SELinux domain."""
import json,os,ssl,sqlite3,subprocess,sys,time,secrets,tempfile,urllib.request,urllib.error
from pathlib import Path
base=Path(os.environ['RELAYKITE_BASE']);native=Path(os.environ['RELAYKITE_NATIVE'])
db=sqlite3.connect(':memory:');db.execute('CREATE VIRTUAL TABLE owned USING fts5(content)');db.execute("INSERT INTO owned VALUES('owned runtime')")
assert db.execute("SELECT count(*) FROM owned WHERE owned MATCH 'runtime'").fetchone()[0]==1;db.close()
node=subprocess.run([str(native/'librelaykite_node.so'),'-e',"const {DatabaseSync}=require('node:sqlite');const d=new DatabaseSync(':memory:');d.exec('CREATE VIRTUAL TABLE own USING fts5(content)');console.log(JSON.stringify({version:process.version,sqlite:true}));"],capture_output=True,text=True,check=True,timeout=15)
shell=subprocess.run(['/system/bin/sh','-c','id -u'],capture_output=True,text=True,check=True,timeout=5)
maps=Path('/proc/self/maps').read_text();domain=Path('/proc/self/attr/current').read_text().strip('\0\n')
result={'version':'0.2.5','uid':os.getuid(),'selinux':domain,'python':sys.version.split()[0],'executable':sys.executable,
        'python_fts5':True,'node':json.loads(node.stdout),'system_shell_uid':int(shell.stdout.strip()),'ca_count':len(ssl.create_default_context().get_ca_certs()),
        'termux_accessible':Path('/data/data/com.termux/files/usr/bin/python').exists(),'termux_mapped':any('com.termux' in line for line in maps.splitlines()),'app_private_base':str(base)}
assert result['uid']>10000 and 'untrusted_app' in domain
assert result['system_shell_uid']==result['uid'] and result['ca_count']>100
assert not result['termux_accessible'] and not result['termux_mapped']
from managed_tools import Runtime,Server
import native_phone as phone
probe=base/'probe';probe.mkdir(exist_ok=True)
runtime=Runtime(probe,phone.dispatch);server=Server(runtime,probe/'managed.sock')
try:
    own=probe/'owned.txt';own.write_text('Свой файл: RelayKite\n')
    rid='app_probe_'+secrets.token_hex(8)
    copied=runtime.invoke('phone_file_copy',{'request_id':rid+'_file','source':str(own),'destination':str(probe/'copy.txt'),'overwrite':True})
    assert (probe/'copy.txt').read_text()==own.read_text()
    terminal=runtime.invoke('phone_command_start',{'request_id':rid+'_pty','command':'id -u; printf "owned-pty"','mode':'app','timeout_seconds':10})
    until=time.monotonic()+10
    while time.monotonic()<until:
        out=runtime.invoke('phone_command_result',{'terminal_id':terminal['terminal_id']})
        if out['eof']:break
        time.sleep(.05)
    assert out['exit_code']==0 and 'owned-pty' in out['text'] and str(os.getuid()) in out['text'],out
    assert runtime.invoke('phone_command_start',{'request_id':rid+'_pty','command':'id -u; printf "owned-pty"','mode':'app','timeout_seconds':10})['terminal_id']==terminal['terminal_id']
    assert phone.dispatch('root_shell',{'command':'id'})['isError']
    result.update(app_pty=True,app_files=True,managed_ipc_same_owner=True,root_denied=True,status_mode=phone.phone_status()['runtime']['mode'])
finally:server.close();runtime.close()
with tempfile.TemporaryDirectory(prefix='owned-memory-proof-',dir=probe) as tmp:
    temporary=Path(tmp);cfg=temporary/'service.json';key=secrets.token_urlsafe(48)
    cfg.write_text(json.dumps({'scope':'relaykite-owned-runtime-probe','key':key,'port':0,'data_dir':str(temporary/'data'),'quota_bytes':16*1024**2}))
    child=subprocess.Popen([str(native/'librelaykite_node.so'),str(Path(__file__).with_name('memory-runtime')/'codaki-external.mjs'),str(cfg)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    try:
        ready=json.loads(child.stdout.readline());url='http://127.0.0.1:'+str(ready['port'])
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(route,body=None,auth=True):
            data=None if body is None else json.dumps(body).encode()
            req=urllib.request.Request(url+route,data=data,headers={'Authorization':'Bearer '+key} if auth else {})
            try:
                with opener.open(req,timeout=5) as response:return json.loads(response.read(65536))
            except urllib.error.HTTPError as error:
                if not auth:raise
                try:detail=json.loads(error.read(8192)).get('error','unknown memory error')
                finally:error.close()
                raise RuntimeError('Owned memory probe: '+str(detail)) from None
        try:request('/health',auth=False)
        except urllib.error.HTTPError as error:
            assert error.code==401;error.close()
        else:raise AssertionError('Memory authentication missing')
        health=request('/health');assert health['engine']=='tencentdb-original-external' and health['fts_available'] and not health['llm_enabled']
        note={'title':'Owned APK memory proof','content':'Сохранение проверено в собственном тестовом хранилище.','memory':{'device':'android','project':'relaykite-acceptance','status':'verified','source':'owned runtime probe'}}
        saved=request('/save',note);assert request('/save',note)['id']==saved['id']
        assert request('/read',{'id':saved['id']})['notes'][0]['content']==note['content']
        assert request('/search',{'query':'Сохранение','limit':3,'filters':{'project':'relaykite-acceptance'}})['notes'][0]['id']==saved['id']
        result.update(original_tencent_memory=True,memory_authentication=True,memory_versions=True)
    finally:
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait()
        child.stdout.close()
print(json.dumps(result))
