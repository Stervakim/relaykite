import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, rmSync,writeFileSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {ExternalMemory, serveExternal} from './external.js';

async function fixture(fn: (m: ExternalMemory, root: string)=>Promise<void>) {
  const root=mkdtempSync(join(tmpdir(),'codaki-memory-'));
  const m=new ExternalMemory(root,'test-owner');
  try {await fn(m,root);} finally {m.close();rmSync(root,{recursive:true,force:true});}
}
test('original Tencent FTS stores and recalls Russian verified facts without network',async()=>fixture(async m=>{
  const previous=globalThis.fetch;globalThis.fetch=async()=>{throw Error('network forbidden');};
  try {
    assert.equal(m.health().engine,'tencentdb-original-external');
    assert.equal(m.health().fts_available,true);
    await m.save({title:'Исправление Termux',content:'Проверено восстановление памяти после обновления',tags:['termux'],memory:{status:'verified',source:'functional-test'}});
    const r=await m.search('ПАМЯТИ обновления');assert.equal(r.notes.length,1);
    assert.equal(r.notes[0].memory.status,'verified');assert.equal(r.notes[0].title,'Исправление Termux');
  } finally {globalThis.fetch=previous;}
}));
test('all four layers are durable and profiles use original file storage',async()=>fixture(async(m,root)=>{
  for(const layer of ['L0','L1','L2','L3'])await m.save({title:'слой '+layer,content:'уникальный контекст '+layer,memory:{layer,source:'test'}});
  for(const layer of ['L0','L1','L2','L3'])assert.equal((await m.search('контекст',5,{layer})).notes[0].memory.layer,layer);
  assert.equal(m.health().notes_count,4);
}));
test('repeat payload is idempotent and changed content increments version',async()=>fixture(async m=>{
  const p={title:'повтор',content:'один'};const a=await m.save(p);const b=await m.save(p);
  assert.equal(a.id,b.id);assert.equal(b.version,1);assert.equal(b.unchanged,true);
  const c=await m.save({...p,content:'два',memory:{expected_version:1}});assert.equal(c.version,2);
  await assert.rejects(m.save({...p,content:'три',memory:{expected_version:1}}),/version conflict/);
}));
test('device and project filters apply before result limits',async()=>fixture(async m=>{
  for(let i=0;i<8;i++)await m.save({title:'PC '+i,content:'общее решение',memory:{device:'windows',project:'other'}});
  await m.save({title:'Android',content:'общее решение',memory:{device:'android',project:'codaki'}});
  assert.equal((await m.search('общее',1,{device:'android',project:'codaki'})).notes[0].title,'Android');
}));
test('user content cannot spoof structured filter markers',async()=>fixture(async m=>{
  await m.save({title:'spoof',content:'collision codakidevicewindows codakilayerL3',memory:{device:'android',layer:'L1'}});
  assert.equal((await m.search('collision',1,{device:'windows'})).notes.length,0);
  assert.equal((await m.search('collision',1,{layer:'L3'})).notes.length,0);
}));
test('status, names, bounds and source validation fail closed',async()=>fixture(async m=>{
  await assert.rejects(m.save({title:'x',content:'x',memory:{status:'verified'}}),/source/);
  await assert.rejects(m.save({title:'x',content:'x',memory:{layer:'../secret'}}),/layer/);
  await assert.rejects(m.save({title:'x',content:'x',memory:{extra:'secret'}}),/unsupported/);
  await assert.rejects(m.search('a',31),/limit/);
  await m.save({title:'old',content:'устаревший рецепт',memory:{status:'superseded'}});
  assert.equal((await m.search('рецепт')).notes.length,0);
}));
test('owner isolation and bounded UTF8 responses',async()=>fixture(async(m,root)=>{
  for(let i=0;i<8;i++)await m.save({title:'бюджет '+i,content:'слово '+('я'.repeat(2500))});
  const r=await m.search('слово',8);assert.ok(Buffer.byteLength(JSON.stringify(r))<=6144);
  const stranger=new ExternalMemory(root,'another-owner');
  try{assert.equal((await stranger.search('слово')).notes.length,0);}finally{stranger.close();}
}));
test('authenticated loopback HTTP gateway rejects unauthorized calls',async()=>{
  const root=mkdtempSync(join(tmpdir(),'codaki-http-'));const service=await serveExternal(root,{scope:'test-owner',key:'k'.repeat(48),port:0});
  try{
    const url='http://127.0.0.1:'+service.port;
    assert.equal((await fetch(url+'/health')).status,401);
    assert.equal((await fetch(url+'/health',{headers:{Authorization:'Bearer '+'k'.repeat(48)}})).status,200);
    assert.equal((await fetch(url+'/save',{method:'POST',body:'{}'})).status,401);
    const r=await fetch(url+'/save',{method:'POST',headers:{Authorization:'Bearer '+'k'.repeat(48)},body:JSON.stringify({title:'HTTP',content:'проверка'})});
    assert.equal(r.status,200);assert.equal((await r.json()).saved,true);
  }finally{await service.stop();rmSync(root,{recursive:true,force:true});}
});
test('read detects tampered immutable blob content',async()=>fixture(async(m,root)=>{
  const r=await m.save({title:'digest',content:'original'});
  const record=m.store.queryL1Records({sessionId:r.id}).find(x=>x.record_id===r.id)!;
  const path=join(root,'files',JSON.parse(record.metadata_json).blob_key);
  const n=JSON.parse(readFileSync(path,'utf8'));n.content='tampered';writeFileSync(path,JSON.stringify(n));
  await assert.rejects(m.read(r.id),/digest/);
}));
test('unsearchable SQLite write is not reported as saved and repeat repairs it',async()=>fixture(async m=>{
  const real=m.store.searchL1Fts.bind(m.store);m.store.searchL1Fts=()=>[];
  await assert.rejects(m.save({title:'index receipt',content:'repairable'}),/FTS/);
  m.store.searchL1Fts=real;
  assert.equal((await m.save({title:'index receipt',content:'repairable'})).version,1);
  assert.equal((await m.search('repairable')).notes.length,1);
}));
test('HTTP read returns complete maximum-size note',async()=>{
  const root=mkdtempSync(join(tmpdir(),'codaki-read-'));const service=await serveExternal(root,{scope:'test-owner',key:'k'.repeat(48),port:0});
  try{
    const content='я'.repeat(3072),r=await service.memory.save({title:'full',content});
    const response=await fetch('http://127.0.0.1:'+service.port+'/read',{method:'POST',headers:{Authorization:'Bearer '+'k'.repeat(48)},body:JSON.stringify({id:r.id})});
    assert.equal((await response.json()).notes[0].content,content);
  }finally{await service.stop();rmSync(root,{recursive:true,force:true});}
});
