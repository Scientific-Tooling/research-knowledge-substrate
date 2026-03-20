CREATE TABLE IF NOT EXISTS paper_tags (
    paper_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (paper_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_paper_tags_tag_created ON paper_tags(tag, created_at);
