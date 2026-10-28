"""Revision-bound comparisons of imported evidence, with explicit human review."""
from __future__ import annotations

import json
import re

from rks.operations.evidence_contract import (
    NAME, digest, fields, note_content, source_key, text, validate_bundle, verify_document,
)
from rks.operations.evidence_import import require_schema as require_evidence, resolve_paper
from rks.storage.comparison_repository import ComparisonRepository
from rks.storage.evidence_repository import EvidenceRepository
from rks.utils import utc_now

SCHEMA = "rks.comparison.v1"


def require_schema(conn):
    require_evidence(conn)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if not {"comparisons", "comparison_versions", "comparison_reviews", "comparison_requests"} <= names:
        raise ValueError("Comparisons require migration 0015; run rks migrate explicitly first")


def validate_scope(conn, workspace_id, source_id, paper_sources):
    require_schema(conn)
    if not all(isinstance(v, str) and re.fullmatch(NAME, v) for v in (workspace_id, source_id)):
        raise ValueError("Explicit workspace and source identities are required")
    if not paper_sources or len(set(paper_sources)) != len(paper_sources):
        raise ValueError("Select unique exact paper sources")
    for value in paper_sources:
        if not isinstance(value, str) or not re.fullmatch(r"p_[0-9]+:[0-9a-f]{64}", value):
            raise ValueError("Paper sources must be paper_id:document_sha256")
        resolve_paper(conn, value.split(":")[0])
    bound = conn.execute("SELECT workspace_id FROM evidence_workspace WHERE singleton = 1").fetchone()
    if bound and bound[0] != workspace_id:
        raise ValueError("This database belongs to another evidence workspace")


def evidence_state(conn, saved, workspace_id, source_id, paper_source, checked):
    """Keep the selected immutable record; report current availability separately."""
    record = saved["record"]
    item = record["item"]
    validate_bundle({**{k: v for k, v in record.items() if k != "item"}, "items": [item]}, workspace_id)
    if (record["source"]["source_id"] != source_id
            or f"{record['paper_id']}:{record['document']['sha256']}" != paper_source
            or saved["source_key"] != source_key(record, item) or saved["revision"] != item["revision"]):
        raise ValueError("Comparison contains inconsistent or out-of-scope evidence")
    current = EvidenceRepository(conn).get(saved["source_key"])
    status = "current"
    if current is None or current["note_id"] != saved["note_id"]:
        status = "evidence_missing"
    elif current["revision"] != saved["revision"]:
        status = "evidence_changed"
    else:
        note = conn.execute("SELECT * FROM notes WHERE id = ?", (saved["note_id"],)).fetchone()
        if (not note or note["target_type"] != "paper"
                or note["target_id"] != resolve_paper(conn, record["paper_id"])
                or note["created_by"] != "external:apw" or note["content"] != note_content(item)):
            status = "note_changed_or_missing"
        elif json.loads(current["record_json"])["item"] != item:
            raise ValueError("Current evidence revision is inconsistent")
    document_key = digest(record["document"])
    if document_key not in checked:
        try:
            verify_document(record["document"])
            checked[document_key] = "available"
        except (OSError, ValueError):
            checked[document_key] = "source_unavailable"
    return {**saved, "status": status, "source_status": checked[document_key]}


