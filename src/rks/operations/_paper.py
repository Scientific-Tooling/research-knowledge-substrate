"""Paper management, merge, duplicate detection, stats, and extraction quality."""

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
from rks.operations._helpers import (
    note_payload,
    paper_payload,
    task_payload,
)
from rks.reasoning.summary import summarize_paper_from_graph


class PaperOps:
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
        tasks,
        query,
    ):
        self.papers = papers
        self.claims = claims
        self.concepts = concepts
        self.notes = notes
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.tasks = tasks
        self.query = query

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
            "paper": paper_payload(paper),
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
            "tasks": [task_payload(task) for task in tasks],
        }

    def claim_relations(self, claim_id: str) -> dict:
        return self.query.claim_relations(claim_id)

    def list_paper_notes(self, paper_id: str) -> list[dict]:
        self.papers.get_paper(paper_id)
        notes = self.notes.list_notes_for_target(target_id=paper_id, target_type="paper")
        return [note_payload(note) for note in notes]

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
        return note_payload(note)

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
                payload = paper_payload(paper_by_id[paper_id])
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

        from rks.utils import utc_now

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
            target.title, source.title, prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        ) or target.title
        resolved_abstract = _pick_value(
            target.abstract, source.abstract, prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_authors_json = _pick_value(
            target.authors_json, source.authors_json, prefer=normalized_prefer,
            is_missing=_authors_json_missing,
        ) or target.authors_json
        resolved_year = _pick_value(
            target.year, source.year, prefer=normalized_prefer,
            is_missing=lambda value: value is None,
        )
        resolved_venue = _pick_value(
            target.venue, source.venue, prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_doi = _pick_value(
            target.doi, source.doi, prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_arxiv_id = _pick_value(
            target.arxiv_id, source.arxiv_id, prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_source_type = _pick_value(
            target.source_type, source.source_type, prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        ) or target.source_type
        resolved_source_ref = _pick_value(
            target.source_ref, source.source_ref, prefer=normalized_prefer,
            is_missing=lambda value: value is None or str(value).strip() == "",
        )
        resolved_reading_status = _pick_reading_status(
            target.reading_status, source.reading_status, prefer=normalized_prefer,
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
                resolved_title, resolved_abstract, resolved_authors_json,
                resolved_year, resolved_venue, resolved_doi, resolved_arxiv_id,
                resolved_source_type, resolved_source_ref, pdf_path,
                resolved_reading_status, text_artifact_id, timestamp,
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
            "paper": paper_payload(merged_paper),
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
                        {**action, "status": "completed", "method_count": len(methods), "method_ids": [method.id for method in methods]}
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
                        {**action, "status": "completed", "dataset_count": len(datasets), "dataset_ids": [dataset.id for dataset in datasets]}
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
                        {**action, "status": "completed", "artifact_id": payload["artifact_id"]}
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
    # Stats and extraction quality
    # ------------------------------------------------------------------

    def workspace_stats(self) -> dict:
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


# ------------------------------------------------------------------
# Private module-level helpers (paper-specific)
# ------------------------------------------------------------------


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
            row["source_id"], row["source_type"], row["relation_type"],
            row["target_id"], row["target_type"], row["evidence_paper_id"],
            row["confidence"], row["metadata_json"], row["created_by"],
        )
        if key in keep:
            duplicate_ids.append(row["id"])
            continue
        keep.add(key)
    return _delete_rows_by_ids(conn, "edges", duplicate_ids)


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


def _review_status(query, claims: list) -> dict:
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
        missing.append({"code": "text_artifact_missing", "message": "No extracted text artifact is stored for this paper yet."})
    if not stages["claims"]:
        missing.append({"code": "claims_missing", "message": "No structured claim artifact is stored for this paper yet."})
    if stages["claims"] and not stages["methods"]:
        missing.append({"code": "methods_missing", "message": "Method structure is still missing for this paper."})
    if stages["claims"] and not stages["datasets"]:
        missing.append({"code": "datasets_missing", "message": "Dataset structure is still missing for this paper."})
    if stages["claims"] and not stages["summary"]:
        missing.append({"code": "summary_missing", "message": "No paper summary artifact is stored yet."})
    if not paper.pdf_path and not stages["text"]:
        missing.append({"code": "source_pdf_unavailable", "message": "No local source PDF is attached, so text extraction may be blocked."})
    if review["review_pending"]:
        missing.append({"code": "relation_review_pending", "message": "The paper has inferred claim relations that have not been reviewed yet."})
    return missing


def _status_blockers(paper, stages: dict, tasks: list) -> list[dict]:
    blockers = []
    if not paper.pdf_path and not stages["text"]:
        blockers.append({"severity": "warning", "code": "no_local_source_pdf", "message": "No local PDF or extracted text is available, which blocks local text extraction."})
    for task in tasks:
        if task.status == "failed":
            blockers.append({"severity": "error", "code": "task_failed", "message": f"{task.task_type} failed and should be inspected before continuing.", "task_id": task.id})
        elif task.status in {"queued", "running"}:
            blockers.append({"severity": "info", "code": "task_in_progress", "message": f"{task.task_type} is still {task.status}. Wait for the result or import it when ready.", "task_id": task.id})
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
            guidance.append({"status": "queued", "task_id": task.id, "message": f"{task.task_type} is queued. Wait for the external agent result or import it when ready.", "commands": _task_recovery_commands(task.task_type, task.status, paper.id, task.id)})
        elif task.status == "running":
            guidance.append({"status": "running", "task_id": task.id, "message": f"{task.task_type} is still running. Do not start a duplicate task until the current one resolves.", "commands": _task_recovery_commands(task.task_type, task.status, paper.id, task.id)})
        elif task.status == "failed":
            guidance.append({"status": "failed", "task_id": task.id, "message": f"{task.task_type} failed. Inspect the task detail, then retry or import a corrected result.", "commands": _task_recovery_commands(task.task_type, task.status, paper.id, task.id)})
    if not paper.pdf_path and not stages["text"]:
        guidance.append({"status": "blocked", "message": "Text extraction is blocked until a local PDF or external text result is available.", "commands": [command for command in (_paper_reingest_command(paper),) if command]})
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
