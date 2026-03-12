from __future__ import annotations

import json

from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService
from rks.reasoning import (
    build_research_answer,
    build_research_opportunities,
    build_topic_brief,
    build_topic_disagreements,
)


class ResearchOperations:
    def __init__(
        self,
        *,
        papers,
        claims,
        concepts,
        notes,
        edges,
        methods,
        datasets,
        embeddings,
        tasks,
    ):
        self.papers = papers
        self.claims = claims
        self.concepts = concepts
        self.notes = notes
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.embeddings = embeddings
        self.tasks = tasks
        self.query = QueryService(
            papers=papers,
            claims=claims,
            concepts=concepts,
            edges=edges,
            methods=methods,
            datasets=datasets,
            embeddings=embeddings,
            embedding_provider=LocalHashEmbeddingProvider(),
        )

    def paper_status(self, paper_id: str) -> dict:
        paper = self.papers.get_paper(paper_id)
        artifacts = self.papers.get_artifacts_for_paper(paper_id)
        notes = self.notes.list_notes_for_target(target_id=paper_id, target_type="paper")
        tasks = self.tasks.list_tasks(paper_id=paper_id)
        artifact_types = {artifact.artifact_type for artifact in artifacts}
        task_summary = {}
        for task in tasks:
            task_summary[task.status] = task_summary.get(task.status, 0) + 1
        return {
            "paper": _paper_payload(paper),
            "artifacts": sorted(artifact_types),
            "stages": {
                "text": "extracted_text" in artifact_types,
                "claims": "structured_claims" in artifact_types,
                "methods": "methods" in artifact_types,
                "datasets": "datasets" in artifact_types,
                "summary": "paper_summary" in artifact_types,
                "citations": "citations" in artifact_types,
            },
            "source_pdf": _source_pdf_status(paper, artifacts),
            "note_count": len(notes),
            "task_summary": task_summary,
            "tasks": [_task_payload(task) for task in tasks],
        }

    def claim_relations(self, claim_id: str) -> dict:
        return self.query.claim_relations(claim_id)

    def list_paper_notes(self, paper_id: str) -> list[dict]:
        self.papers.get_paper(paper_id)
        notes = self.notes.list_notes_for_target(target_id=paper_id, target_type="paper")
        return [_note_payload(note) for note in notes]

    def add_paper_note(self, paper_id: str, *, content: str, created_by: str = "human:user") -> dict:
        self.papers.get_paper(paper_id)
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("content must not be empty")
        note = self.notes.add_note(
            target_id=paper_id,
            target_type="paper",
            content=normalized_content,
            created_by=created_by,
        )
        self.papers.touch_paper(paper_id)
        return _note_payload(note)

    def answer_question(self, question: str) -> dict:
        return build_research_answer(self.query, question)

    def topic_brief(self, topic: str) -> dict:
        return build_topic_brief(self.query, topic)

    def topic_disagreements(self, topic: str) -> dict:
        return build_topic_disagreements(self.query, topic)

    def research_opportunities(self, topic: str) -> dict:
        return build_research_opportunities(self.query, topic)

    def promote_claim_relation(
        self,
        source_claim_id: str,
        relation_type: str,
        target_claim_id: str,
        *,
        confidence: float = 1.0,
        reviewed_by: str = "agent:review",
        note: str | None = None,
    ) -> dict:
        source_claim = self.claims.get_claim(source_claim_id)
        target_claim = self.claims.get_claim(target_claim_id)
        metadata = {
            "source_paper_id": source_claim.paper_id,
            "target_paper_id": target_claim.paper_id,
        }
        if note:
            metadata["note"] = note
        edge = self.edges.upsert_claim_relation_edge(
            source_id=source_claim.id,
            relation_type=relation_type,
            target_id=target_claim.id,
            confidence=confidence,
            metadata=metadata,
            created_by=reviewed_by,
        )
        return _edge_payload(edge)

    def retract_claim_relation(self, source_claim_id: str, relation_type: str, target_claim_id: str) -> dict:
        deleted = self.edges.delete_claim_relation_edge(
            source_id=source_claim_id,
            relation_type=relation_type,
            target_id=target_claim_id,
        )
        return {
            "source_claim_id": source_claim_id,
            "relation_type": relation_type,
            "target_claim_id": target_claim_id,
            "deleted": deleted,
        }


def _paper_payload(paper) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": json.loads(paper.authors_json),
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "source_type": paper.source_type,
        "source_ref": paper.source_ref,
        "pdf_path": paper.pdf_path,
        "text_artifact_id": paper.text_artifact_id,
        "created_at": paper.created_at,
        "updated_at": paper.updated_at,
    }


def _task_payload(task) -> dict:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "paper_id": task.paper_id,
        "mode": task.mode,
        "status": task.status,
        "request_artifact_id": task.request_artifact_id,
        "result_artifact_id": task.result_artifact_id,
        "spec_version": task.spec_version,
        "schema_version": task.schema_version,
        "error": json.loads(task.error_json or "null"),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _edge_payload(edge) -> dict:
    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "source_type": edge.source_type,
        "relation_type": edge.relation_type,
        "target_id": edge.target_id,
        "target_type": edge.target_type,
        "confidence": edge.confidence,
        "created_by": edge.created_by,
        "metadata": json.loads(edge.metadata_json or "{}"),
    }


def _note_payload(note) -> dict:
    return {
        "id": note.id,
        "target_id": note.target_id,
        "target_type": note.target_type,
        "content": note.content,
        "created_by": note.created_by,
        "created_at": note.created_at,
    }


def _source_pdf_status(paper, artifacts) -> dict:
    acquisition = None
    for artifact in artifacts:
        if artifact.artifact_type == "source_pdf_acquisition":
            acquisition = json.loads(artifact.metadata_json or "{}")
            break
    return {
        "available": bool(paper.pdf_path),
        "path": paper.pdf_path,
        "acquisition": acquisition,
    }
