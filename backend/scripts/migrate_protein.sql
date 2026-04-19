-- =============================================
-- 蛋白質互作插件 DB Migration
-- 執行: psql $DATABASE_URL -f migrate_protein.sql
-- =============================================

CREATE TABLE IF NOT EXISTS proteins (
    symbol      TEXT PRIMARY KEY,
    genecards_url TEXT
);

CREATE TABLE IF NOT EXISTS protein_interactions (
    id          SERIAL PRIMARY KEY,
    protein_a   TEXT NOT NULL,
    protein_b   TEXT NOT NULL,
    score       FLOAT NOT NULL,
    network     TEXT NOT NULL,   -- 'USP7', 'SOD1', 'MDM2', 'HSPA4'
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pi_network  ON protein_interactions(network);
CREATE INDEX IF NOT EXISTS idx_pi_pa       ON protein_interactions(protein_a);
CREATE INDEX IF NOT EXISTS idx_pi_pb       ON protein_interactions(protein_b);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pi_uniq
    ON protein_interactions(protein_a, protein_b, network);
