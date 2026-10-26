CREATE TABLE IF NOT EXISTS evidence_workspace (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    workspace_id TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS external_evidence (
    source_key TEXT PRIMARY KEY,
    note_id TEXT NOT NULL UNIQUE,
    revision TEXT NOT NULL,
    record_json TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS external_evidence_history (
    source_key TEXT NOT NULL,
    revision TEXT NOT NULL,
    record_json TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    PRIMARY KEY (source_key, revision)
);

CREATE TABLE IF NOT EXISTS paper_redirects (
    source_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    merged_at TEXT NOT NULL
);
