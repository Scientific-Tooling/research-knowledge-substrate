"""Read-only retrieval over explicitly scoped, current imported evidence."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from rks.operations.evidence_contract import (
    NAME,
    note_content,
    source_key,
    validate_bundle,
)
from rks.operations.evidence_import import require_schema, resolve_paper
from rks.storage.evidence_repository import EvidenceRepository
from rks.storage.text_search import (
    normalize_text,
    search_metadata,
    search_records,
    tokenize,
)


@dataclass
class SearchableEvidence:
    id: str
    entry: dict
    fields: list[dict]


def searchable_fields(item: dict) -> list[dict]:
    fields = [{"field": "quote", "role": "source", "text": p["quote"],
               "page": p["page"], "annotation_id": p["annotation_id"]} for p in item["passages"]]
    for key in ("comment",) if item["kind"] == "annotation" else ("title", "markdown"):
        if item["content"][key]:
            fields.append({"field": key, "role": "commentary", "text": item["content"][key]})
    return fields


def search_evidence(conn, query: str, *, workspace_id: str, source_id: str, paper_sources: list[str],
                    review: str = "all", mode: str = "lexical", limit: int = 20, offset: int = 0) -> dict:
    """The caller owns a read transaction. Filter before ranking, including BM25 statistics."""
    if not conn.in_transaction:
        raise ValueError("Evidence search requires a caller-owned read transaction")
    require_schema(conn)
    if not isinstance(query, str) or len(query) > 2000:
        raise ValueError("Search query must be text of at most 2000 characters")
    if not all(isinstance(v, str) and re.fullmatch(NAME, v) for v in (workspace_id, source_id)):
        raise ValueError("Provide explicit workspace and source identities")
    if review not in {"all", "reviewed", "unreviewed"} or mode not in {"lexical", "phrase"}:
        raise ValueError("Unsupported review filter or search mode")
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError("Limit must be 1-100 and offset must be nonnegative")
    if not paper_sources:
        raise ValueError("Select at least one exact paper:sha256 source")
    scope = {}
    for value in paper_sources:
        if not isinstance(value, str) or not re.fullmatch(r"p_[0-9]+:[0-9a-f]{64}", value):
            raise ValueError("Paper source must be paper_id:document_sha256")
        paper_id, sha = value.split(":")
        scope[(paper_id, sha)] = resolve_paper(conn, paper_id)
    bound = conn.execute("SELECT workspace_id FROM evidence_workspace WHERE singleton = 1").fetchone()
    if bound is not None and bound[0] != workspace_id:
        raise ValueError("This database belongs to a different evidence workspace")
    candidates, unavailable = [], []
    for row in EvidenceRepository(conn).current_records():
        record = json.loads(row["record_json"])
        identity = (record["paper_id"], record["document"]["sha256"])
        if (identity not in scope or record["workspace_id"] != workspace_id
                or record["source"]["source_id"] != source_id):
            continue
        item = record["item"]
        validate_bundle({**{k: v for k, v in record.items() if k != "item"}, "items": [item]}, workspace_id)
        if row["source_key"] != source_key(record, item) or row["revision"] != item["revision"]:
            raise ValueError("Stored evidence identity or revision is inconsistent; inspect RKS before searching")
        if review != "all" and item["review"]["status"] != review:
            continue
        reason = None
        if row["target_type"] != "paper" or row["paper_id"] != scope[identity]:
            reason = "imported_note_missing_or_retargeted"
        elif row["created_by"] != "external:apw" or row["note_content"] != note_content(item):
            reason = "imported_note_locally_edited"
        if reason:
            unavailable.append({"source_key": row["source_key"], "note_id": row["note_id"], "reason": reason})
            continue
        entry = {key: row[key] for key in ("source_key", "note_id", "paper_id", "revision", "imported_at")}
        entry["record"] = record
        candidates.append(SearchableEvidence(row["source_key"], entry, searchable_fields(item)))
    ranked = search_records(candidates, query, lambda r: [f["text"] for f in r.fields], mode=mode)
    terms = set(tokenize(query))
    results = []
    for rank, candidate in enumerate(ranked[offset:offset + limit], start=offset + 1):
        matches = []
        for field in candidate.fields:
            matched_terms = sorted(terms.intersection(tokenize(field["text"])))
            matches_query = (normalize_text(query.strip()) in normalize_text(field["text"])) if mode == "phrase" else bool(matched_terms)
            if matches_query:
                matches.append({**field, "matched_terms": matched_terms if mode == "lexical" else []})
        results.append({**candidate.entry, "rank": rank, "matches": matches})
    return {"schema": "rks.evidence-search.v1", "query": query, "workspace_id": workspace_id,
            "source_id": source_id, "paper_sources": sorted(set(paper_sources)), "review": review,
            "retrieval": {**search_metadata(mode), "corpus_scope": "current imported evidence within the explicit source and review filters"},
            "total": len(ranked), "limit": limit, "offset": offset, "has_more": offset + limit < len(ranked),
            "outcome": "empty_query" if not query.strip() or (mode == "lexical" and not terms) else ("matches" if ranked else "no_matches"),
            "results": results, "unavailable_evidence": unavailable}