def show_comparison(conn, comparison_id, *, workspace_id, source_id, paper_sources, history=False):
    validate_scope(conn, workspace_id, source_id, paper_sources)
    repo = ComparisonRepository(conn)
    row = repo.get(comparison_id)
    definition = json.loads(row["definition_json"])
    if (row["workspace_id"] != workspace_id or row["source_id"] != source_id
            or not set(definition["paper_sources"]) <= set(paper_sources)):
        raise ValueError("Comparison is outside this project's exact source scope")
    version, saved_cells = repo.content(comparison_id)
    reviews, checked, cells = repo.reviews(comparison_id), {}, []
    for paper_source in definition["paper_sources"]:
        for criterion in definition["criteria"]:
            key = f"{paper_source}|{criterion['id']}"
            saved = next((c for c in saved_cells if c["key"] == key), {
                "key": key, "paper_source": paper_source, "criterion_id": criterion["id"], "edit_version": 0,
                "text": "", "conditions": "", "origin": "unspecified", "evidence": [],
            })
            revision = digest(saved)
            evidence = [evidence_state(conn, e, workspace_id, source_id, paper_source, checked) for e in saved["evidence"]]
            stale = any(e["status"] != "current" or e["source_status"] != "available" for e in evidence)
            anchored = any(p["quote"].strip() for e in evidence for p in e["record"]["item"]["passages"])
            support = "gap" if not saved["text"].strip() else ("stale" if stale else ("linked" if anchored else "unsupported"))
            decisions = [r for r in reviews if r["cell_key"] == key]
            latest = decisions[-1] if decisions else None
            review_status = "unreviewed" if latest is None else (
                "stale" if latest["cell_revision"] != revision or stale else latest["decision"])
            cells.append({**saved, "evidence": evidence, "cell_revision": revision, "support_status": support,
                          "review": {"status": review_status, "latest": latest, "history": decisions}})
    result = {"schema": SCHEMA, "id": comparison_id, "workspace_id": workspace_id, "source_id": source_id,
              **definition, "version": version, "created_at": row["created_at"], "cells": cells}
    result["revision"] = digest(result)
    if history:
        result["history"] = repo.history(comparison_id)
    return result


def list_comparisons(conn, *, workspace_id, source_id, paper_sources):
    validate_scope(conn, workspace_id, source_id, paper_sources)
    records = []
    for row in ComparisonRepository(conn).list(workspace_id, source_id):
        definition = json.loads(row["definition_json"])
        if set(definition["paper_sources"]) <= set(paper_sources):
            records.append({"id": row["id"], **definition, "created_at": row["created_at"]})
    return {"schema": "rks.comparison-list.v1", "comparisons": records}


def list_evidence(conn, *, workspace_id, source_id, paper_sources):
    validate_scope(conn, workspace_id, source_id, paper_sources)
    evidence, checked = [], {}
    for row in EvidenceRepository(conn).current_records():
        record = json.loads(row["record_json"])
        identity = f"{record['paper_id']}:{record['document']['sha256']}"
        if identity not in paper_sources or record["workspace_id"] != workspace_id or record["source"]["source_id"] != source_id:
            continue
        entry = {k: row[k] for k in ("note_id", "source_key", "revision")}
        entry["record"] = record
        evidence.append(evidence_state(conn, entry, workspace_id, source_id, identity, checked))
    return {"schema": "rks.comparison-evidence.v1", "evidence": evidence}


