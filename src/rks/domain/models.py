from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PaperRecord:
    id: str
    title: str
    abstract: Optional[str]
    authors_json: str
    year: Optional[int]
    venue: Optional[str]
    doi: Optional[str]
    arxiv_id: Optional[str]
    source_type: str
    source_ref: Optional[str]
    pdf_path: Optional[str]
    text_artifact_id: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    paper_id: Optional[str]
    artifact_type: str
    path: str
    format: str
    metadata_json: str
    created_at: str


@dataclass(frozen=True)
class ClaimRecord:
    id: str
    paper_id: str
    text: str
    subject_concept_id: Optional[str]
    predicate: str
    object_concept_id: Optional[str]
    object_text: Optional[str]
    context_json: Optional[str]
    evidence_json: Optional[str]
    confidence: Optional[float]
    status: str
    created_by: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MethodRecord:
    id: str
    paper_id: str
    name: str
    description: Optional[str]
    about_concept_id: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DatasetRecord:
    id: str
    paper_id: str
    name: str
    description: Optional[str]
    source: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TaskRecord:
    id: str
    task_type: str
    paper_id: str
    mode: str
    status: str
    request_artifact_id: Optional[str]
    result_artifact_id: Optional[str]
    spec_version: Optional[str]
    schema_version: Optional[str]
    error_json: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ConceptRecord:
    id: str
    name: str
    aliases_json: str
    domain: Optional[str]
    parent_concept_id: Optional[str]
    description: Optional[str]
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class NoteRecord:
    id: str
    target_id: str
    target_type: str
    content: str
    created_by: str
    created_at: str


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    name: str
    description: Optional[str]
    research_question: Optional[str]
    status: str
    created_by: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ProjectLinkRecord:
    id: str
    project_id: str
    object_id: str
    object_type: str
    link_type: str
    metadata_json: Optional[str]
    created_by: str
    created_at: str


@dataclass(frozen=True)
class HypothesisRecord:
    id: str
    project_id: str
    text: str
    status: str
    confidence: Optional[float]
    context_json: Optional[str]
    created_by: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class HypothesisEvidenceLinkRecord:
    id: str
    hypothesis_id: str
    object_id: str
    object_type: str
    relation_type: str
    metadata_json: Optional[str]
    created_by: str
    created_at: str


@dataclass(frozen=True)
class ClaimRelationCandidateRecord:
    id: str
    source_claim_id: str
    target_claim_id: str
    relation_type: str
    score: Optional[float]
    algorithm_version: str
    status: str
    metadata_json: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EvolutionEventRecord:
    id: str
    event_type: str
    subject_id: str
    subject_type: str
    detail_json: Optional[str]
    created_by: str
    created_at: str


@dataclass(frozen=True)
class ConceptTimelineSnapshotRecord:
    id: str
    concept_id: str
    snapshot_at: str
    support_count: int
    contradiction_count: int
    paper_count: int
    claim_count: int
    detail_json: Optional[str]
    created_at: str
    time_bucket: Optional[str] = None
    refine_count: int = 0
    consensus_score: Optional[float] = None
    controversy_score: Optional[float] = None
    basis_layer: str = "reviewed"


@dataclass(frozen=True)
class ClaimConflictClusterRecord:
    id: str
    anchor_concept_id: str
    topic_label: Optional[str]
    status: str
    summary_json: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ClaimConflictClusterMemberRecord:
    id: str
    cluster_id: str
    claim_id: str
    role: str
    stance: Optional[str]
    confidence: Optional[float]
    created_at: str


@dataclass(frozen=True)
class EdgeRecord:
    id: str
    source_id: str
    source_type: str
    relation_type: str
    target_id: str
    target_type: str
    evidence_paper_id: Optional[str]
    confidence: Optional[float]
    metadata_json: Optional[str]
    created_by: str
    created_at: str
