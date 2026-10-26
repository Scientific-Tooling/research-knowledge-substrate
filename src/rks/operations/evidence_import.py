"""Plan and atomically apply selected evidence through one native RKS operation."""

from __future__ import annotations

import json

from rks.operations.evidence_contract import (
    digest,
    note_content,
    source_key,
    validate_bundle,
    verify_document,
)
from rks.operations.paper_source import describe_paper_source
from rks.storage.evidence_repository import EvidenceRepository
from rks.storage.paper_repository import PaperRepository

PLAN_SCHEMA = "rks.evidence-import-plan.v1"


def require_schema(conn) -> None:
    needed = {"external_evidence", "external_evidence_history", "evidence_workspace", "paper_redirects"}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if not needed <= tables:
        raise ValueError("Evidence import requires migration 0014; run rks migrate explicitly first")


def resolve_paper(conn, paper_id: str) -> str:
    seen = set()
    while paper_id not in seen:
        seen.add(paper_id)
        redirect = conn.execute("SELECT target_id FROM paper_redirects WHERE source_id = ?", (paper_id,)).fetchone()
        if redirect is None:
            PaperRepository(conn).get_paper(paper_id)
            return paper_id
        paper_id = redirect[0]
    raise ValueError("Paper merge redirect cycle; repair the workspace before importing")


def _plan(conn, bundle: dict, workspace_id: str) -> dict:
    bound = conn.execute("SELECT workspace_id FROM evidence_workspace WHERE singleton = 1").fetchone()
    if bound is not None and bound[0] != workspace_id:
        raise ValueError(f"This RKS database is bound to evidence workspace {bound[0]!r}")
    paper_id = resolve_paper(conn, bundle["paper_id"])
    repo = EvidenceRepository(conn)
    rows = []
    source_problem = None
    try:
        current_pdf = describe_paper_source(PaperRepository(conn).get_paper(paper_id))["pdf"]
        if current_pdf["sha256"] != bundle["document"]["sha256"]:
            source_problem = "paper_source_changed"
    except (OSError, ValueError):
        source_problem = "paper_source_unavailable"
    for item in bundle["items"]:
        key = source_key(bundle, item)
        existing = repo.get(key)
        reason = None
        action = "addition"
        if existing is not None:
            note = conn.execute("SELECT * FROM notes WHERE id = ?", (existing["note_id"],)).fetchone()
            saved = json.loads(existing["record_json"])
            if note is None or note["target_type"] != "paper" or note["target_id"] != paper_id:
                reason = "imported_note_missing_or_retargeted"
            elif note["content"] != note_content(saved["item"]) or note["created_by"] != "external:apw":
                reason = "imported_note_locally_edited"
            elif existing["revision"] == item["revision"]:
                action = "unchanged"
            else:
                reason = "revision_changed"
        # An exact replay remains possible after source replacement or a merge.
        # New/edited evidence must still match the current paper's PDF.
        if action != "unchanged" and source_problem:
            reason = source_problem
        if reason:
            action = "conflict"
        rows.append({
            "source_key": key, "kind": item["kind"], "id": item["id"], "revision": item["revision"],
            "expected_revision": existing["revision"] if existing else None,
            "note_id": existing["note_id"] if existing else None, "paper_id": paper_id,
            "action": action, "reason": reason,
        })
    return {
        "schema": PLAN_SCHEMA, "workspace_id": workspace_id, "bundle_revision": digest(bundle),
        "applied": False, "items": rows,
        "counts": {name: sum(row["action"] == name for row in rows) for name in ("addition", "unchanged", "conflict")},
    }


def import_evidence(conn, bundle: dict, *, workspace_id: str, plan: dict | None = None,
                    apply: bool = False, accept_updates: bool = False) -> dict:
    """Apply only the exact previewed batch, with optimistic revision checks.

    BEGIN IMMEDIATE serializes competing writers before reading identities or
    allocating note IDs. No called repository method may commit this transaction.
    """
    validate_bundle(bundle, workspace_id)
    verify_document(bundle["document"])
    require_schema(conn)
    if conn.in_transaction:
        raise ValueError("Evidence import must own its transaction")
    if apply and (not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA
                  or plan.get("workspace_id") != workspace_id or plan.get("bundle_revision") != digest(bundle)):
        raise ValueError("Apply requires the dry-run plan for this exact bundle and workspace")
    if accept_updates and not apply:
        raise ValueError("accept_updates is only meaningful when applying a reviewed plan")
    conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
    try:
        report = _plan(conn, bundle, workspace_id)
        if not apply:
            return report
        proposed = plan.get("items")
        if not isinstance(proposed, list) or len(proposed) != len(report["items"]):
            raise ValueError("Invalid plan selection; generate a fresh dry-run plan")
        expected = {row["source_key"]: row for row in proposed}
        if len(expected) != len(proposed) or set(expected) != {row["source_key"] for row in report["items"]}:
            raise ValueError("Plan selection does not match this batch")
        blocked = False
        for row in report["items"]:
            prior = expected[row["source_key"]]
            # A retry after a lost commit response is always a no-op.
            if row["action"] == "unchanged":
                continue
            if (prior.get("expected_revision") != row["expected_revision"]
                    or prior.get("paper_id") != row["paper_id"]
                    or prior.get("revision") != row["revision"]):
                row.update(action="conflict", reason="plan_stale")
            if row["action"] == "conflict" and not (accept_updates and row["reason"] == "revision_changed"):
                blocked = True
        if blocked:
            report["counts"] = {name: sum(row["action"] == name for row in report["items"])
                                for name in ("addition", "unchanged", "conflict")}
            return report
        changes = [row for row in report["items"] if row["action"] != "unchanged"]
        if changes:
            conn.execute("INSERT OR IGNORE INTO evidence_workspace(singleton, workspace_id) VALUES (1, ?)", (workspace_id,))
        repo = EvidenceRepository(conn)
        for row, item in zip(report["items"], bundle["items"], strict=True):
            if row["action"] == "unchanged":
                continue
            record = {key: value for key, value in bundle.items() if key != "items"}
            record["item"] = item
            row["note_id"] = repo.save(source_key=row["source_key"], record=record,
                                       paper_id=row["paper_id"], content=note_content(item))
            row["action"] = "updated" if row["expected_revision"] else "added"
            row["reason"] = None
        conn.commit()
        report["applied"] = True
        report["counts"] = {name: sum(row["action"] == name for row in report["items"])
                            for name in ("added", "updated", "unchanged", "conflict")}
        return report
    finally:
        # Includes exceptions, KeyboardInterrupt, and every early return.
        if conn.in_transaction:
            conn.rollback()
