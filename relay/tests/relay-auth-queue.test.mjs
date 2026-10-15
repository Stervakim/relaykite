import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { setTimeout as delay } from "node:timers/promises";
import ts from "typescript";

async function fixture() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(await readFile(new URL("../drizzle/0000_clear_the_call.sql", import.meta.url), "utf8"));
  const db = {
    prepare(sql) {
      const statement = sqlite.prepare(sql);
      let arguments_ = [];
      return {
        bind(...values) { arguments_ = values; return this; },
        run() { statement.run(...arguments_); return { success: true }; },
        first() { return statement.get(...arguments_) ?? null; },
        all() { return { results: statement.all(...arguments_) }; },
      };
    },
    async batch(statements) {
      sqlite.exec("BEGIN");
      try {
        const results = [];
        for (const statement of statements) results.push(statement.run());
        sqlite.exec("COMMIT");
        return results;
      } catch (error) {
        sqlite.exec("ROLLBACK");
        throw error;
      }
    },
  };
  const context = { env: { DB: db, PHONE_AGENT_TOKEN: "a".repeat(64) }, user: null };
  const key = "__relay_test_" + randomUUID().replaceAll("-", "");
  globalThis[key] = context;
  let source = await readFile(new URL("../lib/phone-relay.ts", import.meta.url), "utf8");
  const definitions = JSON.parse(await readFile(new URL("../lib/phone-tools.json", import.meta.url), "utf8"));
  // Replace runtime dependencies only. Auth, owner pin, SQL, queue claiming,
  // deduplication, maintenance and result handling run from the actual source.
  const replacements = [
    ['import { env } from "cloudflare:workers";', `const env = globalThis[${JSON.stringify(key)}].env;`],
    ['import { headers } from "next/headers";', `const headers = async () => new Headers(globalThis[${JSON.stringify(key)}].user ? {"oai-authenticated-user-id":globalThis[${JSON.stringify(key)}].user,"oai-authenticated-user-email":globalThis[${JSON.stringify(key)}].email || ""} : {});`],
    ['import definitions from "./phone-tools.json";', `const definitions = ${JSON.stringify(definitions)};`],
  ];
  for (const [original, replacement] of replacements) {
    assert.ok(source.includes(original), "Runtime dependency changed; update the test adapter");
    source = source.replace(original, replacement);
  }
  const compiled = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText;
  const relay = await import("data:text/javascript;base64," + Buffer.from(compiled).toString("base64"));
  return { relay, sqlite, context, close() { delete globalThis[key]; sqlite.close(); } };
}

test("agent credential is required; wrong and absent credentials are rejected", async () => {
  const f = await fixture();
  try {
    assert.equal(f.relay.validAgent(new Request("https://relay.invalid/agent/jobs/next")), false);
    assert.equal(f.relay.validAgent(new Request("https://relay.invalid/agent/jobs/next", { headers: { authorization: "Bearer " + "b".repeat(64) } })), false);
    assert.equal(f.relay.validAgent(new Request("https://relay.invalid/agent/jobs/next", { headers: { authorization: "Bearer " + f.context.env.PHONE_AGENT_TOKEN } })), true);
    f.context.env.PHONE_AGENT_TOKEN = undefined;
    assert.equal(f.relay.validAgent(new Request("https://relay.invalid/agent/jobs/next", { headers: { authorization: "Bearer " + "a".repeat(64) } })), false);
  } finally { f.close(); }
});

test("first authenticated owner is pinned; anonymous and second owner cannot replace it", async () => {
  const f = await fixture();
  try {
    assert.equal(await f.relay.ownerId(), null);
    assert.equal(f.sqlite.prepare("SELECT COUNT(*) AS n FROM phone_agents").get().n, 0);
    f.context.user = "fixture-owner-a";
    assert.equal(await f.relay.ownerId(), "fixture-owner-a");
    f.context.user = "fixture-owner-b";
    assert.equal(await f.relay.ownerId(), null);
    assert.equal(f.sqlite.prepare("SELECT owner FROM phone_agents WHERE id='phone'").get().owner, "fixture-owner-a");
    f.context.user = "fixture-owner-a";
    assert.equal(await f.relay.ownerId(), "fixture-owner-a");
  } finally { f.close(); }
});

test("a queued request is claimed once, completed and deduplicated on retry", async () => {
  const f = await fixture();
  try {
    f.context.user = "fixture-owner-a";
    const owner = await f.relay.ownerId();
    assert.equal((await f.relay.nextJob()).status, 204); // Agent heartbeat.
    const args = {command:"id -u",request_id:"fixture-request-1"};
    const pending = f.relay.callTool("root_shell", args, owner, "rpc-1");
    await delay(25);
    const responses = await Promise.all([f.relay.nextJob(), f.relay.nextJob(), f.relay.nextJob()]);
    assert.equal(responses.filter(response => response.status === 200).length, 1);
    assert.equal(responses.filter(response => response.status === 204).length, 2);
    const claimed = await responses.find(response => response.status === 200).json();
    assert.equal(claimed.job.tool, "root_shell");
    assert.deepEqual(claimed.job.arguments,{command:"id -u"});
    const result = { content: [{ type: "text", text: "fixture phone result" }], isError: false };
    assert.equal((await f.relay.saveResult(claimed.job.id, { status: "completed", result })).status, 200);
    assert.deepEqual(await pending, result);
    assert.deepEqual(await f.relay.callTool("root_shell", args, owner, "rpc-2"), result);
    assert.equal(f.sqlite.prepare("SELECT COUNT(*) AS n FROM phone_jobs").get().n, 1);
    assert.equal((await f.relay.jobResult(claimed.job.id, "fixture-owner-b")).isError, true);
  } finally { f.close(); }
});

