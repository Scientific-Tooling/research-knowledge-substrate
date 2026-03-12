from __future__ import annotations

import json

from rks.providers import LocalHashEmbeddingProvider
from rks.query import QueryService
from rks.reasoning import (
    build_comparison,
    build_research_answer,
    build_research_opportunities,
    build_topic_brief,
    build_topic_disagreements,
    build_topic_open_questions,
    build_topic_reading_list,
    build_topic_review_priorities,
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
        claims = self.claims.list_claims_for_paper(paper_id)
        notes = self.notes.list_notes_for_target(target_id=paper_id, target_type="paper")
        tasks = self.tasks.list_tasks(paper_id=paper_id)
        artifact_types = {artifact.artifact_type for artifact in artifacts}
        task_summary = {}
        for task in tasks:
            task_summary[task.status] = task_summary.get(task.status, 0) + 1
        stages = {
            "text": "extracted_text" in artifact_types,
            "claims": "structured_claims" in artifact_types,
            "methods": "methods" in artifact_types,
            "datasets": "datasets" in artifact_types,
            "summary": "paper_summary" in artifact_types,
            "citations": "citations" in artifact_types,
        }
        review = _review_status(self.query, claims)
        readiness = _paper_readiness(stages, review)
        blockers = _status_blockers(paper, stages, tasks)
        missing_steps = _missing_steps(paper, stages, review)
        suggested_next_commands = _suggested_next_commands(
            paper=paper,
            stages=stages,
            review=review,
            tasks=tasks,
        )
        return {
            "paper": _paper_payload(paper),
            "artifacts": sorted(artifact_types),
            "stages": stages,
            "readiness": readiness,
            "review": review,
            "missing_steps": missing_steps,
            "blockers": blockers,
            "suggested_next_commands": suggested_next_commands,
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

    def topic_reading_list(self, topic: str) -> dict:
        return build_topic_reading_list(self.query, topic)

    def topic_open_questions(self, topic: str) -> dict:
        return build_topic_open_questions(self.query, topic)

    def topic_review_priorities(self, topic: str) -> dict:
        return build_topic_review_priorities(self.query, topic)

    def compare_targets(self, left: str, right: str) -> dict:
        return build_comparison(self.query, left, right)

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


def _review_status(query: QueryService, claims: list) -> dict:
    reviewed_keys = set()
    inferred_keys = set()
    pending_claim_ids = []
    for claim in claims:
        relations = query.claim_relations(claim.id)
        if relations["inferred_relations"]:
            pending_claim_ids.append(claim.id)
        for relation in relations["reviewed_relations"]:
            reviewed_keys.add(_relation_key(claim.id, relation))
        for relation in relations["inferred_relations"]:
            inferred_keys.add(_relation_key(claim.id, relation))
    return {
        "claim_count": len(claims),
        "reviewed_relation_count": len(reviewed_keys),
        "inferred_relation_count": len(inferred_keys),
        "pending_claim_ids": pending_claim_ids[:5],
        "review_pending": bool(inferred_keys),
    }


def _paper_readiness(stages: dict, review: dict) -> dict:
    levels = {
        "ingested": True,
        "text_ready": stages["text"],
        "claims_ready": stages["claims"],
        "graph_ready": stages["claims"] and (stages["methods"] or stages["datasets"] or stages["citations"]),
        "output_ready": stages["claims"] and stages["summary"],
        "review_pending": review["review_pending"],
    }
    current_level = "ingested"
    if levels["review_pending"]:
        current_level = "review_pending"
    elif levels["output_ready"]:
        current_level = "output_ready"
    elif levels["graph_ready"]:
        current_level = "graph_ready"
    elif levels["claims_ready"]:
        current_level = "claims_ready"
    elif levels["text_ready"]:
        current_level = "text_ready"
    return {
        "current_level": current_level,
        "levels": levels,
    }


def _missing_steps(paper, stages: dict, review: dict) -> list[dict]:
    missing = []
    if not stages["text"]:
        missing.append(
            {
                "code": "text_artifact_missing",
                "message": "No extracted text artifact is stored for this paper yet.",
            }
        )
    if not stages["claims"]:
        missing.append(
            {
                "code": "claims_missing",
                "message": "No structured claim artifact is stored for this paper yet.",
            }
        )
    if stages["claims"] and not stages["methods"]:
        missing.append(
            {
                "code": "methods_missing",
                "message": "Method structure is still missing for this paper.",
            }
        )
    if stages["claims"] and not stages["datasets"]:
        missing.append(
            {
                "code": "datasets_missing",
                "message": "Dataset structure is still missing for this paper.",
            }
        )
    if stages["claims"] and not stages["summary"]:
        missing.append(
            {
                "code": "summary_missing",
                "message": "No paper summary artifact is stored yet.",
            }
        )
    if not paper.pdf_path and not stages["text"]:
        missing.append(
            {
                "code": "source_pdf_unavailable",
                "message": "No local source PDF is attached, so text extraction may be blocked.",
            }
        )
    if review["review_pending"]:
        missing.append(
            {
                "code": "relation_review_pending",
                "message": "The paper has inferred claim relations that have not been reviewed yet.",
            }
        )
    return missing


def _status_blockers(paper, stages: dict, tasks: list) -> list[dict]:
    blockers = []
    if not paper.pdf_path and not stages["text"]:
        blockers.append(
            {
                "severity": "warning",
                "code": "no_local_source_pdf",
                "message": "No local PDF or extracted text is available, which blocks local text extraction.",
            }
        )
    for task in tasks:
        if task.status == "failed":
            blockers.append(
                {
                    "severity": "error",
                    "code": "task_failed",
                    "message": f"{task.task_type} failed and should be inspected before continuing.",
                    "task_id": task.id,
                }
            )
        elif task.status in {"queued", "running"}:
            blockers.append(
                {
                    "severity": "info",
                    "code": "task_in_progress",
                    "message": f"{task.task_type} is still {task.status}. Wait for the result or import it when ready.",
                    "task_id": task.id,
                }
            )
    return blockers


def _suggested_next_commands(*, paper, stages: dict, review: dict, tasks: list) -> list[str]:
    commands: list[str] = []
    if not stages["text"]:
        if paper.pdf_path:
            commands.append(f"rks extract text {paper.id}")
        elif paper.doi:
            commands.append(f"rks ingest doi {paper.doi}")
        elif paper.arxiv_id:
            commands.append(f"rks ingest arxiv {paper.arxiv_id}")
    if stages["text"] and not stages["claims"]:
        commands.append(f"rks extract claims {paper.id}")
    if stages["claims"] and not stages["methods"]:
        commands.append(f"rks extract methods {paper.id}")
    if stages["claims"] and not stages["datasets"]:
        commands.append(f"rks extract datasets {paper.id}")
    if stages["claims"] and not stages["summary"]:
        commands.append(f"rks summarize paper {paper.id}")
    if review["review_pending"]:
        commands.append(f"rks claims {paper.id}")
    for task in tasks:
        if task.status in {"queued", "running", "failed"}:
            commands.append(f"rks tasks show {task.id}")
    deduped = []
    seen = set()
    for command in commands:
        if command in seen:
            continue
        seen.add(command)
        deduped.append(command)
    return deduped[:8]


def _relation_key(anchor_claim_id: str, relation: dict) -> tuple[str, tuple[str, str]]:
    other_claim_id = relation["claim"]["id"]
    pair = tuple(sorted((anchor_claim_id, other_claim_id)))
    return relation["relation_type"], pair
