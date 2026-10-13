// src/core/store/sqlite/memory-store.ts
import { randomUUID } from "node:crypto";
import { createRequire as createRequire2 } from "node:module";
import { mkdirSync, existsSync } from "node:fs";
import path from "node:path";

// src/core/store/isolation.ts
var DEFAULT_ISOLATION_ID = "default";
function rowMatchesIsolation(row, filter) {
  if (!filter) return true;
  if (filter.teamId !== void 0 && row.team_id !== filter.teamId) return false;
  if (filter.userId !== void 0 && row.user_id !== filter.userId) return false;
  if (filter.agentId !== void 0 && row.agent_id !== filter.agentId) return false;
  if (filter.sessionId !== void 0 && row.session_id !== filter.sessionId) return false;
  if (filter.taskId !== void 0 && row.task_id !== filter.taskId) return false;
  if (filter.sessionKey !== void 0 && row.session_key !== filter.sessionKey) return false;
  return true;
}

// src/core/skill/skill-store-ddl.ts
var SKILLS_DDL = `
  CREATE TABLE IF NOT EXISTS skills (
    row_id          TEXT PRIMARY KEY,
    skill_id        TEXT NOT NULL,
    version         INTEGER NOT NULL,
    is_head         INTEGER NOT NULL DEFAULT 1,

    user_id         TEXT NOT NULL,
    owner_agent_id  TEXT NOT NULL,
    team_id         TEXT NOT NULL,
    task_id         TEXT NOT NULL DEFAULT '',

    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    content         TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    manifest_json   TEXT NOT NULL DEFAULT '[]',
    storage_dir     TEXT NOT NULL,

    status          TEXT NOT NULL DEFAULT 'active',
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    created_at_ms   INTEGER NOT NULL,
    updated_at_ms   INTEGER NOT NULL,

    UNIQUE(skill_id, version)
  );

  CREATE UNIQUE INDEX IF NOT EXISTS uniq_skills_team_agent_name_head
    ON skills(team_id, owner_agent_id, name) WHERE is_head=1 AND status='active';

  CREATE INDEX IF NOT EXISTS idx_skills_team_head
    ON skills(team_id, is_head, status);

  CREATE INDEX IF NOT EXISTS idx_skills_owner_head
    ON skills(owner_agent_id, is_head, status);

  CREATE INDEX IF NOT EXISTS idx_skills_user
    ON skills(user_id, is_head);

  CREATE INDEX IF NOT EXISTS idx_skills_skill_version
    ON skills(skill_id, version DESC);

  CREATE INDEX IF NOT EXISTS idx_skills_task_audit
    ON skills(task_id, created_at_ms DESC);
`;
var SKILL_FTS_DDL = `
  CREATE VIRTUAL TABLE IF NOT EXISTS skill_fts USING fts5(
    name,
    description,
    content,
    skill_id UNINDEXED,
    team_id UNINDEXED,
    owner_agent_id UNINDEXED,
    task_id UNINDEXED,
    user_id UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 1'
  );
`;

// src/core/memory-generation-log/types.ts
import { createHash } from "node:crypto";
function buildMemoryGenerationRefId(layer, memoryId) {
  const digest = createHash("sha256").update(memoryId).digest("hex").slice(0, 40);
  return `mgr:${layer}:${digest}`;
}

// src/core/store/tokenize.ts
import { createRequire } from "node:module";
var require2 = createRequire(import.meta.url);
var _jieba;
function getJieba() {
  if (_jieba !== void 0) return _jieba;
  try {
    const { Jieba } = require2("@node-rs/jieba");
    const { dict } = require2("@node-rs/jieba/dict");
    _jieba = Jieba.withDict(dict);
  } catch {
    _jieba = null;
  }
  return _jieba;
}
function tokenizeForFts(raw) {
  const jieba = getJieba();
  if (!jieba) return raw;
  const tokens = jieba.cutForSearch(raw, true);
  return tokens.join(" ");
}
function bm25RankToScore(rank) {
  if (!Number.isFinite(rank)) return 1 / (1 + 999);
  if (rank < 0) {
    const relevance = -rank;
    return relevance / (1 + relevance);
  }
  return 1 / (1 + rank);
}

