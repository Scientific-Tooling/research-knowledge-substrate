CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL,
    context_json TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hypothesis_evidence_links (
    id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    metadata_json TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hypotheses_project ON hypotheses(project_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_hypothesis ON hypothesis_evidence_links(hypothesis_id, created_at);
CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_object ON hypothesis_evidence_links(object_type, object_id, created_at);
