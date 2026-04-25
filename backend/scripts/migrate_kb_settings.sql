-- Knowledge Base 設定欄位 migration
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS embedding_model VARCHAR;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS chunk_size INTEGER;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS chunk_overlap INTEGER;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'auto';
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS rerank_enabled BOOLEAN;
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS default_top_k INTEGER;
