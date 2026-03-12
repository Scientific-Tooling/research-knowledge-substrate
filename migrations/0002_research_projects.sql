CREATE TABLE IF NOT EXISTS research_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    research_question TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_links (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    link_type TEXT NOT NULL,
    metadata_json TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON research_projects(status, created_at);
CREATE INDEX IF NOT EXISTS idx_project_links_project ON project_links(project_id, object_type, created_at);
CREATE INDEX IF NOT EXISTS idx_project_links_object ON project_links(object_type, object_id, created_at);
