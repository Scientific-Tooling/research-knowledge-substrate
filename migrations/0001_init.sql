CREATE TABLE IF NOT EXISTS counters (
    kind TEXT PRIMARY KEY,
    next_value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    authors_json TEXT NOT NULL,
    year INTEGER,
    venue TEXT,
    doi TEXT,
    arxiv_id TEXT,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    pdf_path TEXT,
    text_artifact_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    text TEXT NOT NULL,
    subject_concept_id TEXT,
    predicate TEXT NOT NULL,
    object_concept_id TEXT,
    object_text TEXT,
    context_json TEXT,
    evidence_json TEXT,
    confidence REAL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS methods (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    about_concept_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    aliases_json TEXT,
    domain TEXT,
    parent_concept_id TEXT,
    description TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    evidence_paper_id TEXT,
    confidence REAL,
    metadata_json TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    paper_id TEXT,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    format TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    request_artifact_id TEXT,
    result_artifact_id TEXT,
    spec_version TEXT,
    schema_version TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_claims_paper_id ON claims(paper_id);
CREATE INDEX IF NOT EXISTS idx_methods_paper_id ON methods(paper_id);
CREATE INDEX IF NOT EXISTS idx_datasets_paper_id ON datasets(paper_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_paper_id ON artifacts(paper_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_object ON embeddings(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_tasks_paper ON tasks(paper_id, status);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id, relation_type);
