ALTER TABLE papers ADD COLUMN reading_status TEXT NOT NULL DEFAULT 'unread';

CREATE INDEX IF NOT EXISTS idx_papers_reading_status_created ON papers(reading_status, created_at);
