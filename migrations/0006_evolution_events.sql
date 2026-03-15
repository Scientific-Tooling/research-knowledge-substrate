CREATE TABLE IF NOT EXISTS evolution_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    detail_json TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evolution_events_subject ON evolution_events(subject_id, subject_type, created_at);
CREATE INDEX IF NOT EXISTS idx_evolution_events_type ON evolution_events(event_type, created_at);

CREATE TABLE IF NOT EXISTS concept_timeline_snapshots (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL,
    snapshot_at TEXT NOT NULL,
    support_count INTEGER NOT NULL DEFAULT 0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    paper_count INTEGER NOT NULL DEFAULT 0,
    claim_count INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_concept_timeline_concept ON concept_timeline_snapshots(concept_id, snapshot_at);
