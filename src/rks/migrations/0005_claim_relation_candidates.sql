CREATE TABLE IF NOT EXISTS claim_relation_candidates (
    id TEXT PRIMARY KEY,
    source_claim_id TEXT NOT NULL,
    target_claim_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    score REAL,
    algorithm_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_crc_source ON claim_relation_candidates(source_claim_id, status);
CREATE INDEX IF NOT EXISTS idx_crc_target ON claim_relation_candidates(target_claim_id, status);
CREATE INDEX IF NOT EXISTS idx_crc_status ON claim_relation_candidates(status, relation_type);
