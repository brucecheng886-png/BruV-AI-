-- Phase B1: llm_usage_log 監測表
-- 紀錄每次 LLM 呼叫的使用量、延遲、結果
-- idempotent: 可重複執行

CREATE TABLE IF NOT EXISTS llm_usage_log (
    id               BIGSERIAL PRIMARY KEY,
    conv_id          UUID NULL,
    agent_task_id    UUID NULL,
    user_id          UUID NULL,
    model_name       VARCHAR(128) NOT NULL,
    provider         VARCHAR(32)  NOT NULL,
    call_type        VARCHAR(32)  NOT NULL,  -- chat | embedding | rerank | agent_step | reflection | title
    prompt_tokens    INTEGER      NOT NULL DEFAULT 0,
    completion_tokens INTEGER     NOT NULL DEFAULT 0,
    total_tokens     INTEGER      NOT NULL DEFAULT 0,
    latency_ms       INTEGER      NOT NULL DEFAULT 0,
    cost_usd         NUMERIC(12,6) NULL,
    success          BOOLEAN      NOT NULL DEFAULT TRUE,
    error_message    TEXT         NULL,
    template_id      UUID         NULL,  -- 預留 Phase E
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_llm_usage_log_created_at ON llm_usage_log (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_llm_usage_log_model      ON llm_usage_log (model_name, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_llm_usage_log_user       ON llm_usage_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_llm_usage_log_conv       ON llm_usage_log (conv_id) WHERE conv_id IS NOT NULL;
