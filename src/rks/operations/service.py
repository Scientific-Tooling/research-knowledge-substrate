from __future__ import annotations

import json

from rks.agent import load_task_reports
from rks.config import load_paths
from rks.extraction import (
    extract_claims_for_paper,
    extract_datasets_for_paper,
    extract_methods_for_paper,
    extract_text_for_paper,
)
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
from rks.reasoning.summary import summarize_paper_heuristic


class ResearchOperations:
    def __init__(
        self,
        *,
        papers,
        projects,
        hypotheses,
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
        self.projects = projects
        self.hypotheses = hypotheses
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

    def create_project(
        self,
        *,
        name: str,
        description: str | None = None,
        research_question: str | None = None,
        status: str = "active",
        created_by: str = "human:user",
    ) -> dict:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("name must not be empty")
        normalized_status = status.strip() or "active"
        project = self.projects.create_project(
            name=normalized_name,
            description=_optional_text(description),
            research_question=_optional_text(research_question),
            status=normalized_status,
            created_by=created_by,
        )
        return _project_payload(project)

    def list_projects(self) -> list[dict]:
        return [_project_payload(project) for project in self.projects.list_projects()]

    def get_project(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        notes = self.notes.list_notes_for_target(target_id=project_id, target_type="project")
        paper_links = self.projects.list_links_for_project(project_id, object_type="paper")
        return {
            **_project_payload(project),
            "notes": [_note_payload(note) for note in notes],
            "papers": _project_paper_entries(self.papers, paper_links),
            "hypotheses": [_hypothesis_payload(item) for item in self.hypotheses.list_hypotheses_for_project(project_id)],
        }

    def list_project_notes(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        notes = self.notes.list_notes_for_target(target_id=project_id, target_type="project")
        return [_note_payload(note) for note in notes]

    def add_project_note(self, project_id: str, *, content: str, created_by: str = "human:user") -> dict:
        self.projects.get_project(project_id)
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("content must not be empty")
        note = self.notes.add_note(
            target_id=project_id,
            target_type="project",
            content=normalized_content,
            created_by=created_by,
        )
        self.projects.touch_project(project_id)
        return _note_payload(note)

    def list_project_papers(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="paper")
        return _project_paper_entries(self.papers, links)

    def add_project_paper(
        self,
        project_id: str,
        paper_id: str,
        *,
        link_type: str = "in_scope",
        created_by: str = "human:user",
    ) -> dict:
        self.projects.get_project(project_id)
        paper = self.papers.get_paper(paper_id)
        normalized_link_type = link_type.strip()
        if not normalized_link_type:
            raise ValueError("link_type must not be empty")
        link = self.projects.add_link(
            project_id=project_id,
            object_id=paper.id,
            object_type="paper",
            link_type=normalized_link_type,
            created_by=created_by,
            metadata=None,
        )
        self.projects.touch_project(project_id)
        return _project_paper_entry(link, paper)

    def create_hypothesis(
        self,
        project_id: str,
        *,
        text: str,
        status: str = "draft",
        confidence: float | None = None,
        context: dict | None = None,
        created_by: str = "human:user",
    ) -> dict:
        self.projects.get_project(project_id)
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("text must not be empty")
        normalized_status = status.strip() or "draft"
        hypothesis = self.hypotheses.create_hypothesis(
            project_id=project_id,
            text=normalized_text,
            status=normalized_status,
            confidence=confidence,
            context=context or {},
            created_by=created_by,
        )
        self.projects.touch_project(project_id)
        return _hypothesis_payload(hypothesis)

    def list_project_hypotheses(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        return [_hypothesis_payload(item) for item in self.hypotheses.list_hypotheses_for_project(project_id)]

    def get_hypothesis(self, hypothesis_id: str) -> dict:
        hypothesis = self.hypotheses.get_hypothesis(hypothesis_id)
        evidence_links = self.hypotheses.list_evidence_links_for_hypothesis(hypothesis_id)
        return {
            **_hypothesis_payload(hypothesis),
            "project": _project_payload(self.projects.get_project(hypothesis.project_id)),
            "evidence_links": _hypothesis_evidence_entries(self.papers, self.claims, evidence_links),
        }

    def list_hypothesis_evidence(self, hypothesis_id: str) -> list[dict]:
        self.hypotheses.get_hypothesis(hypothesis_id)
        evidence_links = self.hypotheses.list_evidence_links_for_hypothesis(hypothesis_id)
        return _hypothesis_evidence_entries(self.papers, self.claims, evidence_links)

    def add_hypothesis_evidence(
        self,
        hypothesis_id: str,
        object_type: str,
        object_id: str,
        *,
        relation_type: str = "supported_by",
        created_by: str = "human:user",
        note: str | None = None,
    ) -> dict:
        hypothesis = self.hypotheses.get_hypothesis(hypothesis_id)
        normalized_object_type = object_type.strip()
        normalized_relation_type = relation_type.strip()
        if normalized_object_type not in {"paper", "claim"}:
            raise ValueError("object_type must be one of: paper, claim")
        if not normalized_relation_type:
            raise ValueError("relation_type must not be empty")

        target_payload = _resolve_hypothesis_evidence_target(self.papers, self.claims, normalized_object_type, object_id)
        metadata = {}
        if note:
            metadata["note"] = note.strip()
        link = self.hypotheses.add_evidence_link(
            hypothesis_id=hypothesis.id,
            object_id=object_id,
            object_type=normalized_object_type,
            relation_type=normalized_relation_type,
            created_by=created_by,
            metadata=metadata,
        )
        self.hypotheses.touch_hypothesis(hypothesis_id)
        self.projects.touch_project(hypothesis.project_id)
        return _hypothesis_evidence_entry(link, target_payload)

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
        recovery_guidance = _recovery_guidance(
            paper=paper,
            stages=stages,
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
            "recovery_guidance": recovery_guidance,
            "agent_reports": load_task_reports(self.papers, paper_id),
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

    def prepare_paper_for_output(self, paper_id: str, *, apply: bool = False) -> dict:
        status_before = self.paper_status(paper_id)
        planned_actions = _planned_prepare_actions(status_before)
        executed_actions = []
        skipped_actions = []

        if apply:
            paths = load_paths()
            for action in planned_actions:
                if action["code"] == "extract_text":
                    paper = self.papers.get_paper(paper_id)
                    if not paper.pdf_path:
                        skipped_actions.append({**action, "status": "skipped", "reason": "no_local_pdf"})
                        continue
                    artifact = extract_text_for_paper(repo=self.papers, paths=paths, paper=paper)
                    executed_actions.append({**action, "status": "completed", "artifact_id": artifact.id})
                elif action["code"] == "extract_claims":
                    claims = extract_claims_for_paper(
                        paths=paths,
                        paper_repo=self.papers,
                        claim_repo=self.claims,
                        concept_repo=self.concepts,
                        edge_repo=self.edges,
                        paper_id=paper_id,
                    )
                    executed_actions.append(
                        {**action, "status": "completed", "claim_count": len(claims), "claim_ids": [claim.id for claim in claims]}
                    )
                elif action["code"] == "extract_methods":
                    methods = extract_methods_for_paper(
                        paths=paths,
                        paper_repo=self.papers,
                        claim_repo=self.claims,
                        concept_repo=self.concepts,
                        edge_repo=self.edges,
                        method_repo=self.methods,
                        dataset_repo=self.datasets,
                        paper_id=paper_id,
                    )
                    executed_actions.append(
                        {
                            **action,
                            "status": "completed",
                            "method_count": len(methods),
                            "method_ids": [method.id for method in methods],
                        }
                    )
                elif action["code"] == "extract_datasets":
                    datasets = extract_datasets_for_paper(
                        paths=paths,
                        paper_repo=self.papers,
                        claim_repo=self.claims,
                        edge_repo=self.edges,
                        dataset_repo=self.datasets,
                        method_repo=self.methods,
                        paper_id=paper_id,
                    )
                    executed_actions.append(
                        {
                            **action,
                            "status": "completed",
                            "dataset_count": len(datasets),
                            "dataset_ids": [dataset.id for dataset in datasets],
                        }
                    )
                elif action["code"] == "summarize_paper":
                    payload = summarize_paper_heuristic(
                        paths=paths,
                        paper_repo=self.papers,
                        claim_repo=self.claims,
                        concept_repo=self.concepts,
                        paper_id=paper_id,
                    )
                    executed_actions.append(
                        {
                            **action,
                            "status": "completed",
                            "artifact_id": payload["artifact_id"],
                        }
                    )

        status_after = self.paper_status(paper_id)
        return {
            "paper_id": paper_id,
            "goal": "output",
            "apply": apply,
            "ready_before": status_before["readiness"]["levels"]["output_ready"],
            "ready_after": status_after["readiness"]["levels"]["output_ready"],
            "planned_actions": planned_actions,
            "executed_actions": executed_actions,
            "skipped_actions": skipped_actions,
            "status_before": status_before,
            "status_after": status_after,
        }

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


def _project_payload(project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "research_question": project.research_question,
        "status": project.status,
        "created_by": project.created_by,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _hypothesis_payload(hypothesis) -> dict:
    return {
        "id": hypothesis.id,
        "project_id": hypothesis.project_id,
        "text": hypothesis.text,
        "status": hypothesis.status,
        "confidence": hypothesis.confidence,
        "context": json.loads(hypothesis.context_json or "{}"),
        "created_by": hypothesis.created_by,
        "created_at": hypothesis.created_at,
        "updated_at": hypothesis.updated_at,
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


def _project_link_payload(link) -> dict:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "object_id": link.object_id,
        "object_type": link.object_type,
        "link_type": link.link_type,
        "metadata": json.loads(link.metadata_json or "{}"),
        "created_by": link.created_by,
        "created_at": link.created_at,
    }


def _project_paper_entry(link, paper) -> dict:
    return {
        "link": _project_link_payload(link),
        "paper": _paper_payload(paper),
    }


def _project_paper_entries(papers, links: list) -> list[dict]:
    entries = []
    for link in links:
        if link.object_type != "paper":
            continue
        entries.append(_project_paper_entry(link, papers.get_paper(link.object_id)))
    return entries


def _hypothesis_evidence_link_payload(link) -> dict:
    return {
        "id": link.id,
        "hypothesis_id": link.hypothesis_id,
        "object_id": link.object_id,
        "object_type": link.object_type,
        "relation_type": link.relation_type,
        "metadata": json.loads(link.metadata_json or "{}"),
        "created_by": link.created_by,
        "created_at": link.created_at,
    }


def _hypothesis_evidence_entry(link, target_payload: dict) -> dict:
    return {
        "link": _hypothesis_evidence_link_payload(link),
        **target_payload,
    }


def _hypothesis_evidence_entries(papers, claims, links: list) -> list[dict]:
    return [_hypothesis_evidence_entry(link, _resolve_hypothesis_evidence_target(papers, claims, link.object_type, link.object_id)) for link in links]


def _resolve_hypothesis_evidence_target(papers, claims, object_type: str, object_id: str) -> dict:
    if object_type == "paper":
        return {"paper": _paper_payload(papers.get_paper(object_id))}
    if object_type == "claim":
        claim = claims.get_claim(object_id)
        return {
            "claim": {
                "id": claim.id,
                "paper_id": claim.paper_id,
                "text": claim.text,
                "predicate": claim.predicate,
                "confidence": claim.confidence,
                "evidence": json.loads(claim.evidence_json or "{}"),
            }
        }
    raise ValueError(f"Unsupported hypothesis evidence object type: {object_type}")


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


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


def _recovery_guidance(*, paper, stages: dict, tasks: list) -> list[dict]:
    guidance = []
    for task in tasks:
        if task.status == "queued":
            guidance.append(
                {
                    "status": "queued",
                    "task_id": task.id,
                    "message": f"{task.task_type} is queued. Wait for the external agent result or import it when ready.",
                    "commands": _task_recovery_commands(task.task_type, task.status, paper.id, task.id),
                }
            )
        elif task.status == "running":
            guidance.append(
                {
                    "status": "running",
                    "task_id": task.id,
                    "message": f"{task.task_type} is still running. Do not start a duplicate task until the current one resolves.",
                    "commands": _task_recovery_commands(task.task_type, task.status, paper.id, task.id),
                }
            )
        elif task.status == "failed":
            guidance.append(
                {
                    "status": "failed",
                    "task_id": task.id,
                    "message": f"{task.task_type} failed. Inspect the task detail, then retry or import a corrected result.",
                    "commands": _task_recovery_commands(task.task_type, task.status, paper.id, task.id),
                }
            )
    if not paper.pdf_path and not stages["text"]:
        guidance.append(
            {
                "status": "blocked",
                "message": "Text extraction is blocked until a local PDF or external text result is available.",
                "commands": [command for command in (f"rks ingest doi {paper.doi}" if paper.doi else None, f"rks ingest arxiv {paper.arxiv_id}" if paper.arxiv_id else None) if command],
            }
        )
    return guidance


def _relation_key(anchor_claim_id: str, relation: dict) -> tuple[str, tuple[str, str]]:
    other_claim_id = relation["claim"]["id"]
    pair = tuple(sorted((anchor_claim_id, other_claim_id)))
    return relation["relation_type"], pair


def _planned_prepare_actions(status_payload: dict) -> list[dict]:
    paper_id = status_payload["paper"]["id"]
    stages = status_payload["stages"]
    actions = []
    if not stages["text"]:
        actions.append({"code": "extract_text", "command": f"rks extract text {paper_id}", "reason": "text artifact missing"})
    if not stages["claims"]:
        actions.append({"code": "extract_claims", "command": f"rks extract claims {paper_id}", "reason": "claims missing"})
    if stages["claims"] and not stages["methods"]:
        actions.append({"code": "extract_methods", "command": f"rks extract methods {paper_id}", "reason": "methods missing"})
    if stages["claims"] and not stages["datasets"]:
        actions.append({"code": "extract_datasets", "command": f"rks extract datasets {paper_id}", "reason": "datasets missing"})
    if stages["claims"] and not stages["summary"]:
        actions.append({"code": "summarize_paper", "command": f"rks summarize paper {paper_id}", "reason": "summary missing"})
    return actions


def _task_recovery_commands(task_type: str, status: str, paper_id: str, task_id: str) -> list[str]:
    commands = [f"rks tasks show {task_id}"]
    if status in {"queued", "running"}:
        if task_type == "extract_text":
            commands.append(f"rks import text {paper_id} <agent-result.json>")
        elif task_type == "extract_claims":
            commands.append(f"rks import claims {paper_id} <agent-result.json>")
        elif task_type == "summarize_paper":
            commands.append(f"rks import summary {paper_id} <agent-result.json>")
    elif status == "failed":
        if task_type == "extract_text":
            commands.append(f"rks extract text {paper_id} --mode agent")
        elif task_type == "extract_claims":
            commands.append(f"rks extract claims {paper_id} --mode agent")
        elif task_type == "summarize_paper":
            commands.append(f"rks summarize paper {paper_id} --mode agent")
    return commands
