-- Phase A2: LLMModel governance columns
-- 加入 enabled / is_default / monthly_quota_usd 三欄，供前端「啟用 / 預設 / 月度上限」管理
-- 冪等：可重複執行
--
-- is_default 採用 partial unique index：每個 model_type 最多只能有一筆 is_default=TRUE
-- monthly_quota_usd NULL 代表不限制

ALTER TABLE llm_models
    ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE llm_models
    ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE llm_models
    ADD COLUMN IF NOT EXISTS monthly_quota_usd NUMERIC(10, 2) NULL;

-- 每個 model_type 最多一個 is_default=TRUE
CREATE UNIQUE INDEX IF NOT EXISTS ux_llm_models_default_per_type
    ON llm_models (model_type)
    WHERE is_default = TRUE;
