/** Codaki external distillation: original Tencent storage, GPT supplies facts. */
import {VectorStore} from '../core/store/sqlite/memory-store.js';
import {LocalStorageBackend} from '../core/storage/local-backend.js';
import {createHash, timingSafeEqual} from 'node:crypto';
import {createServer} from 'node:http';
import {mkdirSync, readFileSync, readdirSync, statSync, lstatSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const ENGINE='tencentdb-original-external';
const PIN='b1f79fc4714b1e20a1ab94ec6b98e50100af6dc4';
const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
const ADAPTER_REVISION=hash(readFileSync(fileURLToPath(import.meta.url),'utf8'));
const layers=['L0','L1','L2','L3'];
const statuses=['historical','proposed','verified','superseded'];
function text(v:unknown,name:string,max:number,empty=false):string {
  if(typeof v!=='string'||(!empty&&!v.trim())||v.length>max||v.includes('\0'))throw Error('invalid '+name);
  return v;
}
function object(v:unknown):Record<string,any>{if(!v||typeof v!=='object'||Array.isArray(v))throw Error('object required');return v as Record<string,any>;}
function fields(o:Record<string,any>,allowed:string[]){for(const k of Object.keys(o))if(!allowed.includes(k))throw Error('unsupported field '+k);}
function bytes(root:string):number {
  let n=0;for(const d of readdirSync(root,{withFileTypes:true})){
    const p=join(root,d.name),s=lstatSync(p);if(s.isSymbolicLink())throw Error('storage symlink rejected');
    n+=s.isDirectory()?bytes(p):(s as any).blocks?((s as any).blocks*512):s.size;
  }return n;
}
function bounded(result:any):any {
  while(Buffer.byteLength(JSON.stringify(result))>6144&&result.notes.length>1)result.notes.pop();
  if(Buffer.byteLength(JSON.stringify(result))>6144&&result.notes.length){
    const n=result.notes[0];n.truncated=true;
    while(Buffer.byteLength(JSON.stringify(result))>6144&&n.content.length)n.content=Array.from(n.content).slice(0,-64).join('');
  }
  if(Buffer.byteLength(JSON.stringify(result))>6144)throw Error('response metadata exceeds budget');
  return result;
}
export class ExternalMemory {
  readonly store:VectorStore;
  private files:LocalStorageBackend;
  private scope:any;
  private tail:Promise<any>=Promise.resolve();
  constructor(readonly root:string,owner:string,private quota=5*1024**3){
    text(owner,'owner',160);mkdirSync(root,{recursive:true,mode:0o700});
    this.scope={teamId:hash(owner).slice(0,32),userId:hash('user:'+owner).slice(0,32),agentId:'codaki-memory'};
    this.store=new VectorStore(join(root,'vectors.db'),0);
    this.store.init();
    if(this.store.isDegraded()||!this.store.getCapabilities().ftsSearch){this.store.close();throw Error('Tencent SQLite FTS5 unavailable');}
    this.files=new LocalStorageBackend(join(root,'files'));
  }
  health(){return {engine:ENGINE,mode:'external',vendor_revision:PIN,adapter_revision:ADAPTER_REVISION,fts_available:this.store.getCapabilities().ftsSearch,llm_enabled:false,embeddings_enabled:false,notes_count:this.store.countL1(this.scope),storage_bytes:bytes(this.root)};}
  close(){this.store.close();}
  save(payload:any):Promise<any>{const r=this.tail.then(()=>this.saveOne(payload));this.tail=r.catch(()=>{});return r;}
  private async saveOne(raw:any){
    const p=object(raw);fields(p,['title','content','tags','memory']);
    const title=text(p.title,'title',160),content=text(p.content,'content',24000);
    if(Buffer.byteLength(content)>6144)throw Error('memory content exceeds 6 KiB');
    const tags=p.tags??[];if(!Array.isArray(tags)||tags.length>20)throw Error('invalid tags');for(const t of tags)text(t,'tag',80);
    const m=object(p.memory??{});fields(m,['layer','status','source','device','project','versions','expected_version','valid_from','source_id']);
    const layer=m.layer??'L1',status=m.status??'historical',device=m.device??'android',project=m.project??'';
    if(!layers.includes(layer))throw Error('invalid layer');if(!statuses.includes(status))throw Error('invalid status');
    if(!['android','windows','shared'].includes(device))throw Error('invalid device');text(project,'project',160,true);
    for(const k of ['source','versions','valid_from','source_id'])if(m[k]!==undefined)text(m[k],k,500,true);
    if(status==='verified'&&!m.source?.trim())throw Error('verified memory requires source');
    if(m.expected_version!==undefined&&(!Number.isSafeInteger(m.expected_version)||m.expected_version<0))throw Error('invalid expected_version');
    const id=hash(JSON.stringify([this.scope,layer,device,project,title]));
    const old=this.store.queryL1Records({...this.scope,sessionId:id}).find(r=>r.record_id===id);
    const previous=old?JSON.parse(old.metadata_json):null;
    const mem={layer,status,device,project,source:m.source??'',versions:m.versions??'',valid_from:m.valid_from??'',source_id:m.source_id??''};
    const digest=hash(JSON.stringify({title,content,tags,memory:mem}));
    const unchanged=previous?.digest===digest;
    if(!unchanged&&m.expected_version!==undefined&&m.expected_version!==(old?.version??0))throw Error('version conflict');
    if(bytes(this.root)+Buffer.byteLength(JSON.stringify(p))*5+65536>this.quota)throw Error('memory quota exceeded');
    const version=unchanged?old!.version:(old?.version??0)+1,now=new Date().toISOString();
    const blobKey=`profiles/${this.scope.teamId}/${layer}/${id}/v${version}-${digest}.json`;
    const note=unchanged?await this.read(id):{id,title,content,tags,updated:Date.now()/1000,archived:false,version,memory:mem,digest};
    // Immutable version blobs go through Tencent's original filesystem backend.
    // An interrupted save never points the search index at an incomplete blob.
    if(!unchanged)await this.files.putObject(blobKey,JSON.stringify(note));
    if(layer==='L0'&&!unchanged){
      const ok=this.store.upsertL0({id:id+':'+version,sessionKey:project||'codaki',sessionId:id,...this.scope,role:'assistant',messageText:content,recordedAt:now,timestamp:Date.now()},undefined);
      if(!ok)throw Error('Tencent L0 write failed');
    }
    const metadata={...note,blob_key:blobKey};
    const markers=`codakiversion${digest}`;
    const record={id,content:[title,tags.join(' '),content,markers].join('\n'),type:layer==='L3'?'persona':layer==='L2'?'work_method':'episodic',priority:status==='verified'?80:40,scene_name:project,source_message_ids:m.source_id?[m.source_id]:[],metadata,timestamps:[now],createdAt:old?.created_time??now,updatedAt:now,version,sessionKey:project||'codaki',sessionId:id,...this.scope};
    if(!this.store.upsertL1(record as any,undefined))throw Error('Tencent index write failed');
    const verify=this.store.queryL1Records({...this.scope,sessionId:id}).find(r=>r.record_id===id);
    if(!verify||JSON.parse(verify.metadata_json).digest!==digest)throw Error('Tencent write verification failed');
    const indexed=this.store.searchL1Fts('"codakiversion'+digest+'"',1,this.scope);
    if(!indexed.some(r=>r.record_id===id&&r.version===version))throw Error('Tencent FTS write verification failed');
    this.store.appendAudit({audit_id:hash(id+':'+version),record_id:id,layer:layer==='L0'?'L1':layer as any,action:'update',team_id:this.scope.teamId,user_id:this.scope.userId,agent_id:this.scope.agentId,version,updated_at_ms:Date.now(),request_id:digest} as any);
    return {saved:true,engine:ENGINE,id,version,unchanged:!!unchanged,notes_count:this.store.countL1(this.scope)};
  }
  async read(id:string){
    if(!/^[a-f0-9]{64}$/.test(id))throw Error('invalid record id');
    const r=this.store.queryL1Records({...this.scope,sessionId:id}).find(r=>r.record_id===id);if(!r)throw Error('record not found');
    const meta=JSON.parse(r.metadata_json),blob=await this.files.getObject(meta.blob_key);
    if(!blob)throw Error('memory blob unavailable');const n=JSON.parse(blob.content.toString('utf8'));
    if(n.digest!==meta.digest||n.version!==r.version||hash(JSON.stringify({title:n.title,content:n.content,tags:n.tags,memory:n.memory}))!==meta.digest)throw Error('memory blob digest/version mismatch');
    return n;
  }
  async search(query:string,limit=5,filters:any={}){
    text(query,'query',2000,true);if(!Number.isSafeInteger(limit)||limit<1||limit>30)throw Error('invalid limit');
    const f=object(filters);fields(f,['layer','device','project','status']);
    const terms=Array.from(new Set(query.match(/[\p{L}\p{N}_]+/gu)??[])).slice(0,16).map(x=>'"'+x+'"*');
    for(const [k,v] of Object.entries(f)){
      if(k==='layer'&&!layers.includes(v as string))throw Error('invalid layer');
      if(k==='device'&&!['android','windows','shared'].includes(v as string))throw Error('invalid device');
      if(k==='status'&&!statuses.includes(v as string))throw Error('invalid status');
      text(v,k,160,k==='project');
    }
    if(!terms.length)return {engine:ENGINE,notes:[]};
    const q=terms.join(' AND ');
    const found=this.store.searchL1Fts(q,limit,this.scope,{...f,excludeSuperseded:!f.status});const notes=[];
    for(const r of found){const n=await this.read(r.record_id);notes.push({...n,score:r.score});}
    return bounded({engine:ENGINE,notes});
  }
}
export async function serveExternal(root:string,opts:{scope:string,key:string,port?:number,quota?:number}){
  text(opts.key,'key',256);if(opts.key.length<40)throw Error('local key too short');
  const memory=new ExternalMemory(root,opts.scope,opts.quota);
  const server=createServer(async(req,res)=>{
    const send=(status:number,value:any)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
    const supplied=Buffer.from(req.headers.authorization??''),wanted=Buffer.from('Bearer '+opts.key);
    if(supplied.length!==wanted.length||!timingSafeEqual(supplied,wanted))return send(401,{error:'unauthorized'});
    try{
      if(req.method==='GET'&&req.url==='/health')return send(200,memory.health());
      if(req.method!=='POST'||!['/save','/search','/read'].includes(req.url??''))return send(404,{error:'unknown route'});
      let size=0;const chunks=[];for await(const c of req){size+=c.length;if(size>256*1024)throw Error('request too large');chunks.push(c);}
      const p=object(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      const r=req.url==='/save'?await memory.save(p):req.url==='/read'?{engine:ENGINE,notes:[await memory.read(p.id)]}:await memory.search(p.query,p.limit,p.filters);
      if(Buffer.byteLength(JSON.stringify(r))>65536)throw Error('single-record response exceeds budget');
      send(200,r);
    }catch(e){send(400,{error:e instanceof Error?e.message:'memory request failed'});}
  });
  await new Promise<void>((yes,no)=>{server.once('error',no);server.listen(opts.port??8420,'127.0.0.1',()=>yes());});
  return {port:(server.address() as any).port,memory,stop:async()=>{await new Promise<void>((yes,no)=>server.close(e=>e?no(e):yes()));memory.close();}};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const cfg=JSON.parse(readFileSync(process.argv[2]??'', 'utf8'));
  const svc=await serveExternal(cfg.data_dir,{scope:cfg.scope,key:cfg.key,port:cfg.port,quota:cfg.quota_bytes});
  console.log(JSON.stringify({ready:true,port:svc.port,engine:ENGINE}));
  let stopping=false;for(const signal of ['SIGTERM','SIGINT'])process.on(signal,async()=>{if(stopping)return;stopping=true;await svc.stop();process.exit(0);});
}