test("explicit second-account invitation pins identity and maps to the original phone owner", async () => {
  const f=await fixture();
  try {
    f.context.env.PHONE_ADDITIONAL_ACCOUNT_EMAILS='["second@example.test"]';
    f.context.user='second-user';f.context.email='second@example.test';
    assert.equal(await f.relay.ownerId(),null); // Cannot initialise ownership.
    f.context.user='owner-a';f.context.email='owner@example.test';
    assert.equal(await f.relay.ownerId(),'owner-a');
    f.context.user='second-user';f.context.email='SECOND@example.test';
    assert.equal(await f.relay.ownerId(),'owner-a');
    f.context.user='replacement-user';
    assert.equal(await f.relay.ownerId(),null); // Same email cannot replace pinned ID.
    f.context.user='uninvited-user';f.context.email='other@example.test';
    assert.equal(await f.relay.ownerId(),null);
    f.context.user='second-user';f.context.email='second@example.test';
    f.context.env.PHONE_ADDITIONAL_ACCOUNT_EMAILS='[]';
    assert.equal(await f.relay.ownerId(),null); // Revocation is immediate.
  } finally {f.close();}
});

test("read-only calls remain fresh when the host reuses JSON-RPC ids", async () => {
  const f=await fixture();
  try {
    await f.relay.nextJob();
    const ids=[];
    for (let index=0;index<2;index++) {
      const pending=f.relay.callTool('phone_status',{},'owner-a',1);
      await delay(25);
      const claimed=await (await f.relay.nextJob()).json();ids.push(claimed.job.id);
      const result={content:[{type:'text',text:'fresh-'+index}],isError:false};
      await f.relay.saveResult(claimed.job.id,{status:'completed',result});
      assert.deepEqual(await pending,result);
    }
    assert.notEqual(ids[0],ids[1]);
  } finally {f.close();}
});

test("mutations require stable identity and reject changed retry arguments", async () => {
  const f=await fixture();
  try {
    await assert.rejects(f.relay.callTool('root_shell',{command:'id'},'owner-a',1),/request_id/);
    assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM phone_jobs').get().n,0);
    await f.relay.nextJob();
    const pending=f.relay.callTool('root_shell',{command:'id',request_id:'stable-operation'},'owner-a',1);
    await delay(25);
    const claimed=await (await f.relay.nextJob()).json();
    await f.relay.saveResult(claimed.job.id,{status:'completed',result:{content:[],isError:false}});
    await pending;
    await assert.rejects(f.relay.callTool('root_shell',{command:'pwd',request_id:'stable-operation'},'owner-a',1),/changed arguments/);
    assert.equal(f.sqlite.prepare('SELECT COUNT(*) AS n FROM phone_jobs').get().n,1);
  } finally {f.close();}
});

test("expired queued/running jobs become uncertain and are not claimed again", async () => {
  const f = await fixture();
  try {
    const timestamp = f.relay.now();
    const insert = f.sqlite.prepare("INSERT INTO phone_jobs (id,request_key,owner,tool,arguments,state,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)");
    for (const state of ["queued", "running"]) {
      insert.run("fixture-" + state, "key-" + state, "fixture-owner-a", "phone_status", "{}", state, timestamp - 121, timestamp - 1);
    }
    assert.equal((await f.relay.nextJob()).status, 204);
    const states = f.sqlite.prepare("SELECT state FROM phone_jobs ORDER BY id").all();
    assert.deepEqual(states.map(row => row.state), ["uncertain", "uncertain"]);
    const result = await f.relay.jobResult("fixture-queued", "fixture-owner-a");
    assert.equal(result.isError, true);
    assert.equal(JSON.parse(result.content[0].text).status, "uncertain");
    assert.equal((await f.relay.nextJob()).status, 204);
  } finally { f.close(); }
});
test("cancel applies only to owner queued jobs and is idempotent",async()=>{
 const f=await fixture();
 try{
  const insert=f.sqlite.prepare("INSERT INTO phone_jobs(id,request_key,owner,tool,arguments,state,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)");
  const t=f.relay.now();
  for(const state of ['queued','running'])insert.run('cancel-'+state,'key-'+state,'owner-a','phone_status','{}',state,t,t+120);
  assert.equal((await f.relay.cancelJob('cancel-queued','owner-b')).isError,true);
  assert.equal((await f.relay.cancelJob('cancel-running','owner-a')).isError,true);
  for(let i=0;i<2;i++)assert.equal(JSON.parse((await f.relay.cancelJob('cancel-queued','owner-a')).content[0].text).status,'cancelled');
  assert.equal(f.sqlite.prepare("SELECT state FROM phone_jobs WHERE id='cancel-running'").get().state,'running');
  assert.equal((await f.relay.nextJob()).status,204);
  assert.equal(JSON.parse((await f.relay.jobResult('cancel-queued','owner-a')).content[0].text).status,'cancelled');
 }finally{f.close();}
});
test("empty batch and invalid stable identity are rejected before queueing",async()=>{
 const f=await fixture();
 try{
  await assert.rejects(f.relay.callTool('phone_use_batch',{request_id:'fixture_batch_1',session_id:'s',observation_id:'o',steps:[]},'owner-a','outer1'),/few|items/);
  await assert.rejects(f.relay.callTool('phone_use_capabilities',{request_id:'../../evil'},'owner-a','outer2'),/pattern/);
  assert.equal(f.sqlite.prepare('SELECT count(*) AS n FROM phone_jobs').get().n,0);
 }finally{f.close();}
});
