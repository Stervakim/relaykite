/** Execute the real TypeScript bridge with local auth/database/phone fixtures. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';

const source = await fs.readFile(new URL('../relay/lib/pc-relay.ts', import.meta.url), 'utf8');
const definitions = JSON.parse(await fs.readFile(new URL('../relay/lib/phone-tools.json', import.meta.url), 'utf8'));
const phoneCalls = [], jobs = new Map();
let user = {userId:'owner', email:'owner@example.com'}, phoneOwner = 'owner', grants = ['codex'];
const link = {id:'pc-owned',inviter:'owner',owner:'pc-owner',capabilities:'[]',last_seen:1000,state:'active'};
const database = {
  async batch() {},
  prepare(sql) {
    let values;
    return {
      bind(...arguments_) { values=arguments_; return this; },
      async run() {
        if(sql.startsWith('INSERT OR IGNORE INTO pc_jobs')) jobs.set(values[2], {id:values[0],link_id:values[1],request_key:values[2],tool:values[3],arguments:values[4],expires_at:values[6],state:'queued',result:null});
      },
      async first() {
        if(sql.includes('FROM pc_links')) return values[0]==='pc-owned' && ['owner','pc-owner'].includes(values[1]) ? {...link,capabilities:JSON.stringify(grants)} : null;
        if(sql.includes('COUNT(*)')) return {n:0};
        if(sql.includes('FROM pc_jobs WHERE request_key=')) return jobs.get(values[0]) || null;
        if(sql.includes('FROM pc_jobs WHERE link_id=')) return [...jobs.values()].find(job=>job.link_id===values[0] && job.id===values[1]) || null;
        return null;
      },
    };
  },
};
const context = vm.createContext({crypto:webcrypto,TextEncoder,Uint8Array,Buffer,setTimeout});
function synthetic(values) {
  return new vm.SyntheticModule(Object.keys(values), function(){for(const [key,value] of Object.entries(values))this.setExport(key,value);},{context});
}
const imports = {
  'cloudflare:workers': synthetic({env:{DB:database}}),
  '../app/chatgpt-auth': synthetic({getChatGPTUser:async()=>user}),
  './phone-relay': synthetic({ownerId:async()=>phoneOwner,callTool:async(...args)=>{phoneCalls.push(args);return {phone:true};},now:()=>1000,json:value=>value,validAgent:()=>false}),
  './pc-portable-tools.json': synthetic({default:[]}),
  './phone-tools.json': synthetic({default:definitions}),
};
const module = new vm.SourceTextModule(stripTypeScriptTypes(source,{mode:'transform'}),{context});
await module.link(specifier=>{assert.ok(imports[specifier],specifier);return imports[specifier];});
await module.evaluate();
const {callBridge,bridgeTools} = module.namespace;
const entry=bridgeTools.find(tool=>tool.name==='relaykite_dev');
assert.ok(entry);
assert.ok(!entry.inputSchema.required.includes('connection_id'),'The primary phone entry must not require a PC');
assert.deepEqual(await callBridge('relaykite_dev',{operation:'capabilities',request_id:'probe-1'}),{phone:true});
assert.equal(phoneCalls.length,1);
assert.deepEqual(JSON.parse(JSON.stringify(phoneCalls[0])),['phone_development',{operation:'capabilities',request_id:'probe-1',arguments:{}},'owner','probe-1']);
phoneOwner=null;
await assert.rejects(()=>callBridge('relaykite_dev',{operation:'capabilities',request_id:'probe-2'}),/owner/i);
assert.equal(phoneCalls.length,1);
phoneOwner='owner'; user=null;
await assert.rejects(()=>callBridge('relaykite_dev',{operation:'capabilities',request_id:'probe-3'}),/Authenticated/);
user={userId:'owner'};
const pc=await callBridge('relaykite_dev',{connection_id:'pc-owned',operation:'status',request_id:'pc-status'});
assert.equal(JSON.parse(pc.content[0].text).status,'queued');
assert.equal(phoneCalls.length,1);
assert.equal([...jobs.values()][0].tool,'relaykite_dev');
grants=[];
await assert.rejects(()=>callBridge('relaykite_dev',{connection_id:'pc-owned',operation:'status',request_id:'pc-denied'}),/grant/);
grants=['codex'];user={userId:'stranger'};
await assert.rejects(()=>callBridge('relaykite_dev',{connection_id:'pc-owned',operation:'status',request_id:'pc-foreign'}),/permitted/);
user={userId:'owner'};
for(const arguments_ of [{execution_policy:'android-root'},{endpoint:'http://remote'},{request_id:'override'},{limits:{unknown:true}},{run_id:'bad'}]){
 await assert.rejects(()=>callBridge('relaykite_dev',{operation:'status',request_id:'invalid',arguments:arguments_}),/argument|Invalid|Unknown/i);
}
assert.equal(phoneCalls.length,1);
console.log('Phone default, explicit PC auth/grants, single entry schema and argument injection checks passed.');
