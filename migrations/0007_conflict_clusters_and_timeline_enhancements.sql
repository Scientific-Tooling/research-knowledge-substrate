-- Phase 2: Conflict clustering and timeline enhancements

CREATE TABLE IF NOT EXISTS claim_conflict_clusters (
    id TEXT PRIMARY KEY,
    anchor_concept_id TEXT NOT NULL,
    topic_label TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    summary_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_conflict_cluster_members (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    stance TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conflict_clusters_concept ON claim_conflict_clusters(anchor_concept_id, status);
CREATE INDEX IF NOT EXISTS idx_conflict_cluster_members_cluster ON claim_conflict_cluster_members(cluster_id);
CREATE INDEX IF NOT EXISTS idx_conflict_cluster_members_claim ON claim_conflict_cluster_members(claim_id);

-- Extend timeline snapshots with scoring and bucketing columns
ALTER TABLE concept_timeline_snapshots ADD COLUMN time_bucket TEXT;
ALTER TABLE concept_timeline_snapshots ADD COLUMN refine_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE concept_timeline_snapshots ADD COLUMN consensus_score REAL;
ALTER TABLE concept_timeline_snapshots ADD COLUMN controversy_score REAL;
ALTER TABLE concept_timeline_snapshots ADD COLUMN basis_layer TEXT NOT NULL DEFAULT 'reviewed';
