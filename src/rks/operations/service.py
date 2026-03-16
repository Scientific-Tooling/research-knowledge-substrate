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
    build_scoped_answer,
    build_scoped_brief,
    build_comparison,
    build_research_answer,
    build_research_opportunities,
    build_scoped_disagreements,
    build_scoped_open_questions,
    build_scoped_opportunities,
    build_scoped_reading_list,
    build_scoped_review_priorities,
    build_topic_brief,
    build_topic_disagreements,
    build_topic_open_questions,
    build_topic_reading_list,
    build_topic_review_priorities,
    plan_research_request,
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
        candidates=None,
        evolution=None,
        conflict_clusters=None,
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
        self.candidates = candidates
        self.conflict_clusters = conflict_clusters
        self.evolution = evolution
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
        grouped_links = self._grouped_project_links(project_id)
        return {
            **_project_payload(project),
            "notes": [_note_payload(note) for note in notes],
            "links": grouped_links["links"],
            "papers": grouped_links["papers"],
            "claims": grouped_links["claims"],
            "methods": grouped_links["methods"],
            "datasets": grouped_links["datasets"],
            "concepts": grouped_links["concepts"],
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

    def list_project_links(self, project_id: str, *, object_type: str | None = None) -> list[dict]:
        self.projects.get_project(project_id)
        return _project_link_entries(
            self.papers,
            self.claims,
            self.methods,
            self.datasets,
            self.concepts,
            self.query,
            self.projects.list_links_for_project(project_id, object_type=object_type),
        )

    def list_project_claims(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="claim")
        return _project_link_entries(self.papers, self.claims, self.methods, self.datasets, self.concepts, self.query, links)

    def list_project_methods(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="method")
        return _project_link_entries(self.papers, self.claims, self.methods, self.datasets, self.concepts, self.query, links)

    def list_project_datasets(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="dataset")
        return _project_link_entries(self.papers, self.claims, self.methods, self.datasets, self.concepts, self.query, links)

    def list_project_concepts(self, project_id: str) -> list[dict]:
        self.projects.get_project(project_id)
        links = self.projects.list_links_for_project(project_id, object_type="concept")
        return _project_link_entries(self.papers, self.claims, self.methods, self.datasets, self.concepts, self.query, links)

    def add_project_link(
        self,
        project_id: str,
        object_type: str,
        object_id: str,
        *,
        link_type: str = "in_scope",
        created_by: str = "human:user",
    ) -> dict:
        self.projects.get_project(project_id)
        normalized_object_type = object_type.strip()
        normalized_link_type = link_type.strip()
        if normalized_object_type not in {"paper", "claim", "method", "dataset", "concept"}:
            raise ValueError("object_type must be one of: paper, claim, method, dataset, concept")
        if not normalized_link_type:
            raise ValueError("link_type must not be empty")

        target_payload = _resolve_project_link_target(
            self.papers,
            self.claims,
            self.methods,
            self.datasets,
            self.concepts,
            self.query,
            normalized_object_type,
            object_id,
        )
        link = self.projects.add_link(
            project_id=project_id,
            object_id=object_id,
            object_type=normalized_object_type,
            link_type=normalized_link_type,
            created_by=created_by,
            metadata=None,
        )
        self.projects.touch_project(project_id)
        return _project_link_entry(link, target_payload)

    def add_project_paper(
        self,
        project_id: str,
        paper_id: str,
        *,
        link_type: str = "in_scope",
        created_by: str = "human:user",
    ) -> dict:
        return self.add_project_link(
            project_id,
            "paper",
            paper_id,
            link_type=link_type,
            created_by=created_by,
        )

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
        result = build_topic_disagreements(self.query, topic)
        result["conflict_clusters"] = self._global_conflict_clusters(limit=5)
        return result

    def research_opportunities(self, topic: str) -> dict:
        return build_research_opportunities(self.query, topic)

    def topic_reading_list(self, topic: str) -> dict:
        return build_topic_reading_list(self.query, topic)

    def topic_open_questions(self, topic: str) -> dict:
        result = build_topic_open_questions(self.query, topic)
        evo = self.compute_open_questions()
        result["evolution_questions"] = evo.get("questions", [])[:5]
        return result

    def topic_review_priorities(self, topic: str) -> dict:
        result = build_topic_review_priorities(self.query, topic)
        evo = self.compute_review_priorities()
        result["evolution_priorities"] = evo.get("priorities", [])[:10]
        return result

    def project_answer(self, project_id: str, *, question: str | None = None) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        return build_scoped_answer(
            self.query,
            "project",
            project.name,
            context,
            question=_optional_text(question) or project.research_question or project.name,
        )

    def project_brief(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        return build_scoped_brief(
            self.query,
            "project",
            project.name,
            context,
            hypotheses=self.list_project_hypotheses(project_id),
            research_question=project.research_question,
        )

    def project_disagreements(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        result = build_scoped_disagreements(self.query, "project", project.name, context)
        result["conflict_clusters"] = self._project_conflict_clusters(project_id, limit=5)
        return result

    def project_opportunities(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        return build_scoped_opportunities(self.query, "project", project.name, context)

    def project_reading_list(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        return build_scoped_reading_list(self.query, "project", project.name, context)

    def project_open_questions(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        result = build_scoped_open_questions(
            self.query,
            "project",
            project.name,
            context,
            hypotheses=self.list_project_hypotheses(project_id),
        )
        evo = self.compute_open_questions(scope_type="project", scope_id=project_id)
        result["evolution_questions"] = evo.get("questions", [])[:5]
        return result

    def project_review_priorities(self, project_id: str) -> dict:
        project = self.projects.get_project(project_id)
        context = self._project_output_context(project_id)
        result = build_scoped_review_priorities(self.query, "project", project.name, context)
        evo = self.compute_review_priorities(scope_type="project", scope_id=project_id)
        result["evolution_priorities"] = evo.get("priorities", [])[:10]
        return result

    def plan_query(self, request: str, *, project_id: str | None = None) -> dict:
        project = None
        if project_id is not None:
            project = _project_payload(self.projects.get_project(project_id))
        return plan_research_request(request, project=project)

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

    # ------------------------------------------------------------------
    # Extraction quality metrics
    # ------------------------------------------------------------------

    def extraction_quality_report(self) -> dict:
        """Compute extraction quality metrics across all papers.

        Returns per-paper claim counts, zero-claim papers, predicate
        frequency distribution, and per-mode breakdowns.
        """
        papers = self.papers.list_papers()
        per_paper: list[dict] = []
        zero_claim_papers: list[dict] = []
        predicate_counts: dict[str, int] = {}
        mode_counts: dict[str, int] = {}
        total_claims = 0

        for paper in papers:
            claims = self.claims.list_claims_for_paper(paper.id)
            count = len(claims)
            total_claims += count
            entry = {"paper_id": paper.id, "title": paper.title, "claim_count": count}
            per_paper.append(entry)
            if count == 0:
                artifacts = self.papers.get_artifacts_for_paper(paper.id)
                has_text = any(a.artifact_type == "extracted_text" for a in artifacts)
                zero_claim_papers.append({**entry, "has_text": has_text})

            for claim in claims:
                pred = claim.predicate or "unknown"
                predicate_counts[pred] = predicate_counts.get(pred, 0) + 1
                evidence = json.loads(claim.evidence_json or "{}")
                mode = evidence.get("extraction", "unknown")
                mode_counts[mode] = mode_counts.get(mode, 0) + 1

        claim_counts = sorted([p["claim_count"] for p in per_paper])
        n = len(claim_counts)
        if n > 0:
            median = claim_counts[n // 2] if n % 2 else (claim_counts[n // 2 - 1] + claim_counts[n // 2]) / 2
            mean = total_claims / n
        else:
            median = 0
            mean = 0

        return {
            "paper_count": len(papers),
            "total_claims": total_claims,
            "claims_per_paper": {
                "mean": round(mean, 2),
                "median": median,
                "min": claim_counts[0] if claim_counts else 0,
                "max": claim_counts[-1] if claim_counts else 0,
            },
            "zero_claim_papers": zero_claim_papers,
            "predicate_distribution": dict(sorted(predicate_counts.items(), key=lambda x: -x[1])),
            "extraction_mode_distribution": mode_counts,
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
        if self.evolution is not None:
            self.evolution.record_event(
                event_type="relation_promoted",
                subject_id=source_claim.id,
                subject_type="claim",
                detail={
                    "relation_type": relation_type,
                    "target_claim_id": target_claim.id,
                    "confidence": confidence,
                    "edge_id": edge.id,
                },
                created_by=reviewed_by,
            )
        return _edge_payload(edge)

    def retract_claim_relation(self, source_claim_id: str, relation_type: str, target_claim_id: str) -> dict:
        deleted = self.edges.delete_claim_relation_edge(
            source_id=source_claim_id,
            relation_type=relation_type,
            target_id=target_claim_id,
        )
        if self.evolution is not None and deleted:
            self.evolution.record_event(
                event_type="relation_retracted",
                subject_id=source_claim_id,
                subject_type="claim",
                detail={
                    "relation_type": relation_type,
                    "target_claim_id": target_claim_id,
                },
                created_by="system:retract",
            )
        return {
            "source_claim_id": source_claim_id,
            "relation_type": relation_type,
            "target_claim_id": target_claim_id,
            "deleted": deleted,
        }

    def materialize_claim_relation_candidates(self, claim_id: str | None = None) -> dict:
        """Materialize inferred claim relations into the candidate table.

        If claim_id is given, materialize candidates for that claim only.
        Otherwise, materialize for all claims in the system.
        """
        if self.candidates is None:
            return {"error": "candidate repository not available", "materialized": 0}

        claims_to_process = []
        if claim_id:
            claims_to_process.append(self.claims.get_claim(claim_id))
        else:
            for paper in self.papers.list_papers():
                claims_to_process.extend(self.claims.list_claims_for_paper(paper.id))

        materialized = 0
        for anchor in claims_to_process:
            relations = self.query.claim_relations(anchor.id)
            for rel in relations.get("inferred_relations", []):
                target_id = rel["claim"]["id"]
                self.candidates.upsert_candidate(
                    source_claim_id=anchor.id,
                    target_claim_id=target_id,
                    relation_type=rel["relation_type"],
                    score=rel["claim"].get("confidence"),
                    metadata={
                        "anchor_paper_id": anchor.paper_id,
                        "target_paper_id": rel["claim"].get("paper_id"),
                    },
                )
                materialized += 1
        self.query.clear_relation_cache()
        return {"claim_id": claim_id, "materialized": materialized}

    def list_relation_candidates(self, claim_id: str | None = None, status: str | None = None) -> list[dict]:
        if self.candidates is None:
            return []
        if claim_id:
            records = self.candidates.list_for_claim(claim_id, status=status)
        else:
            records = self.candidates.list_pending()
        return [
            {
                "id": r.id,
                "source_claim_id": r.source_claim_id,
                "target_claim_id": r.target_claim_id,
                "relation_type": r.relation_type,
                "score": r.score,
                "algorithm_version": r.algorithm_version,
                "status": r.status,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in records
        ]

    def promote_candidate(self, candidate_id: str, reviewed_by: str = "agent:review") -> dict:
        if self.candidates is None:
            return {"error": "candidate repository not available"}
        candidate = self.candidates.get_candidate(candidate_id)
        result = self.promote_claim_relation(
            source_claim_id=candidate.source_claim_id,
            relation_type=candidate.relation_type,
            target_claim_id=candidate.target_claim_id,
            reviewed_by=reviewed_by,
        )
        self.candidates.update_status(candidate_id, "promoted")
        result["candidate_id"] = candidate_id
        return result

    def reject_candidate(self, candidate_id: str) -> dict:
        if self.candidates is None:
            return {"error": "candidate repository not available"}
        record = self.candidates.update_status(candidate_id, "rejected")
        return {"candidate_id": candidate_id, "status": record.status}

    # ------------------------------------------------------------------
    # Evolution: events and timeline
    # ------------------------------------------------------------------

    def list_evolution_events(self, subject_id: str, subject_type: str | None = None) -> list[dict]:
        if self.evolution is None:
            return []
        records = self.evolution.list_events_for_subject(subject_id, subject_type)
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "subject_id": r.subject_id,
                "subject_type": r.subject_type,
                "detail": json.loads(r.detail_json or "{}"),
                "created_by": r.created_by,
                "created_at": r.created_at,
            }
            for r in records
        ]

    def build_concept_timeline(self, concept_id: str) -> dict:
        """Snapshot current state of a concept and append to timeline."""
        if self.evolution is None:
            return {"error": "evolution repository not available"}

        concept = self.concepts.get_concept(concept_id)
        claims = self.claims.list_claims_for_concept(concept_id)
        paper_ids = sorted({claim.paper_id for claim in claims})

        support_count = 0
        contradiction_count = 0
        refine_count = 0
        for claim in claims:
            for edge in self.edges.list_claim_relation_edges(claim.id):
                if edge.relation_type == "supports":
                    support_count += 1
                elif edge.relation_type == "contradicts":
                    contradiction_count += 1
                elif edge.relation_type == "refines":
                    refine_count += 1

        total = support_count + contradiction_count
        consensus_score = support_count / max(1, total)
        controversy_score = min(support_count, contradiction_count) / max(1, total)

        snapshot = self.evolution.create_snapshot(
            concept_id=concept_id,
            support_count=support_count,
            contradiction_count=contradiction_count,
            paper_count=len(paper_ids),
            claim_count=len(claims),
            detail={"paper_ids": paper_ids},
            refine_count=refine_count,
            consensus_score=consensus_score,
            controversy_score=controversy_score,
            basis_layer="reviewed",
        )

        self.evolution.record_event(
            event_type="concept_snapshot",
            subject_id=concept_id,
            subject_type="concept",
            detail={
                "snapshot_id": snapshot.id,
                "support_count": support_count,
                "contradiction_count": contradiction_count,
                "refine_count": refine_count,
                "paper_count": len(paper_ids),
                "claim_count": len(claims),
                "consensus_score": consensus_score,
                "controversy_score": controversy_score,
            },
            created_by="system:timeline",
        )

        return {
            "concept": {"id": concept.id, "name": concept.name},
            "snapshot": {
                "id": snapshot.id,
                "snapshot_at": snapshot.snapshot_at,
                "support_count": snapshot.support_count,
                "contradiction_count": snapshot.contradiction_count,
                "refine_count": snapshot.refine_count,
                "paper_count": snapshot.paper_count,
                "claim_count": snapshot.claim_count,
                "consensus_score": snapshot.consensus_score,
                "controversy_score": snapshot.controversy_score,
            },
        }

    def build_hypothesis_evolution(self, hypothesis_id: str) -> dict:
        """Build an evolution view for a hypothesis.

        Aggregates evidence links by relation type, counts supporting vs
        contradicting evidence, includes evolution events if available,
        and computes a trend indicator.
        """
        hypothesis = self.hypotheses.get_hypothesis(hypothesis_id)
        evidence_links = self.hypotheses.list_evidence_links_for_hypothesis(hypothesis_id)

        support_count = 0
        contradiction_count = 0
        neutral_count = 0
        for link in evidence_links:
            if link.relation_type in ("supported_by", "supports"):
                support_count += 1
            elif link.relation_type in ("contradicted_by", "contradicts"):
                contradiction_count += 1
            else:
                neutral_count += 1

        total = support_count + contradiction_count + neutral_count
        if total == 0:
            trend = "no_evidence"
        elif contradiction_count == 0:
            trend = "strengthening"
        elif support_count == 0:
            trend = "weakening"
        elif support_count > contradiction_count * 2:
            trend = "strengthening"
        elif contradiction_count > support_count * 2:
            trend = "weakening"
        else:
            trend = "contested"

        events = []
        if self.evolution is not None:
            events = [
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "detail": json.loads(r.detail_json or "{}"),
                    "created_by": r.created_by,
                    "created_at": r.created_at,
                }
                for r in self.evolution.list_events_for_subject(hypothesis_id, "hypothesis")
            ]

        return {
            "hypothesis": _hypothesis_payload(hypothesis),
            "evidence_summary": {
                "support_count": support_count,
                "contradiction_count": contradiction_count,
                "neutral_count": neutral_count,
                "total": total,
            },
            "trend": trend,
            "events": events,
        }

    def concept_timeline(self, concept_id: str) -> dict:
        """Return the full timeline of snapshots for a concept."""
        if self.evolution is None:
            return {"error": "evolution repository not available", "snapshots": []}
        concept = self.concepts.get_concept(concept_id)
        snapshots = self.evolution.list_snapshots_for_concept(concept_id)
        return {
            "concept": {"id": concept.id, "name": concept.name},
            "snapshots": [_snapshot_payload(s) for s in snapshots],
        }

    # ------------------------------------------------------------------
    # Phase 2: Time-bucketed trend analysis
    # ------------------------------------------------------------------

    def build_concept_timeline_bucketed(self, concept_id: str, bucket_size: str = "yearly") -> dict:
        """Build time-bucketed snapshots grouped by paper year."""
        if self.evolution is None:
            return {"error": "evolution repository not available"}

        concept = self.concepts.get_concept(concept_id)
        claims = self.claims.list_claims_for_concept(concept_id)

        # Group claims by paper year
        buckets: dict[str, list] = {}
        for claim in claims:
            try:
                paper = self.papers.get_paper(claim.paper_id)
            except KeyError:
                continue
            year = paper.year
            if year is None:
                bucket_key = "unknown"
            else:
                bucket_key = str(year)
            buckets.setdefault(bucket_key, []).append(claim)

        created_snapshots = []
        for bucket_key in sorted(buckets):
            bucket_claims = buckets[bucket_key]
            bucket_claim_ids = {c.id for c in bucket_claims}
            paper_ids = sorted({c.paper_id for c in bucket_claims})

            support_count = 0
            contradiction_count = 0
            refine_count = 0
            for claim in bucket_claims:
                for edge in self.edges.list_claim_relation_edges(claim.id):
                    # Only count edges where both sides are in the same bucket
                    other_id = edge.target_id if edge.source_id == claim.id else edge.source_id
                    if other_id not in bucket_claim_ids:
                        continue
                    if edge.relation_type == "supports":
                        support_count += 1
                    elif edge.relation_type == "contradicts":
                        contradiction_count += 1
                    elif edge.relation_type == "refines":
                        refine_count += 1

            # Each edge counted from both sides, halve
            support_count = support_count // 2
            contradiction_count = contradiction_count // 2
            refine_count = refine_count // 2

            total = support_count + contradiction_count
            consensus_score = support_count / max(1, total)
            controversy_score = min(support_count, contradiction_count) / max(1, total)

            snapshot = self.evolution.create_snapshot(
                concept_id=concept_id,
                support_count=support_count,
                contradiction_count=contradiction_count,
                paper_count=len(paper_ids),
                claim_count=len(bucket_claims),
                detail={"paper_ids": paper_ids},
                time_bucket=bucket_key,
                refine_count=refine_count,
                consensus_score=consensus_score,
                controversy_score=controversy_score,
                basis_layer="reviewed",
            )
            created_snapshots.append(snapshot)

        self.evolution.record_event(
            event_type="concept_timeline_bucketed",
            subject_id=concept_id,
            subject_type="concept",
            detail={
                "bucket_size": bucket_size,
                "bucket_count": len(created_snapshots),
                "buckets": [s.time_bucket for s in created_snapshots],
            },
            created_by="system:timeline",
        )

        return {
            "concept": {"id": concept.id, "name": concept.name},
            "bucket_size": bucket_size,
            "snapshots": [_snapshot_payload(s) for s in created_snapshots],
        }

    # ------------------------------------------------------------------
    # Phase 2: Conflict clustering
    # ------------------------------------------------------------------

    def cluster_claim_conflicts(self, concept_id: str | None = None) -> dict:
        """Detect and persist conflict clusters from contradicts edges."""
        if self.conflict_clusters is None:
            return {"error": "conflict cluster repository not available"}

        concept_ids = []
        if concept_id:
            concept_ids.append(concept_id)
        else:
            for paper in self.papers.list_papers():
                for claim in self.claims.list_claims_for_paper(paper.id):
                    if claim.subject_concept_id and claim.subject_concept_id not in concept_ids:
                        concept_ids.append(claim.subject_concept_id)
                    if claim.object_concept_id and claim.object_concept_id not in concept_ids:
                        concept_ids.append(claim.object_concept_id)

        total_clusters = 0
        results = []
        for cid in concept_ids:
            concept = self.concepts.get_concept(cid)
            claims = self.claims.list_claims_for_concept(cid)
            claim_ids = {c.id for c in claims}

            # Build adjacency from contradicts edges
            adjacency: dict[str, set[str]] = {c.id: set() for c in claims}
            for claim in claims:
                for edge in self.edges.list_claim_relation_edges(claim.id, relation_types=["contradicts"]):
                    src, tgt = edge.source_id, edge.target_id
                    if src in claim_ids and tgt in claim_ids:
                        adjacency.setdefault(src, set()).add(tgt)
                        adjacency.setdefault(tgt, set()).add(src)

            # Find connected components via BFS
            visited: set[str] = set()
            components: list[set[str]] = []
            for node in adjacency:
                if node in visited or not adjacency[node]:
                    continue
                component: set[str] = set()
                queue = [node]
                while queue:
                    current = queue.pop()
                    if current in visited:
                        continue
                    visited.add(current)
                    component.add(current)
                    for neighbor in adjacency.get(current, set()):
                        if neighbor not in visited:
                            queue.append(neighbor)
                if len(component) >= 2:
                    components.append(component)

            if not components:
                continue

            # Clear old clusters for this concept before creating new ones
            self.conflict_clusters.clear_clusters_for_concept(cid)

            for component in components:
                cluster = self.conflict_clusters.create_cluster(
                    anchor_concept_id=cid,
                    topic_label=concept.name,
                    summary={"claim_count": len(component)},
                )

                # Assign stances: count support edges to determine majority
                claim_support_counts: dict[str, int] = {}
                for claim_id_in_component in component:
                    count = 0
                    for edge in self.edges.list_claim_relation_edges(claim_id_in_component, relation_types=["supports"]):
                        count += 1
                    claim_support_counts[claim_id_in_component] = count

                if claim_support_counts:
                    median_support = sorted(claim_support_counts.values())[len(claim_support_counts) // 2]
                else:
                    median_support = 0

                for claim_id_in_component in component:
                    support = claim_support_counts.get(claim_id_in_component, 0)
                    stance = "mainstream" if support >= median_support else "dissenting"
                    self.conflict_clusters.add_member(
                        cluster_id=cluster.id,
                        claim_id=claim_id_in_component,
                        role="member",
                        stance=stance,
                    )

                total_clusters += 1

                if self.evolution is not None:
                    self.evolution.record_event(
                        event_type="conflict_cluster_created",
                        subject_id=cluster.id,
                        subject_type="conflict_cluster",
                        detail={
                            "anchor_concept_id": cid,
                            "concept_name": concept.name,
                            "member_count": len(component),
                        },
                        created_by="system:clustering",
                    )

            results.append({
                "concept_id": cid,
                "concept_name": concept.name,
                "cluster_count": len(components),
            })

        return {"total_clusters": total_clusters, "concepts": results}

    def list_conflict_clusters(self, concept_id: str) -> dict:
        """List conflict clusters for a concept with members."""
        if self.conflict_clusters is None:
            return {"error": "conflict cluster repository not available", "clusters": []}

        concept = self.concepts.get_concept(concept_id)
        clusters = self.conflict_clusters.list_clusters_for_concept(concept_id)
        result = []
        for cluster in clusters:
            members = self.conflict_clusters.list_members_for_cluster(cluster.id)
            result.append({
                "id": cluster.id,
                "topic_label": cluster.topic_label,
                "status": cluster.status,
                "members": [
                    {
                        "id": m.id,
                        "claim_id": m.claim_id,
                        "role": m.role,
                        "stance": m.stance,
                        "confidence": m.confidence,
                    }
                    for m in members
                ],
                "created_at": cluster.created_at,
            })
        return {
            "concept": {"id": concept.id, "name": concept.name},
            "clusters": result,
        }

    # ------------------------------------------------------------------
    # Phase 2: Discovery engine — review priorities and open questions
    # ------------------------------------------------------------------

    def compute_review_priorities(self, scope_type: str = "concept", scope_id: str | None = None) -> dict:
        """Rank pending candidates by evolution-derived priority."""
        if self.candidates is None:
            return {"error": "candidate repository not available", "priorities": []}

        pending = self.candidates.list_pending(limit=200)
        if not pending:
            return {"priorities": [], "count": 0}

        # Gather hypothesis claim IDs for relevance check
        hypothesis_claim_ids: set[str] = set()
        try:
            for paper in self.papers.list_papers():
                pass  # iterate to confirm connectivity
            if scope_id and scope_type == "project":
                for h in self.hypotheses.list_hypotheses_for_project(scope_id):
                    for link in self.hypotheses.list_evidence_links_for_hypothesis(h.id):
                        if link.object_type == "claim":
                            hypothesis_claim_ids.add(link.object_id)
            else:
                for project in self.projects.list_projects():
                    for h in self.hypotheses.list_hypotheses_for_project(project.id):
                        for link in self.hypotheses.list_evidence_links_for_hypothesis(h.id):
                            if link.object_type == "claim":
                                hypothesis_claim_ids.add(link.object_id)
        except Exception:
            pass

        # Cache latest concept controversy scores
        concept_controversy: dict[str, float] = {}

        priorities = []
        for candidate in pending:
            score = candidate.score or 0.0

            # Hypothesis relevance
            hypothesis_relevant = (
                candidate.source_claim_id in hypothesis_claim_ids
                or candidate.target_claim_id in hypothesis_claim_ids
            )

            # Concept controversy
            controversy = 0.0
            try:
                source_claim = self.claims.get_claim(candidate.source_claim_id)
                for cid in [source_claim.subject_concept_id, source_claim.object_concept_id]:
                    if cid and cid not in concept_controversy and self.evolution:
                        snapshots = self.evolution.list_snapshots_for_concept(cid)
                        if snapshots:
                            latest = snapshots[-1]
                            concept_controversy[cid] = latest.controversy_score or 0.0
                    if cid and cid in concept_controversy:
                        controversy = max(controversy, concept_controversy[cid])
            except (KeyError, Exception):
                pass

            # Recency bonus
            recency = 0.0
            try:
                source_claim = self.claims.get_claim(candidate.source_claim_id)
                paper = self.papers.get_paper(source_claim.paper_id)
                if paper.year and paper.year >= 2024:
                    recency = 1.0
                elif paper.year and paper.year >= 2022:
                    recency = 0.5
            except (KeyError, Exception):
                pass

            priority_score = (
                score * 0.3
                + controversy * 0.25
                + (1.0 if hypothesis_relevant else 0.0) * 0.25
                + recency * 0.2
            )

            priorities.append({
                "candidate_id": candidate.id,
                "source_claim_id": candidate.source_claim_id,
                "target_claim_id": candidate.target_claim_id,
                "relation_type": candidate.relation_type,
                "priority_score": round(priority_score, 4),
                "factors": {
                    "candidate_score": score,
                    "controversy": round(controversy, 4),
                    "hypothesis_relevant": hypothesis_relevant,
                    "recency": recency,
                },
            })

        priorities.sort(key=lambda p: p["priority_score"], reverse=True)
        return {"priorities": priorities, "count": len(priorities)}

    def compute_open_questions(self, scope_type: str = "concept", scope_id: str | None = None) -> dict:
        """Identify evidence-sparse controversies and under-explored areas."""
        if self.evolution is None:
            return {"error": "evolution repository not available", "questions": []}

        questions = []

        # Gather concepts to analyze
        concept_ids: list[str] = []
        if scope_id and scope_type == "concept":
            concept_ids = [scope_id]
        elif scope_id and scope_type == "project":
            links = self.projects.list_links_for_project(scope_id)
            concept_ids = [link.object_id for link in links if link.object_type == "concept"]
        else:
            # All concepts with snapshots — check up to 200 concepts
            seen = set()
            for paper in self.papers.list_papers():
                for claim in self.claims.list_claims_for_paper(paper.id):
                    for cid in [claim.subject_concept_id, claim.object_concept_id]:
                        if cid and cid not in seen:
                            seen.add(cid)
                            concept_ids.append(cid)
                            if len(concept_ids) >= 200:
                                break

        for cid in concept_ids:
            try:
                concept = self.concepts.get_concept(cid)
            except KeyError:
                continue
            snapshots = self.evolution.list_snapshots_for_concept(cid)
            if not snapshots:
                continue
            latest = snapshots[-1]

            # High controversy, low claim count → evidence-sparse controversy
            cs = latest.controversy_score or 0.0
            if cs > 0.3 and latest.claim_count <= 5:
                questions.append({
                    "concept_id": cid,
                    "concept_name": concept.name,
                    "type": "evidence_sparse_controversy",
                    "controversy_score": cs,
                    "claim_count": latest.claim_count,
                    "description": f"'{concept.name}' has controversy score {cs:.2f} but only {latest.claim_count} claims — more evidence needed.",
                })

            # Trend shift detection: compare first and last snapshot
            if len(snapshots) >= 2:
                first = snapshots[0]
                first_cs = first.consensus_score or 0.5
                latest_cs = latest.consensus_score or 0.5
                shift = abs(latest_cs - first_cs)
                if shift > 0.3:
                    direction = "weakening consensus" if latest_cs < first_cs else "strengthening consensus"
                    questions.append({
                        "concept_id": cid,
                        "concept_name": concept.name,
                        "type": "trend_shift",
                        "consensus_shift": round(shift, 4),
                        "direction": direction,
                        "description": f"'{concept.name}' shows {direction} (shift={shift:.2f}) — worth investigating.",
                    })

        return {"questions": questions, "count": len(questions)}

    def list_concept_controversies(self, min_score: float = 0.0, limit: int = 50) -> dict:
        """Rank concepts by their latest controversy score (descending)."""
        if self.evolution is None:
            return {"error": "evolution repository not available", "concepts": []}

        concept_ids = self.evolution.list_concept_ids_with_snapshots()
        entries = []
        for cid in concept_ids:
            snapshot = self.evolution.get_latest_snapshot_for_concept(cid)
            if snapshot is None:
                continue
            score = snapshot.controversy_score or 0.0
            if score < min_score:
                continue
            try:
                concept = self.concepts.get_concept(cid)
                name = concept.name
            except KeyError:
                name = cid
            entries.append({
                "concept_id": cid,
                "concept_name": name,
                "controversy_score": round(score, 4),
                "consensus_score": round(snapshot.consensus_score or 0.0, 4),
                "claim_count": snapshot.claim_count,
                "support_count": snapshot.support_count,
                "contradiction_count": snapshot.contradiction_count,
                "snapshot_at": snapshot.snapshot_at,
            })

        entries.sort(key=lambda x: x["controversy_score"], reverse=True)
        return {"concepts": entries[:limit], "count": len(entries)}

    def _global_conflict_clusters(self, limit: int = 5) -> list[dict]:
        """Return a sample of conflict clusters across all concepts."""
        if self.conflict_clusters is None:
            return []
        concept_ids = []
        seen: set[str] = set()
        for paper in self.papers.list_papers():
            for claim in self.claims.list_claims_for_paper(paper.id):
                for cid in [claim.subject_concept_id, claim.object_concept_id]:
                    if cid and cid not in seen:
                        seen.add(cid)
                        concept_ids.append(cid)
        results = []
        for cid in concept_ids:
            if len(results) >= limit:
                break
            clusters = self.conflict_clusters.list_clusters_for_concept(cid)
            for cluster in clusters:
                if len(results) >= limit:
                    break
                members = self.conflict_clusters.list_members_for_cluster(cluster.id)
                results.append({
                    "id": cluster.id,
                    "anchor_concept_id": cid,
                    "topic_label": cluster.topic_label,
                    "member_count": len(members),
                    "status": cluster.status,
                })
        return results

    def _project_conflict_clusters(self, project_id: str, limit: int = 5) -> list[dict]:
        """Return conflict clusters for concepts linked to a project."""
        if self.conflict_clusters is None:
            return []
        links = self.projects.list_links_for_project(project_id)
        concept_ids = [link.object_id for link in links if link.object_type == "concept"]
        results = []
        for cid in concept_ids:
            if len(results) >= limit:
                break
            clusters = self.conflict_clusters.list_clusters_for_concept(cid)
            for cluster in clusters:
                if len(results) >= limit:
                    break
                members = self.conflict_clusters.list_members_for_cluster(cluster.id)
                results.append({
                    "id": cluster.id,
                    "anchor_concept_id": cid,
                    "topic_label": cluster.topic_label,
                    "member_count": len(members),
                    "status": cluster.status,
                })
        return results

    # ------------------------------------------------------------------
    # Phase 2: Project-scoped evolution
    # ------------------------------------------------------------------

    def project_evolution_summary(self, project_id: str) -> dict:
        """Aggregate evolution data across all concepts and hypotheses linked to a project."""
        project = self.projects.get_project(project_id)

        # Gather linked concepts
        links = self.projects.list_links_for_project(project_id)
        concept_ids = [link.object_id for link in links if link.object_type == "concept"]

        concept_summaries = []
        for cid in concept_ids:
            try:
                concept = self.concepts.get_concept(cid)
            except KeyError:
                continue
            snapshots = self.evolution.list_snapshots_for_concept(cid) if self.evolution else []
            latest = snapshots[-1] if snapshots else None
            cluster_count = 0
            if self.conflict_clusters:
                cluster_count = len(self.conflict_clusters.list_clusters_for_concept(cid))
            concept_summaries.append({
                "concept_id": cid,
                "concept_name": concept.name,
                "snapshot_count": len(snapshots),
                "latest_consensus": latest.consensus_score if latest else None,
                "latest_controversy": latest.controversy_score if latest else None,
                "conflict_cluster_count": cluster_count,
            })

        # Gather hypothesis evolution summaries
        hypotheses = self.hypotheses.list_hypotheses_for_project(project_id)
        hypothesis_summaries = []
        for h in hypotheses:
            evo = self.build_hypothesis_evolution(h.id)
            hypothesis_summaries.append({
                "hypothesis_id": h.id,
                "text": h.text,
                "trend": evo["trend"],
                "evidence_summary": evo["evidence_summary"],
            })

        # Review priorities scoped to project
        priorities = self.compute_review_priorities(scope_type="project", scope_id=project_id)

        return {
            "project": {"id": project.id, "name": project.name},
            "concepts": concept_summaries,
            "hypotheses": hypothesis_summaries,
            "review_priorities": priorities.get("priorities", [])[:10],
        }

    def _grouped_project_links(self, project_id: str) -> dict:
        entries = self.list_project_links(project_id)
        grouped = {
            "links": entries,
            "papers": [],
            "claims": [],
            "methods": [],
            "datasets": [],
            "concepts": [],
        }
        for entry in entries:
            object_type = entry["link"]["object_type"]
            if object_type == "paper":
                grouped["papers"].append(entry)
            elif object_type == "claim":
                grouped["claims"].append(entry)
            elif object_type == "method":
                grouped["methods"].append(entry)
            elif object_type == "dataset":
                grouped["datasets"].append(entry)
            elif object_type == "concept":
                grouped["concepts"].append(entry)
        return grouped

    def _project_output_context(self, project_id: str) -> dict:
        self.projects.get_project(project_id)
        paper_ids: set[str] = set()
        claim_ids: set[str] = set()
        method_ids: set[str] = set()
        dataset_ids: set[str] = set()
        concept_ids: set[str] = set()
        expanded_papers: set[str] = set()
        expanded_methods: set[str] = set()
        expanded_concepts: set[str] = set()

        def include_paper(paper_id: str) -> bool:
            if paper_id in paper_ids:
                return False
            self.papers.get_paper(paper_id)
            paper_ids.add(paper_id)
            return True

        def include_claim(claim_id: str) -> bool:
            if claim_id in claim_ids:
                return False
            claim = self.claims.get_claim(claim_id)
            claim_ids.add(claim_id)
            include_paper(claim.paper_id)
            if claim.subject_concept_id:
                concept_ids.add(claim.subject_concept_id)
            if claim.object_concept_id:
                concept_ids.add(claim.object_concept_id)
            return True

        def include_method(method_id: str) -> bool:
            if method_id in method_ids:
                return False
            method = self.methods.get_method(method_id)
            method_ids.add(method_id)
            include_paper(method.paper_id)
            if method.about_concept_id:
                concept_ids.add(method.about_concept_id)
            return True

        def include_dataset(dataset_id: str) -> bool:
            if dataset_id in dataset_ids:
                return False
            dataset = self.datasets.get_dataset(dataset_id)
            dataset_ids.add(dataset_id)
            include_paper(dataset.paper_id)
            return True

        def include_concept(concept_id: str) -> bool:
            if concept_id in concept_ids:
                return False
            self.concepts.get_concept(concept_id)
            concept_ids.add(concept_id)
            return True

        for link in self.projects.list_links_for_project(project_id):
            if link.object_type == "paper":
                include_paper(link.object_id)
            elif link.object_type == "claim":
                include_claim(link.object_id)
            elif link.object_type == "method":
                include_method(link.object_id)
            elif link.object_type == "dataset":
                include_dataset(link.object_id)
            elif link.object_type == "concept":
                include_concept(link.object_id)

        for hypothesis in self.hypotheses.list_hypotheses_for_project(project_id):
            for evidence_link in self.hypotheses.list_evidence_links_for_hypothesis(hypothesis.id):
                if evidence_link.object_type == "paper":
                    include_paper(evidence_link.object_id)
                elif evidence_link.object_type == "claim":
                    include_claim(evidence_link.object_id)

        changed = True
        while changed:
            changed = False

            for paper_id in list(paper_ids - expanded_papers):
                expanded_papers.add(paper_id)
                for claim in self.claims.list_claims_for_paper(paper_id):
                    changed = include_claim(claim.id) or changed
                for method in self.methods.list_methods_for_paper(paper_id):
                    changed = include_method(method.id) or changed
                for dataset in self.datasets.list_datasets_for_paper(paper_id):
                    changed = include_dataset(dataset.id) or changed
                for concept in self.query.concepts_for_paper(paper_id):
                    changed = include_concept(concept["id"]) or changed

            for method_id in list(method_ids - expanded_methods):
                expanded_methods.add(method_id)
                for dataset in self.query.datasets_for(method_id).get("datasets", []):
                    changed = include_dataset(dataset["id"]) or changed

            for concept_id in list(concept_ids - expanded_concepts):
                expanded_concepts.add(concept_id)
                claims_payload = self.query.claims_about(concept_id).get("claims", [])
                methods_payload = self.query.methods_for(concept_id).get("methods", [])
                datasets_payload = self.query.evidence_for(concept_id).get("datasets", [])
                for claim in claims_payload:
                    changed = include_claim(claim["id"]) or changed
                for method in methods_payload:
                    changed = include_method(method["id"]) or changed
                for dataset in datasets_payload:
                    changed = include_dataset(dataset["id"]) or changed

        claims = sorted(
            [_claim_payload(self.concepts, self.claims.get_claim(claim_id)) for claim_id in claim_ids],
            key=lambda item: (item.get("confidence") or 0.0, item["id"]),
            reverse=True,
        )
        papers = sorted(
            [_paper_payload(self.papers.get_paper(paper_id)) for paper_id in paper_ids],
            key=lambda item: (item["title"].lower(), item["id"]),
        )
        methods = sorted(
            [_method_payload(self.concepts, self.methods.get_method(method_id)) for method_id in method_ids],
            key=lambda item: (item["name"].lower(), item["id"]),
        )
        datasets = sorted(
            [_dataset_payload(self.datasets.get_dataset(dataset_id)) for dataset_id in dataset_ids],
            key=lambda item: (item["name"].lower(), item["id"]),
        )
        concepts = sorted(
            [_concept_payload(self.concepts.get_concept(concept_id)) for concept_id in concept_ids],
            key=lambda item: (item["name"].lower(), item["id"]),
        )
        return {
            "project_id": project_id,
            "claims": claims,
            "claim_ids": [claim["id"] for claim in claims[:12]],
            "papers": papers,
            "methods": methods,
            "datasets": datasets,
            "concepts": concepts,
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


def _claim_payload(concepts, claim) -> dict:
    context = json.loads(claim.context_json or "{}")
    subject_name = context.get("subject_text")
    object_name = claim.object_text
    if claim.subject_concept_id:
        subject_name = concepts.get_concept(claim.subject_concept_id).name
    if claim.object_concept_id:
        object_name = concepts.get_concept(claim.object_concept_id).name
    return {
        "id": claim.id,
        "paper_id": claim.paper_id,
        "text": claim.text,
        "subject": subject_name,
        "predicate": claim.predicate,
        "object": object_name,
        "confidence": claim.confidence,
        "context": context,
        "evidence": json.loads(claim.evidence_json or "{}"),
        "created_by": claim.created_by,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
    }


def _method_payload(concepts, method) -> dict:
    about_concept = None
    if method.about_concept_id:
        concept = concepts.get_concept(method.about_concept_id)
        about_concept = {"id": concept.id, "name": concept.name}
    return {
        "id": method.id,
        "paper_id": method.paper_id,
        "name": method.name,
        "description": method.description,
        "about_concept": about_concept,
        "created_at": method.created_at,
        "updated_at": method.updated_at,
    }


def _dataset_payload(dataset) -> dict:
    return {
        "id": dataset.id,
        "paper_id": dataset.paper_id,
        "name": dataset.name,
        "description": dataset.description,
        "source": dataset.source,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def _concept_payload(concept) -> dict:
    return {
        "id": concept.id,
        "name": concept.name,
        "aliases": json.loads(concept.aliases_json or "[]"),
        "domain": concept.domain,
        "parent_concept_id": concept.parent_concept_id,
        "description": concept.description,
        "status": concept.status,
        "created_at": concept.created_at,
        "updated_at": concept.updated_at,
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


def _snapshot_payload(s) -> dict:
    return {
        "id": s.id,
        "snapshot_at": s.snapshot_at,
        "support_count": s.support_count,
        "contradiction_count": s.contradiction_count,
        "refine_count": s.refine_count,
        "paper_count": s.paper_count,
        "claim_count": s.claim_count,
        "consensus_score": s.consensus_score,
        "controversy_score": s.controversy_score,
        "time_bucket": s.time_bucket,
        "basis_layer": s.basis_layer,
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


def _project_link_entry(link, target_payload: dict) -> dict:
    return {
        "link": _project_link_payload(link),
        **target_payload,
    }


def _project_link_entries(papers, claims, methods, datasets, concepts, query, links: list) -> list[dict]:
    return [
        _project_link_entry(
            link,
            _resolve_project_link_target(papers, claims, methods, datasets, concepts, query, link.object_type, link.object_id),
        )
        for link in links
    ]


def _resolve_project_link_target(papers, claims, methods, datasets, concepts, query, object_type: str, object_id: str) -> dict:
    if object_type == "paper":
        return {"paper": _paper_payload(papers.get_paper(object_id))}
    if object_type == "claim":
        return {"claim": _claim_payload(concepts, claims.get_claim(object_id))}
    if object_type == "method":
        return {"method": _method_payload(concepts, methods.get_method(object_id))}
    if object_type == "dataset":
        return {"dataset": _dataset_payload(datasets.get_dataset(object_id))}
    if object_type == "concept":
        concept = concepts.get_concept(object_id)
        evidence = query.evidence_for(object_id)
        return {
            "concept": {
                **_concept_payload(concept),
                "claim_count": len(evidence.get("claims", [])),
                "paper_count": len(evidence.get("papers", [])),
                "method_count": len(evidence.get("methods", [])),
                "dataset_count": len(evidence.get("datasets", [])),
            }
        }
    raise ValueError(f"Unsupported project link object type: {object_type}")


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
        else:
            reingest_command = _paper_reingest_command(paper)
            if reingest_command:
                commands.append(reingest_command)
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
                "commands": [command for command in (_paper_reingest_command(paper),) if command],
            }
        )
    return guidance


def _paper_reingest_command(paper) -> str | None:
    if paper.source_type == "doi" and paper.source_ref:
        return f"rks ingest doi {paper.source_ref}"
    if paper.source_type == "arxiv" and paper.source_ref:
        return f"rks ingest arxiv {paper.source_ref}"
    if paper.source_type == "pmid" and paper.source_ref:
        return f"rks ingest pmid {paper.source_ref}"
    if paper.source_ref and str(paper.source_ref).startswith(("http://", "https://")):
        return f"rks ingest url {paper.source_ref}"
    if paper.doi:
        return f"rks ingest doi {paper.doi}"
    if paper.arxiv_id:
        return f"rks ingest arxiv {paper.arxiv_id}"
    return None


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
