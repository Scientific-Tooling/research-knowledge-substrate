SCHEMA_SQL = """
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
CREATE INDEX IF NOT EXISTS idx_projects_status ON research_projects(status, created_at);
CREATE INDEX IF NOT EXISTS idx_project_links_project ON project_links(project_id, object_type, created_at);
CREATE INDEX IF NOT EXISTS idx_project_links_object ON project_links(object_type, object_id, created_at);
CREATE INDEX IF NOT EXISTS idx_hypotheses_project ON hypotheses(project_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_hypothesis ON hypothesis_evidence_links(hypothesis_id, created_at);
CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_object ON hypothesis_evidence_links(object_type, object_id, created_at);
CREATE INDEX IF NOT EXISTS idx_claims_subject_concept ON claims(subject_concept_id);
CREATE INDEX IF NOT EXISTS idx_claims_object_concept ON claims(object_concept_id);
CREATE INDEX IF NOT EXISTS idx_edges_types ON edges(source_type, target_type, relation_type);
CREATE INDEX IF NOT EXISTS idx_notes_target ON notes(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name);

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
    created_at TEXT NOT NULL,
    time_bucket TEXT,
    refine_count INTEGER NOT NULL DEFAULT 0,
    consensus_score REAL,
    controversy_score REAL,
    basis_layer TEXT NOT NULL DEFAULT 'reviewed'
);

CREATE INDEX IF NOT EXISTS idx_concept_timeline_concept ON concept_timeline_snapshots(concept_id, snapshot_at);

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
"""
