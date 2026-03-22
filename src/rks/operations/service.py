from __future__ import annotations

import json
import re
from collections import defaultdict

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
from rks.reasoning.summary import summarize_paper_from_graph
from rks.utils import utc_now


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
        relation_type: str = "supports",
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

    def find_duplicate_papers(self, *, mode: str = "title") -> dict:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"title", "identifiers"}:
            raise ValueError("mode must be one of: title, identifiers")

        papers = self.papers.list_papers()
        paper_by_id = {paper.id: paper for paper in papers}
        signal_to_paper_ids: dict[tuple[str, str], list[str]] = defaultdict(list)

        for paper in papers:
            doi_key = _normalized_optional_key(paper.doi)
            if doi_key:
                signal_to_paper_ids[("doi", doi_key)].append(paper.id)
            arxiv_key = _normalized_optional_key(paper.arxiv_id)
            if arxiv_key:
                signal_to_paper_ids[("arxiv_id", arxiv_key)].append(paper.id)
            if normalized_mode == "title":
                title_key = _normalized_title_key(paper.title)
                if title_key:
                    signal_to_paper_ids[("title", title_key)].append(paper.id)

        duplicate_signal_keys = [
            (kind, value, _dedupe_preserve_order(ids))
            for (kind, value), ids in signal_to_paper_ids.items()
            if len(set(ids)) > 1
        ]
        if not duplicate_signal_keys:
            return {
                "mode": normalized_mode,
                "paper_count": len(papers),
                "group_count": 0,
                "groups": [],
            }

        duplicates_paper_ids = sorted({paper_id for _, _, ids in duplicate_signal_keys for paper_id in ids})
        parent = {paper_id: paper_id for paper_id in duplicates_paper_ids}

        def find(node_id: str) -> str:
            root = node_id
            while parent[root] != root:
                root = parent[root]
            while node_id != root:
                next_node = parent[node_id]
                parent[node_id] = root
                node_id = next_node
            return root

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for _, _, ids in duplicate_signal_keys:
            anchor = ids[0]
            for candidate in ids[1:]:
                union(anchor, candidate)

        groups_by_root: dict[str, list[str]] = defaultdict(list)
        for paper_id in duplicates_paper_ids:
            groups_by_root[find(paper_id)].append(paper_id)

        signals_by_root: dict[str, list[dict]] = defaultdict(list)
        for kind, value, ids in duplicate_signal_keys:
            roots = {find(paper_id) for paper_id in ids}
            if len(roots) != 1:
                continue
            root = next(iter(roots))
            signals_by_root[root].append(
                {
                    "kind": kind,
                    "value": value,
                    "paper_ids": ids,
                }
            )

        group_rows = []
        for root, group_ids in groups_by_root.items():
            if len(group_ids) < 2:
                continue
            ordered_ids = sorted(group_ids)
            group_rows.append((ordered_ids, signals_by_root.get(root, [])))
        group_rows.sort(key=lambda item: (-len(item[0]), item[0][0]))

        groups = []
        for index, (group_ids, signals) in enumerate(group_rows, start=1):
            papers_payload = []
            for paper_id in group_ids:
                payload = _paper_payload(paper_by_id[paper_id])
                payload["tags"] = self.papers.list_tags_for_paper(paper_id)
                papers_payload.append(payload)
            signals.sort(key=lambda item: (item["kind"], item["value"]))
            groups.append(
                {
                    "id": f"dup_{index:04d}",
                    "paper_ids": group_ids,
                    "papers": papers_payload,
                    "signals": signals,
                }
            )

        return {
            "mode": normalized_mode,
            "paper_count": len(papers),
            "group_count": len(groups),
            "groups": groups,
        }

    def merge_papers(self, target_paper_id: str, source_paper_id: str, *, prefer: str = "target") -> dict:
        normalized_prefer = prefer.strip().lower()
        if normalized_prefer not in {"target", "source"}:
            raise ValueError("prefer must be one of: target, source")
        if target_paper_id == source_paper_id:
            raise ValueError("target_paper_id and source_paper_id must be different")

        conn = self.papers.conn
        target = self.papers.get_paper(target_paper_id)
        source = self.papers.get_paper(source_paper_id)
        timestamp = utc_now()

        moved_claims = conn.execute(
            "UPDATE claims SET paper_id = ?, updated_at = ? WHERE paper_id = ?",
            (target_paper_id, timestamp, source_paper_id),
        ).rowcount
        moved_methods = conn.execute(
            "UPDATE methods SET paper_id = ?, updated_at = ? WHERE paper_id = ?",
            (target_paper_id, timestamp, source_paper_id),
        ).rowcount
        moved_datasets = conn.execute(
            "UPDATE datasets SET paper_id = ?, updated_at = ? WHERE paper_id = ?",
            (target_paper_id, timestamp, source_paper_id),
        ).rowcount
        moved_tasks = conn.execute(
            "UPDATE tasks SET paper_id = ?, updated_at = ? WHERE paper_id = ?",
            (target_paper_id, timestamp, source_paper_id),
        ).rowcount
        moved_notes = conn.execute(
            """
            UPDATE notes
            SET target_id = ?
            WHERE target_type = 'paper' AND target_id = ?
            """,
            (target_paper_id, source_paper_id),
        ).rowcount

        moved_edge_evidence = conn.execute(
            """
            UPDATE edges
            SET evidence_paper_id = ?
            WHERE evidence_paper_id = ?
            """,
            (target_paper_id, source_paper_id),
        ).rowcount
        moved_edge_sources = conn.execute(
            """
            UPDATE edges
            SET source_id = ?
            WHERE source_type = 'paper' AND source_id = ?
            """,
            (target_paper_id, source_paper_id),
        ).rowcount
        moved_edge_targets = conn.execute(
            """
            UPDATE edges
            SET target_id = ?
            WHERE target_type = 'paper' AND target_id = ?
            """,
            (target_paper_id, source_paper_id),
        ).rowcount

        before_tag_changes = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO paper_tags(paper_id, tag, created_at)
            SELECT ?, tag, created_at
            FROM paper_tags
            WHERE paper_id = ?
            """,
            (target_paper_id, source_paper_id),
        )
        tags_added = conn.total_changes - before_tag_changes
        source_tags_removed = conn.execute(
            "DELETE FROM paper_tags WHERE paper_id = ?",
            (source_paper_id,),
        ).rowcount

        moved_project_links = conn.execute(
            """
            UPDATE project_links
            SET object_id = ?
            WHERE object_type = 'paper' AND object_id = ?
            """,
            (target_paper_id, source_paper_id),
        ).rowcount
        deduped_project_links = _dedupe_project_paper_links(conn, target_paper_id)

        moved_hypothesis_links = conn.execute(
            """
            UPDATE edges
            SET target_id = ?
            WHERE source_type = 'hypothesis' AND target_type = 'paper' AND target_id = ?
            """,
            (target_paper_id, source_paper_id),
        ).rowcount
        deduped_hypothesis_links = _dedupe_hypothesis_paper_links(conn, target_paper_id)

        artifact_summary = _merge_paper_artifacts(
            conn,
            target_paper_id=target_paper_id,
            source_paper_id=source_paper_id,
            prefer=normalized_prefer,
        )
        deduped_edges = _dedupe_paper_edges(conn, target_paper_id)

        source_pdf_artifact = _latest_artifact_for_type(conn, target_paper_id, "source_pdf")
        text_artifact = _latest_artifact_for_type(conn, target_paper_id, "extracted_text")
        text_artifact_id = text_artifact["id"] if text_artifact is not None else None
        pdf_path = source_pdf_artifact["path"] if source_pdf_artifact is not None else None

        resolved_title = _pick_value(
            target.title,
            source.title,
            prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        ) or target.title
        resolved_abstract = _pick_value(
            target.abstract,
            source.abstract,
            prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_authors_json = _pick_value(
            target.authors_json,
            source.authors_json,
            prefer=normalized_prefer,
            is_missing=_authors_json_missing,
        ) or target.authors_json
        resolved_year = _pick_value(
            target.year,
            source.year,
            prefer=normalized_prefer,
            is_missing=lambda value: value is None,
        )
        resolved_venue = _pick_value(
            target.venue,
            source.venue,
            prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_doi = _pick_value(
            target.doi,
            source.doi,
            prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_arxiv_id = _pick_value(
            target.arxiv_id,
            source.arxiv_id,
            prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_source_type = _pick_value(
            target.source_type,
            source.source_type,
            prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        ) or target.source_type
        resolved_source_ref = _pick_value(
            target.source_ref,
            source.source_ref,
            prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_reading_status = _pick_reading_status(
            target.reading_status,
            source.reading_status,
            prefer=normalized_prefer,
        )

        conn.execute(
            """
            UPDATE papers
            SET title = ?, abstract = ?, authors_json = ?, year = ?, venue = ?, doi = ?, arxiv_id = ?,
                source_type = ?, source_ref = ?, pdf_path = ?, reading_status = ?, text_artifact_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                resolved_title,
                resolved_abstract,
                resolved_authors_json,
                resolved_year,
                resolved_venue,
                resolved_doi,
                resolved_arxiv_id,
                resolved_source_type,
                resolved_source_ref,
                pdf_path,
                resolved_reading_status,
                text_artifact_id,
                timestamp,
                target_paper_id,
            ),
        )

        source_deleted = conn.execute(
            "DELETE FROM papers WHERE id = ?",
            (source_paper_id,),
        ).rowcount > 0
        conn.commit()

        merged_paper = self.papers.get_paper(target_paper_id)
        return {
            "target_paper_id": target_paper_id,
            "source_paper_id": source_paper_id,
            "prefer": normalized_prefer,
            "source_deleted": source_deleted,
            "paper": _paper_payload(merged_paper),
            "moves": {
                "claims": moved_claims,
                "methods": moved_methods,
                "datasets": moved_datasets,
                "tasks": moved_tasks,
                "notes": moved_notes,
                "edge_evidence": moved_edge_evidence,
                "edge_source_nodes": moved_edge_sources,
                "edge_target_nodes": moved_edge_targets,
                "project_links_repointed": moved_project_links,
                "project_links_deduped": deduped_project_links,
                "hypothesis_links_repointed": moved_hypothesis_links,
                "hypothesis_links_deduped": deduped_hypothesis_links,
                "tags_added": tags_added,
                "source_tags_removed": source_tags_removed,
                "artifacts_moved": artifact_summary["moved"],
                "artifacts_replaced": artifact_summary["replaced"],
                "artifacts_deleted": artifact_summary["deleted"],
                "edges_deduped": deduped_edges,
            },
        }

    def add_concept_alias(self, concept_id: str, alias: str) -> dict:
        concept = self.concepts.add_aliases(concept_id, [alias])
        return {
            "concept_id": concept.id,
            "name": concept.name,
            "aliases": json.loads(concept.aliases_json or "[]"),
        }

    def merge_concepts(self, source_id: str, target_id: str) -> dict:
        if source_id == target_id:
            raise ValueError("source_id and target_id must be different")
        return self.concepts.merge_into(source_id, target_id)

    def find_duplicate_concepts(self, threshold: float = 0.75, limit: int = 20) -> list[dict]:
        return self.concepts.find_duplicate_candidates(threshold=threshold, limit=limit)

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
                    payload = summarize_paper_from_graph(
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

    def workspace_stats(self) -> dict:
        """Return workspace-level inventory and coverage statistics."""
        conn = self.papers.conn

        def scalar_count(query: str, params: tuple = ()) -> int:
            row = conn.execute(query, params).fetchone()
            return int(row[0]) if row is not None and row[0] is not None else 0

        def grouped_counts(query: str, params: tuple = ()) -> dict[str, int]:
            rows = conn.execute(query, params).fetchall()
            payload: dict[str, int] = {}
            for row in rows:
                key = str(row[0] or "unknown")
                payload[key] = int(row[1])
            return payload

        paper_count = scalar_count("SELECT COUNT(*) FROM papers")
        papers_with_local_pdf_count = scalar_count(
            "SELECT COUNT(*) FROM papers WHERE pdf_path IS NOT NULL AND TRIM(pdf_path) <> ''"
        )
        source_pdf_artifact_count = scalar_count(
            "SELECT COUNT(*) FROM artifacts WHERE artifact_type = ?",
            ("source_pdf",),
        )
        source_type_counts = grouped_counts(
            """
            SELECT COALESCE(source_type, 'unknown') AS source_type, COUNT(*) AS count
            FROM papers
            GROUP BY source_type
            ORDER BY count DESC, source_type ASC
            """
        )
        artifact_type_counts = grouped_counts(
            """
            SELECT COALESCE(artifact_type, 'unknown') AS artifact_type, COUNT(*) AS count
            FROM artifacts
            GROUP BY artifact_type
            ORDER BY count DESC, artifact_type ASC
            """
        )
        task_status_counts = grouped_counts(
            """
            SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS count
            FROM tasks
            GROUP BY status
            ORDER BY count DESC, status ASC
            """
        )

        quality = self.extraction_quality_report()
        zero_claim_count = len(quality.get("zero_claim_papers", []))
        zero_claim_rate = (zero_claim_count / paper_count) if paper_count else 0.0

        return {
            "papers": {
                "tracked_count": paper_count,
                "with_local_pdf_count": papers_with_local_pdf_count,
                "without_local_pdf_count": max(paper_count - papers_with_local_pdf_count, 0),
                "source_pdf_artifact_count": source_pdf_artifact_count,
                "source_type_counts": source_type_counts,
                "tag_count": scalar_count("SELECT COUNT(*) FROM paper_tags"),
                "tag_distribution": self.papers.list_tag_counts(),
            },
            "objects": {
                "claim_count": scalar_count("SELECT COUNT(*) FROM claims"),
                "concept_count": scalar_count("SELECT COUNT(*) FROM concepts"),
                "method_count": scalar_count("SELECT COUNT(*) FROM methods"),
                "dataset_count": scalar_count("SELECT COUNT(*) FROM datasets"),
                "edge_count": scalar_count("SELECT COUNT(*) FROM edges"),
                "embedding_count": scalar_count("SELECT COUNT(*) FROM embeddings"),
                "note_count": scalar_count("SELECT COUNT(*) FROM notes"),
            },
            "artifacts": {
                "total_count": scalar_count("SELECT COUNT(*) FROM artifacts"),
                "by_type": artifact_type_counts,
            },
            "tasks": {
                "total_count": scalar_count("SELECT COUNT(*) FROM tasks"),
                "by_status": task_status_counts,
            },
            "projects": {
                "project_count": scalar_count("SELECT COUNT(*) FROM research_projects"),
                "project_link_count": scalar_count("SELECT COUNT(*) FROM project_links"),
                "hypothesis_count": scalar_count("SELECT COUNT(*) FROM hypotheses"),
                "hypothesis_evidence_link_count": scalar_count("SELECT COUNT(*) FROM edges WHERE source_type = 'hypothesis'"),
            },
            "quality": {
                "total_claims": int(quality.get("total_claims", 0)),
                "papers_with_zero_claim_count": zero_claim_count,
                "zero_claim_rate": round(zero_claim_rate, 4),
                "claims_per_paper": quality.get("claims_per_paper", {}),
                "predicate_distribution": quality.get("predicate_distribution", {}),
                "extraction_mode_distribution": quality.get("extraction_mode_distribution", {}),
            },
        }

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
            "per_paper": per_paper,
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
            if link.relation_type == "supports":
                support_count += 1
            elif link.relation_type == "contradicts":
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

    def build_hypothesis_evolution_bucketed(self, hypothesis_id: str, bucket_size: str = "yearly") -> dict:
        """Build a time-bucketed view of hypothesis evidence by paper year.

        Groups each evidence link by the publication year of the linked paper
        (or claim's paper) and computes support/contradiction counts per bucket.
        No snapshots are persisted — this is a read-only aggregation.
        """
        hypothesis = self.hypotheses.get_hypothesis(hypothesis_id)
        evidence_links = self.hypotheses.list_evidence_links_for_hypothesis(hypothesis_id)

        # Group evidence links by paper year
        buckets: dict[str, dict] = {}
        for link in evidence_links:
            year_key = "unknown"
            try:
                if link.object_type == "claim":
                    claim = self.claims.get_claim(link.object_id)
                    paper = self.papers.get_paper(claim.paper_id)
                elif link.object_type == "paper":
                    paper = self.papers.get_paper(link.object_id)
                else:
                    paper = None
                if paper and paper.year:
                    year_key = str(paper.year)
            except (KeyError, Exception):
                pass

            if year_key not in buckets:
                buckets[year_key] = {"support": 0, "contradiction": 0, "neutral": 0, "links": []}
            bucket = buckets[year_key]
            if link.relation_type == "supports":
                bucket["support"] += 1
            elif link.relation_type == "contradicts":
                bucket["contradiction"] += 1
            else:
                bucket["neutral"] += 1
            bucket["links"].append({
                "object_type": link.object_type,
                "object_id": link.object_id,
                "relation_type": link.relation_type,
            })

        result_buckets = []
        for key in sorted(buckets):
            b = buckets[key]
            total = b["support"] + b["contradiction"]
            consensus_score = b["support"] / max(1, total)
            controversy_score = min(b["support"], b["contradiction"]) / max(1, total)
            if total == 0:
                trend = "no_evidence"
            elif b["contradiction"] == 0:
                trend = "strengthening"
            elif b["support"] == 0:
                trend = "weakening"
            elif b["support"] > b["contradiction"] * 2:
                trend = "strengthening"
            elif b["contradiction"] > b["support"] * 2:
                trend = "weakening"
            else:
                trend = "contested"
            result_buckets.append({
                "time_bucket": key,
                "support_count": b["support"],
                "contradiction_count": b["contradiction"],
                "neutral_count": b["neutral"],
                "total_evidence": b["support"] + b["contradiction"] + b["neutral"],
                "consensus_score": round(consensus_score, 4),
                "controversy_score": round(controversy_score, 4),
                "trend": trend,
                "links": b["links"],
            })

        return {
            "hypothesis": _hypothesis_payload(hypothesis),
            "bucket_size": bucket_size,
            "buckets": result_buckets,
        }

    def project_evolution_timeline(self, project_id: str) -> dict:
        """Aggregate hypothesis evidence by year across all hypotheses in a project.

        For each year bucket, returns the total support, contradiction, and
        neutral evidence counts summed across all project hypotheses. Provides a
        project-level time-series view of how the evidence base evolved.
        """
        project = self.projects.get_project(project_id)
        hypotheses = self.hypotheses.list_hypotheses_for_project(project_id)

        # Aggregate year → counts across all hypotheses
        year_totals: dict[str, dict] = {}
        hypothesis_summaries = []

        for h in hypotheses:
            h_bucketed = self.build_hypothesis_evolution_bucketed(h.id)
            hypothesis_summaries.append({
                "hypothesis_id": h.id,
                "text": h.text,
                "bucket_count": len(h_bucketed["buckets"]),
            })
            for bucket in h_bucketed["buckets"]:
                key = bucket["time_bucket"]
                if key not in year_totals:
                    year_totals[key] = {
                        "support": 0,
                        "contradiction": 0,
                        "neutral": 0,
                        "hypothesis_ids": [],
                    }
                year_totals[key]["support"] += bucket["support_count"]
                year_totals[key]["contradiction"] += bucket["contradiction_count"]
                year_totals[key]["neutral"] += bucket["neutral_count"]
                if h.id not in year_totals[key]["hypothesis_ids"]:
                    year_totals[key]["hypothesis_ids"].append(h.id)

        timeline = []
        for key in sorted(year_totals):
            t = year_totals[key]
            total = t["support"] + t["contradiction"]
            consensus_score = t["support"] / max(1, total)
            controversy_score = min(t["support"], t["contradiction"]) / max(1, total)
            timeline.append({
                "time_bucket": key,
                "support_count": t["support"],
                "contradiction_count": t["contradiction"],
                "neutral_count": t["neutral"],
                "hypothesis_count": len(t["hypothesis_ids"]),
                "hypothesis_ids": t["hypothesis_ids"],
                "consensus_score": round(consensus_score, 4),
                "controversy_score": round(controversy_score, 4),
            })

        return {
            "project": {"id": project.id, "name": project.name},
            "timeline": timeline,
            "hypotheses": hypothesis_summaries,
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
        """List conflict clusters for a concept with members (enriched with claim text and paper info)."""
        if self.conflict_clusters is None:
            return {"error": "conflict cluster repository not available", "clusters": []}

        concept = self.concepts.get_concept(concept_id)
        clusters = self.conflict_clusters.list_clusters_for_concept(concept_id)
        result = []
        for cluster in clusters:
            members = self.conflict_clusters.list_members_for_cluster(cluster.id)
            enriched_members = []
            for m in members:
                member_entry = {
                    "id": m.id,
                    "claim_id": m.claim_id,
                    "role": m.role,
                    "stance": m.stance,
                    "confidence": m.confidence,
                }
                try:
                    claim = self.claims.get_claim(m.claim_id)
                    paper = self.papers.get_paper(claim.paper_id)
                    member_entry["claim_text"] = claim.text
                    member_entry["claim_predicate"] = claim.predicate
                    member_entry["claim_confidence"] = claim.confidence
                    member_entry["paper_id"] = claim.paper_id
                    member_entry["paper_title"] = paper.title
                    member_entry["paper_year"] = paper.year
                except (KeyError, Exception):
                    pass
                enriched_members.append(member_entry)
            result.append({
                "id": cluster.id,
                "topic_label": cluster.topic_label,
                "status": cluster.status,
                "members": enriched_members,
                "created_at": cluster.created_at,
            })
        return {
            "concept": {"id": concept.id, "name": concept.name},
            "clusters": result,
        }

    def conflict_graph(self, concept_id: str) -> dict:
        """Return the full contradiction graph for a concept as nodes and edges.

        Nodes are claims (with text, paper info, confidence). Edges are all
        ``contradicts`` relations between claims that share this concept. Useful
        for analysing controversy structure without having to look up each claim
        separately.
        """
        concept = self.concepts.get_concept(concept_id)
        claims = self.claims.list_claims_for_concept(concept_id)
        claim_ids = {c.id for c in claims}

        # Build adjacency and collect edges
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        seen_edges: set[frozenset] = set()

        for claim in claims:
            for edge in self.edges.list_claim_relation_edges(claim.id, relation_types=["contradicts"]):
                src, tgt = edge.source_id, edge.target_id
                if src not in claim_ids or tgt not in claim_ids:
                    continue
                pair = frozenset((src, tgt))
                if pair in seen_edges:
                    continue
                seen_edges.add(pair)
                edges.append({
                    "source_id": src,
                    "target_id": tgt,
                    "relation_type": edge.relation_type,
                    "confidence": edge.confidence,
                    "created_by": edge.created_by,
                })
                for cid in (src, tgt):
                    if cid not in nodes:
                        nodes[cid] = cid  # placeholder

        # Resolve node details only for claims that participate in edges
        resolved_nodes = []
        for cid in nodes:
            try:
                claim = self.claims.get_claim(cid)
                paper = self.papers.get_paper(claim.paper_id)
                subject_name = None
                if claim.subject_concept_id:
                    try:
                        subject_name = self.concepts.get_concept(claim.subject_concept_id).name
                    except KeyError:
                        pass
                resolved_nodes.append({
                    "id": cid,
                    "text": claim.text,
                    "predicate": claim.predicate,
                    "subject": subject_name,
                    "object": claim.object_text,
                    "confidence": claim.confidence,
                    "paper_id": claim.paper_id,
                    "paper_title": paper.title,
                    "paper_year": paper.year,
                })
            except (KeyError, Exception):
                resolved_nodes.append({"id": cid})

        # Attach cluster membership if available
        cluster_membership: dict[str, dict] = {}
        if self.conflict_clusters is not None:
            for cluster in self.conflict_clusters.list_clusters_for_concept(concept_id):
                for m in self.conflict_clusters.list_members_for_cluster(cluster.id):
                    cluster_membership[m.claim_id] = {
                        "cluster_id": cluster.id,
                        "stance": m.stance,
                        "role": m.role,
                    }
        for node in resolved_nodes:
            if node["id"] in cluster_membership:
                node["cluster"] = cluster_membership[node["id"]]

        return {
            "concept": {"id": concept.id, "name": concept.name},
            "node_count": len(resolved_nodes),
            "edge_count": len(edges),
            "nodes": resolved_nodes,
            "edges": edges,
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

            # Conflict cluster membership bonus — claims in an active cluster
            # are more important to review because they anchor a known controversy
            cluster_member = False
            if self.conflict_clusters is not None:
                try:
                    source_claim = self.claims.get_claim(candidate.source_claim_id)
                    for cid in [source_claim.subject_concept_id, source_claim.object_concept_id]:
                        if cid and self.conflict_clusters.list_clusters_for_concept(cid):
                            # Check if either claim is an actual cluster member
                            for cluster in self.conflict_clusters.list_clusters_for_concept(cid):
                                member_ids = {m.claim_id for m in self.conflict_clusters.list_members_for_cluster(cluster.id)}
                                if candidate.source_claim_id in member_ids or candidate.target_claim_id in member_ids:
                                    cluster_member = True
                                    break
                        if cluster_member:
                            break
                except (KeyError, Exception):
                    pass

            priority_score = (
                score * 0.25
                + controversy * 0.25
                + (1.0 if hypothesis_relevant else 0.0) * 0.25
                + recency * 0.15
                + (1.0 if cluster_member else 0.0) * 0.1
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
                    "cluster_member": cluster_member,
                },
            })

        priorities.sort(key=lambda p: p["priority_score"], reverse=True)
        return {"priorities": priorities, "count": len(priorities)}

    def compute_open_questions(self, scope_type: str = "concept", scope_id: str | None = None) -> dict:
        """Identify evidence-sparse controversies and under-explored areas.

        Detects five signal types:
        - ``evidence_sparse_controversy``: high controversy score with few claims
        - ``trend_shift``: concept consensus changed significantly across snapshots
        - ``unsupported_hypothesis``: a project hypothesis has no supporting evidence
        - ``unreviewed_conflict_cluster``: conflict cluster with no reviewed member relations
        - ``hypothesis_concept_divergence``: hypothesis trend contradicts concept timeline trend
        """
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

        # Build concept trend index for divergence detection below
        concept_trend: dict[str, str] = {}

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
                    concept_trend[cid] = direction
                    questions.append({
                        "concept_id": cid,
                        "concept_name": concept.name,
                        "type": "trend_shift",
                        "consensus_shift": round(shift, 4),
                        "direction": direction,
                        "description": f"'{concept.name}' shows {direction} (shift={shift:.2f}) — worth investigating.",
                    })
                else:
                    concept_trend[cid] = "stable"
            else:
                latest_cs = latest.consensus_score or 0.5
                concept_trend[cid] = "strengthening" if latest_cs >= 0.6 else "weakening" if latest_cs <= 0.4 else "stable"

        # Signal: unreviewed conflict clusters — clusters where no member claim
        # has any reviewed (promoted) relation edge. These clusters are "stuck"
        # and represent unresolved controversies awaiting first review.
        if self.conflict_clusters is not None:
            for cid in concept_ids:
                try:
                    concept = self.concepts.get_concept(cid)
                except KeyError:
                    continue
                clusters = self.conflict_clusters.list_clusters_for_concept(cid)
                for cluster in clusters:
                    members = self.conflict_clusters.list_members_for_cluster(cluster.id)
                    has_reviewed = False
                    for m in members:
                        # Check if this claim has any reviewed (promoted) edges
                        edges = self.edges.list_claim_relation_edges(m.claim_id)
                        if any(e.created_by and "review" in e.created_by for e in edges):
                            has_reviewed = True
                            break
                    if not has_reviewed and len(members) >= 2:
                        questions.append({
                            "concept_id": cid,
                            "concept_name": concept.name,
                            "cluster_id": cluster.id,
                            "type": "unreviewed_conflict_cluster",
                            "member_count": len(members),
                            "description": f"Conflict cluster for '{concept.name}' has {len(members)} members but no reviewed relations — review is blocked.",
                        })

        # Signal: unsupported hypotheses — hypotheses whose evidence_summary
        # shows no supporting links yet (trend == "no_evidence" or support==0).
        try:
            project_ids_to_check: list[str] = []
            if scope_id and scope_type == "project":
                project_ids_to_check = [scope_id]
            else:
                project_ids_to_check = [p.id for p in self.projects.list_projects()]

            for project_id in project_ids_to_check:
                for h in self.hypotheses.list_hypotheses_for_project(project_id):
                    evo = self.build_hypothesis_evolution(h.id)
                    ev = evo["evidence_summary"]
                    if ev["total"] == 0 or ev["support_count"] == 0:
                        questions.append({
                            "hypothesis_id": h.id,
                            "hypothesis_text": h.text,
                            "project_id": project_id,
                            "type": "unsupported_hypothesis",
                            "evidence_total": ev["total"],
                            "description": f"Hypothesis '{h.text[:80]}' has no supporting evidence — needs claim-level evidence links.",
                        })
        except Exception:
            pass

        # Signal: hypothesis_concept_divergence — a hypothesis is strengthening
        # but its subject concept's timeline shows weakening consensus (or vice
        # versa), indicating a potential inconsistency worth investigating.
        try:
            project_ids_to_check2: list[str] = []
            if scope_id and scope_type == "project":
                project_ids_to_check2 = [scope_id]
            else:
                project_ids_to_check2 = [p.id for p in self.projects.list_projects()]

            for project_id in project_ids_to_check2:
                for h in self.hypotheses.list_hypotheses_for_project(project_id):
                    evo = self.build_hypothesis_evolution(h.id)
                    h_trend = evo["trend"]
                    if h_trend not in ("strengthening", "weakening"):
                        continue
                    # Check if any concept linked to this hypothesis has a diverging trend
                    for link in self.hypotheses.list_evidence_links_for_hypothesis(h.id):
                        if link.object_type != "claim":
                            continue
                        try:
                            claim = self.claims.get_claim(link.object_id)
                        except KeyError:
                            continue
                        for concept_id in [claim.subject_concept_id, claim.object_concept_id]:
                            if not concept_id or concept_id not in concept_trend:
                                continue
                            c_trend = concept_trend[concept_id]
                            diverges = (
                                (h_trend == "strengthening" and "weakening" in c_trend)
                                or (h_trend == "weakening" and "strengthening" in c_trend)
                            )
                            if diverges:
                                try:
                                    concept = self.concepts.get_concept(concept_id)
                                    concept_name = concept.name
                                except KeyError:
                                    concept_name = concept_id
                                questions.append({
                                    "hypothesis_id": h.id,
                                    "hypothesis_text": h.text,
                                    "concept_id": concept_id,
                                    "concept_name": concept_name,
                                    "type": "hypothesis_concept_divergence",
                                    "hypothesis_trend": h_trend,
                                    "concept_trend": c_trend,
                                    "description": (
                                        f"Hypothesis is '{h_trend}' but concept '{concept_name}' shows '{c_trend}' — "
                                        "the hypothesis may be based on stale or inconsistent evidence."
                                    ),
                                })
                                break  # one divergence per hypothesis is enough
        except Exception:
            pass

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


def _pick_value(target_value, source_value, *, prefer: str, is_missing) -> object:
    target_missing = is_missing(target_value)
    source_missing = is_missing(source_value)
    if prefer == "source":
        if not source_missing:
            return source_value
        return target_value
    if not target_missing:
        return target_value
    return source_value


def _authors_json_missing(value: str | None) -> bool:
    if value is None:
        return True
    text = value.strip()
    if not text:
        return True
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    if isinstance(parsed, list):
        return len(parsed) == 0
    return False


def _pick_reading_status(target_status: str | None, source_status: str | None, *, prefer: str) -> str:
    target = (target_status or "unread").strip() or "unread"
    source = (source_status or "unread").strip() or "unread"
    if prefer == "source":
        if source != "unread":
            return source
        return target
    if target != "unread":
        return target
    return source


def _normalized_optional_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalized_title_key(title: str | None) -> str | None:
    if title is None:
        return None
    collapsed = re.sub(r"\s+", " ", title.strip().lower())
    normalized = re.sub(r"[^a-z0-9]+", " ", collapsed)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _delete_rows_by_ids(conn, table: str, ids: list[str]) -> int:
    if not ids:
        return 0
    placeholders = ", ".join("?" for _ in ids)
    return conn.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", tuple(ids)).rowcount


def _latest_artifact_for_type(conn, paper_id: str, artifact_type: str):
    return conn.execute(
        """
        SELECT *
        FROM artifacts
        WHERE paper_id = ? AND artifact_type = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (paper_id, artifact_type),
    ).fetchone()


def _merge_paper_artifacts(conn, *, target_paper_id: str, source_paper_id: str, prefer: str) -> dict:
    target_rows = conn.execute(
        "SELECT * FROM artifacts WHERE paper_id = ? ORDER BY created_at ASC, id ASC",
        (target_paper_id,),
    ).fetchall()
    source_rows = conn.execute(
        "SELECT * FROM artifacts WHERE paper_id = ? ORDER BY created_at ASC, id ASC",
        (source_paper_id,),
    ).fetchall()
    target_by_type: dict[str, list] = defaultdict(list)
    source_by_type: dict[str, list] = defaultdict(list)
    for row in target_rows:
        target_by_type[row["artifact_type"]].append(row)
    for row in source_rows:
        source_by_type[row["artifact_type"]].append(row)

    moved = 0
    replaced = 0
    deleted = 0
    for artifact_type, source_group in source_by_type.items():
        target_group = target_by_type.get(artifact_type, [])
        if not target_group:
            ids = [row["id"] for row in source_group]
            placeholders = ", ".join("?" for _ in ids)
            moved += conn.execute(
                f"UPDATE artifacts SET paper_id = ? WHERE id IN ({placeholders})",
                (target_paper_id, *ids),
            ).rowcount
            continue

        if prefer == "target":
            deleted += _delete_rows_by_ids(conn, "artifacts", [row["id"] for row in source_group])
            continue

        keep_row = source_group[-1]
        replaced += _delete_rows_by_ids(conn, "artifacts", [row["id"] for row in target_group])
        extra_source_ids = [row["id"] for row in source_group[:-1]]
        deleted += _delete_rows_by_ids(conn, "artifacts", extra_source_ids)
        moved += conn.execute(
            "UPDATE artifacts SET paper_id = ? WHERE id = ?",
            (target_paper_id, keep_row["id"]),
        ).rowcount

    return {"moved": moved, "replaced": replaced, "deleted": deleted}


def _dedupe_project_paper_links(conn, paper_id: str) -> int:
    rows = conn.execute(
        """
        SELECT id, project_id, object_id, object_type, link_type
        FROM project_links
        WHERE object_type = 'paper' AND object_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (paper_id,),
    ).fetchall()
    keep: set[tuple[str, str, str, str]] = set()
    duplicate_ids: list[str] = []
    for row in rows:
        key = (row["project_id"], row["object_id"], row["object_type"], row["link_type"])
        if key in keep:
            duplicate_ids.append(row["id"])
            continue
        keep.add(key)
    return _delete_rows_by_ids(conn, "project_links", duplicate_ids)


def _dedupe_hypothesis_paper_links(conn, paper_id: str) -> int:
    rows = conn.execute(
        """
        SELECT id, source_id, target_id, target_type, relation_type
        FROM edges
        WHERE source_type = 'hypothesis' AND target_type = 'paper' AND target_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (paper_id,),
    ).fetchall()
    keep: set[tuple[str, str, str, str]] = set()
    duplicate_ids: list[str] = []
    for row in rows:
        key = (row["source_id"], row["target_id"], row["target_type"], row["relation_type"])
        if key in keep:
            duplicate_ids.append(row["id"])
            continue
        keep.add(key)
    return _delete_rows_by_ids(conn, "edges", duplicate_ids)


def _dedupe_paper_edges(conn, paper_id: str) -> int:
    rows = conn.execute(
        """
        SELECT id, source_id, source_type, relation_type, target_id, target_type, evidence_paper_id, confidence, metadata_json, created_by
        FROM edges
        WHERE (source_type = 'paper' AND source_id = ?)
           OR (target_type = 'paper' AND target_id = ?)
           OR evidence_paper_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (paper_id, paper_id, paper_id),
    ).fetchall()
    keep: set[tuple] = set()
    duplicate_ids: list[str] = []
    for row in rows:
        key = (
            row["source_id"],
            row["source_type"],
            row["relation_type"],
            row["target_id"],
            row["target_type"],
            row["evidence_paper_id"],
            row["confidence"],
            row["metadata_json"],
            row["created_by"],
        )
        if key in keep:
            duplicate_ids.append(row["id"])
            continue
        keep.add(key)
    return _delete_rows_by_ids(conn, "edges", duplicate_ids)


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
