-- ================================================================
-- 地端 AI 知識庫 — PostgreSQL 初始化腳本
-- ================================================================

-- 啟用 UUID 擴充
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- 全文搜尋加速

-- ── 使用者 ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,              -- bcrypt hash
    role        TEXT NOT NULL DEFAULT 'user',  -- user | admin
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 文件 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT NOT NULL,
    source          TEXT,                   -- 檔案名稱或 URL
    file_path       TEXT,                   -- MinIO 物件路徑
    file_type       TEXT,                   -- pdf | docx | xlsx | html | txt
    status          TEXT NOT NULL DEFAULT 'pending',
                                            -- pending | processing | done | error
    error_message   TEXT,
    chunk_count     INT DEFAULT 0,
    custom_fields   JSONB NOT NULL DEFAULT '{}',
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_status    ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_custom    ON documents USING gin(custom_fields);
CREATE INDEX IF NOT EXISTS idx_documents_created   ON documents(created_at DESC);

-- ── Chunks（對應 Qdrant point）────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id          UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    chunk_index     INT NOT NULL,
    vector_id       TEXT,                   -- Qdrant point ID
    window_context  TEXT,                   -- ±3 句 context
    page_number     INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id    ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_vector_id ON chunks(vector_id);

-- ── 對話 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id),
    title       TEXT DEFAULT '新對話',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conv_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,              -- user | assistant | system
    content     TEXT NOT NULL,
    sources     JSONB DEFAULT '[]',         -- [{chunk_id, doc_title, score}]
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conv_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

-- ── 插件 ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plugins (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT UNIQUE NOT NULL,
    description     TEXT,
    input_schema    JSONB NOT NULL DEFAULT '{}',
    plugin_type     TEXT NOT NULL DEFAULT 'webhook',  -- webhook | builtin
    builtin_key     TEXT,                             -- notion | chart | calculator | email | rss | weather
    plugin_config   JSONB NOT NULL DEFAULT '{}',      -- 非敏感設定（smtp_host 等）
    endpoint        TEXT NOT NULL DEFAULT '',
    auth_header     TEXT,                   -- Fernet 加密後的字串
    enabled         BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 現有 DB 升級用（新欄位 idempotent migration）────────────────
ALTER TABLE plugins ADD COLUMN IF NOT EXISTS plugin_type   TEXT NOT NULL DEFAULT 'webhook';
ALTER TABLE plugins ADD COLUMN IF NOT EXISTS builtin_key   TEXT;
ALTER TABLE plugins ADD COLUMN IF NOT EXISTS plugin_config JSONB NOT NULL DEFAULT '{}';
ALTER TABLE plugins ALTER COLUMN endpoint SET DEFAULT '';
ALTER TABLE llm_models ADD COLUMN IF NOT EXISTS model_type   TEXT NOT NULL DEFAULT 'chat';
ALTER TABLE llm_models ADD COLUMN IF NOT EXISTS max_tokens   INT;
ALTER TABLE llm_models ADD COLUMN IF NOT EXISTS vision_support BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE llm_models ADD COLUMN IF NOT EXISTS provider     TEXT;
ALTER TABLE llm_models ADD COLUMN IF NOT EXISTS base_url     TEXT;
ALTER TABLE llm_models ADD COLUMN IF NOT EXISTS api_key      TEXT;  -- Fernet 加密

-- ── v3 升級：對話 Scope（方案 C）───────────────────────────────
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS kb_scope_id   UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS doc_scope_ids JSONB NOT NULL DEFAULT '[]';

-- ── LLM Wiki ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS llm_models (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    family          TEXT,
    developer       TEXT,
    params_b        FLOAT,
    context_length  INT,
    license         TEXT,
    release_date    DATE,
    tags            TEXT[] DEFAULT '{}',
    benchmarks      JSONB DEFAULT '{}',
    quantizations   JSONB DEFAULT '{}',
    ollama_id       TEXT,
    hf_id           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Ontology Review Queue ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS ontology_review_queue (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_name     TEXT NOT NULL,
    entity_type     TEXT NOT NULL,          -- Concept | Entity
    action          TEXT NOT NULL,          -- create | update | delete
    proposed_data   JSONB DEFAULT '{}',
    source_doc_id   UUID REFERENCES documents(id),
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    reviewed_by     UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Ontology 封鎖清單 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ontology_blocklist (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    blocked_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(name, entity_type)
);

-- ── Saga 補償日誌（必要元件）─────────────────────────────────
-- 注意：此表也存在於 /data/saga.db（SQLite），此為 PG 備份版本
CREATE TABLE IF NOT EXISTS saga_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation       TEXT NOT NULL,          -- ingest_document | delete_document
    resource_id     TEXT NOT NULL,          -- doc_id 或其他資源 ID
    completed_steps JSONB NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | committed | compensated | failed
    error_detail    TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_saga_log_status      ON saga_log(status);
CREATE INDEX IF NOT EXISTS idx_saga_log_resource    ON saga_log(resource_id);

-- ================================================================
-- v2 升級：批量爬取 / Notion 同步 / 本體論審核修正（idempotent）
-- ================================================================

-- crawl_batches：批量爬取任務進度
CREATE TABLE IF NOT EXISTS crawl_batches (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_name  TEXT,
    total       INT NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'queued',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- documents：新增 url_fingerprint（SHA256 防重複）與 batch_id
ALTER TABLE documents ADD COLUMN IF NOT EXISTS url_fingerprint TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES crawl_batches(id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_url_fp
    ON documents(url_fingerprint)
    WHERE url_fingerprint IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_batch_id ON documents(batch_id);

-- notion_sync_log：Notion 增量同步紀錄
CREATE TABLE IF NOT EXISTS notion_sync_log (
    page_id          TEXT PRIMARY KEY,
    last_edited_time TIMESTAMPTZ NOT NULL,
    doc_id           UUID REFERENCES documents(id) ON DELETE SET NULL,
    synced_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ontology_review_queue 唯一部分索引（防止重複 pending 審核）
CREATE UNIQUE INDEX IF NOT EXISTS idx_orq_entity_uniq
    ON ontology_review_queue(entity_name, entity_type)
    WHERE status = 'pending';

-- ── 預設管理員帳號（密碼需在首次部署後修改）─────────────────
-- 密碼 hash 對應 'changeme123'（bcrypt），部署後請立即修改
INSERT INTO users (email, password, role)
VALUES ('admin@local', '$2b$12$placeholder_hash_change_on_deploy', 'admin')
ON CONFLICT (email) DO NOTHING;


-- ── Prompt 模板 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prompt_templates (
    template_id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category        TEXT NOT NULL,
    title           TEXT NOT NULL,
    template        TEXT NOT NULL,
    required_vars   JSONB NOT NULL DEFAULT '[]',
    optional_vars   JSONB NOT NULL DEFAULT '[]',
    example_triggers JSONB NOT NULL DEFAULT '[]',
    pit_warnings    JSONB NOT NULL DEFAULT '[]',
    usage_count     INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_templates_category
    ON prompt_templates(category);
