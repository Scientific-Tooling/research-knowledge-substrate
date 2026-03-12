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
