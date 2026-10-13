import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {ExternalMemory,serveExternal} from './codaki-external.mjs';

test('shipped original-store adapter preserves versions and authoritative scope',async()=>{
 const root=mkdtempSync(join(tmpdir(),'codaki-release-'));const memory=new ExternalMemory(root,'release-test');
 try{
  const payload={title:'Termux recovery',content:'проверенная память codakidevicewindows',memory:{device:'android',status:'verified',source:'release smoke'}};
  const saved=await memory.save(payload);assert.equal(saved.version,1);
  assert.equal((await memory.save(payload)).version,1);
  assert.equal((await memory.search('память',1,{device:'windows'})).notes.length,0);
  assert.equal((await memory.search('память',1,{device:'android'})).notes[0].id,saved.id);
  assert.equal(memory.health().llm_enabled,false);
 }finally{memory.close();rmSync(root,{recursive:true,force:true});}
});
test('shipped gateway authenticates and reads a full6KiB record',async()=>{
 const root=mkdtempSync(join(tmpdir(),'codaki-http-release-'));const key='k'.repeat(48);
 const service=await serveExternal(root,{scope:'release-test',key,port:0});
 try{
  const content='я'.repeat(3072),saved=await service.memory.save({title:'full note',content});
  const url='http://127.0.0.1:'+service.port;
  assert.equal((await fetch(url+'/health')).status,401);
  const response=await fetch(url+'/read',{method:'POST',headers:{Authorization:'Bearer '+key},body:JSON.stringify({id:saved.id})});
  assert.equal((await response.json()).notes[0].content,content);
 }finally{await service.stop();rmSync(root,{recursive:true,force:true});}
});
