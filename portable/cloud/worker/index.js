const tools=[{"name":"use_apps","description":"List discoverable applications and their app_id. Launch only a returned app.","inputSchema":{"type":"object","properties":{"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false,"openWorldHint":true}},{"name":"use_capabilities","description":"Report platform support; do not assume unsupported actions.","inputSchema":{"type":"object","properties":{"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false,"openWorldHint":true}},{"name":"use_diagnostics","description":"Read session and uncertain request state; works while input is blocked.","inputSchema":{"type":"object","properties":{"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false,"openWorldHint":true}},{"name":"use_session_start","description":"Start an owned Android display or select a returned Windows window. Does not unlock the physical screen.","inputSchema":{"type":"object","properties":{"lease_seconds":{"type":"integer","minimum":30,"maximum":1800},"target":{"type":"string","maxLength":256},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":true,"openWorldHint":true}},{"name":"use_session_extend","description":"Extend the current session lease; observation freshness remains separate.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string","maxLength":256},"lease_seconds":{"type":"integer","minimum":30,"maximum":1800},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["session_id","device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":true,"openWorldHint":true}},{"name":"use_session_stop","description":"Release only this owned session. Windows apps remain open.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string","maxLength":256},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["session_id","device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":true,"openWorldHint":true}},{"name":"use_observe","description":"Read windows, nodes and focus with observation_id. Request screenshots only when needed.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string","maxLength":256},"screenshot":{"type":"boolean"},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["session_id","device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false,"openWorldHint":true}},{"name":"use_launch","description":"Launch a previously discovered app on the current session.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string","maxLength":256},"app_id":{"type":"string","maxLength":256},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["session_id","app_id","device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":true,"openWorldHint":true}},{"name":"use_action","description":"Execute one action bound to a fresh observation. Selectors must identify one node; occurrence is zero-based. Text replace accepts empty string; append/insert require a verified native field value. Never replay an uncertain action.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string","maxLength":256},"observation_id":{"type":"string","maxLength":256},"action":{"type":"object","properties":{"kind":{"type":"string","enum":["click","long_click","focus","set_text","selection","select","scroll","key","gesture","secondary","drag"]},"selector":{"type":"object","properties":{"node_id":{"type":"string","maxLength":256},"resource_id":{"type":"string","maxLength":256},"text":{"type":"string","maxLength":256},"description":{"type":"string","maxLength":256},"role":{"type":"string","maxLength":256},"parent_id":{"type":"string","maxLength":256},"window_id":{"type":"string","maxLength":256},"occurrence":{"type":"integer","minimum":0}},"additionalProperties":false},"x":{"type":"integer"},"y":{"type":"integer"},"start":{"type":"integer"},"end":{"type":"integer"},"duration_ms":{"type":"integer"},"scroll_x":{"type":"integer"},"scroll_y":{"type":"integer"},"click_count":{"type":"integer"},"from_x":{"type":"integer"},"from_y":{"type":"integer"},"to_x":{"type":"integer"},"to_y":{"type":"integer"},"key":{"type":"string","maxLength":256},"mode":{"type":"string","maxLength":256},"direction":{"type":"string","maxLength":256},"button":{"type":"string","maxLength":256},"action":{"type":"string","maxLength":256},"text":{"type":"string","maxLength":65536},"paths":{"type":"array","minItems":1,"maxItems":5,"items":{"type":"array","minItems":2,"maxItems":120,"items":{"type":"array","minItems":2,"maxItems":2,"items":{"type":"integer"}}}}},"required":["kind"],"additionalProperties":false},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["session_id","observation_id","action","device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":true,"openWorldHint":true}},{"name":"use_result","description":"Read a locally saved request outcome without executing it again.","inputSchema":{"type":"object","properties":{"target_request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["target_request_id","device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false,"openWorldHint":true}},{"name":"use_reconcile","description":"Record an explicitly checked uncertain outcome and evidence; never executes the original action. Do not invent evidence.","inputSchema":{"type":"object","properties":{"target_request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"},"outcome":{"type":"string","enum":["applied","not_applied"]},"evidence":{"type":"string","minLength":1,"maxLength":2000},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"}},"required":["target_request_id","outcome","evidence","device_id","request_id"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":true,"openWorldHint":true}},{"name":"use_devices","description":"List authorized connected device IDs and platform capabilities.","inputSchema":{"type":"object","properties":{},"required":[],"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false}},{"name":"use_job_result","description":"Read a queued job receipt; do not resubmit the original action.","inputSchema":{"type":"object","properties":{"job_id":{"type":"string","maxLength":256}},"required":["job_id"],"additionalProperties":false},"annotations":{"readOnlyHint":true,"destructiveHint":false}},{"name":"use_cancel","description":"Cancel only a job that has not been claimed; running actions cannot be cancelled.","inputSchema":{"type":"object","properties":{"job_id":{"type":"string","maxLength":256}},"required":["job_id"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":true}},{"name":"use_batch","description":"Execute 1–12 known semantic steps sequentially on a fresh observation. Stops on first error, ambiguity, uncertainty or timeout. Completed steps are retained; no rollback, replay or automatic resume. Use stable selectors without positional IDs or coordinates. Reconcile uncertain child request IDs after checking the actual screen. Retrieve pending job_id with use_job_result; never resubmit input to poll.","inputSchema":{"type":"object","properties":{"session_id":{"type":"string","maxLength":256},"observation_id":{"type":"string","maxLength":256},"device_id":{"type":"string","maxLength":256},"request_id":{"type":"string","minLength":8,"maxLength":80,"pattern":"^[A-Za-z0-9_-]+$"},"steps":{"type":"array","minItems":1,"maxItems":12,"items":{"type":"object","properties":{"action":{"type":"object","properties":{"kind":{"type":"string","enum":["click","long_click","focus","set_text","selection","select","scroll","key"]},"selector":{"type":"object","properties":{"resource_id":{"type":"string","maxLength":256},"text":{"type":"string","maxLength":256},"description":{"type":"string","maxLength":256},"role":{"type":"string","maxLength":256},"occurrence":{"type":"integer","minimum":0}},"additionalProperties":false},"start":{"type":"integer"},"end":{"type":"integer"},"duration_ms":{"type":"integer"},"scroll_x":{"type":"integer"},"scroll_y":{"type":"integer"},"click_count":{"type":"integer"},"key":{"type":"string","maxLength":256},"mode":{"type":"string","maxLength":256},"direction":{"type":"string","maxLength":256},"button":{"type":"string","maxLength":256},"action":{"type":"string","maxLength":256},"text":{"type":"string","maxLength":65536}},"required":["kind"],"additionalProperties":false},"wait_for":{"type":"object","properties":{"resource_id":{"type":"string","maxLength":256},"text":{"type":"string","maxLength":256},"description":{"type":"string","maxLength":256},"role":{"type":"string","maxLength":256},"occurrence":{"type":"integer","minimum":0}},"additionalProperties":false},"wait_timeout_ms":{"type":"integer","minimum":0,"maximum":5000}},"required":["action"],"additionalProperties":false}},"timeout_ms":{"type":"integer","minimum":1,"maximum":30000}},"required":["device_id","request_id","session_id","observation_id","steps"],"additionalProperties":false},"annotations":{"readOnlyHint":false,"destructiveHint":true,"openWorldHint":true}}];
const MAX=4*1024*1024,now=()=>Math.floor(Date.now()/1000),pause=ms=>new Promise(r=>setTimeout(r,ms));
const response=(value,status=200)=>Response.json(value,{status,headers:{'Cache-Control':'no-store'}});
const text=(value,isError=false)=>({content:[{type:'text',text:JSON.stringify(value)}],isError});
const sql=[
 'CREATE TABLE IF NOT EXISTS pu_devices (id TEXT PRIMARY KEY, seen INTEGER NOT NULL, capabilities TEXT NOT NULL)',
 'CREATE TABLE IF NOT EXISTS pu_jobs (id TEXT PRIMARY KEY, device TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, op TEXT NOT NULL, args TEXT NOT NULL, state TEXT NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL, result TEXT, result_hash TEXT, UNIQUE(device,request_id))',
 'CREATE TABLE IF NOT EXISTS pu_parts (job_id TEXT NOT NULL, part INTEGER NOT NULL, content TEXT NOT NULL, PRIMARY KEY(job_id,part))'];
const ready=new WeakMap();
async function database(env){if(!env.DB)throw new Error('Missing DB');if(!ready.has(env.DB))ready.set(env.DB,env.DB.batch(sql.map(s=>env.DB.prepare(s))).catch(e=>{ready.delete(env.DB);throw e;}));await ready.get(env.DB);return env.DB;}
async function body(req){
 if(Number(req.headers.get('content-length')||0)>MAX)throw new Error('Payload too large');
 const reader=req.body?.getReader();if(!reader)throw new Error('Body required');const chunks=[];let n=0;
 try{while(true){const v=await reader.read();if(v.done)break;n+=v.value.length;if(n>MAX){await reader.cancel();throw new Error('Payload too large');}chunks.push(v.value);}}finally{reader.releaseLock();}
 const bytes=new Uint8Array(n);let i=0;for(const c of chunks){bytes.set(c,i);i+=c.length;}return JSON.parse(new TextDecoder().decode(bytes));
}
const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,stable(value[k])])):value;
async function hash(s){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');}
function deviceTokens(env){
 const tokens=JSON.parse(env.DEVICE_TOKENS||'{}');
 if(/^[A-Za-z0-9_-]{1,64}$/.test(env.WINDOWS_DEVICE_ID||'')&&typeof env.WINDOWS_DEVICE_TOKEN==='string'&&env.WINDOWS_DEVICE_TOKEN.length>=40&&!Object.hasOwn(tokens,env.WINDOWS_DEVICE_ID))tokens[env.WINDOWS_DEVICE_ID]=env.WINDOWS_DEVICE_TOKEN;
 return tokens;
}
async function deviceAuth(req,env){
 const id=req.headers.get('X-Device-ID'),tokens=deviceTokens(env),expected=tokens[id],given=req.headers.get('Authorization')?.replace(/^Bearer /i,'');
 if(!/^[A-Za-z0-9_-]{1,64}$/.test(id||'')||typeof expected!=='string'||expected.length<40||typeof given!=='string'||given.length>256)return null;
 const a=await hash(expected),b=await hash(given);let difference=0;for(let i=0;i<a.length;i++)difference|=a.charCodeAt(i)^b.charCodeAt(i);return difference===0?id:null;
}
async function ownerAuth(req,env){
 // Only deploy this worker behind Sites' authenticated, owner-private gateway.
 // Caller-supplied identity headers are replaced by that gateway.
 return !!req.headers.get('oai-authenticated-user-id') && !!env.OWNER_EMAIL &&
   req.headers.get('oai-authenticated-user-email')===env.OWNER_EMAIL;
}

function validate(s,v){
 if(s.type==='object'){
  if(!v||typeof v!=='object'||Array.isArray(v))throw new Error('Expected object');
  if((s.required||[]).some(k=>!Object.hasOwn(v,k)))throw new Error('Missing argument');
  for(const [k,x] of Object.entries(v)){if(!Object.hasOwn(s.properties||{},k)){if(s.additionalProperties===false)throw new Error('Unknown argument');}else validate(s.properties[k],x);}
 }
 if(s.type==='string'&&(typeof v!=='string'||v.includes('\0')||v.length<(s.minLength||0)||v.length>(s.maxLength??100000)||s.pattern&&!new RegExp(s.pattern).test(v)))throw new Error('Invalid string');
 if(s.type==='integer'&&(!Number.isSafeInteger(v)||v<(s.minimum??-2147483648)||v>(s.maximum??2147483647)))throw new Error('Invalid integer');
 if(s.type==='boolean'&&typeof v!=='boolean')throw new Error('Expected boolean');
 if(s.type==='array'){if(!Array.isArray(v)||v.length<(s.minItems||0)||v.length>(s.maxItems??10000))throw new Error('Invalid array');for(const x of v)validate(s.items,x);}
 if(s.enum&&!s.enum.includes(v))throw new Error('Invalid choice');
}
async function cleanup(db){await db.batch([
 db.prepare("UPDATE pu_jobs SET state='expired' WHERE state='queued' AND expires<?").bind(now()),
 db.prepare("UPDATE pu_jobs SET state='uncertain' WHERE state='running' AND expires<?").bind(now()),
 db.prepare('DELETE FROM pu_parts WHERE job_id IN (SELECT id FROM pu_jobs WHERE created<?)').bind(now()-86400),
 db.prepare("UPDATE pu_jobs SET result=NULL,state=CASE WHEN state='completed' THEN 'compacted' ELSE state END WHERE created<? AND result IS NOT NULL").bind(now()-86400)]);}
async function result(db,id){
 const job=await db.prepare('SELECT * FROM pu_jobs WHERE id=?').bind(id).first();if(!job)return text({error:'Job not found; do not replay'},true);
 if(job.result){const chunks=await db.prepare('SELECT content FROM pu_parts WHERE job_id=? ORDER BY part').bind(id).all();const data=JSON.parse(chunks.results.map(x=>x.content).join('')||job.result);const images=[];function extract(v){if(v&&typeof v==='object'){if(!Array.isArray(v)){const image=v.screenshot;delete v.screenshot;if(image){if(['image/png','image/jpeg'].includes(image.mime_type)&&typeof image.base64==='string')images.push({type:'image',data:image.base64,mimeType:image.mime_type});else v.screenshot_warning='Invalid screenshot omitted; receipt retained';}}for(const child of Object.values(v))extract(child);}}extract(data);const output=text(data,!!data.error||data.status==='stopped');output.content.push(...images.slice(-1));return output;}
 return text({job_id:id,status:job.state,instruction:'Retrieve this job ID; never submit a second action to poll.'},['uncertain','expired','compacted'].includes(job.state));
}
async function call(db,name,args,env){
 const tool=tools.find(t=>t.name===name);if(!tool)throw new Error('Unknown tool');validate(tool.inputSchema,args);
 if(name==='use_devices'){const devices=await db.prepare('SELECT * FROM pu_devices').all();return text({devices:devices.results.map(d=>({device_id:d.id,online:now()-d.seen<30,capabilities:JSON.parse(d.capabilities)}))});}
 if(name==='use_job_result')return result(db,args.job_id);
 if(name==='use_cancel'){
  const r=await db.prepare("UPDATE pu_jobs SET state='cancelled' WHERE id=? AND state='queued'").bind(args.job_id).run();
  return text({job_id:args.job_id,cancelled:r.meta.changes===1},r.meta.changes!==1);
 }
 const {device_id,request_id,...rest}=args;const tokens=deviceTokens(env);if(!Object.hasOwn(tokens,device_id))throw new Error('Unknown device');
 const op=name.slice(4);if(Object.hasOwn(rest,'target_request_id')){rest.request_id=rest.target_request_id;delete rest.target_request_id;}
 const fingerprint=await hash(JSON.stringify(stable([op,rest])));
 let row=await db.prepare('SELECT * FROM pu_jobs WHERE device=? AND request_id=?').bind(device_id,request_id).first();
 if(row&&row.fingerprint!==fingerprint)throw new Error('request_id reused with different arguments');
 if(!row){
  const count=await db.prepare("SELECT COUNT(*) AS n FROM pu_jobs WHERE device=? AND state IN ('queued','running')").bind(device_id).first();if(count.n>=8)throw new Error('Queue full');
  const id=crypto.randomUUID();await db.prepare("INSERT OR IGNORE INTO pu_jobs (id,device,request_id,fingerprint,op,args,state,created,expires,result) VALUES (?,?,?,?,?,?,'queued',?,?,NULL)").bind(id,device_id,request_id,fingerprint,op,JSON.stringify(rest),now(),now()+300).run();
  row=await db.prepare('SELECT * FROM pu_jobs WHERE device=? AND request_id=?').bind(device_id,request_id).first();if(row.fingerprint!==fingerprint)throw new Error('Conflicting request');
 }
 const wait=Math.min(8000,Math.max(0,Number(env.WAIT_MS??5000)));const until=Date.now()+wait;
 while(Date.now()<until){const r=await db.prepare('SELECT state FROM pu_jobs WHERE id=?').bind(row.id).first();if(!['queued','running'].includes(r.state))break;await pause(200);}
 return result(db,row.id);
}
async function agent(req,path,db,id,env){
 const data=await body(req);
 if(path==='/agent/next'){
  const cap=JSON.stringify(data.capabilities||{});if(cap.length>8192)throw new Error('Capabilities too large');
  await db.prepare('INSERT OR REPLACE INTO pu_devices VALUES (?,?,?)').bind(id,now(),cap).run();
  // Offering a job does not claim it. A lost offer can be fetched again.
  let job;const until=Date.now()+Math.min(15000,Math.max(0,Number(env.AGENT_WAIT_MS??15000)));
  do{
   job=await db.prepare("SELECT * FROM pu_jobs WHERE device=? AND state IN ('queued','running') AND expires>=? ORDER BY CASE state WHEN 'running' THEN 0 ELSE 1 END,created,rowid LIMIT 1").bind(id,now()).first();
   if(job||Date.now()>=until)break;await pause(500);
  }while(!req.signal.aborted);
  return response({job:job?{id:job.id,request_id:job.request_id,op:job.op,args:JSON.parse(job.args),expires:job.expires}:null});
 }
 if(typeof data.job_id!=='string')throw new Error('Missing job ID');
 const job=await db.prepare('SELECT * FROM pu_jobs WHERE id=? AND device=?').bind(data.job_id,id).first();if(!job)return response({error:'Unknown job'},404);
 if(path==='/agent/claim'){
  if(job.state==='running')return response({claimed:true});
  const r=await db.prepare("UPDATE pu_jobs SET state='running' WHERE id=? AND device=? AND state='queued' AND expires>=?").bind(job.id,id,now()).run();return response({claimed:r.meta.changes===1});
 }
 if(path==='/agent/result'){
  const raw=JSON.stringify(data.result);if(!data.result||typeof data.result!=='object'||raw.length>MAX-4096)throw new Error('Invalid result');
  const resultHash=await hash(raw);
  if(job.result_hash)return job.result_hash===resultHash?response({saved:true}):response({error:'Result conflict'},409);
  if(job.result){const prior=await db.prepare('SELECT content FROM pu_parts WHERE job_id=? ORDER BY part').bind(job.id).all();if(prior.results.map(r=>r.content).join('')!==raw)return response({error:'Result conflict'},409);return response({saved:true});}
  if(!['running','uncertain'].includes(job.state))return response({error:'Job cannot accept a result'},409);
  const statements=[];
  for(let offset=0,part=0;offset<raw.length;part++){
   let end=Math.min(raw.length,offset+50000);
   if(end<raw.length&&raw.charCodeAt(end-1)>=0xD800&&raw.charCodeAt(end-1)<=0xDBFF)end--;
   statements.push(db.prepare('INSERT INTO pu_parts VALUES (?,?,?)').bind(job.id,part,raw.slice(offset,end)));offset=end;
  }
  statements.push(db.prepare('UPDATE pu_jobs SET state=?,result=?,result_hash=? WHERE id=?').bind(data.result.code==='UNCERTAIN'?'uncertain':'completed','{}',resultHash,job.id));await db.batch(statements);return response({saved:true});
 }
 return response({error:'Not found'},404);
}
export default {async fetch(req,env){
 const path=new URL(req.url).pathname;
 try{
  if(req.method==='GET'&&path==='/')return new Response("<!doctype html><html lang=\"ru\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Codaki Portable Use</title>\n<style>body{margin:0;background:#101719;color:#e9f0ed;font:16px system-ui}main{max-width:820px;margin:auto;padding:64px 24px}small{color:#94b5a7}h1{font-size:clamp(32px,7vw,56px);letter-spacing:-2px;margin:12px 0}p{line-height:1.6;color:#bbc9c3}.panel{margin-top:32px;padding:24px;background:#1b2525;border:1px solid #354943;border-radius:20px}.device{padding:14px 0;border-bottom:1px solid #354943}.online{color:#87e0b3}a{color:#a5ecc7}button{background:#a5ecc7;color:#101719;border:0;border-radius:12px;padding:12px 18px;font:inherit;cursor:pointer}footer{margin-top:32px;font-size:14px;color:#94b5a7}</style>\n<main><small>CODAKI · 0.1.0</small><h1>Portable Use</h1><p>Управляйте Android и ПК из чата: запускайте приложения, читайте экран, вводите текст и выполняйте жесты. На Android работа идёт на отдельном экране.</p><div class=\"panel\"><h2>Подключённые устройства</h2><div id=\"devices\" aria-live=\"polite\">Проверяем связь…</div><p><button id=\"refresh\">Обновить статус</button></p></div><footer>Карточка плагина доступна в «Плагины → Личные → Созданные вами». Выберите Codaki Portable Use и подключите его к чату. Телефону нужен интернет; ПК для управления Android можно выключить.</footer></main>\n<script>async function refresh(){const box=document.getElementById('devices');try{const r=await fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'use_devices',arguments:{}}})});if(!r.ok)throw Error();const data=await r.json();if(data.result.isError)throw Error();const devices=JSON.parse(data.result.content[0].text).devices;box.replaceChildren();if(!devices.length)box.textContent='Устройство ещё не подключено.';for(const d of devices){const row=document.createElement('div');row.className='device';const name=document.createElement('strong');name.textContent=d.device_id;const status=document.createElement('span');status.textContent=d.online?' · На связи':' · Не в сети';if(d.online)status.className='online';row.append(name,status);box.append(row)}}catch{box.textContent='Не удалось получить статус. Войдите в аккаунт владельца.'}}document.getElementById('refresh').onclick=refresh;refresh();setInterval(refresh,20000)</script></html>",{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'}});
  if(req.method!=='POST')return response({name:'Codaki Portable Use',version:'0.1.0',mcp:'/mcp'});
  if(path==='/mcp'){
   const preview=await body(req.clone());
   if(preview.method==='server/discover')return response({jsonrpc:'2.0',id:preview.id,result:{supportedVersions:['2026-07-28'],capabilities:{tools:{}}}});
   if(preview.method==='tools/list')return response({jsonrpc:'2.0',id:preview.id,result:{tools}});
  }
  const db=await database(env);await cleanup(db);
  if(path.startsWith('/agent/')){const id=await deviceAuth(req,env);if(!id)return response({error:'Forbidden'},403);return agent(req,path,db,id,env);}
  if(path!=='/mcp')return response({error:'Not found'},404);
  if(!await ownerAuth(req,env))return response({error:'Forbidden'},403);
  const q=await body(req);if(q.method?.startsWith('notifications/'))return new Response(null,{status:202});
  let out;if(q.method==='initialize')out={protocolVersion:'2026-07-28',capabilities:{tools:{}},serverInfo:{name:'Codaki Portable Use',version:'0.1.0'},instructions:'Observe before acting. Use the same request_id only for retries of the same action. Reconcile only a verified outcome.'};
  else if(q.method==='tools/list')out={tools};else if(q.method==='ping')out={};
  else if(q.method==='tools/call'){try{out=await call(db,q.params?.name,q.params?.arguments||{},env);}catch(e){out=text({error:String(e.message)},true);}}
  else return response({jsonrpc:'2.0',id:q.id,error:{code:-32601,message:'Unknown method'}});
  return response({jsonrpc:'2.0',id:q.id,result:out});
 }catch(e){return response({error:'Request rejected; inspect existing job state before retrying input.'},400);}
}};