def apply_comparison(conn, request, *, workspace_id, source_id, paper_sources):
    """One transaction for CAS, immutable history, review and exact request replay."""
    if conn.in_transaction:
        raise ValueError("Comparison mutations must own their transaction")
    fields(request, "schema request_id action comparison_id expected_revision payload")
    if request["schema"] != "rks.comparison-request.v1" or not re.fullmatch(r"[0-9a-f]{32}", request["request_id"]):
        raise ValueError("Use a versioned comparison request with a unique UUID hex request_id")
    request_hash = digest({"request": request, "workspace_id": workspace_id, "source_id": source_id,
                           "paper_sources": sorted(paper_sources)})
    conn.execute("BEGIN IMMEDIATE")
    try:
        validate_scope(conn, workspace_id, source_id, paper_sources)
        repo = ComparisonRepository(conn)
        replay = repo.receipt(request["request_id"])
        if replay:
            if replay["request_hash"] != request_hash:
                raise ValueError("Request ID was already used for different comparison content")
            return {"replayed": True, "comparison": show_comparison(conn, replay["comparison_id"],
                    workspace_id=workspace_id, source_id=source_id, paper_sources=paper_sources)}
        action, payload = request["action"], request["payload"]
        if action == "create":
            fields(payload, "title question criteria")
            for value in (payload["title"], payload["question"]):
                text(value)
            criteria = payload["criteria"]
            if not isinstance(criteria, list) or not 1 <= len(criteria) <= 20:
                raise ValueError("Define between one and twenty comparison criteria")
            for criterion in criteria:
                text(criterion)
            if len({c.strip().casefold() for c in criteria}) != len(criteria):
                raise ValueError("Comparison criteria must be distinct")
            if request["comparison_id"] is not None or request["expected_revision"] is not None:
                raise ValueError("Creation cannot replace an existing comparison")
            comparison_id = "cmp_" + request["request_id"]
            definition = {"title": payload["title"].strip(), "question": payload["question"].strip(),
                          "criteria": [{"id": f"c{i + 1}", "label": c.strip()} for i, c in enumerate(criteria)],
                          "paper_sources": sorted(paper_sources)}
            conn.execute("INSERT OR IGNORE INTO evidence_workspace VALUES (1, ?)", (workspace_id,))
            repo.create(comparison_id, workspace_id, source_id, definition)
        elif action in {"set", "review"}:
            comparison_id = request["comparison_id"]
            current = show_comparison(conn, comparison_id, workspace_id=workspace_id, source_id=source_id,
                                      paper_sources=paper_sources)
            if request["expected_revision"] != current["revision"]:
                raise ValueError("Comparison changed after inspection; reload it before saving or reviewing")
            expected_fields = ("paper_source criterion_id text conditions origin evidence" if action == "set" else
                               "paper_source criterion_id reviewer scope decision statement")
            fields(payload, expected_fields)
            key = f"{payload['paper_source']}|{payload['criterion_id']}"
            cell = next((c for c in current["cells"] if c["key"] == key), None)
            if cell is None:
                raise ValueError("Choose a paper and criterion from this comparison")
            if action == "set":
                text(payload["text"], empty=True)
                text(payload["conditions"], empty=True)
                if payload["origin"] not in {"human", "agent"}:
                    raise ValueError("Identify the interpretation's origin as human or agent")
                selections = payload["evidence"]
                if not isinstance(selections, list) or len(selections) > 100:
                    raise ValueError("Select at most 100 imported evidence revisions")
                selected, checked = [], {}
                for selection in selections:
                    fields(selection, "note_id revision")
                    row = conn.execute("SELECT * FROM external_evidence WHERE note_id = ?", (selection["note_id"],)).fetchone()
                    if row is None or row["revision"] != selection["revision"]:
                        raise ValueError("Selected evidence changed or is missing; inspect a fresh selection")
                    entry = {k: row[k] for k in ("note_id", "source_key", "revision")}
                    entry["record"] = json.loads(row["record_json"])
                    state = evidence_state(conn, entry, workspace_id, source_id, payload["paper_source"], checked)
                    if state["status"] != "current" or state["source_status"] != "available":
                        raise ValueError("Selected evidence is unavailable or locally edited; restore or reimport it")
                    selected.append(entry)
                if len({e["note_id"] for e in selected}) != len(selected):
                    raise ValueError("Select each evidence item once")
                version, cells = repo.content(comparison_id)
                saved = {k: payload[k] for k in ("paper_source", "criterion_id", "text", "conditions", "origin")}
                saved.update(key=key, edit_version=version + 1, evidence=sorted(selected, key=lambda e: e["source_key"]))
                repo.save(comparison_id, version + 1, [c for c in cells if c["key"] != key] + [saved])
            else:
                for name in ("reviewer", "scope", "statement"):
                    text(payload[name])
                if payload["decision"] not in {"accepted", "needs_changes"}:
                    raise ValueError("Review decision must be accepted or needs_changes")
                if payload["decision"] == "accepted" and cell["support_status"] != "linked":
                    raise ValueError("Only entries with current supporting quotations can be accepted; gaps remain gaps")
                repo.review(comparison_id, {"id": request["request_id"], "cell_key": key,
                    "cell_revision": cell["cell_revision"], "comparison_revision": current["revision"],
                    "evidence_revisions": [{"source_key": e["source_key"], "revision": e["revision"]} for e in cell["evidence"]],
                    "method": "human", "reviewed_at": utc_now(),
                    **{k: payload[k] for k in ("reviewer", "scope", "decision", "statement")}})
        else:
            raise ValueError("Unknown comparison action")
        repo.remember(request["request_id"], request_hash, comparison_id)
        result = show_comparison(conn, comparison_id, workspace_id=workspace_id, source_id=source_id,
                                 paper_sources=paper_sources)
        conn.commit()
        return {"replayed": False, "comparison": result}
    finally:
        if conn.in_transaction:
            conn.rollback()