// src/core/store/sqlite/memory-store.ts
var TAG = "[memory-tdai][sqlite]";
var require3 = createRequire2(import.meta.url);
function requireNodeSqlite() {
  return require3("node:sqlite");
}
var VectorStore = class _VectorStore {
  db;
  dimensions;
  logger;
  /** @see IMemoryStore.supportsDeferredEmbedding */
  supportsDeferredEmbedding = true;
  /**
   * When `true`, the store is in a degraded state (e.g. sqlite-vec failed to
   * load, or init() encountered an unrecoverable error).  All public methods
   * become safe no-ops so the plugin never blocks the main OpenClaw flow.
   */
  degraded = false;
  /** Tracks whether close() has been called to prevent double-close errors. */
  closed = false;
  /**
   * `true` when vec0 virtual tables (l1_vec / l0_vec) have been created and
   * their prepared statements are ready.  When `dimensions === 0` (i.e.
   * provider="none"), vec0 tables are deferred and this stays `false`.
   */
  vecTablesReady = false;
  // Prepared statements — L1 (initialized in init())
  stmtUpsertMeta;
  stmtDeleteVec;
  // optional — only set when vecTablesReady
  stmtInsertVec;
  // optional — only set when vecTablesReady
  stmtDeleteMeta;
  stmtGetMeta;
  stmtSearchVec;
  // optional — only set when vecTablesReady
  stmtQueryBySessionId;
  stmtQueryBySessionIdSince;
  stmtQueryBySessionKey;
  stmtQueryBySessionKeySince;
  stmtQueryAll;
  stmtQueryAllSince;
  // Prepared statements — L0 (initialized in init())
  stmtL0UpsertMeta;
  stmtL0DeleteVec;
  // optional — only set when vecTablesReady
  stmtL0InsertVec;
  // optional — only set when vecTablesReady
  stmtL0DeleteMeta;
  stmtL0GetMeta;
  stmtL0SearchVec;
  // optional — only set when vecTablesReady
  /** L0 query for L1 runner: all messages for a session key */
  stmtL0QueryAll;
  /** L0 query for L1 runner: messages after a timestamp cursor */
  stmtL0QueryAfter;
  /** L1 cursor-based pagination for migration (by PK) */
  stmtL1QueryMigrationCursor;
  /** L0 cursor-based pagination for migration (by PK) */
  stmtL0QueryMigrationCursor;
  // FTS5 tables availability flag (created best-effort — may be false if fts5 is not compiled in)
  ftsAvailable = false;
  // Prepared statements — FTS5 L1 (initialized in init())
  stmtL1FtsInsert;
  stmtL1FtsDelete;
  stmtL1FtsSearch;
  // Prepared statements — FTS5 L0 (initialized in init())
  stmtL0FtsInsert;
  stmtL0FtsDelete;
  stmtL0FtsSearch;
  /**
   * Create a VectorStore instance.
   *
   * Note: After construction, you MUST call `init()` to load the sqlite-vec
   * extension and create the schema.
   */
  constructor(dbPath, dimensions, logger) {
    this.dimensions = dimensions;
    this.logger = logger;
    const dbDir = path.dirname(dbPath);
    if (!existsSync(dbDir)) {
      mkdirSync(dbDir, { recursive: true });
    }
    const { DatabaseSync: DbSync } = requireNodeSqlite();
    this.db = new DbSync(dbPath, { allowExtension: true });
    this.db.exec("PRAGMA busy_timeout = 5000");
    this.db.exec("PRAGMA journal_mode = WAL");
    this.db.exec("PRAGMA cache_size = -65536");
    this.db.exec("PRAGMA mmap_size = 134217728");
    this.db.exec("PRAGMA wal_autocheckpoint = 1000");
  }
  /**
   * Expose the underlying `DatabaseSync` handle for tightly-coupled co-tenants
   * that need to live in the SAME SQLite connection (skill_meta / skill_fts /
   * skill_vec live alongside l1_records — see SKILL_ENGINEERING_DESIGN §13.3).
   *
   * Intentional escape hatch: do NOT use this for unrelated stores. Sharing
   * the connection is what gives us one sqlite-vec load + one WAL session +
   * cross-table transactions; opening a second connection on `vectors.db`
   * would defeat all three.
   */
  getRawDb() {
    return this.db;
  }
  /** Embedding dimension this store was opened with (0 when provider="none"). */
  getEmbeddingDimensions() {
    return this.dimensions;
  }
  /**
   * Whether the store is in degraded mode (e.g. sqlite-vec failed to load).
   * When degraded, all write/search operations become safe no-ops.
   */
  isDegraded() {
    return this.degraded;
  }
  /**
   * Load sqlite-vec extension and initialize database schema.
   * Must be called once after construction.
   *
   * @param providerInfo  Current embedding provider info. When provided,
   *   the store compares it against the persisted metadata. If the provider,
   *   model, or dimensions changed, the vector tables are dropped and
   *   re-created with the new dimensions, and `needsReindex: true` is returned
   *   so the caller can schedule a full re-embed.
   */
  init(providerInfo) {
    if (this.dimensions > 0) {
      try {
        const sqliteVec = require3("sqlite-vec");
        this.db.enableLoadExtension(true);
        sqliteVec.load(this.db);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        this.logger?.error(
          `${TAG} Failed to load sqlite-vec extension: ${message}. VectorStore entering degraded mode \u2014 all operations will be no-ops.`
        );
        this.degraded = true;
        return { needsReindex: false, reason: `sqlite-vec load failed: ${message}` };
      }
    }
    try {
      return this.initSchema(providerInfo);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.logger?.error(
        `${TAG} Schema initialization failed: ${message}. VectorStore entering degraded mode.`
      );
      this.degraded = true;
      return { needsReindex: false, reason: `schema init failed: ${message}` };
    }
  }
  /**
   * Internal schema initialization — separated from init() so we can
   * catch errors at the top level and degrade gracefully.
   */
  initSchema(providerInfo) {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS embedding_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      )
    `);
    let needsReindex = false;
    let reindexReason;
    const savedMeta = this.readEmbeddingMeta();
    if (providerInfo) {
      if (savedMeta) {
        const providerChanged = savedMeta.provider !== providerInfo.provider;
        const modelChanged = savedMeta.model !== providerInfo.model;
        const dimsChanged = savedMeta.dimensions !== this.dimensions;
        if (providerChanged || modelChanged || dimsChanged) {
          const reasons = [];
          if (providerChanged) reasons.push(`provider: ${savedMeta.provider} \u2192 ${providerInfo.provider}`);
          if (modelChanged) reasons.push(`model: ${savedMeta.model} \u2192 ${providerInfo.model}`);
          if (dimsChanged) reasons.push(`dimensions: ${savedMeta.dimensions} \u2192 ${this.dimensions}`);
          reindexReason = reasons.join(", ");
          this.logger?.info(
            `${TAG} Embedding config changed (${reindexReason}). Dropping vector tables for rebuild...`
          );
          this.dropVectorTables();
          needsReindex = true;
        }
      } else {
        const l1Count = this.tableRowCount("l1_records");
        const l0Count = this.tableRowCount("l0_conversations");
        const existingVecDims = this.getVecTableDimensions();
        if (l1Count > 0 || l0Count > 0) {
          this.logger?.info(
            `${TAG} No embedding_meta found but existing data exists (L1=${l1Count}, L0=${l0Count}). Dropping vector tables for safety...`
          );
          this.dropVectorTables();
          needsReindex = true;
          reindexReason = "legacy DB without embedding_meta \u2014 cannot verify vector compatibility";
        } else if (existingVecDims !== null && existingVecDims !== this.dimensions) {
          this.logger?.info(
            `${TAG} vec0 table dimension mismatch (existing=${existingVecDims}, required=${this.dimensions}). Dropping vector tables for rebuild...`
          );
          this.dropVectorTables();
        }
      }
    }
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS l1_records (
        record_id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        type TEXT DEFAULT '',
        priority INTEGER DEFAULT 50,
        scene_name TEXT DEFAULT '',
        session_key TEXT DEFAULT '',
        session_id TEXT DEFAULT 'default',
        team_id TEXT DEFAULT 'default',
        task_id TEXT DEFAULT '',
        user_id TEXT NOT NULL DEFAULT 'default',
        agent_id TEXT NOT NULL DEFAULT 'default',
        version INTEGER NOT NULL DEFAULT 0,
        timestamp_str TEXT DEFAULT '',
        timestamp_start TEXT DEFAULT '',
        timestamp_end TEXT DEFAULT '',
        created_time TEXT DEFAULT '',
        updated_time TEXT DEFAULT '',
        metadata_json TEXT DEFAULT '{}'
      )
    `);
    try {
      this.db.exec("ALTER TABLE l1_records ADD COLUMN team_id TEXT DEFAULT 'default'");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE l1_records ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE l1_records ADD COLUMN agent_id TEXT NOT NULL DEFAULT 'default'");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE l1_records ADD COLUMN task_id TEXT DEFAULT ''");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE l1_records ADD COLUMN version INTEGER NOT NULL DEFAULT 0");
    } catch {
    }
    this.db.prepare("UPDATE l1_records SET team_id = ? WHERE team_id = '' OR team_id IS NULL").run(DEFAULT_ISOLATION_ID);
    this.db.prepare("UPDATE l1_records SET user_id = ? WHERE user_id = '' OR user_id IS NULL").run(DEFAULT_ISOLATION_ID);
    this.db.prepare("UPDATE l1_records SET agent_id = ? WHERE agent_id = '' OR agent_id IS NULL").run(DEFAULT_ISOLATION_ID);
    this.db.prepare("UPDATE l1_records SET session_id = ? WHERE session_id = '' OR session_id IS NULL").run(DEFAULT_ISOLATION_ID);
    this.db.exec("UPDATE l1_records SET version = 0 WHERE version IS NULL OR version < 0");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_type ON l1_records(type)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_session_key ON l1_records(session_key)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_session_id ON l1_records(session_id)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_scene ON l1_records(scene_name)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_ts_start ON l1_records(timestamp_start)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_ts_end ON l1_records(timestamp_end)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_session_updated ON l1_records(session_id, updated_time)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_sessionkey_updated ON l1_records(session_key, updated_time)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_task_updated ON l1_records(task_id, updated_time)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_team_agent_updated ON l1_records(team_id, agent_id, updated_time)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_user_agent_session ON l1_records(user_id, agent_id, session_id)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_user_updated  ON l1_records(user_id, updated_time)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l1_agent_updated ON l1_records(agent_id, updated_time)");
    if (this.dimensions > 0) {
      this.db.exec(`
        CREATE VIRTUAL TABLE IF NOT EXISTS l1_vec USING vec0(
          record_id TEXT PRIMARY KEY,
          embedding float[${this.dimensions}] distance_metric=cosine,
          updated_time TEXT DEFAULT ''
        )
      `);
    }
    this.stmtUpsertMeta = this.db.prepare(`
      INSERT INTO l1_records (
        record_id, content, type, priority, scene_name, session_key, session_id,
        team_id, task_id, version, timestamp_str, timestamp_start, timestamp_end,
        created_time, updated_time, metadata_json,
        user_id, agent_id
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(record_id) DO UPDATE SET
        content=excluded.content,
        type=excluded.type,
        priority=excluded.priority,
        scene_name=excluded.scene_name,
        team_id=excluded.team_id,
        task_id=excluded.task_id,
        version=excluded.version,
        timestamp_str=excluded.timestamp_str,
        timestamp_start=excluded.timestamp_start,
        timestamp_end=excluded.timestamp_end,
        updated_time=excluded.updated_time,
        metadata_json=excluded.metadata_json,
        user_id=excluded.user_id,
        agent_id=excluded.agent_id
    `);
    if (this.dimensions > 0) {
      this.stmtDeleteVec = this.db.prepare("DELETE FROM l1_vec WHERE record_id = ?");
      this.stmtInsertVec = this.db.prepare("INSERT INTO l1_vec (record_id, embedding, updated_time) VALUES (?, ?, ?)");
    }
    this.stmtDeleteMeta = this.db.prepare("DELETE FROM l1_records WHERE record_id = ?");
    this.stmtGetMeta = this.db.prepare(`
      SELECT content, type, priority, scene_name, session_key, session_id, team_id, task_id, user_id, agent_id,
             version, timestamp_str, timestamp_start, timestamp_end, metadata_json
      FROM l1_records WHERE record_id = ?
    `);
    if (this.dimensions > 0) {
      this.stmtSearchVec = this.db.prepare(`
        SELECT record_id, distance
        FROM l1_vec
        WHERE embedding MATCH ?
          AND k = ?
        ORDER BY distance
      `);
    }
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS l0_conversations (
        record_id TEXT PRIMARY KEY,
        session_key TEXT NOT NULL,
        session_id TEXT DEFAULT 'default',
        team_id TEXT DEFAULT 'default',
        task_id TEXT DEFAULT '',
        user_id TEXT NOT NULL DEFAULT 'default',
        agent_id TEXT NOT NULL DEFAULT 'default',
        role TEXT NOT NULL DEFAULT '',
        message_text TEXT NOT NULL,
        recorded_at TEXT DEFAULT '',
        timestamp INTEGER DEFAULT 0
      )
    `);
    try {
      this.db.exec("ALTER TABLE l0_conversations ADD COLUMN timestamp INTEGER DEFAULT 0");
      this.logger?.debug?.(`${TAG} Migrated l0_conversations: added timestamp column`);
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE l0_conversations ADD COLUMN team_id TEXT DEFAULT 'default'");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE l0_conversations ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE l0_conversations ADD COLUMN agent_id TEXT NOT NULL DEFAULT 'default'");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE l0_conversations ADD COLUMN task_id TEXT DEFAULT ''");
    } catch {
    }
    this.db.prepare("UPDATE l0_conversations SET team_id = ? WHERE team_id = '' OR team_id IS NULL").run(DEFAULT_ISOLATION_ID);
    this.db.prepare("UPDATE l0_conversations SET user_id = ? WHERE user_id = '' OR user_id IS NULL").run(DEFAULT_ISOLATION_ID);
    this.db.prepare("UPDATE l0_conversations SET agent_id = ? WHERE agent_id = '' OR agent_id IS NULL").run(DEFAULT_ISOLATION_ID);
    this.db.prepare("UPDATE l0_conversations SET session_id = ? WHERE session_id = '' OR session_id IS NULL").run(DEFAULT_ISOLATION_ID);
    try {
      this.db.exec(SKILLS_DDL);
      this.db.exec(SKILL_FTS_DDL);
    } catch (err) {
      this.logger?.warn(
        `${TAG} Skill base schema init failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
    }
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_session ON l0_conversations(session_key)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_session_id ON l0_conversations(session_id)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_task ON l0_conversations(task_id)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_team_agent ON l0_conversations(team_id, agent_id)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_recorded ON l0_conversations(recorded_at)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_timestamp ON l0_conversations(timestamp)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_user_agent_session ON l0_conversations(user_id, agent_id, session_id)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_user_recorded  ON l0_conversations(user_id, recorded_at)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_l0_agent_recorded ON l0_conversations(agent_id, recorded_at)");
    if (this.dimensions > 0) {
      this.db.exec(`
        CREATE VIRTUAL TABLE IF NOT EXISTS l0_vec USING vec0(
          record_id TEXT PRIMARY KEY,
          embedding float[${this.dimensions}] distance_metric=cosine,
          recorded_at TEXT DEFAULT ''
        )
      `);
    }
    this.stmtL0UpsertMeta = this.db.prepare(`
      INSERT INTO l0_conversations (
        record_id, session_key, session_id, team_id, task_id, role, message_text, recorded_at, timestamp,
        user_id, agent_id
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(record_id) DO UPDATE SET
        message_text=excluded.message_text,
        recorded_at=excluded.recorded_at,
        timestamp=excluded.timestamp,
        team_id=excluded.team_id,
        task_id=excluded.task_id,
        user_id=excluded.user_id,
        agent_id=excluded.agent_id
    `);
    if (this.dimensions > 0) {
      this.stmtL0DeleteVec = this.db.prepare("DELETE FROM l0_vec WHERE record_id = ?");
      this.stmtL0InsertVec = this.db.prepare("INSERT INTO l0_vec (record_id, embedding, recorded_at) VALUES (?, ?, ?)");
    }
    this.stmtL0DeleteMeta = this.db.prepare("DELETE FROM l0_conversations WHERE record_id = ?");
    this.stmtL0GetMeta = this.db.prepare(`
      SELECT session_key, session_id, team_id, task_id, user_id, agent_id, role, message_text, recorded_at, timestamp
      FROM l0_conversations WHERE record_id = ?
    `);
    if (this.dimensions > 0) {
      this.stmtL0SearchVec = this.db.prepare(`
        SELECT record_id, distance
        FROM l0_vec
        WHERE embedding MATCH ?
          AND k = ?
        ORDER BY distance
      `);
    }
    this.stmtL0QueryAll = this.db.prepare(`
      SELECT record_id, session_key, session_id, team_id, task_id, user_id, agent_id, role, message_text, recorded_at, timestamp
      FROM l0_conversations
      WHERE session_key = ?
      ORDER BY recorded_at ASC
      LIMIT ?
    `);
    this.stmtL0QueryAfter = this.db.prepare(`
      SELECT record_id, session_key, session_id, team_id, task_id, user_id, agent_id, role, message_text, recorded_at, timestamp
      FROM l0_conversations
      WHERE session_key = ? AND recorded_at > ?
      ORDER BY recorded_at ASC
      LIMIT ?
    `);
    this.stmtL0QueryMigrationCursor = this.db.prepare(`
      SELECT record_id, session_key, session_id, role, message_text, recorded_at, timestamp
      FROM l0_conversations
      WHERE record_id > ?
      ORDER BY record_id ASC
      LIMIT ?
    `);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS entity_teams (
        team_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        owner_user_id TEXT NOT NULL,
        user_ids_json TEXT NOT NULL DEFAULT '[]',
        agent_ids_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS entity_users (
        user_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        job_description TEXT DEFAULT '',
        team_ids_json TEXT NOT NULL DEFAULT '[]',
        task_ids_json TEXT NOT NULL DEFAULT '[]',
        owned_agent_ids_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS entity_agents (
        agent_id TEXT PRIMARY KEY,
        team_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        prompt TEXT DEFAULT '',
        owner_user_id TEXT DEFAULT '',
        visibility TEXT NOT NULL DEFAULT 'team',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS entity_tasks (
        task_id TEXT PRIMARY KEY,
        team_id TEXT NOT NULL,
        creator_user_id TEXT NOT NULL,
        title TEXT DEFAULT '',
        description TEXT DEFAULT '',
        source_type TEXT NOT NULL DEFAULT 'manual',
        source_url TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        auto_assign_floating_assets INTEGER NOT NULL DEFAULT 0,
        risk_level TEXT NOT NULL DEFAULT 'low',
        agent_ids_json TEXT NOT NULL DEFAULT '[]',
        user_ids_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS entity_knowledge (
        knowledge_id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        service_url TEXT NOT NULL,
        name TEXT NOT NULL,
        summary TEXT,
        team_id TEXT NOT NULL,
        agent_id TEXT NOT NULL DEFAULT '',
        user_id TEXT,
        repo_url TEXT,
        branch TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    try {
      this.db.exec("ALTER TABLE entity_knowledge ADD COLUMN agent_id TEXT NOT NULL DEFAULT ''");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE entity_teams ADD COLUMN user_ids_json TEXT NOT NULL DEFAULT '[]'");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE entity_teams ADD COLUMN agent_ids_json TEXT NOT NULL DEFAULT '[]'");
    } catch {
    }
    try {
      this.db.exec("ALTER TABLE entity_tasks ADD COLUMN user_ids_json TEXT NOT NULL DEFAULT '[]'");
    } catch {
    }
    this.db.exec("DROP INDEX IF EXISTS idx_entity_teams_name");
    this.db.exec("DROP INDEX IF EXISTS idx_entity_agents_team_name");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_entity_teams_name ON entity_teams(name)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_entity_users_status ON entity_users(status)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_entity_agents_team_name ON entity_agents(team_id, name)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_entity_agents_team_status ON entity_agents(team_id, status)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_entity_tasks_team_status ON entity_tasks(team_id, status)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_entity_knowledge_team ON entity_knowledge(team_id)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_entity_knowledge_team_type ON entity_knowledge(team_id, type)");
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS memory_audit (
        audit_id      TEXT PRIMARY KEY,
        record_id     TEXT NOT NULL,
        layer         TEXT NOT NULL CHECK (layer IN ('L1','L2','L3')),
        action        TEXT NOT NULL CHECK (action IN ('update','delete')),
        team_id       TEXT,
        agent_id      TEXT,
        user_id       TEXT,
        task_id       TEXT,
        version       INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        request_id    TEXT
      )
    `);
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_memory_audit_record    ON memory_audit(record_id, updated_at_ms)");
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_memory_audit_isolation ON memory_audit(team_id, agent_id, user_id, task_id)");
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS memory_prompts (
        memory_prompt_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        layer TEXT NOT NULL CHECK (layer IN ('l1','l2','l3')),
        prompt TEXT NOT NULL,
        version INTEGER NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active','deleting')),
        created_by TEXT,
        updated_by TEXT,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_memory_prompts_layer_updated
        ON memory_prompts(layer, updated_at_ms);
      CREATE INDEX IF NOT EXISTS idx_memory_prompts_status
        ON memory_prompts(status);

      CREATE TABLE IF NOT EXISTS memory_prompt_settings (
        setting_id TEXT PRIMARY KEY,
        target_type TEXT NOT NULL CHECK (target_type IN ('instance','team','agent')),
        team_id TEXT,
        agent_id TEXT,
        layer TEXT NOT NULL CHECK (layer IN ('l1','l2','l3')),
        memory_prompt_id TEXT NOT NULL,
        updated_by TEXT,
        updated_at_ms INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_memory_prompt_settings_prompt
        ON memory_prompt_settings(memory_prompt_id);
      CREATE INDEX IF NOT EXISTS idx_memory_prompt_settings_target
        ON memory_prompt_settings(team_id, agent_id, layer);

      CREATE TABLE IF NOT EXISTS memory_prompt_setting_logs (
        setting_log_id TEXT PRIMARY KEY,
        target_type TEXT NOT NULL CHECK (target_type IN ('instance','team','agent')),
        team_id TEXT,
        agent_id TEXT,
        layer TEXT NOT NULL CHECK (layer IN ('l1','l2','l3')),
        action TEXT NOT NULL CHECK (action IN ('apply','replace','clear')),
        reason TEXT NOT NULL CHECK (reason IN ('explicit','prompt_deleted')),
        before_memory_prompt_id TEXT,
        after_memory_prompt_id TEXT,
        operator_id TEXT,
        operated_at_ms INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_memory_prompt_logs_prompt_before
        ON memory_prompt_setting_logs(before_memory_prompt_id, operated_at_ms);
      CREATE INDEX IF NOT EXISTS idx_memory_prompt_logs_prompt_after
        ON memory_prompt_setting_logs(after_memory_prompt_id, operated_at_ms);
      CREATE INDEX IF NOT EXISTS idx_memory_prompt_logs_target
        ON memory_prompt_setting_logs(team_id, agent_id, operated_at_ms);

      CREATE TABLE IF NOT EXISTS memory_generation_refs (
        generation_ref_id TEXT PRIMARY KEY,
        layer TEXT NOT NULL CHECK (layer IN ('l1','l2','l3')),
        memory_id TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        generation_log_id TEXT NOT NULL,
        generation_log_key TEXT NOT NULL,
        memory_prompt_id TEXT NOT NULL,
        memory_prompt_version INTEGER NOT NULL,
        memory_prompt_source TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_memory_generation_refs_memory
        ON memory_generation_refs(layer, memory_id);
    `);
    this.db.exec("CREATE INDEX IF NOT EXISTS idx_memory_audit_time      ON memory_audit(updated_at_ms)");
    try {
      const needsFtsRebuild = this.migrateFtsTablesIfNeeded();
      this.db.exec(`
        CREATE VIRTUAL TABLE IF NOT EXISTS l1_fts USING fts5(
          content,
          content_original UNINDEXED,
          record_id UNINDEXED,
          type UNINDEXED,
          priority UNINDEXED,
          scene_name UNINDEXED,
          session_key UNINDEXED,
          session_id UNINDEXED,
          team_id UNINDEXED,
          task_id UNINDEXED,
          user_id UNINDEXED,
          agent_id UNINDEXED,
          version UNINDEXED,
          timestamp_str UNINDEXED,
          timestamp_start UNINDEXED,
          timestamp_end UNINDEXED,
          metadata_json UNINDEXED
        )
      `);
      this.db.exec(`
        CREATE VIRTUAL TABLE IF NOT EXISTS l0_fts USING fts5(
          message_text,
          message_text_original UNINDEXED,
          record_id UNINDEXED,
          session_key UNINDEXED,
          session_id UNINDEXED,
          team_id UNINDEXED,
          task_id UNINDEXED,
          user_id UNINDEXED,
          agent_id UNINDEXED,
          role UNINDEXED,
          recorded_at UNINDEXED,
          timestamp UNINDEXED
        )
      `);
      this.stmtL1FtsInsert = this.db.prepare(`
        INSERT INTO l1_fts (content, content_original, record_id, type, priority, scene_name,
          session_key, session_id, team_id, task_id, user_id, agent_id, version,
          timestamp_str, timestamp_start, timestamp_end, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `);
      this.stmtL1FtsDelete = this.db.prepare("DELETE FROM l1_fts WHERE record_id = ?");
      this.stmtL1FtsSearch = this.db.prepare(`
        SELECT record_id, content_original AS content, type, priority, scene_name,
               session_key, session_id, team_id, task_id, user_id, agent_id, version,
               timestamp_str, timestamp_start, timestamp_end,
               metadata_json,
               bm25(l1_fts) AS rank
        FROM l1_fts
        WHERE l1_fts MATCH ?
        ORDER BY rank ASC
        LIMIT ?
      `);
      this.stmtL0FtsInsert = this.db.prepare(`
        INSERT INTO l0_fts (message_text, message_text_original, record_id,
          session_key, session_id, team_id, task_id, user_id, agent_id, role, recorded_at, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `);
      this.stmtL0FtsDelete = this.db.prepare("DELETE FROM l0_fts WHERE record_id = ?");
      this.stmtL0FtsSearch = this.db.prepare(`
        SELECT record_id, message_text_original AS message_text,
               session_key, session_id, team_id, task_id, user_id, agent_id, role, recorded_at, timestamp,
               bm25(l0_fts) AS rank
        FROM l0_fts
        WHERE l0_fts MATCH ?
        ORDER BY rank ASC
        LIMIT ?
      `);
      this.ftsAvailable = true;
      this.logger?.debug?.(`${TAG} FTS5 tables initialized (l1_fts, l0_fts) [schema v2 \u2014 jieba segmented]`);
      if (needsFtsRebuild) {
        this.rebuildFtsIndex();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.ftsAvailable = false;
      this.logger?.warn(
        `${TAG} FTS5 tables NOT available (fts5 may not be compiled in): ${message}. FTS-based keyword search will be unavailable; recall will use in-memory scoring if needed.`
      );
    }
    if (providerInfo) {
      this.writeEmbeddingMeta({
        provider: providerInfo.provider,
        model: providerInfo.model,
        dimensions: this.dimensions
      });
    }
    this.vecTablesReady = this.dimensions > 0;
    const l1QueryCols = `record_id, content, type, priority, scene_name, session_key, session_id,
      team_id, task_id, user_id, agent_id, version,
      timestamp_str, timestamp_start, timestamp_end,
      created_time, updated_time, metadata_json`;
    this.stmtQueryBySessionId = this.db.prepare(`
      SELECT ${l1QueryCols} FROM l1_records
      WHERE session_id = ?
      ORDER BY updated_time ASC
    `);
    this.stmtQueryBySessionIdSince = this.db.prepare(`
      SELECT ${l1QueryCols} FROM l1_records
      WHERE session_id = ? AND updated_time > ?
      ORDER BY updated_time ASC
    `);
    this.stmtQueryBySessionKey = this.db.prepare(`
      SELECT ${l1QueryCols} FROM l1_records
      WHERE session_key = ?
      ORDER BY updated_time ASC
    `);
    this.stmtQueryBySessionKeySince = this.db.prepare(`
      SELECT ${l1QueryCols} FROM l1_records
      WHERE session_key = ? AND updated_time > ?
      ORDER BY updated_time ASC
    `);
    this.stmtQueryAll = this.db.prepare(`
      SELECT ${l1QueryCols} FROM l1_records
      ORDER BY updated_time ASC
    `);
    this.stmtQueryAllSince = this.db.prepare(`
      SELECT ${l1QueryCols} FROM l1_records
      WHERE updated_time > ?
      ORDER BY updated_time ASC
    `);
    this.stmtL1QueryMigrationCursor = this.db.prepare(`
      SELECT ${l1QueryCols} FROM l1_records
      WHERE record_id > ?
      ORDER BY record_id ASC
      LIMIT ?
    `);
    this.logger?.debug?.(`${TAG} Initialized (dimensions=${this.dimensions})`);
    return { needsReindex, reason: reindexReason };
  }
  // ── Embedding meta helpers ──────────────────────────────
  readEmbeddingMeta() {
    try {
      const row = this.db.prepare("SELECT value FROM embedding_meta WHERE key = ?").get("embedding_provider_info");
      if (!row) return null;
      return JSON.parse(row.value);
    } catch {
      return null;
    }
  }
  writeEmbeddingMeta(meta) {
    this.db.prepare(
      "INSERT INTO embedding_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value"
    ).run("embedding_provider_info", JSON.stringify(meta));
  }
  /** Allowed table names for row counting (whitelist to prevent SQL injection). */
  static COUNTABLE_TABLES = /* @__PURE__ */ new Set(["l1_records", "l0_conversations"]);
  /**
   * Extra rows to retrieve from vec0 KNN search to compensate for legacy
   * zero-vector placeholders that may still linger from older data.
   */
  static ZERO_VEC_BUFFER = 10;
  /** Default result limit for FTS5 keyword searches. */
  static FTS_DEFAULT_LIMIT = 20;
  tableRowCount(table) {
    if (!_VectorStore.COUNTABLE_TABLES.has(table)) {
      this.logger?.warn(`${TAG} tableRowCount: rejected unknown table name "${table}"`);
      return 0;
    }
    try {
      const row = this.db.prepare(`SELECT COUNT(*) AS cnt FROM ${table}`).get();
      return row?.cnt ?? 0;
    } catch {
      return 0;
    }
  }
  /**
   * Detect the embedding dimension of an existing vec0 table by inspecting
   * the DDL stored in sqlite_master.  Returns `null` if the table doesn't
   * exist or the dimension cannot be determined.
   *
   * The vec0 DDL looks like:
   *   CREATE VIRTUAL TABLE l1_vec USING vec0(... embedding float[768] ...)
   * We parse the number inside `float[N]`.
   */
  getVecTableDimensions() {
    try {
      const row = this.db.prepare("SELECT sql FROM sqlite_master WHERE type='table' AND name=?").get("l1_vec");
      if (!row?.sql) return null;
      const match = row.sql.match(/float\[(\d+)\]/);
      return match ? Number(match[1]) : null;
    } catch {
      return null;
    }
  }
  /**
   * Drop both L1 and L0 vector virtual tables.
   * Metadata tables (l1_records, l0_conversations) are preserved — only
   * the vec0 tables need to be rebuilt with the new dimensions.
   */
  dropVectorTables() {
    this.db.exec("DROP TABLE IF EXISTS l1_vec");
    this.db.exec("DROP TABLE IF EXISTS l0_vec");
    this.logger?.info(`${TAG} Dropped vector tables (l1_vec, l0_vec)`);
  }
  /**
   * Write or update a memory record (metadata + vector).
   * Uses a manual transaction for atomicity.
   *
   * If `embedding` is `undefined` or a zero vector (all elements are 0), only
   * the metadata row is written — the vec0 table is left untouched.  This
   * allows callers without an EmbeddingService to still persist metadata + FTS
   * without constructing a throwaway zero-vector, and prevents placeholder
   * zero vectors (from embedding-service failures) from polluting KNN search
   * results with null / NaN distances.
   *
   * **Fault-tolerant**: catches all errors internally so that a vector store
   * failure never propagates to the caller / main OpenClaw flow.
   * Returns `true` on success, `false` on failure (logged as warning).
   */
  upsertL1(record, embedding) {
    if (this.degraded) {
      this.logger?.warn(`${TAG} [L1-upsert] SKIPPED (degraded mode) id=${record.id}`);
      return false;
    }
    try {
      const { id: recordId, timestamps } = record;
      const tsStr = timestamps[0] ?? "";
      const tsStart = timestamps.length > 0 ? timestamps.reduce((a, b) => a < b ? a : b) : tsStr;
      const tsEnd = timestamps.length > 0 ? timestamps.reduce((a, b) => a > b ? a : b) : tsStr;
      const skipVec = !embedding || embedding.every((v) => v === 0) || !this.vecTablesReady;
      this.logger?.debug?.(
        `${TAG} [L1-upsert] START id=${recordId}, type=${record.type}, content="${record.content.slice(0, 60)}..."` + (embedding ? `, embeddingDims=${embedding.length}, embeddingNorm=${Math.sqrt(Array.from(embedding).reduce((s, v) => s + v * v, 0)).toFixed(4)}${skipVec ? " (ZERO VECTOR or vec tables not ready \u2014 vec write will be skipped)" : ""}` : " (no embedding \u2014 metadata-only write)")
      );
      this.db.exec("BEGIN");
      try {
        this.stmtUpsertMeta.run(
          recordId,
          record.content,
          record.type,
          record.priority,
          record.scene_name,
          record.sessionKey,
          record.sessionId || DEFAULT_ISOLATION_ID,
          record.teamId || DEFAULT_ISOLATION_ID,
          record.taskId || "",
          record.version ?? 0,
          tsStr,
          tsStart,
          tsEnd,
          record.createdAt,
          record.updatedAt,
          JSON.stringify(record.metadata),
          record.userId || DEFAULT_ISOLATION_ID,
          record.agentId || DEFAULT_ISOLATION_ID
        );
        if (!skipVec) {
          this.stmtDeleteVec.run(recordId);
          this.stmtInsertVec.run(recordId, Buffer.from(embedding.buffer), record.updatedAt);
        } else {
          this.logger?.debug?.(
            `${TAG} [L1-upsert] Skipping vec write (${embedding ? "zero vector" : "no embedding"}) id=${recordId}`
          );
        }
        if (this.ftsAvailable) {
          try {
            this.stmtL1FtsDelete.run(recordId);
            this.stmtL1FtsInsert.run(
              tokenizeForFts(record.content),
              // content — segmented for indexing
              record.content,
              // content_original — raw for display
              recordId,
              record.type,
              record.priority,
              record.scene_name,
              record.sessionKey,
              record.sessionId || DEFAULT_ISOLATION_ID,
              record.teamId || DEFAULT_ISOLATION_ID,
              record.taskId || "",
              record.userId || DEFAULT_ISOLATION_ID,
              record.agentId || DEFAULT_ISOLATION_ID,
              record.version ?? 0,
              tsStr,
              tsStart,
              tsEnd,
              JSON.stringify(record.metadata)
            );
          } catch (ftsErr) {
            this.logger?.warn(
              `${TAG} [L1-upsert] FTS write failed (non-fatal) id=${recordId}: ${ftsErr instanceof Error ? ftsErr.message : String(ftsErr)}`
            );
          }
        }
        this.db.exec("COMMIT");
      } catch (err) {
        try {
          this.db.exec("ROLLBACK");
        } catch {
        }
        throw err;
      }
      this.logger?.debug?.(`${TAG} [L1-upsert] OK id=${recordId}${skipVec ? " (meta-only)" : ""}`);
      return true;
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L1-upsert] FAILED (non-fatal) id=${record.id}: ${err instanceof Error ? err.message : String(err)}`
      );
      return false;
    }
  }
  /**
   * Vector similarity search (cosine distance).
   * Returns top-k results sorted by similarity (highest first).
   *
   * **Fault-tolerant**: returns an empty array on any error (e.g. dimension
   * mismatch, corrupted DB) so callers can fall back to keyword search.
   */
  searchL1Vector(queryEmbedding, topK = 5, _queryText, filter) {
    if (this.degraded || !this.vecTablesReady) {
      if (this.degraded) this.logger?.warn(`${TAG} [L1-search] SKIPPED (degraded mode)`);
      return [];
    }
    try {
      const ZERO_VEC_BUFFER = 10;
      const retrieveCount = filter ? Math.max(topK * 5, topK + ZERO_VEC_BUFFER) : topK + ZERO_VEC_BUFFER;
      this.logger?.debug?.(
        `${TAG} [L1-search] START topK=${topK}, retrieveCount=${retrieveCount}, queryEmbeddingDims=${queryEmbedding.length}, queryNorm=${Math.sqrt(Array.from(queryEmbedding).reduce((s, v) => s + v * v, 0)).toFixed(4)}`
      );
      const rows = this.stmtSearchVec.all(
        Buffer.from(queryEmbedding.buffer),
        retrieveCount
      );
      this.logger?.debug?.(`${TAG} [L1-search] vec0 returned ${rows.length} candidate(s)`);
      if (rows.length === 0) return [];
      const results = [];
      for (const { record_id, distance } of rows) {
        if (distance == null || Number.isNaN(distance)) {
          this.logger?.warn(
            `${TAG} [L1-search] record_id=${record_id} has null/NaN distance (likely zero vector) \u2014 skipping`
          );
          continue;
        }
        const meta = this.stmtGetMeta.get(record_id);
        if (!meta) {
          this.logger?.warn(`${TAG} [L1-search] record_id=${record_id} has vector but NO metadata (orphan)`);
          continue;
        }
        if (!rowMatchesIsolation(meta, filter)) {
          continue;
        }
        const score = 1 - distance;
        this.logger?.debug?.(
          `${TAG} [L1-search] HIT id=${record_id}, distance=${distance.toFixed(4)}, score=${score.toFixed(4)}, type=${meta.type}, content="${meta.content.slice(0, 60)}..."`
        );
        results.push({
          record_id,
          content: meta.content,
          type: meta.type,
          priority: meta.priority,
          scene_name: meta.scene_name,
          score,
          timestamp_str: meta.timestamp_str,
          timestamp_start: meta.timestamp_start,
          timestamp_end: meta.timestamp_end,
          version: meta.version ?? 0,
          session_key: meta.session_key,
          session_id: meta.session_id,
          team_id: meta.team_id ?? "",
          task_id: meta.task_id ?? "",
          user_id: meta.user_id ?? "",
          agent_id: meta.agent_id ?? "",
          metadata_json: meta.metadata_json
        });
      }
      const trimmed = results.slice(0, topK);
      this.logger?.info(
        `${TAG} [L1-search] DONE returning ${trimmed.length} result(s) (from ${results.length} valid, ${rows.length} raw)`
      );
      return trimmed;
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L1-search] FAILED (non-fatal, returning empty): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  /**
   * Delete a single record (metadata + vector).
   *
   * **Fault-tolerant**: logs a warning on failure, never throws.
   */
  deleteL1(recordId, filter) {
    if (this.degraded) return false;
    try {
      if (filter) {
        const meta = this.stmtGetMeta.get(recordId);
        if (!meta || !rowMatchesIsolation(meta, filter)) return false;
      }
      this.db.exec("BEGIN");
      try {
        const result = this.stmtDeleteMeta.run(recordId);
        const deleted = result?.changes > 0;
        if (this.vecTablesReady) this.stmtDeleteVec.run(recordId);
        if (this.ftsAvailable) {
          try {
            this.stmtL1FtsDelete.run(recordId);
          } catch {
          }
        }
        this.db.exec("COMMIT");
        return deleted;
      } catch (err) {
        try {
          this.db.exec("ROLLBACK");
        } catch {
        }
        throw err;
      }
    } catch (err) {
      this.logger?.warn(
        `${TAG} delete failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return false;
    }
  }
  /**
   * Delete multiple records (metadata + vector).
   *
   * **Fault-tolerant**: logs a warning on failure, never throws.
   */
  deleteL1Batch(recordIds, filter) {
    if (this.degraded) return false;
    if (recordIds.length === 0) return true;
    try {
      this.db.exec("BEGIN");
      try {
        for (const id of recordIds) {
          if (filter) {
            const meta = this.stmtGetMeta.get(id);
            if (!meta || !rowMatchesIsolation(meta, filter)) continue;
          }
          this.stmtDeleteMeta.run(id);
          if (this.vecTablesReady) this.stmtDeleteVec.run(id);
          if (this.ftsAvailable) {
            try {
              this.stmtL1FtsDelete.run(id);
            } catch {
            }
          }
        }
        this.db.exec("COMMIT");
      } catch (err) {
        try {
          this.db.exec("ROLLBACK");
        } catch {
        }
        throw err;
      }
      return true;
    } catch (err) {
      this.logger?.warn(
        `${TAG} deleteBatch failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return false;
    }
  }
  /**
   * Get the total number of L1 records in the store.
   *
   * **Fault-tolerant**: returns 0 on failure.
   * TTL cleanup by updated_time.
   *
   * Deletes expired rows from l1_records and matching vectors from l1_vec
   * in a single transaction to guarantee consistency.
   */
  deleteL1Expired(cutoffIso) {
    if (this.degraded) {
      this.logger?.warn(`${TAG} [deleteExpired] SKIPPED (degraded mode)`);
      return 0;
    }
    try {
      const row = this.db.prepare(
        "SELECT COUNT(*) AS cnt FROM l1_records WHERE updated_time != '' AND updated_time < ?"
      ).get(cutoffIso);
      const expiredCount = row?.cnt ?? 0;
      if (expiredCount <= 0) return 0;
      const totalRow = this.db.prepare(
        "SELECT COUNT(*) AS cnt FROM l1_records"
      ).get();
      const total = totalRow.cnt;
      const ratio = total > 0 ? expiredCount / total : 0;
      if (ratio > 0.8) {
        this.logger?.warn(
          `${TAG} [L1-deleteExpired] BLOCKED: would delete ${expiredCount}/${total} (${(ratio * 100).toFixed(1)}%) \u2014 exceeds 80% safety threshold, cutoff=${cutoffIso}`
        );
        return 0;
      }
      this.db.exec("BEGIN");
      try {
        if (this.vecTablesReady) {
          this.db.prepare(
            "DELETE FROM l1_vec WHERE updated_time != '' AND updated_time < ?"
          ).run(cutoffIso);
        }
        this.db.prepare(
          "DELETE FROM l1_records WHERE updated_time != '' AND updated_time < ?"
        ).run(cutoffIso);
        this.db.exec("COMMIT");
        this.logger?.info?.(
          `${TAG} [L1-deleteExpired] Deleted ${expiredCount}/${total} records (cutoff=${cutoffIso})`
        );
        return expiredCount;
      } catch (err) {
        try {
          this.db.exec("ROLLBACK");
        } catch {
        }
        throw err;
      }
    } catch (err) {
      this.logger?.warn(
        `${TAG} deleteL1ExpiredByUpdatedTime failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return 0;
    }
  }
  /**
   * Get the total number of L1 records matching optional filters.
   */
  countL1(filter) {
    if (this.degraded) return 0;
    try {
      const conditions = [];
      const params = [];
      if (filter?.type) {
        conditions.push("type = ?");
        params.push(filter.type);
      }
      if (filter?.sessionId) {
        conditions.push("session_id = ?");
        params.push(filter.sessionId);
      }
      if (filter?.teamId !== void 0) {
        conditions.push("team_id = ?");
        params.push(filter.teamId);
      }
      if (filter?.userId !== void 0) {
        conditions.push("user_id = ?");
        params.push(filter.userId);
      }
      if (filter?.agentId !== void 0) {
        conditions.push("agent_id = ?");
        params.push(filter.agentId);
      }
      if (filter?.taskId !== void 0) {
        conditions.push("task_id = ?");
        params.push(filter.taskId);
      }
      if (filter?.timeStart) {
        conditions.push("updated_time >= ?");
        params.push(filter.timeStart);
      }
      if (filter?.timeEnd) {
        conditions.push("updated_time <= ?");
        params.push(filter.timeEnd);
      }
      const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
      const row = this.db.prepare(`SELECT COUNT(*) AS cnt FROM l1_records ${where}`).get(...params);
      const total = row?.cnt ?? 0;
      this.logger?.debug?.(`${TAG} [L1-count] total=${total}`);
      return total;
    } catch (err) {
      this.logger?.warn(
        `${TAG} count failed (non-fatal, returning 0): ${err instanceof Error ? err.message : String(err)}`
      );
      return 0;
    }
  }
  /**
   * Query L1 records with optional session and time filters.
   *
   * Uses the composite index `idx_l1_session_updated(session_id, updated_time)`
   * for efficient filtering. All timestamps are compared as UTC ISO 8601 strings.
   *
   * **Fault-tolerant**: returns an empty array on any error (degraded mode, DB issues).
   */
  queryL1Records(filter) {
    if (this.degraded) {
      this.logger?.warn(`${TAG} [L1-query] SKIPPED (degraded mode)`);
      return [];
    }
    try {
      const { sessionKey, sessionId, taskId, updatedAfter } = filter ?? {};
      let raw;
      if (sessionId && updatedAfter) {
        raw = this.stmtQueryBySessionIdSince.all(sessionId, updatedAfter);
      } else if (sessionId) {
        raw = this.stmtQueryBySessionId.all(sessionId);
      } else if (sessionKey && updatedAfter) {
        raw = this.stmtQueryBySessionKeySince.all(sessionKey, updatedAfter);
      } else if (sessionKey) {
        raw = this.stmtQueryBySessionKey.all(sessionKey);
      } else if (updatedAfter) {
        raw = this.stmtQueryAllSince.all(updatedAfter);
      } else {
        raw = this.stmtQueryAll.all();
      }
      if (raw.length > 0 && !("record_id" in raw[0] && "content" in raw[0])) {
        this.logger?.warn(
          `${TAG} [L1-query] Schema mismatch: first row missing expected columns. Got keys: [${Object.keys(raw[0]).join(", ")}]`
        );
        return [];
      }
      let rows = raw;
      if (filter?.teamId !== void 0) rows = rows.filter((r) => r.team_id === filter.teamId);
      if (filter?.userId !== void 0) rows = rows.filter((r) => r.user_id === filter.userId);
      if (filter?.agentId !== void 0) rows = rows.filter((r) => r.agent_id === filter.agentId);
      if (taskId !== void 0) rows = rows.filter((r) => r.task_id === taskId);
      this.logger?.info(
        `${TAG} [L1-query] filter={sessionKey=${sessionKey ?? "(all)"}, sessionId=${sessionId ?? "(all)"}, teamId=${filter?.teamId ?? "(all)"}, userId=${filter?.userId ?? "(all)"}, agentId=${filter?.agentId ?? "(all)"}, taskId=${taskId ?? "(all)"}, updatedAfter=${updatedAfter ?? "(none)"}}, returned ${rows.length} record(s)`
      );
      return rows;
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L1-query] FAILED (non-fatal, returning empty): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  // ── L0 operations ──────────────────────────────────
  /**
   * Write or update an L0 single-message record (metadata + vector).
   * Uses a manual transaction for atomicity.
   *
   * If `embedding` is `undefined` or a zero vector (all elements are 0), only
   * the metadata row (`l0_conversations`) is written — the vec0 table
   * (`l0_vec`) is left untouched.  This allows callers without an
   * EmbeddingService to still persist metadata + FTS without constructing a
   * throwaway zero-vector, and prevents placeholder zero vectors (from
   * embedding-service failures) from polluting KNN search results.
   *
   * **Fault-tolerant**: catches all errors internally, never throws.
   * Returns `true` on success, `false` on failure (logged as warning).
   */
  upsertL0(record, embedding) {
    if (this.degraded) {
      this.logger?.warn(`${TAG} [L0-upsert] SKIPPED (degraded mode) id=${record.id}`);
      return false;
    }
    try {
      const skipVec = !embedding || embedding.every((v) => v === 0) || !this.vecTablesReady;
      this.logger?.debug?.(
        `${TAG} [L0-upsert] START id=${record.id}, session=${record.sessionKey}, role=${record.role}, text="${record.messageText.slice(0, 60)}..."` + (embedding ? `, embeddingDims=${embedding.length}, embeddingNorm=${Math.sqrt(Array.from(embedding).reduce((s, v) => s + v * v, 0)).toFixed(4)}${skipVec ? " (ZERO VECTOR or vec tables not ready \u2014 vec write will be skipped)" : ""}` : " (no embedding \u2014 metadata-only write)")
      );
      this.db.exec("BEGIN");
      try {
        this.stmtL0UpsertMeta.run(
          record.id,
          record.sessionKey,
          record.sessionId || DEFAULT_ISOLATION_ID,
          record.teamId || DEFAULT_ISOLATION_ID,
          record.taskId || "",
          record.role,
          record.messageText,
          record.recordedAt,
          record.timestamp,
          record.userId || DEFAULT_ISOLATION_ID,
          record.agentId || DEFAULT_ISOLATION_ID
        );
        if (!skipVec) {
          this.stmtL0DeleteVec.run(record.id);
          this.stmtL0InsertVec.run(record.id, Buffer.from(embedding.buffer), record.recordedAt);
        } else {
          this.logger?.debug?.(
            `${TAG} [L0-upsert] Skipping vec write (${embedding ? "zero vector" : "no embedding"}) id=${record.id}`
          );
        }
        if (this.ftsAvailable) {
          try {
            this.stmtL0FtsDelete.run(record.id);
            this.stmtL0FtsInsert.run(
              tokenizeForFts(record.messageText),
              // message_text — segmented for indexing
              record.messageText,
              // message_text_original — raw for display
              record.id,
              record.sessionKey,
              record.sessionId || DEFAULT_ISOLATION_ID,
              record.teamId || DEFAULT_ISOLATION_ID,
              record.taskId || "",
              record.userId || DEFAULT_ISOLATION_ID,
              record.agentId || DEFAULT_ISOLATION_ID,
              record.role,
              record.recordedAt,
              record.timestamp
            );
          } catch (ftsErr) {
            this.logger?.warn(
              `${TAG} [L0-upsert] FTS write failed (non-fatal) id=${record.id}: ${ftsErr instanceof Error ? ftsErr.message : String(ftsErr)}`
            );
          }
        }
        this.db.exec("COMMIT");
      } catch (err) {
        try {
          this.db.exec("ROLLBACK");
        } catch {
        }
        throw err;
      }
      this.logger?.debug?.(`${TAG} [L0-upsert] OK id=${record.id}${skipVec ? " (meta-only)" : ""}`);
      return true;
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L0-upsert] FAILED (non-fatal) id=${record.id}: ${err instanceof Error ? err.message : String(err)}`
      );
      return false;
    }
  }
  /**
   * Update ONLY the vector embedding for an existing L0 record.
   * The metadata row must already exist in l0_conversations (written by upsertL0).
   *
   * This is used by the background embedding task in auto-capture:
   *   1. upsertL0() writes metadata + FTS synchronously (no embedding)
   *   2. Background task calls embedBatch() then updateL0Embedding() for each record
   *
   * **Fault-tolerant**: catches all errors internally, never throws.
   * Returns `true` on success, `false` on failure.
   */
  updateL0Embedding(recordId, embedding) {
    if (this.degraded || !this.vecTablesReady) {
      return false;
    }
    if (!embedding || embedding.every((v) => v === 0)) {
      this.logger?.debug?.(`${TAG} [L0-update-embedding] Skipping zero vector for ${recordId}`);
      return false;
    }
    try {
      const meta = this.stmtL0GetMeta.get(recordId);
      if (!meta) {
        this.logger?.warn(`${TAG} [L0-update-embedding] No metadata found for ${recordId}, skipping`);
        return false;
      }
      this.db.exec("BEGIN");
      try {
        this.stmtL0DeleteVec.run(recordId);
        this.stmtL0InsertVec.run(recordId, Buffer.from(embedding.buffer), meta.recorded_at);
        this.db.exec("COMMIT");
      } catch (err) {
        try {
          this.db.exec("ROLLBACK");
        } catch {
        }
        throw err;
      }
      return true;
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L0-update-embedding] FAILED (non-fatal) id=${recordId}: ${err instanceof Error ? err.message : String(err)}`
      );
      return false;
    }
  }
  /**
   * Vector similarity search on L0 individual messages (cosine distance).
   * Returns top-k results sorted by similarity (highest first).
   *
   * **Fault-tolerant**: returns an empty array on any error.
   */
  searchL0Vector(queryEmbedding, topK = 5, _queryText, filter) {
    if (this.degraded || !this.vecTablesReady) {
      if (this.degraded) this.logger?.warn(`${TAG} [L0-search] SKIPPED (degraded mode)`);
      return [];
    }
    try {
      const retrieveCount = filter ? Math.max(topK * 5, topK + _VectorStore.ZERO_VEC_BUFFER) : topK + _VectorStore.ZERO_VEC_BUFFER;
      this.logger?.debug?.(
        `${TAG} [L0-search] START topK=${topK}, retrieveCount=${retrieveCount}, queryEmbeddingDims=${queryEmbedding.length}, queryNorm=${Math.sqrt(Array.from(queryEmbedding).reduce((s, v) => s + v * v, 0)).toFixed(4)}`
      );
      const rows = this.stmtL0SearchVec.all(
        Buffer.from(queryEmbedding.buffer),
        retrieveCount
      );
      this.logger?.debug?.(`${TAG} [L0-search] vec0 returned ${rows.length} candidate(s)`);
      if (rows.length === 0) return [];
      const results = [];
      for (const { record_id, distance } of rows) {
        if (distance == null || Number.isNaN(distance)) {
          this.logger?.warn(
            `${TAG} [L0-search] record_id=${record_id} has null/NaN distance (likely zero vector) \u2014 skipping`
          );
          continue;
        }
        const meta = this.stmtL0GetMeta.get(record_id);
        if (!meta) {
          this.logger?.warn(`${TAG} [L0-search] record_id=${record_id} has vector but NO metadata (orphan)`);
          continue;
        }
        if (!rowMatchesIsolation(meta, filter)) {
          continue;
        }
        const score = 1 - distance;
        this.logger?.debug?.(
          `${TAG} [L0-search] HIT id=${record_id}, distance=${distance.toFixed(4)}, score=${score.toFixed(4)}, role=${meta.role}, session=${meta.session_key}, text="${meta.message_text.slice(0, 60)}..."`
        );
        results.push({
          record_id,
          session_key: meta.session_key,
          session_id: meta.session_id,
          team_id: meta.team_id ?? "",
          task_id: meta.task_id ?? "",
          user_id: meta.user_id ?? "",
          agent_id: meta.agent_id ?? "",
          role: meta.role,
          message_text: meta.message_text,
          score,
          recorded_at: meta.recorded_at,
          timestamp: meta.timestamp ?? 0
        });
      }
      const trimmed = results.slice(0, topK);
      this.logger?.info(
        `${TAG} [L0-search] DONE returning ${trimmed.length} result(s) (from ${results.length} valid, ${rows.length} raw)`
      );
      return trimmed;
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L0-search] FAILED (non-fatal, returning empty): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  /**
   * Delete a single L0 record (metadata + vector).
   *
   * **Fault-tolerant**: logs a warning on failure, never throws.
   */
  deleteL0(recordId, filter) {
    if (this.degraded) return false;
    try {
      if (filter) {
        const meta = this.stmtL0GetMeta.get(recordId);
        if (!meta || !rowMatchesIsolation(meta, filter)) return false;
      }
      this.db.exec("BEGIN");
      try {
        const result = this.stmtL0DeleteMeta.run(recordId);
        const deleted = result?.changes > 0;
        if (this.vecTablesReady) this.stmtL0DeleteVec.run(recordId);
        if (this.ftsAvailable) {
          try {
            this.stmtL0FtsDelete.run(recordId);
          } catch {
          }
        }
        this.db.exec("COMMIT");
        return deleted;
      } catch (err) {
        try {
          this.db.exec("ROLLBACK");
        } catch {
        }
        throw err;
      }
    } catch (err) {
      this.logger?.warn(
        `${TAG} deleteL0 failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return false;
    }
  }
  /**
   * TTL cleanup by recorded_at (ISO string) for L0 records.
   *
   * Deletes expired rows from l0_conversations and matching vectors from l0_vec
   * in a single transaction to guarantee consistency.
   */
  deleteL0Expired(cutoffIso) {
    if (this.degraded) {
      this.logger?.warn(`${TAG} [deleteExpiredL0] SKIPPED (degraded mode)`);
      return 0;
    }
    try {
      const row = this.db.prepare(
        "SELECT COUNT(*) AS cnt FROM l0_conversations WHERE recorded_at != '' AND recorded_at < ?"
      ).get(cutoffIso);
      const expiredCount = row?.cnt ?? 0;
      if (expiredCount <= 0) return 0;
      const totalRow = this.db.prepare(
        "SELECT COUNT(*) AS cnt FROM l0_conversations"
      ).get();
      const total = totalRow.cnt;
      const ratio = total > 0 ? expiredCount / total : 0;
      if (ratio > 0.8) {
        this.logger?.warn(
          `${TAG} [L0-deleteExpired] BLOCKED: would delete ${expiredCount}/${total} (${(ratio * 100).toFixed(1)}%) \u2014 exceeds 80% safety threshold, cutoff=${cutoffIso}`
        );
        return 0;
      }
      this.db.exec("BEGIN");
      try {
        if (this.vecTablesReady) {
          this.db.prepare(
            "DELETE FROM l0_vec WHERE recorded_at != '' AND recorded_at < ?"
          ).run(cutoffIso);
        }
        this.db.prepare(
          "DELETE FROM l0_conversations WHERE recorded_at != '' AND recorded_at < ?"
        ).run(cutoffIso);
        this.db.exec("COMMIT");
        this.logger?.info?.(
          `${TAG} [L0-deleteExpired] Deleted ${expiredCount}/${total} records (cutoff=${cutoffIso})`
        );
        return expiredCount;
      } catch (err) {
        try {
          this.db.exec("ROLLBACK");
        } catch {
        }
        throw err;
      }
    } catch (err) {
      this.logger?.warn(
        `${TAG} deleteL0ExpiredByRecordedAt failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return 0;
    }
  }
  /**
   * Get the total number of L0 message records matching optional filters.
   *
   * **Fault-tolerant**: returns 0 on failure.
   */
  countL0(filter) {
    if (this.degraded) return 0;
    try {
      const conditions = [];
      const params = [];
      if (filter?.sessionId) {
        conditions.push("(session_key = ? OR session_id = ?)");
        params.push(filter.sessionId, filter.sessionId);
      }
      if (filter?.teamId !== void 0) {
        conditions.push("team_id = ?");
        params.push(filter.teamId);
      }
      if (filter?.userId !== void 0) {
        conditions.push("user_id = ?");
        params.push(filter.userId);
      }
      if (filter?.agentId !== void 0) {
        conditions.push("agent_id = ?");
        params.push(filter.agentId);
      }
      if (filter?.taskId !== void 0) {
        conditions.push("task_id = ?");
        params.push(filter.taskId);
      }
      if (filter?.timeStartMs !== void 0) {
        conditions.push("timestamp >= ?");
        params.push(filter.timeStartMs);
      }
      if (filter?.timeEndMs !== void 0) {
        conditions.push("timestamp <= ?");
        params.push(filter.timeEndMs);
      }
      const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
      const row = this.db.prepare(`SELECT COUNT(*) AS cnt FROM l0_conversations ${where}`).get(...params);
      const total = row?.cnt ?? 0;
      this.logger?.debug?.(`${TAG} [L0-count] total=${total}`);
      return total;
    } catch (err) {
      this.logger?.warn(
        `${TAG} countL0 failed (non-fatal, returning 0): ${err instanceof Error ? err.message : String(err)}`
      );
      return 0;
    }
  }
  // ── Re-index operations ──────────────────────────────────
  /**
   * Get all L1 record texts for re-embedding.
   * Returns record_id → content pairs.
   */
  getAllL1Texts() {
    if (this.degraded) return [];
    try {
      return this.db.prepare("SELECT record_id, content, updated_time FROM l1_records").all();
    } catch (err) {
      this.logger?.warn(
        `${TAG} getAllL1Texts failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  /**
   * Get all L0 message texts for re-embedding.
   * Returns record_id → message_text/recorded_at tuples.
   */
  getAllL0Texts() {
    if (this.degraded) return [];
    try {
      return this.db.prepare("SELECT record_id, message_text, recorded_at FROM l0_conversations").all();
    } catch (err) {
      this.logger?.warn(
        `${TAG} getAllL0Texts failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  /**
   * Re-embed all existing L1 and L0 texts with a new embedding function.
   *
   * This is called after `init()` returns `needsReindex: true` — the vector
   * tables have already been dropped and re-created with the correct dimensions.
   * This method reads every text from the metadata tables and writes fresh
   * embeddings into the new vector tables.
   *
   * @param embedFn  A function that converts text → Float32Array embedding.
   * @param onProgress  Optional callback for progress reporting.
   */
  async reindexAll(embedFn, onProgress) {
    if (this.degraded || !this.vecTablesReady) {
      if (this.degraded) this.logger?.warn(`${TAG} reindexAll skipped: VectorStore is in degraded mode`);
      return { l1Count: 0, l0Count: 0 };
    }
    try {
      const l1Rows = this.getAllL1Texts();
      let l1Done = 0;
      for (const { record_id, content, updated_time } of l1Rows) {
        try {
          const embedding = await embedFn(content);
          this.db.exec("BEGIN");
          try {
            this.stmtDeleteVec.run(record_id);
            this.stmtInsertVec.run(record_id, Buffer.from(embedding.buffer), updated_time);
            this.db.exec("COMMIT");
          } catch (txErr) {
            try {
              this.db.exec("ROLLBACK");
            } catch {
            }
            throw txErr;
          }
        } catch (err) {
          this.logger?.warn?.(
            `${TAG} reindex L1 skip ${record_id}: ${err instanceof Error ? err.message : String(err)}`
          );
        }
        l1Done++;
        onProgress?.(l1Done, l1Rows.length, "L1");
      }
      const l0Rows = this.getAllL0Texts();
      let l0Done = 0;
      for (const { record_id, message_text, recorded_at } of l0Rows) {
        try {
          const embedding = await embedFn(message_text);
          this.db.exec("BEGIN");
          try {
            this.stmtL0DeleteVec.run(record_id);
            this.stmtL0InsertVec.run(record_id, Buffer.from(embedding.buffer), recorded_at);
            this.db.exec("COMMIT");
          } catch (txErr) {
            try {
              this.db.exec("ROLLBACK");
            } catch {
            }
            throw txErr;
          }
        } catch (err) {
          this.logger?.warn?.(
            `${TAG} reindex L0 skip ${record_id}: ${err instanceof Error ? err.message : String(err)}`
          );
        }
        l0Done++;
        onProgress?.(l0Done, l0Rows.length, "L0");
      }
      this.logger?.info(
        `${TAG} Reindex complete: L1=${l1Done}/${l1Rows.length}, L0=${l0Done}/${l0Rows.length}`
      );
      return { l1Count: l1Done, l0Count: l0Done };
    } catch (err) {
      this.logger?.error(
        `${TAG} reindexAll failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return { l1Count: 0, l0Count: 0 };
    }
  }
  // ── L0 query operations (for L1 runner) ──────────────────────────────────
  /**
   * Query L0 messages for a given session key, optionally filtered by recorded_at cursor.
   * Returns up to `limit` rows with `recorded_at > afterRecordedAtMs`, ordered by
   * recorded_at ASC (chronological write order, **oldest-first**).
   *
   * Used by L1 runner to read L0 data from DB. The runner is responsible for
   * batching/slicing the returned rows (e.g. process N, defer the rest).
   */
  queryL0ForL1(sessionKey, afterRecordedAtMs, limit = 50) {
    if (this.degraded) {
      this.logger?.warn(`${TAG} [L0-query] SKIPPED (degraded mode)`);
      return [];
    }
    try {
      let rows;
      if (afterRecordedAtMs && afterRecordedAtMs > 0) {
        const afterRecordedAtIso = new Date(afterRecordedAtMs).toISOString();
        rows = this.stmtL0QueryAfter.all(sessionKey, afterRecordedAtIso, limit);
      } else {
        rows = this.stmtL0QueryAll.all(sessionKey, limit);
      }
      this.logger?.info(
        `${TAG} [L0-query] session=${sessionKey}, afterRecordedAtMs=${afterRecordedAtMs ?? "(all)"}, limit=${limit}, returned ${rows.length} row(s)`
      );
      return rows.map((r) => ({
        record_id: r.record_id,
        session_key: r.session_key,
        session_id: r.session_id || "",
        team_id: r.team_id || "",
        task_id: r.task_id || "",
        user_id: r.user_id || "",
        agent_id: r.agent_id || "",
        role: r.role,
        message_text: r.message_text,
        recorded_at: r.recorded_at || "",
        timestamp: r.timestamp || 0
      }));
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L0-query] FAILED (non-fatal, returning empty): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  /**
   * Query L0 messages for a given session key, grouped by session_id.
   * Each group's messages are in chronological order (recorded_at ASC).
   * Groups are sorted by earliest message timestamp.
   *
   * Used by L1 runner to replace readConversationMessagesGroupedBySessionId().
   */
  queryL0GroupedBySessionId(sessionKey, afterRecordedAtMs, limit = 50) {
    if (this.degraded) {
      this.logger?.warn(`${TAG} [L0-query-grouped] SKIPPED (degraded mode)`);
      return [];
    }
    try {
      const rows = this.queryL0ForL1(sessionKey, afterRecordedAtMs, limit);
      const groupMap = /* @__PURE__ */ new Map();
      for (const row of rows) {
        const sid = row.session_id || "";
        const teamId = row.team_id || void 0;
        const taskId = row.task_id || void 0;
        const userId = row.user_id || "";
        const agentId = row.agent_id || "";
        const groupKey = `${teamId ?? ""}\0${userId}\0${agentId}\0${sid}\0${taskId ?? ""}`;
        let group = groupMap.get(groupKey);
        if (!group) {
          group = { sessionId: sid, teamId, taskId, userId, agentId, messages: [] };
          groupMap.set(groupKey, group);
        }
        group.messages.push({
          id: row.record_id,
          role: row.role,
          content: row.message_text,
          timestamp: row.timestamp,
          recordedAtMs: row.recorded_at ? Date.parse(row.recorded_at) || 0 : 0
        });
      }
      const groups = [];
      for (const group of groupMap.values()) {
        if (group.messages.length > 0) {
          groups.push(group);
        }
      }
      groups.sort((a, b) => a.messages[0].timestamp - b.messages[0].timestamp);
      this.logger?.info(
        `${TAG} [L0-query-grouped] session=${sessionKey}, afterRecordedAtMs=${afterRecordedAtMs ?? "(all)"}, ${rows.length} messages across ${groups.length} group(s)`
      );
      return groups;
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L0-query-grouped] FAILED (non-fatal, returning empty): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  // ── Cursor-based pagination for migration ──────────────────
  /**
   * Read a page of L1 records using primary key cursor.
   * Returns rows with `record_id > afterId`, ordered by PK, limited to `pageSize`.
   * Pass `""` as `afterId` for the first page.
   */
  queryL1RecordsCursor(afterId, pageSize) {
    if (this.degraded) return [];
    try {
      return this.stmtL1QueryMigrationCursor.all(afterId, pageSize);
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L1-query-cursor] FAILED (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  /**
   * Read a page of L0 records using primary key cursor.
   * Returns rows with `record_id > afterId`, ordered by PK, limited to `pageSize`.
   * Pass `""` as `afterId` for the first page.
   */
  queryL0RecordsCursor(afterId, pageSize) {
    if (this.degraded) return [];
    try {
      return this.stmtL0QueryMigrationCursor.all(afterId, pageSize);
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L0-query-cursor] FAILED (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  // ── FTS5 search operations ──────────────────────────────────
  /**
   * Whether FTS5 full-text search is available.
   * When `false`, callers should skip keyword-based recall entirely.
   */
  isFtsAvailable() {
    return this.ftsAvailable;
  }
  // ── v2 API: Paginated queries ─────────────────────────────
  /**
   * L0 paginated query for v2 `/conversation/query`.
   * Uses SQL WHERE + LIMIT + OFFSET, no full-table scan.
   */
  queryL0Paginated(filter) {
    if (this.degraded) return { rows: [], total: 0 };
    try {
      const conditions = [];
      const params = [];
      if (filter.sessionId) {
        conditions.push("(session_key = ? OR session_id = ?)");
        params.push(filter.sessionId, filter.sessionId);
      }
      if (filter.teamId !== void 0) {
        conditions.push("team_id = ?");
        params.push(filter.teamId);
      }
      if (filter.userId !== void 0) {
        conditions.push("user_id = ?");
        params.push(filter.userId);
      }
      if (filter.agentId !== void 0) {
        conditions.push("agent_id = ?");
        params.push(filter.agentId);
      }
      if (filter.taskId !== void 0) {
        conditions.push("task_id = ?");
        params.push(filter.taskId);
      }
      if (filter.timeStartMs !== void 0) {
        conditions.push("timestamp >= ?");
        params.push(filter.timeStartMs);
      }
      if (filter.timeEndMs !== void 0) {
        conditions.push("timestamp <= ?");
        params.push(filter.timeEndMs);
      }
      const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
      const countSql = `SELECT COUNT(*) AS cnt FROM l0_conversations ${where}`;
      const countRow = this.db.prepare(countSql).get(...params);
      const total = countRow?.cnt ?? 0;
      const dataSql = `SELECT record_id, session_key, session_id, team_id, task_id, user_id, agent_id, role, message_text, recorded_at, timestamp FROM l0_conversations ${where} ORDER BY timestamp DESC LIMIT ? OFFSET ?`;
      const rows = this.db.prepare(dataSql).all(...params, filter.limit, filter.offset);
      return { rows, total };
    } catch (err) {
      this.logger?.warn(`[sqlite] queryL0Paginated failed: ${err instanceof Error ? err.message : String(err)}`);
      return { rows: [], total: 0 };
    }
  }
  /**
   * L1 paginated query for v2 `/atomic/query`.
   * Uses SQL WHERE + LIMIT + OFFSET, no full-table scan.
   */
  queryL1Paginated(filter) {
    if (this.degraded) return { rows: [], total: 0 };
    try {
      const conditions = [];
      const params = [];
      if (filter.type) {
        conditions.push("type = ?");
        params.push(filter.type);
      }
      if (filter.sessionId) {
        conditions.push("session_id = ?");
        params.push(filter.sessionId);
      }
      if (filter.teamId !== void 0) {
        conditions.push("team_id = ?");
        params.push(filter.teamId);
      }
      if (filter.userId !== void 0) {
        conditions.push("user_id = ?");
        params.push(filter.userId);
      }
      if (filter.agentId !== void 0) {
        conditions.push("agent_id = ?");
        params.push(filter.agentId);
      }
      if (filter.taskId !== void 0) {
        conditions.push("task_id = ?");
        params.push(filter.taskId);
      }
      if (filter.timeStart) {
        conditions.push("updated_time >= ?");
        params.push(filter.timeStart);
      }
      if (filter.timeEnd) {
        conditions.push("updated_time <= ?");
        params.push(filter.timeEnd);
      }
      const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
      const countSql = `SELECT COUNT(*) AS cnt FROM l1_records ${where}`;
      const countRow = this.db.prepare(countSql).get(...params);
      const total = countRow?.cnt ?? 0;
      const dataSql = `SELECT record_id, content, type, priority, scene_name, session_key, session_id, team_id, task_id, user_id, agent_id, version, timestamp_str, timestamp_start, timestamp_end, created_time, updated_time, metadata_json FROM l1_records ${where} ORDER BY updated_time DESC LIMIT ? OFFSET ?`;
      const rows = this.db.prepare(dataSql).all(...params, filter.limit, filter.offset);
      return { rows, total };
    } catch (err) {
      this.logger?.warn(`[sqlite] queryL1Paginated failed: ${err instanceof Error ? err.message : String(err)}`);
      return { rows: [], total: 0 };
    }
  }
  /**
   * Delete all L0 messages belonging to a session.
   * Returns the count of actually deleted rows.
   */
  deleteL0BySession(sessionId, filter) {
    const sessionIdTrimmed = (sessionId ?? "").trim();
    if (!sessionIdTrimmed) {
      throw new Error("[sqlite] deleteL0BySession requires a non-empty sessionId");
    }
    if (this.degraded) return 0;
    try {
      const rows = this.db.prepare(
        "SELECT record_id, session_key, session_id, team_id, task_id, user_id, agent_id FROM l0_conversations WHERE session_key = ? OR session_id = ?"
      ).all(sessionIdTrimmed, sessionIdTrimmed);
      if (rows.length === 0) return 0;
      this.db.exec("BEGIN");
      try {
        let deletedCount = 0;
        for (const row of rows) {
          if (filter && !rowMatchesIsolation(row, filter)) continue;
          const result = this.db.prepare("DELETE FROM l0_conversations WHERE record_id = ?").run(row.record_id);
          if ((result?.changes ?? 0) <= 0) continue;
          deletedCount++;
          if (this.vecTablesReady) {
            try {
              this.db.prepare("DELETE FROM l0_vec WHERE record_id = ?").run(row.record_id);
            } catch {
            }
          }
          if (this.ftsAvailable) {
            try {
              this.db.prepare("DELETE FROM l0_fts WHERE record_id = ?").run(row.record_id);
            } catch {
            }
          }
        }
        this.db.exec("COMMIT");
        return deletedCount;
      } catch (err) {
        this.db.exec("ROLLBACK");
        throw err;
      }
    } catch (err) {
      this.logger?.warn(`[sqlite] deleteL0BySession failed: ${err instanceof Error ? err.message : String(err)}`);
      return 0;
    }
  }
  /**
   * 清空某个 (team, agent) 下的全部 L0 + L1 内容（含向量 / FTS 附属行）。
   * 不动entity_* / meta_* 资产表 —— 资产 ID 与绑定关系完整保留。
   *
   * sqlite store 不落L2/L3 profile 行（profiles 表只存在于 TCVDB），
   * 所以 profilesDeleted 恒为 0，L2/L3 文件由调用方走 StorageAdapter 清理。
   */
  clearMemoryContent(filter) {
    const teamId = (filter?.teamId ?? "").trim();
    const agentId = (filter?.agentId ?? "").trim();
    if (!teamId || !agentId) {
      throw new Error("clearMemoryContent requires non-empty teamId and agentId");
    }
    const userId = filter.userId?.trim() || void 0;
    const empty = { l0Deleted: 0, l1Deleted: 0, profilesDeleted: 0 };
    if (this.degraded) return empty;
    const where = `team_id = ? AND agent_id = ?${userId ? " AND user_id = ?" : ""}`;
    const params = userId ? [teamId, agentId, userId] : [teamId, agentId];
    try {
      const l0Ids = this.db.prepare(
        `SELECT record_id FROM l0_conversations WHERE ${where}`
      ).all(...params).map((r) => r.record_id);
      const l1Ids = this.db.prepare(
        `SELECT record_id FROM l1_records WHERE ${where}`
      ).all(...params).map((r) => r.record_id);
      if (l0Ids.length === 0 && l1Ids.length === 0) return empty;
      this.db.exec("BEGIN");
      try {
        let l0Deleted = 0;
        for (const id of l0Ids) {
          const res = this.db.prepare("DELETE FROM l0_conversations WHERE record_id = ?").run(id);
          if ((res?.changes ?? 0) <= 0) continue;
          l0Deleted++;
          if (this.vecTablesReady) {
            try {
              this.db.prepare("DELETE FROM l0_vec WHERE record_id = ?").run(id);
            } catch {
            }
          }
          if (this.ftsAvailable) {
            try {
              this.db.prepare("DELETE FROM l0_fts WHERE record_id = ?").run(id);
            } catch {
            }
          }
        }
        let l1Deleted = 0;
        for (const id of l1Ids) {
          const res = this.db.prepare("DELETE FROM l1_records WHERE record_id = ?").run(id);
          if ((res?.changes ?? 0) <= 0) continue;
          l1Deleted++;
          if (this.vecTablesReady) {
            try {
              this.db.prepare("DELETE FROM l1_vec WHERE record_id = ?").run(id);
            } catch {
            }
          }
          if (this.ftsAvailable) {
            try {
              this.db.prepare("DELETE FROM l1_fts WHERE record_id = ?").run(id);
            } catch {
            }
          }
        }
        this.db.exec("COMMIT");
        return { l0Deleted, l1Deleted, profilesDeleted: 0 };
      } catch (err) {
        this.db.exec("ROLLBACK");
        throw err;
      }
    } catch (err) {
      this.logger?.warn(`[sqlite] clearMemoryContent failed: ${err instanceof Error ? err.message : String(err)}`);
      throw err;
    }
  }
  entityId(prefix) {
    return `${prefix}_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
  }
  jsonArray(value) {
    return JSON.stringify(Array.isArray(value) ? value.filter((v) => typeof v === "string" && v.trim().length > 0) : []);
  }
  parseArray(value) {
    if (Array.isArray(value)) return value.filter((v) => typeof v === "string");
    if (typeof value !== "string" || !value) return [];
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed.filter((v) => typeof v === "string") : [];
    } catch {
      return [];
    }
  }
  teamFromRow(row, includeRefs = false) {
    const teamId = String(row.team_id ?? "");
    const ownerUserId = String(row.owner_user_id ?? "");
    const team = {
      team_id: teamId,
      name: String(row.name ?? ""),
      description: String(row.description ?? "") || void 0,
      owner_user_id: ownerUserId,
      status: row.status || "active",
      created_at: String(row.created_at ?? ""),
      updated_at: String(row.updated_at ?? "")
    };
    if (includeRefs) {
      const userIds = new Set(this.parseArray(row.user_ids_json));
      if (ownerUserId) userIds.add(ownerUserId);
      team.user_ids = Array.from(userIds).sort();
      const agentIds = new Set(this.parseArray(row.agent_ids_json));
      const agents = this.db.prepare("SELECT agent_id FROM entity_agents WHERE team_id = ? AND status = 'active' ORDER BY agent_id").all(teamId);
      for (const agent of agents) agentIds.add(String(agent.agent_id));
      team.agent_ids = Array.from(agentIds).sort();
      team.task_ids = this.db.prepare("SELECT task_id FROM entity_tasks WHERE team_id = ? ORDER BY task_id").all(teamId).map((r) => String(r.task_id));
    }
    return team;
  }
  userFromRow(row, includeDerived = false) {
    const userId = String(row.user_id ?? "");
    const user = {
      user_id: userId,
      name: String(row.name ?? ""),
      job_description: String(row.job_description ?? "") || void 0,
      team_ids: [],
      task_ids: [],
      owned_agent_ids: [],
      status: row.status || "active",
      created_at: String(row.created_at ?? ""),
      updated_at: String(row.updated_at ?? "")
    };
    if (includeDerived) {
      const teams = this.db.prepare("SELECT team_id, owner_user_id, user_ids_json FROM entity_teams WHERE status = 'active'").all();
      user.team_ids = teams.filter((team) => String(team.owner_user_id ?? "") === userId || this.parseArray(team.user_ids_json).includes(userId)).map((team) => String(team.team_id)).sort();
      const tasks = this.db.prepare("SELECT task_id, creator_user_id, user_ids_json, agent_ids_json FROM entity_tasks ORDER BY task_id").all();
      const taskIds = /* @__PURE__ */ new Set();
      const taskAgentIds = /* @__PURE__ */ new Set();
      for (const task of tasks) {
        const participates = String(task.creator_user_id ?? "") === userId || this.parseArray(task.user_ids_json).includes(userId);
        if (!participates) continue;
        taskIds.add(String(task.task_id));
        for (const agentId of this.parseArray(task.agent_ids_json)) taskAgentIds.add(agentId);
      }
      user.task_ids = Array.from(taskIds).sort();
      user.task_agent_ids = Array.from(taskAgentIds).sort();
      user.owned_agent_ids = this.db.prepare("SELECT agent_id FROM entity_agents WHERE owner_user_id = ? AND status = 'active' ORDER BY agent_id").all(userId).map((r) => String(r.agent_id));
    }
    return user;
  }
  agentFromRow(row, includeDerived = true) {
    const agentId = String(row.agent_id ?? "");
    const agent = {
      agent_id: agentId,
      team_id: String(row.team_id ?? ""),
      name: String(row.name ?? ""),
      description: String(row.description ?? "") || void 0,
      prompt: String(row.prompt ?? "") || void 0,
      owner_user_id: String(row.owner_user_id ?? "") || void 0,
      visibility: row.visibility || "team",
      status: row.status || "active",
      created_at: String(row.created_at ?? ""),
      updated_at: String(row.updated_at ?? "")
    };
    if (includeDerived) {
      const tasks = this.db.prepare("SELECT task_id, agent_ids_json FROM entity_tasks ORDER BY task_id").all();
      agent.task_ids = tasks.filter((task) => this.parseArray(task.agent_ids_json).includes(agentId)).map((task) => String(task.task_id));
    }
    return agent;
  }
  taskFromRow(row) {
    return {
      task_id: String(row.task_id ?? ""),
      team_id: String(row.team_id ?? ""),
      creator_user_id: String(row.creator_user_id ?? ""),
      title: String(row.title ?? "") || void 0,
      description: String(row.description ?? "") || void 0,
      source_type: row.source_type || "manual",
      source_url: String(row.source_url ?? "") || void 0,
      agent_ids: this.parseArray(row.agent_ids_json),
      user_ids: this.parseArray(row.user_ids_json),
      created_at: String(row.created_at ?? ""),
      updated_at: String(row.updated_at ?? "")
    };
  }
  createTeam(input) {
    const now = (/* @__PURE__ */ new Date()).toISOString();
    const id = input.team_id || this.entityId("team");
    this.db.prepare("INSERT INTO entity_teams (team_id, name, description, owner_user_id, user_ids_json, agent_ids_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)").run(id, input.name, input.description ?? "", input.owner_user_id, this.jsonArray([input.owner_user_id]), this.jsonArray([]), input.status ?? "active", now, now);
    return this.getTeam(id) ?? { team_id: id, name: input.name, owner_user_id: input.owner_user_id, status: input.status ?? "active", created_at: now, updated_at: now };
  }
  getTeam(teamId) {
    const row = this.db.prepare("SELECT * FROM entity_teams WHERE team_id = ?").get(teamId);
    return row ? this.teamFromRow(row, true) : null;
  }
  updateTeam(teamId, patch) {
    const row = this.db.prepare("SELECT * FROM entity_teams WHERE team_id = ?").get(teamId);
    if (!row) return null;
    const current = this.teamFromRow(row, true);
    const ownerUserId = patch.owner_user_id ?? current.owner_user_id;
    const userIds = patch.user_ids !== void 0 ? Array.from(/* @__PURE__ */ new Set([...patch.user_ids, ownerUserId])).sort() : this.parseArray(row.user_ids_json);
    if (ownerUserId && !userIds.includes(ownerUserId)) userIds.push(ownerUserId);
    const agentIds = patch.agent_ids !== void 0 ? patch.agent_ids : this.parseArray(row.agent_ids_json);
    const next = { ...current, ...patch, owner_user_id: ownerUserId, updated_at: (/* @__PURE__ */ new Date()).toISOString() };
    this.db.prepare("UPDATE entity_teams SET name = ?, description = ?, owner_user_id = ?, user_ids_json = ?, agent_ids_json = ?, status = ?, updated_at = ? WHERE team_id = ?").run(next.name, next.description ?? "", ownerUserId, this.jsonArray(userIds), this.jsonArray(agentIds), next.status, next.updated_at, teamId);
    return this.getTeam(teamId);
  }
  deleteTeams(teamIds) {
    const result = { deleted_ids: [], failed: [] };
    for (const id of teamIds) {
      const row = this.getTeam(id);
      if (!row) {
        result.failed.push({ id, reason: "not_found" });
        continue;
      }
      this.updateTeam(id, { status: "archived" });
      result.deleted_ids.push(id);
    }
    return result;
  }
  createUser(input) {
    const now = (/* @__PURE__ */ new Date()).toISOString();
    const id = input.user_id || this.entityId("user");
    this.db.prepare("INSERT INTO entity_users (user_id, name, job_description, team_ids_json, task_ids_json, owned_agent_ids_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)").run(id, input.name, input.job_description ?? "", this.jsonArray([]), this.jsonArray([]), this.jsonArray([]), input.status ?? "active", now, now);
    return this.getUser(id) ?? { user_id: id, name: input.name, team_ids: [], task_ids: [], owned_agent_ids: [], status: input.status ?? "active", created_at: now, updated_at: now };
  }
  getUser(userId) {
    const row = this.db.prepare("SELECT * FROM entity_users WHERE user_id = ?").get(userId);
    return row ? this.userFromRow(row, true) : null;
  }
  updateUser(userId, patch) {
    const current = this.getUser(userId);
    if (!current) return null;
    const next = { ...current, ...patch, updated_at: (/* @__PURE__ */ new Date()).toISOString() };
    this.db.prepare("UPDATE entity_users SET name = ?, job_description = ?, status = ?, updated_at = ? WHERE user_id = ?").run(next.name, next.job_description ?? "", next.status, next.updated_at, userId);
    return this.getUser(userId);
  }
  deleteUsers(userIds) {
    const result = { deleted_ids: [], failed: [] };
    for (const id of userIds) {
      if (!this.getUser(id)) {
        result.failed.push({ id, reason: "not_found" });
        continue;
      }
      this.updateUser(id, { status: "inactive" });
      result.deleted_ids.push(id);
    }
    return result;
  }
  createAgent(input) {
    const now = (/* @__PURE__ */ new Date()).toISOString();
    const id = input.agent_id || this.entityId("agent");
    this.db.prepare("INSERT INTO entity_agents (agent_id, team_id, name, description, prompt, owner_user_id, visibility, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(id, input.team_id, input.name, input.description ?? "", input.prompt ?? "", input.owner_user_id ?? "", input.visibility ?? "team", input.status ?? "active", now, now);
    const team = this.getTeam(input.team_id);
    if (team && !(team.agent_ids ?? []).includes(id)) this.updateTeam(input.team_id, { agent_ids: [...team.agent_ids ?? [], id] });
    return this.getAgent(id) ?? { agent_id: id, team_id: input.team_id, name: input.name, visibility: input.visibility ?? "team", status: input.status ?? "active", created_at: now, updated_at: now };
  }
  getAgent(agentId) {
    const row = this.db.prepare("SELECT * FROM entity_agents WHERE agent_id = ?").get(agentId);
    return row ? this.agentFromRow(row) : null;
  }
  updateAgent(agentId, patch) {
    const current = this.getAgent(agentId);
    if (!current) return null;
    const next = { ...current, ...patch, updated_at: (/* @__PURE__ */ new Date()).toISOString() };
    this.db.prepare("UPDATE entity_agents SET name = ?, description = ?, prompt = ?, owner_user_id = ?, visibility = ?, status = ?, updated_at = ? WHERE agent_id = ?").run(next.name, next.description ?? "", next.prompt ?? "", next.owner_user_id ?? "", next.visibility, next.status, next.updated_at, agentId);
    return this.getAgent(agentId);
  }
  deleteAgents(agentIds) {
    const result = { deleted_ids: [], failed: [] };
    for (const id of agentIds) {
      if (!this.getAgent(id)) {
        result.failed.push({ id, reason: "not_found" });
        continue;
      }
      this.updateAgent(id, { status: "inactive" });
      result.deleted_ids.push(id);
    }
    return result;
  }
  createTask(input) {
    const now = (/* @__PURE__ */ new Date()).toISOString();
    const id = input.task_id || this.entityId("task");
    this.db.prepare("INSERT INTO entity_tasks (task_id, team_id, creator_user_id, title, description, source_type, source_url, status, auto_assign_floating_assets, risk_level, agent_ids_json, user_ids_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(id, input.team_id, input.creator_user_id, input.title ?? "", input.description ?? "", input.source_type ?? "manual", input.source_url ?? "", "pending", 0, "low", this.jsonArray(input.agent_ids), this.jsonArray(input.user_ids), now, now);
    return this.getTask(id) ?? { task_id: id, team_id: input.team_id, creator_user_id: input.creator_user_id, source_type: input.source_type ?? "manual", agent_ids: input.agent_ids ?? [], user_ids: input.user_ids ?? [], created_at: now, updated_at: now };
  }
  getTask(taskId) {
    const row = this.db.prepare("SELECT * FROM entity_tasks WHERE task_id = ?").get(taskId);
    return row ? this.taskFromRow(row) : null;
  }
  updateTask(taskId, patch) {
    const current = this.getTask(taskId);
    if (!current) return null;
    const next = { ...current, ...patch, updated_at: (/* @__PURE__ */ new Date()).toISOString() };
    this.db.prepare("UPDATE entity_tasks SET title = ?, description = ?, source_type = ?, source_url = ?, agent_ids_json = ?, user_ids_json = ?, updated_at = ? WHERE task_id = ?").run(next.title ?? "", next.description ?? "", next.source_type, next.source_url ?? "", this.jsonArray(next.agent_ids), this.jsonArray(next.user_ids), next.updated_at, taskId);
    return this.getTask(taskId);
  }
  deleteTasks(taskIds) {
    const result = { deleted_ids: [], failed: [] };
    for (const id of taskIds) {
      if (!this.getTask(id)) {
        result.failed.push({ id, reason: "not_found" });
        continue;
      }
      this.db.prepare("DELETE FROM entity_tasks WHERE task_id = ?").run(id);
      result.deleted_ids.push(id);
    }
    return result;
  }
  // ── Knowledge entity ──
  knowledgeFromRow(row) {
    return {
      knowledge_id: String(row.knowledge_id ?? ""),
      type: row.type ?? "wiki",
      service_url: String(row.service_url ?? ""),
      name: String(row.name ?? ""),
      summary: row.summary ?? null,
      team_id: String(row.team_id ?? ""),
      agent_id: String(row.agent_id ?? ""),
      user_id: row.user_id ?? null,
      repo_url: row.repo_url ?? void 0,
      branch: row.branch ?? void 0,
      created_at: String(row.created_at ?? ""),
      updated_at: String(row.updated_at ?? "")
    };
  }
  createKnowledge(input) {
    const now = (/* @__PURE__ */ new Date()).toISOString();
    const existing = this.db.prepare("SELECT created_at FROM entity_knowledge WHERE knowledge_id = ?").get(input.knowledge_id);
    if (existing) {
      this.db.prepare(
        "UPDATE entity_knowledge SET type=?, service_url=?, name=?, summary=?, team_id=?, agent_id=?, user_id=?, repo_url=?, branch=?, updated_at=? WHERE knowledge_id=?"
      ).run(input.type, input.service_url, input.name, input.summary ?? null, input.team_id, input.agent_id ?? "", input.user_id ?? null, input.repo_url ?? null, input.branch ?? null, now, input.knowledge_id);
      return this.getKnowledge(input.knowledge_id);
    }
    this.db.prepare(
      "INSERT INTO entity_knowledge (knowledge_id, type, service_url, name, summary, team_id, agent_id, user_id, repo_url, branch, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ).run(input.knowledge_id, input.type, input.service_url, input.name, input.summary ?? null, input.team_id, input.agent_id ?? "", input.user_id ?? null, input.repo_url ?? null, input.branch ?? null, now, now);
    return this.getKnowledge(input.knowledge_id);
  }
  getKnowledge(knowledgeId) {
    const row = this.db.prepare("SELECT * FROM entity_knowledge WHERE knowledge_id = ?").get(knowledgeId);
    return row ? this.knowledgeFromRow(row) : null;
  }
  updateKnowledge(knowledgeId, patch) {
    const current = this.getKnowledge(knowledgeId);
    if (!current) return null;
    const now = (/* @__PURE__ */ new Date()).toISOString();
    const sets = ["updated_at = ?"];
    const args = [now];
    if (patch.name !== void 0) {
      sets.push("name = ?");
      args.push(patch.name);
    }
    if (patch.summary !== void 0) {
      sets.push("summary = ?");
      args.push(patch.summary);
    }
    if (patch.service_url !== void 0) {
      sets.push("service_url = ?");
      args.push(patch.service_url);
    }
    if (patch.repo_url !== void 0) {
      sets.push("repo_url = ?");
      args.push(patch.repo_url);
    }
    if (patch.branch !== void 0) {
      sets.push("branch = ?");
      args.push(patch.branch);
    }
    args.push(knowledgeId);
    this.db.prepare(`UPDATE entity_knowledge SET ${sets.join(", ")} WHERE knowledge_id = ?`).run(...args);
    return this.getKnowledge(knowledgeId);
  }
  deleteKnowledge(knowledgeIds, teamId) {
    const result = { deleted_ids: [], failed: [] };
    for (const id of knowledgeIds) {
      const row = this.getKnowledge(id);
      if (!row) {
        result.failed.push({ id, reason: "not_found" });
        continue;
      }
      if (teamId && row.team_id !== teamId) {
        result.failed.push({ id, reason: "team_mismatch" });
        continue;
      }
      this.db.prepare("DELETE FROM entity_knowledge WHERE knowledge_id = ?").run(id);
      result.deleted_ids.push(id);
    }
    return result;
  }
  listKnowledge(input) {
    const limit = Math.min(Math.max(input.limit ?? 20, 1), 1e3);
    const offset = Math.max(input.offset ?? 0, 0);
    const ids = input.knowledge_ids;
    if (ids && ids.length === 0) return { items: [], total: 0 };
    const idClause = ids && ids.length > 0 ? ` AND knowledge_id IN (${ids.map(() => "?").join(",")})` : "";
    let sql = "SELECT * FROM entity_knowledge WHERE team_id = ?";
    const args = [input.team_id];
    if (input.type) {
      sql += " AND type = ?";
      args.push(input.type);
    }
    if (idClause) {
      sql += idClause;
      args.push(...ids);
    }
    sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?";
    args.push(limit, offset);
    const rows = this.db.prepare(sql).all(...args);
    const items = rows.map((r) => this.knowledgeFromRow(r));
    let countSql = "SELECT COUNT(*) as total FROM entity_knowledge WHERE team_id = ?";
    const countArgs = [input.team_id];
    if (input.type) {
      countSql += " AND type = ?";
      countArgs.push(input.type);
    }
    if (idClause) {
      countSql += idClause;
      countArgs.push(...ids);
    }
    const totalRow = this.db.prepare(countSql).get(...countArgs);
    return { items, total: totalRow?.total ?? 0 };
  }
  /**
   * FTS5 keyword search on L1 records.
   * Returns top-`limit` results sorted by BM25 relevance (highest first).
   *
   * @param ftsQuery  A pre-built FTS5 MATCH expression (from `buildFtsQuery()`).
   * @param limit     Maximum number of results to return.
   *
   * **Fault-tolerant**: returns an empty array on any error.
   */
  searchL1Fts(ftsQuery, limit = 20, filter, memoryFilter) {
    if (this.degraded || !this.ftsAvailable) return [];
    try {
      const retrieveLimit = filter ? Math.max(limit * 5, limit) : limit;
      let statement = this.stmtL1FtsSearch;
      const parameters = [ftsQuery];
      if (memoryFilter) {
        const conditions = ["l1_fts MATCH ?"];
        for (const key of ["layer", "device", "project", "status"]) {
          if (memoryFilter[key] !== void 0) {
            conditions.push(`json_extract(metadata_json, '$.memory.${key}') = ?`);
            parameters.push(memoryFilter[key]);
          }
        }
        if (memoryFilter.excludeSuperseded) {
          conditions.push("COALESCE(json_extract(metadata_json, '$.memory.status'), '') <> ?");
          parameters.push("superseded");
        }
        for (const [key, column] of [["teamId", "team_id"], ["userId", "user_id"], ["agentId", "agent_id"]]) {
          if (filter?.[key]) {
            conditions.push(column + " = ?");
            parameters.push(filter[key]);
          }
        }
        statement = this.db.prepare(`SELECT *, content_original AS content, bm25(l1_fts) AS rank FROM l1_fts WHERE ${conditions.join(" AND ")} ORDER BY rank ASC LIMIT ?`);
      }
      parameters.push(retrieveLimit);
      const rows = statement.all(...parameters);
      return rows.filter((r) => rowMatchesIsolation(r, filter)).slice(0, limit).map((r) => ({
        record_id: r.record_id,
        content: r.content,
        type: r.type,
        priority: r.priority,
        scene_name: r.scene_name,
        score: bm25RankToScore(r.rank),
        timestamp_str: r.timestamp_str,
        timestamp_start: r.timestamp_start,
        timestamp_end: r.timestamp_end,
        version: r.version ?? 0,
        session_key: r.session_key,
        session_id: r.session_id,
        team_id: r.team_id ?? "",
        task_id: r.task_id ?? "",
        user_id: r.user_id ?? "",
        agent_id: r.agent_id ?? "",
        metadata_json: r.metadata_json
      }));
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L1-fts-search] FAILED (non-fatal, returning empty): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  /**
   * FTS5 keyword search on L0 conversation messages.
   * Returns top-`limit` results sorted by BM25 relevance (highest first).
   *
   * @param ftsQuery  A pre-built FTS5 MATCH expression (from `buildFtsQuery()`).
   * @param limit     Maximum number of results to return.
   *
   * **Fault-tolerant**: returns an empty array on any error.
   */
  searchL0Fts(ftsQuery, limit = _VectorStore.FTS_DEFAULT_LIMIT, filter) {
    if (this.degraded || !this.ftsAvailable) return [];
    try {
      const retrieveLimit = filter ? Math.max(limit * 5, limit) : limit;
      const rows = this.stmtL0FtsSearch.all(ftsQuery, retrieveLimit);
      return rows.filter((r) => rowMatchesIsolation(r, filter)).slice(0, limit).map((r) => ({
        record_id: r.record_id,
        session_key: r.session_key,
        session_id: r.session_id,
        team_id: r.team_id ?? "",
        task_id: r.task_id ?? "",
        user_id: r.user_id ?? "",
        agent_id: r.agent_id ?? "",
        role: r.role,
        message_text: r.message_text,
        score: bm25RankToScore(r.rank),
        recorded_at: r.recorded_at,
        timestamp: r.timestamp ?? 0
      }));
    } catch (err) {
      this.logger?.warn(
        `${TAG} [L0-fts-search] FAILED (non-fatal, returning empty): ${err instanceof Error ? err.message : String(err)}`
      );
      return [];
    }
  }
  // ── FTS5 migration & rebuild ──────────────────────────────────────────────
  /**
   * Detect old FTS5 v1 schema (no `content_original` column) and drop the
   * tables so they can be recreated with the v2 schema.
   *
   * FTS5 virtual tables do NOT support `ALTER TABLE ADD COLUMN`, so the only
   * migration path is DROP + recreate + repopulate.
   *
   * @returns `true` if migration was performed (= FTS index needs rebuilding).
   * @internal
   */
  migrateFtsTablesIfNeeded() {
    try {
      const l1Exists = this.db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='l1_fts'").get();
      if (!l1Exists) {
        const hasData = this.db.prepare("SELECT 1 FROM l1_records LIMIT 1").get();
        return !!hasData;
      }
      const cols = this.db.prepare("SELECT name FROM pragma_table_info('l1_fts')").all();
      const hasV2Col = cols.some((c) => c.name === "content_original");
      const hasV3Col = cols.some((c) => c.name === "user_id") && cols.some((c) => c.name === "agent_id");
      const hasV4Col = cols.some((c) => c.name === "version");
      const hasV5Col = cols.some((c) => c.name === "task_id");
      if (hasV2Col && hasV3Col && hasV4Col && hasV5Col) {
        return false;
      }
      if (!hasV2Col) {
        this.logger?.info(`${TAG} Migrating FTS5 tables v1 \u2192 v3 (jieba + tenancy isolation)`);
      } else if (!hasV3Col) {
        this.logger?.info(`${TAG} Migrating FTS5 tables v2 \u2192 v3 (add user_id / agent_id columns)`);
      } else if (!hasV4Col) {
        this.logger?.info(`${TAG} Migrating FTS5 tables v3 \u2192 v4 (add version column)`);
      } else if (!hasV5Col) {
        this.logger?.info(`${TAG} Migrating FTS5 tables v4 \u2192 v5 (add task_id column)`);
      }
      this.db.exec("DROP TABLE IF EXISTS l1_fts");
      this.db.exec("DROP TABLE IF EXISTS l0_fts");
      return true;
    } catch (err) {
      this.logger?.warn(
        `${TAG} FTS migration check failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
      return false;
    }
  }
  /**
   * Rebuild the FTS5 index from scratch by reading all records from the
   * metadata tables and re-inserting them with jieba-segmented text.
   *
   * Called automatically after:
   *  - Schema migration from v1 to v2
   *  - Fresh table creation when existing data exists
   *
   * Safe to call multiple times (idempotent — clears FTS tables first).
   */
  rebuildFtsIndex() {
    if (!this.ftsAvailable) return;
    try {
      this.logger?.info(`${TAG} Rebuilding FTS5 index with jieba segmentation\u2026`);
      this.db.exec("DELETE FROM l1_fts");
      const l1Rows = this.db.prepare(`
          SELECT record_id, content, type, priority, scene_name,
                 session_key, session_id, team_id, task_id, user_id, agent_id, version,
                 timestamp_str, timestamp_start, timestamp_end, metadata_json
          FROM l1_records
        `).all();
      let l1Count = 0;
      for (const r of l1Rows) {
        try {
          this.stmtL1FtsInsert.run(
            tokenizeForFts(r.content),
            // content — segmented
            r.content,
            // content_original — raw
            r.record_id,
            r.type,
            r.priority,
            r.scene_name,
            r.session_key,
            r.session_id || DEFAULT_ISOLATION_ID,
            r.team_id || "",
            r.task_id || "",
            r.user_id || DEFAULT_ISOLATION_ID,
            r.agent_id || DEFAULT_ISOLATION_ID,
            r.version ?? 0,
            r.timestamp_str,
            r.timestamp_start,
            r.timestamp_end,
            r.metadata_json
          );
          l1Count++;
        } catch (err) {
          this.logger?.warn?.(
            `${TAG} FTS rebuild skip L1 ${r.record_id}: ${err instanceof Error ? err.message : String(err)}`
          );
        }
      }
      this.db.exec("DELETE FROM l0_fts");
      const l0Rows = this.db.prepare(`
          SELECT record_id, message_text, session_key, session_id, team_id, task_id, user_id, agent_id,
                 role, recorded_at, timestamp
          FROM l0_conversations
        `).all();
      let l0Count = 0;
      for (const r of l0Rows) {
        try {
          this.stmtL0FtsInsert.run(
            tokenizeForFts(r.message_text),
            // message_text — segmented
            r.message_text,
            // message_text_original — raw
            r.record_id,
            r.session_key,
            r.session_id,
            r.team_id ?? "",
            r.task_id ?? "",
            r.user_id ?? "",
            r.agent_id ?? "",
            r.role,
            r.recorded_at,
            r.timestamp
          );
          l0Count++;
        } catch (err) {
          this.logger?.warn?.(
            `${TAG} FTS rebuild skip L0 ${r.record_id}: ${err instanceof Error ? err.message : String(err)}`
          );
        }
      }
      this.logger?.info(
        `${TAG} FTS5 rebuild complete: L1=${l1Count}/${l1Rows.length}, L0=${l0Count}/${l0Rows.length}`
      );
    } catch (err) {
      this.logger?.warn(
        `${TAG} FTS5 rebuild failed (non-fatal): ${err instanceof Error ? err.message : String(err)}`
      );
    }
  }
  // ============================
  // IMemoryStore interface implementation
  // ============================
  /** Query the store's search capabilities. */
  getCapabilities() {
    return {
      vectorSearch: this.vecTablesReady,
      ftsSearch: this.ftsAvailable,
      nativeHybridSearch: false,
      sparseVectors: false,
      profileRows: false
    };
  }
  // ─────────────────────────────────────────────────────────
  // Memory Audit (修改审计)
  // ─────────────────────────────────────────────────────────
  appendAudit(entry) {
    const stmt = this.db.prepare(`
      INSERT OR REPLACE INTO memory_audit
        (audit_id, record_id, layer, action,
         team_id, agent_id, user_id, task_id,
         version, updated_at_ms, request_id)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      entry.audit_id,
      entry.record_id,
      entry.layer,
      entry.action,
      entry.team_id ?? null,
      entry.agent_id ?? null,
      entry.user_id ?? null,
      entry.task_id ?? null,
      entry.version,
      entry.updated_at_ms,
      entry.request_id ?? null
    );
  }
  queryAudit(filter) {
    const conds = [];
    const args = [];
    if (filter.record_id !== void 0) {
      conds.push("record_id = ?");
      args.push(filter.record_id);
    }
    if (filter.layer !== void 0) {
      conds.push("layer = ?");
      args.push(filter.layer);
    }
    if (filter.action !== void 0) {
      conds.push("action = ?");
      args.push(filter.action);
    }
    if (filter.team_id !== void 0) {
      conds.push("team_id = ?");
      args.push(filter.team_id);
    }
    if (filter.agent_id !== void 0) {
      conds.push("agent_id = ?");
      args.push(filter.agent_id);
    }
    if (filter.user_id !== void 0) {
      conds.push("user_id = ?");
      args.push(filter.user_id);
    }
    if (filter.task_id !== void 0) {
      conds.push("task_id = ?");
      args.push(filter.task_id);
    }
    if (filter.since_ms !== void 0) {
      conds.push("updated_at_ms >= ?");
      args.push(filter.since_ms);
    }
    if (filter.until_ms !== void 0) {
      conds.push("updated_at_ms <= ?");
      args.push(filter.until_ms);
    }
    const where = conds.length > 0 ? `WHERE ${conds.join(" AND ")}` : "";
    const limit = Math.min(Math.max(filter.limit ?? 100, 1), 1e3);
    const offset = Math.max(filter.offset ?? 0, 0);
    const sql = `
      SELECT audit_id, record_id, layer, action,
             team_id, agent_id, user_id, task_id,
             version, updated_at_ms, request_id
      FROM memory_audit
      ${where}
      ORDER BY updated_at_ms DESC, audit_id DESC
      LIMIT ? OFFSET ?
    `;
    const stmt = this.db.prepare(sql);
    const rows = stmt.all(...args, limit, offset);
    return rows.map((r) => ({
      audit_id: r.audit_id,
      record_id: r.record_id,
      layer: r.layer,
      action: r.action,
      team_id: r.team_id ?? void 0,
      agent_id: r.agent_id ?? void 0,
      user_id: r.user_id ?? void 0,
      task_id: r.task_id ?? void 0,
      version: r.version,
      updated_at_ms: r.updated_at_ms,
      request_id: r.request_id ?? void 0
    }));
  }
  // ─────────────────────────────────────────────────────────
  // Memory Generation Provenance References
  // ─────────────────────────────────────────────────────────
  upsertMemoryGenerationRefs(records) {
    const stmt = this.db.prepare(`
      INSERT INTO memory_generation_refs
        (generation_ref_id, layer, memory_id, generation_id, generation_log_id,
         generation_log_key, memory_prompt_id, memory_prompt_version,
         memory_prompt_source, created_at_ms)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(generation_ref_id) DO UPDATE SET
        memory_id=excluded.memory_id,
        generation_id=excluded.generation_id,
        generation_log_id=excluded.generation_log_id,
        generation_log_key=excluded.generation_log_key,
        memory_prompt_id=excluded.memory_prompt_id,
        memory_prompt_version=excluded.memory_prompt_version,
        memory_prompt_source=excluded.memory_prompt_source,
        created_at_ms=excluded.created_at_ms
    `);
    this.db.exec("BEGIN IMMEDIATE");
    try {
      for (const record of records) {
        stmt.run(
          record.generation_ref_id,
          record.layer,
          record.memory_id,
          record.generation_id,
          record.generation_log_id,
          record.generation_log_key,
          record.memory_prompt_id,
          record.memory_prompt_version,
          record.memory_prompt_source,
          record.created_at_ms
        );
      }
      this.db.exec("COMMIT");
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }
  getMemoryGenerationRef(layer, memoryId) {
    const id = buildMemoryGenerationRefId(layer, memoryId);
    return this.db.prepare(
      "SELECT * FROM memory_generation_refs WHERE generation_ref_id = ? AND layer = ? AND memory_id = ?"
    ).get(id, layer, memoryId) ?? null;
  }
  // ─────────────────────────────────────────────────────────
  // Custom Memory Prompt
  // ─────────────────────────────────────────────────────────
  countMemoryPrompts() {
    const row = this.db.prepare("SELECT COUNT(*) AS total FROM memory_prompts").get();
    return Number(row?.total ?? 0);
  }
  createMemoryPrompt(record) {
    this.db.prepare(`
      INSERT INTO memory_prompts
        (memory_prompt_id, name, layer, prompt, version, status,
         created_by, updated_by, created_at_ms, updated_at_ms)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      record.memory_prompt_id,
      record.name,
      record.layer,
      record.prompt,
      record.version,
      record.status,
      record.created_by ?? null,
      record.updated_by ?? null,
      record.created_at_ms,
      record.updated_at_ms
    );
    return record;
  }
  getMemoryPrompts(ids) {
    if (ids.length === 0) return [];
    const placeholders = ids.map(() => "?").join(",");
    return this.db.prepare(
      `SELECT * FROM memory_prompts WHERE memory_prompt_id IN (${placeholders})`
    ).all(...ids);
  }
  listMemoryPrompts(filter) {
    const conds = ["status = 'active'"];
    const args = [];
    if (filter.layer) {
      conds.push("layer = ?");
      args.push(filter.layer);
    }
    const order = filter.timeOrder === "asc" ? "ASC" : "DESC";
    const limit = Math.min(Math.max(filter.limit ?? 20, 1), 100);
    const offset = Math.max(filter.offset ?? 0, 0);
    return this.db.prepare(`
      SELECT * FROM memory_prompts
      WHERE ${conds.join(" AND ")}
      ORDER BY updated_at_ms ${order}, memory_prompt_id ${order}
      LIMIT ? OFFSET ?
    `).all(...args, limit, offset);
  }
  updateMemoryPrompt(id, patch) {
    const current = this.getMemoryPrompts([id])[0];
    if (!current || current.status !== "active") return null;
    const sameName = patch.name === void 0 || patch.name === current.name;
    const samePrompt = patch.prompt === void 0 || patch.prompt === current.prompt;
    if (sameName && samePrompt) return current;
    const sets = ["version = version + 1", "updated_at_ms = ?", "updated_by = ?"];
    const args = [patch.updated_at_ms, patch.updated_by ?? null];
    if (patch.name !== void 0) {
      sets.push("name = ?");
      args.push(patch.name);
    }
    if (patch.prompt !== void 0) {
      sets.push("prompt = ?");
      args.push(patch.prompt);
    }
    args.push(id);
    const result = this.db.prepare(
      `UPDATE memory_prompts SET ${sets.join(", ")} WHERE memory_prompt_id = ? AND status = 'active'`
    ).run(...args);
    if (Number(result.changes ?? 0) === 0) return null;
    return this.getMemoryPrompts([id])[0] ?? null;
  }
  getMemoryPromptSettings(ids) {
    if (ids.length === 0) return [];
    const placeholders = ids.map(() => "?").join(",");
    return this.db.prepare(
      `SELECT * FROM memory_prompt_settings WHERE setting_id IN (${placeholders})`
    ).all(...ids);
  }
  listMemoryPromptSettings(filter) {
    const conds = [];
    const args = [];
    if (filter.memoryPromptId) {
      conds.push("memory_prompt_id = ?");
      args.push(filter.memoryPromptId);
    }
    if (filter.targetType) {
      conds.push("target_type = ?");
      args.push(filter.targetType);
    }
    if (filter.teamId) {
      conds.push("team_id = ?");
      args.push(filter.teamId);
    }
    if (filter.agentId) {
      conds.push("agent_id = ?");
      args.push(filter.agentId);
    }
    if (filter.layer) {
      conds.push("layer = ?");
      args.push(filter.layer);
    }
    const where = conds.length > 0 ? `WHERE ${conds.join(" AND ")}` : "";
    const order = filter.timeOrder === "asc" ? "ASC" : "DESC";
    const limit = Math.min(Math.max(filter.limit ?? 20, 1), 100);
    const offset = Math.max(filter.offset ?? 0, 0);
    return this.db.prepare(`
      SELECT * FROM memory_prompt_settings ${where}
      ORDER BY updated_at_ms ${order}, setting_id ${order}
      LIMIT ? OFFSET ?
    `).all(...args, limit, offset);
  }
  upsertMemoryPromptSettings(records, logs) {
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const upsert = this.db.prepare(`
        INSERT INTO memory_prompt_settings
          (setting_id, target_type, team_id, agent_id, layer, memory_prompt_id, updated_by, updated_at_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(setting_id) DO UPDATE SET
          target_type=excluded.target_type, team_id=excluded.team_id,
          agent_id=excluded.agent_id, layer=excluded.layer,
          memory_prompt_id=excluded.memory_prompt_id, updated_by=excluded.updated_by,
          updated_at_ms=excluded.updated_at_ms
      `);
      for (const record of records) {
        upsert.run(
          record.setting_id,
          record.target_type,
          record.team_id ?? null,
          record.agent_id ?? null,
          record.layer,
          record.memory_prompt_id,
          record.updated_by ?? null,
          record.updated_at_ms
        );
      }
      this.insertMemoryPromptSettingLogs(logs);
      this.db.exec("COMMIT");
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }
  clearMemoryPromptSettings(ids, logs) {
    if (ids.length === 0) return;
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const del = this.db.prepare("DELETE FROM memory_prompt_settings WHERE setting_id = ?");
      for (const id of ids) del.run(id);
      this.insertMemoryPromptSettingLogs(logs);
      this.db.exec("COMMIT");
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }
  insertMemoryPromptSettingLogs(logs) {
    const insert = this.db.prepare(`
      INSERT OR IGNORE INTO memory_prompt_setting_logs
        (setting_log_id, target_type, team_id, agent_id, layer, action, reason,
         before_memory_prompt_id, after_memory_prompt_id, operator_id, operated_at_ms)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    for (const log of logs) {
      insert.run(
        log.setting_log_id,
        log.target_type,
        log.team_id ?? null,
        log.agent_id ?? null,
        log.layer,
        log.action,
        log.reason,
        log.before_memory_prompt_id ?? null,
        log.after_memory_prompt_id ?? null,
        log.operator_id ?? null,
        log.operated_at_ms
      );
    }
  }
  deleteMemoryPrompts(ids, operatorId) {
    const prompts = this.getMemoryPrompts(ids);
    if (prompts.length !== ids.length) return { deleted_prompt_ids: [], cleared_settings: { instance: 0, team: 0, agent: 0 } };
    const cleared = { instance: 0, team: 0, agent: 0 };
    const placeholders = ids.map(() => "?").join(",");
    const settings = this.db.prepare(
      `SELECT * FROM memory_prompt_settings WHERE memory_prompt_id IN (${placeholders})`
    ).all(...ids);
    const now = Date.now();
    const logs = settings.map((setting) => {
      cleared[setting.target_type] += 1;
      return {
        setting_log_id: `mpsl:delete:${setting.setting_id}:${setting.memory_prompt_id}`,
        target_type: setting.target_type,
        team_id: setting.team_id,
        agent_id: setting.agent_id,
        layer: setting.layer,
        action: "clear",
        reason: "prompt_deleted",
        before_memory_prompt_id: setting.memory_prompt_id,
        operator_id: operatorId,
        operated_at_ms: now
      };
    });
    this.db.exec("BEGIN IMMEDIATE");
    try {
      this.db.prepare(`UPDATE memory_prompts SET status = 'deleting' WHERE memory_prompt_id IN (${placeholders})`).run(...ids);
      this.db.prepare(`DELETE FROM memory_prompt_settings WHERE memory_prompt_id IN (${placeholders})`).run(...ids);
      this.insertMemoryPromptSettingLogs(logs);
      this.db.prepare(`DELETE FROM memory_prompts WHERE memory_prompt_id IN (${placeholders})`).run(...ids);
      this.db.exec("COMMIT");
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
    return { deleted_prompt_ids: ids, cleared_settings: cleared };
  }
  queryMemoryPromptSettingLogs(filter) {
    const conds = [];
    const args = [];
    if (filter.memoryPromptId) {
      conds.push("(before_memory_prompt_id = ? OR after_memory_prompt_id = ?)");
      args.push(filter.memoryPromptId, filter.memoryPromptId);
    }
    if (filter.teamId) {
      conds.push("team_id = ?");
      args.push(filter.teamId);
    }
    if (filter.agentId) {
      conds.push("agent_id = ?");
      args.push(filter.agentId);
    }
    if (filter.action) {
      conds.push("action = ?");
      args.push(filter.action);
    }
    if (filter.startTimeMs !== void 0) {
      conds.push("operated_at_ms >= ?");
      args.push(filter.startTimeMs);
    }
    if (filter.endTimeMs !== void 0) {
      conds.push("operated_at_ms <= ?");
      args.push(filter.endTimeMs);
    }
    const where = conds.length > 0 ? `WHERE ${conds.join(" AND ")}` : "";
    const order = filter.timeOrder === "asc" ? "ASC" : "DESC";
    const limit = Math.min(Math.max(filter.limit ?? 20, 1), 100);
    const offset = Math.max(filter.offset ?? 0, 0);
    return this.db.prepare(`
      SELECT * FROM memory_prompt_setting_logs ${where}
      ORDER BY operated_at_ms ${order}, setting_log_id ${order}
      LIMIT ? OFFSET ?
    `).all(...args, limit, offset);
  }
  /**
   * Close the database connection.
   * Should be called on shutdown. Idempotent — safe to call multiple times.
   */
  close() {
    if (this.closed) return;
    this.closed = true;
    try {
      this.db.close();
    } catch (err) {
      this.logger?.warn?.(
        `${TAG} Error closing database: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  }
};

// src/core/storage/local-backend.ts
import { readFile, writeFile, mkdir, readdir, unlink, stat, rm, appendFile } from "node:fs/promises";
import { existsSync as existsSync2 } from "node:fs";
import { join, dirname, sep, resolve } from "node:path";

// src/core/storage/list-page.ts
function pageEntries(all, opts) {
  const maxKeys = opts?.maxKeys ?? 100;
  const sorted = all.slice().sort((a, b) => a.key < b.key ? -1 : a.key > b.key ? 1 : 0);
  const marker = opts?.marker;
  const found = marker ? sorted.findIndex((e) => e.key > marker) : 0;
  const startIdx = found < 0 ? sorted.length : found;
  const page = sorted.slice(startIdx, startIdx + maxKeys);
  return {
    entries: page,
    nextMarker: startIdx + page.length < sorted.length ? page[page.length - 1]?.key : void 0,
    total: page.length
  };
}

// src/core/storage/local-backend.ts
var TAG2 = "[storage][local]";
var LocalStorageBackend = class {
  type = "local";
  rootDir;
  logger;
  constructor(opts) {
    if (typeof opts === "string") {
      this.rootDir = opts;
    } else {
      this.rootDir = opts.rootDir;
      this.logger = opts.logger;
    }
  }
  /**
   * Resolve a storage key to an absolute filesystem path under rootDir.
   *
   * CR-6 fix (2026-05-19): rejects path-traversal attempts. Without this guard
   * a key containing "../" or absolute paths could read/write arbitrary files
   * on disk (e.g. getObject("../../../etc/passwd") would resolve outside
   * rootDir). Affects standalone mode where user-controllable fields like
   * instanceId / sceneName / sessionKey end up in the key.
   *
   * Rejected:
   * - Empty key
   * - Keys containing NUL (\0) — POSIX/Linux path terminator, can confuse
   *   downstream tooling (sqlite, file managers).
   * - Keys with leading "/" or "\" (absolute paths).
   * - Keys whose resolved path falls outside rootDir (../ traversal).
   */
  resolvePath(key) {
    if (!key || typeof key !== "string") {
      throw new Error(`Invalid storage key: ${JSON.stringify(key)}`);
    }
    if (key.includes("\0")) {
      throw new Error("Storage key must not contain NUL character");
    }
    if (key.startsWith("/") || key.startsWith("\\")) {
      throw new Error(`Storage key must be relative, got absolute: ${key}`);
    }
    const normalized = key.split("/").join(sep);
    const absRoot = resolve(this.rootDir);
    const absResolved = resolve(absRoot, normalized);
    const rootWithSep = absRoot.endsWith(sep) ? absRoot : absRoot + sep;
    if (absResolved !== absRoot && !absResolved.startsWith(rootWithSep)) {
      throw new Error(`Path traversal rejected: key "${key}" escapes rootDir`);
    }
    return absResolved;
  }
  async putObject(key, content, opts) {
    const filePath = this.resolvePath(key);
    await mkdir(dirname(filePath), { recursive: true });
    const buf = typeof content === "string" ? Buffer.from(content, "utf-8") : content;
    await writeFile(filePath, buf);
    if (opts?.contentType || opts?.metadata && Object.keys(opts.metadata).length > 0) {
      const metaPath = filePath + ".meta.json";
      await writeFile(metaPath, JSON.stringify({
        contentType: opts.contentType,
        metadata: opts.metadata
      }));
    }
    this.logger?.debug?.(`${TAG2} putObject: ${key} (${buf.length} bytes)`);
  }
  /**
   * Append content to the end of a file. CR-1 fix (2026-05-19): uses POSIX
   * fs.appendFile (with O_APPEND flag) which is atomic per call on local fs,
   * so concurrent appendObject calls to the same key do not race.
   */
  async appendObject(key, content) {
    const filePath = this.resolvePath(key);
    await mkdir(dirname(filePath), { recursive: true });
    const buf = typeof content === "string" ? Buffer.from(content, "utf-8") : content;
    await appendFile(filePath, buf);
    this.logger?.debug?.(`${TAG2} appendObject: ${key} (+${buf.length} bytes)`);
  }
  async getObject(key) {
    const filePath = this.resolvePath(key);
    if (!existsSync2(filePath)) {
      return null;
    }
    try {
      const [content, stats] = await Promise.all([
        readFile(filePath),
        stat(filePath)
      ]);
      let contentType;
      let metadata;
      const metaPath = filePath + ".meta.json";
      if (existsSync2(metaPath)) {
        try {
          const metaRaw = await readFile(metaPath, "utf-8");
          const meta = JSON.parse(metaRaw);
          contentType = meta.contentType;
          metadata = meta.metadata;
        } catch {
        }
      }
      return {
        key,
        content,
        contentType,
        metadata,
        lastModified: stats.mtime,
        size: stats.size
      };
    } catch (err) {
      if (err.code === "ENOENT") {
        return null;
      }
      throw err;
    }
  }
  async exists(key) {
    const filePath = this.resolvePath(key);
    return existsSync2(filePath);
  }
  /**
   * List objects under a key prefix, per the D9.2 contract
   * (see storage/__contract__/storage-backend.contract.ts).
   *
   * The prefix is a *string* prefix rather than a directory, so it is split
   * into the deepest enclosing directory plus a leading fragment of the entry
   * name: "scene_blocks/wo" lists "scene_blocks/" and keeps names starting
   * with "wo".
   */
  async listObjects(prefix, opts) {
    const recursive = opts?.recursive ?? false;
    const lastSlash = prefix.lastIndexOf("/");
    const dirKey = lastSlash >= 0 ? prefix.slice(0, lastSlash + 1) : "";
    const namePrefix = lastSlash >= 0 ? prefix.slice(lastSlash + 1) : prefix;
    const dirPath = this.resolveDir(dirKey);
    if (!existsSync2(dirPath)) {
      return { entries: [], total: 0 };
    }
    const allEntries = [];
    if (recursive) {
      await this.collectFiles(dirPath, dirKey, prefix, allEntries, 1e4);
    } else {
      await this.collectFolded(dirPath, dirKey, namePrefix, allEntries);
    }
    return pageEntries(allEntries, opts);
  }
  async deleteObject(key) {
    const filePath = this.resolvePath(key);
    try {
      await unlink(filePath);
      const metaPath = filePath + ".meta.json";
      if (existsSync2(metaPath)) {
        await unlink(metaPath);
      }
      this.logger?.debug?.(`${TAG2} deleteObject: ${key}`);
    } catch (err) {
      if (err.code !== "ENOENT") {
        throw err;
      }
    }
  }
  async deleteByPrefix(prefix) {
    const dirPath = this.resolvePath(prefix);
    if (!existsSync2(dirPath)) {
      return 0;
    }
    const entries = [];
    const dirKey = prefix.endsWith("/") ? prefix : `${prefix}/`;
    await this.collectFiles(dirPath, dirKey, dirKey, entries, Number.MAX_SAFE_INTEGER);
    const fileCount = entries.length;
    await rm(dirPath, { recursive: true, force: true });
    this.logger?.debug?.(`${TAG2} deleteByPrefix: ${prefix} (${fileCount} files)`);
    return fileCount;
  }
  // ── Private helpers ──────────────────────────────────────
  /** Resolve the directory part of a key prefix; "" means the backend root. */
  resolveDir(dirKey) {
    return dirKey ? this.resolvePath(dirKey) : resolve(this.rootDir);
  }
  /**
   * Non-recursive listing (D9.2-2): direct children whose name starts with
   * `namePrefix`; subdirectories collapse into a single trailing-slash entry
   * without being descended into.
   */
  async collectFolded(dirPath, dirKey, namePrefix, entries) {
    let items;
    try {
      items = await readdir(dirPath);
    } catch {
      return;
    }
    for (const item of items) {
      if (item.endsWith(".meta.json")) continue;
      if (!item.startsWith(namePrefix)) continue;
      try {
        const stats = await stat(join(dirPath, item));
        entries.push(stats.isDirectory() ? { key: `${dirKey}${item}/`, size: 0, lastModified: stats.mtime, isDirectory: true } : { key: `${dirKey}${item}`, size: stats.size, lastModified: stats.mtime, isDirectory: false });
      } catch {
      }
    }
  }
  /**
   * Recursive listing (D9.2-3): files only. Descends a subdirectory only when
   * it can still contain keys matching `filterPrefix`.
   */
  async collectFiles(dirPath, dirKey, filterPrefix, entries, limit) {
    if (entries.length >= limit) return;
    let items;
    try {
      items = await readdir(dirPath);
    } catch {
      return;
    }
    for (const item of items) {
      if (entries.length >= limit) break;
      if (item.endsWith(".meta.json")) continue;
      const fullPath = join(dirPath, item);
      const itemKey = `${dirKey}${item}`;
      try {
        const stats = await stat(fullPath);
        if (stats.isDirectory()) {
          const subKey = `${itemKey}/`;
          if (subKey.startsWith(filterPrefix) || filterPrefix.startsWith(subKey)) {
            await this.collectFiles(fullPath, subKey, filterPrefix, entries, limit);
          }
        } else if (itemKey.startsWith(filterPrefix)) {
          entries.push({
            key: itemKey,
            size: stats.size,
            lastModified: stats.mtime,
            isDirectory: false
          });
        }
      } catch {
      }
    }
  }
};

// src/codaki/external.ts
import { createHash as createHash2, timingSafeEqual } from "node:crypto";
import { createServer } from "node:http";
import { mkdirSync as mkdirSync2, readFileSync, readdirSync, lstatSync } from "node:fs";
import { join as join2, resolve as resolve2 } from "node:path";
import { fileURLToPath } from "node:url";
var ENGINE = "tencentdb-original-external";
var PIN = "b1f79fc4714b1e20a1ab94ec6b98e50100af6dc4";
var hash = (s) => createHash2("sha256").update(s).digest("hex");
var ADAPTER_REVISION = hash(readFileSync(fileURLToPath(import.meta.url), "utf8"));
var layers = ["L0", "L1", "L2", "L3"];
var statuses = ["historical", "proposed", "verified", "superseded"];
function text(v, name, max, empty = false) {
  if (typeof v !== "string" || !empty && !v.trim() || v.length > max || v.includes("\0")) throw Error("invalid " + name);
  return v;
}
function object(v) {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw Error("object required");
  return v;
}
function fields(o, allowed) {
  for (const k of Object.keys(o)) if (!allowed.includes(k)) throw Error("unsupported field " + k);
}
function bytes(root) {
  let n = 0;
  for (const d of readdirSync(root, { withFileTypes: true })) {
    const p = join2(root, d.name), s = lstatSync(p);
    if (s.isSymbolicLink()) throw Error("storage symlink rejected");
    n += s.isDirectory() ? bytes(p) : s.blocks ? s.blocks * 512 : s.size;
  }
  return n;
}
function bounded(result) {
  while (Buffer.byteLength(JSON.stringify(result)) > 6144 && result.notes.length > 1) result.notes.pop();
  if (Buffer.byteLength(JSON.stringify(result)) > 6144 && result.notes.length) {
    const n = result.notes[0];
    n.truncated = true;
    while (Buffer.byteLength(JSON.stringify(result)) > 6144 && n.content.length) n.content = Array.from(n.content).slice(0, -64).join("");
  }
  if (Buffer.byteLength(JSON.stringify(result)) > 6144) throw Error("response metadata exceeds budget");
  return result;
}
var ExternalMemory = class {
  constructor(root, owner, quota = 5 * 1024 ** 3) {
    this.root = root;
    this.quota = quota;
    text(owner, "owner", 160);
    mkdirSync2(root, { recursive: true, mode: 448 });
    this.scope = { teamId: hash(owner).slice(0, 32), userId: hash("user:" + owner).slice(0, 32), agentId: "codaki-memory" };
    this.store = new VectorStore(join2(root, "vectors.db"), 0);
    this.store.init();
    if (this.store.isDegraded() || !this.store.getCapabilities().ftsSearch) {
      this.store.close();
      throw Error("Tencent SQLite FTS5 unavailable");
    }
    this.files = new LocalStorageBackend(join2(root, "files"));
  }
  root;
  quota;
  store;
  files;
  scope;
  tail = Promise.resolve();
  health() {
    return { engine: ENGINE, mode: "external", vendor_revision: PIN, adapter_revision: ADAPTER_REVISION, fts_available: this.store.getCapabilities().ftsSearch, llm_enabled: false, embeddings_enabled: false, notes_count: this.store.countL1(this.scope), storage_bytes: bytes(this.root) };
  }
  close() {
    this.store.close();
  }
  save(payload) {
    const r = this.tail.then(() => this.saveOne(payload));
    this.tail = r.catch(() => {
    });
    return r;
  }
  async saveOne(raw) {
    const p = object(raw);
    fields(p, ["title", "content", "tags", "memory"]);
    const title = text(p.title, "title", 160), content = text(p.content, "content", 24e3);
    if (Buffer.byteLength(content) > 6144) throw Error("memory content exceeds 6 KiB");
    const tags = p.tags ?? [];
    if (!Array.isArray(tags) || tags.length > 20) throw Error("invalid tags");
    for (const t of tags) text(t, "tag", 80);
    const m = object(p.memory ?? {});
    fields(m, ["layer", "status", "source", "device", "project", "versions", "expected_version", "valid_from", "source_id"]);
    const layer = m.layer ?? "L1", status = m.status ?? "historical", device = m.device ?? "android", project = m.project ?? "";
    if (!layers.includes(layer)) throw Error("invalid layer");
    if (!statuses.includes(status)) throw Error("invalid status");
    if (!["android", "windows", "shared"].includes(device)) throw Error("invalid device");
    text(project, "project", 160, true);
    for (const k of ["source", "versions", "valid_from", "source_id"]) if (m[k] !== void 0) text(m[k], k, 500, true);
    if (status === "verified" && !m.source?.trim()) throw Error("verified memory requires source");
    if (m.expected_version !== void 0 && (!Number.isSafeInteger(m.expected_version) || m.expected_version < 0)) throw Error("invalid expected_version");
    const id = hash(JSON.stringify([this.scope, layer, device, project, title]));
    const old = this.store.queryL1Records({ ...this.scope, sessionId: id }).find((r) => r.record_id === id);
    const previous = old ? JSON.parse(old.metadata_json) : null;
    const mem = { layer, status, device, project, source: m.source ?? "", versions: m.versions ?? "", valid_from: m.valid_from ?? "", source_id: m.source_id ?? "" };
    const digest = hash(JSON.stringify({ title, content, tags, memory: mem }));
    const unchanged = previous?.digest === digest;
    if (!unchanged && m.expected_version !== void 0 && m.expected_version !== (old?.version ?? 0)) throw Error("version conflict");
    if (bytes(this.root) + Buffer.byteLength(JSON.stringify(p)) * 5 + 65536 > this.quota) throw Error("memory quota exceeded");
    const version = unchanged ? old.version : (old?.version ?? 0) + 1, now = (/* @__PURE__ */ new Date()).toISOString();
    const blobKey = `profiles/${this.scope.teamId}/${layer}/${id}/v${version}-${digest}.json`;
    const note = unchanged ? await this.read(id) : { id, title, content, tags, updated: Date.now() / 1e3, archived: false, version, memory: mem, digest };
    if (!unchanged) await this.files.putObject(blobKey, JSON.stringify(note));
    if (layer === "L0" && !unchanged) {
      const ok = this.store.upsertL0({ id: id + ":" + version, sessionKey: project || "codaki", sessionId: id, ...this.scope, role: "assistant", messageText: content, recordedAt: now, timestamp: Date.now() }, void 0);
      if (!ok) throw Error("Tencent L0 write failed");
    }
    const metadata = { ...note, blob_key: blobKey };
    const markers = `codakiversion${digest}`;
    const record = { id, content: [title, tags.join(" "), content, markers].join("\n"), type: layer === "L3" ? "persona" : layer === "L2" ? "work_method" : "episodic", priority: status === "verified" ? 80 : 40, scene_name: project, source_message_ids: m.source_id ? [m.source_id] : [], metadata, timestamps: [now], createdAt: old?.created_time ?? now, updatedAt: now, version, sessionKey: project || "codaki", sessionId: id, ...this.scope };
    if (!this.store.upsertL1(record, void 0)) throw Error("Tencent index write failed");
    const verify = this.store.queryL1Records({ ...this.scope, sessionId: id }).find((r) => r.record_id === id);
    if (!verify || JSON.parse(verify.metadata_json).digest !== digest) throw Error("Tencent write verification failed");
    const indexed = this.store.searchL1Fts('"codakiversion' + digest + '"', 1, this.scope);
    if (!indexed.some((r) => r.record_id === id && r.version === version)) throw Error("Tencent FTS write verification failed");
    this.store.appendAudit({ audit_id: hash(id + ":" + version), record_id: id, layer: layer === "L0" ? "L1" : layer, action: "update", team_id: this.scope.teamId, user_id: this.scope.userId, agent_id: this.scope.agentId, version, updated_at_ms: Date.now(), request_id: digest });
    return { saved: true, engine: ENGINE, id, version, unchanged: !!unchanged, notes_count: this.store.countL1(this.scope) };
  }
  async read(id) {
    if (!/^[a-f0-9]{64}$/.test(id)) throw Error("invalid record id");
    const r = this.store.queryL1Records({ ...this.scope, sessionId: id }).find((r2) => r2.record_id === id);
    if (!r) throw Error("record not found");
    const meta = JSON.parse(r.metadata_json), blob = await this.files.getObject(meta.blob_key);
    if (!blob) throw Error("memory blob unavailable");
    const n = JSON.parse(blob.content.toString("utf8"));
    if (n.digest !== meta.digest || n.version !== r.version || hash(JSON.stringify({ title: n.title, content: n.content, tags: n.tags, memory: n.memory })) !== meta.digest) throw Error("memory blob digest/version mismatch");
    return n;
  }
  async search(query, limit = 5, filters = {}) {
    text(query, "query", 2e3, true);
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 30) throw Error("invalid limit");
    const f = object(filters);
    fields(f, ["layer", "device", "project", "status"]);
    const terms = Array.from(new Set(query.match(/[\p{L}\p{N}_]+/gu) ?? [])).slice(0, 16).map((x) => '"' + x + '"*');
    for (const [k, v] of Object.entries(f)) {
      if (k === "layer" && !layers.includes(v)) throw Error("invalid layer");
      if (k === "device" && !["android", "windows", "shared"].includes(v)) throw Error("invalid device");
      if (k === "status" && !statuses.includes(v)) throw Error("invalid status");
      text(v, k, 160, k === "project");
    }
    if (!terms.length) return { engine: ENGINE, notes: [] };
    const q = terms.join(" AND ");
    const found = this.store.searchL1Fts(q, limit, this.scope, { ...f, excludeSuperseded: !f.status });
    const notes = [];
    for (const r of found) {
      const n = await this.read(r.record_id);
      notes.push({ ...n, score: r.score });
    }
    return bounded({ engine: ENGINE, notes });
  }
};
async function serveExternal(root, opts) {
  text(opts.key, "key", 256);
  if (opts.key.length < 40) throw Error("local key too short");
  const memory = new ExternalMemory(root, opts.scope, opts.quota);
  const server = createServer(async (req, res) => {
    const send = (status, value) => {
      res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      res.end(JSON.stringify(value));
    };
    const supplied = Buffer.from(req.headers.authorization ?? ""), wanted = Buffer.from("Bearer " + opts.key);
    if (supplied.length !== wanted.length || !timingSafeEqual(supplied, wanted)) return send(401, { error: "unauthorized" });
    try {
      if (req.method === "GET" && req.url === "/health") return send(200, memory.health());
      if (req.method !== "POST" || !["/save", "/search", "/read"].includes(req.url ?? "")) return send(404, { error: "unknown route" });
      let size = 0;
      const chunks = [];
      for await (const c of req) {
        size += c.length;
        if (size > 256 * 1024) throw Error("request too large");
        chunks.push(c);
      }
      const p = object(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      const r = req.url === "/save" ? await memory.save(p) : req.url === "/read" ? { engine: ENGINE, notes: [await memory.read(p.id)] } : await memory.search(p.query, p.limit, p.filters);
      if (Buffer.byteLength(JSON.stringify(r)) > 65536) throw Error("single-record response exceeds budget");
      send(200, r);
    } catch (e) {
      send(400, { error: e instanceof Error ? e.message : "memory request failed" });
    }
  });
  await new Promise((yes, no) => {
    server.once("error", no);
    server.listen(opts.port ?? 8420, "127.0.0.1", () => yes());
  });
  return { port: server.address().port, memory, stop: async () => {
    await new Promise((yes, no) => server.close((e) => e ? no(e) : yes()));
    memory.close();
  } };
}
if (process.argv[1] && resolve2(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const cfg = JSON.parse(readFileSync(process.argv[2] ?? "", "utf8"));
  const svc = await serveExternal(cfg.data_dir, { scope: cfg.scope, key: cfg.key, port: cfg.port, quota: cfg.quota_bytes });
  console.log(JSON.stringify({ ready: true, port: svc.port, engine: ENGINE }));
  let stopping = false;
  for (const signal of ["SIGTERM", "SIGINT"]) process.on(signal, async () => {
    if (stopping) return;
    stopping = true;
    await svc.stop();
    process.exit(0);
  });
}
export {
  ExternalMemory,
  serveExternal
};
