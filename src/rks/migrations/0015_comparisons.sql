CREATE TABLE IF NOT EXISTS comparisons (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comparison_versions (
    comparison_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (comparison_id, version)
);
CREATE TABLE IF NOT EXISTS comparison_reviews (
    comparison_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    review_json TEXT NOT NULL,
    PRIMARY KEY (comparison_id, sequence)
);
CREATE TABLE IF NOT EXISTS comparison_requests (
    request_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    comparison_id TEXT NOT NULL
);
