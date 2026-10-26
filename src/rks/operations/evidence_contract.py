"""Validation for the independently versioned APW selected-evidence boundary."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

SCHEMA = "scientific-tooling.selected-evidence.v1"
NAME = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def fields(value, expected: str) -> None:
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ValueError(f"Expected exactly these fields: {expected}")


def text(value, *, empty=False) -> None:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError("Expected a non-empty string" if not empty else "Expected a string")


def timestamp(value) -> None:
    text(value)
    if datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("Timestamps must include a timezone")


def sha256(value) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Expected a lowercase SHA-256 digest")


def passage(value) -> None:
    fields(value, "annotation_id page quote anchor rects")
    text(value["annotation_id"])
    if type(value["page"]) is not int or value["page"] < 1:
        raise ValueError("Passage page must be an integer >= 1")
    text(value["quote"], empty=True)
    anchor = value["anchor"]
    if anchor is not None:
        fields(anchor, "quote start end prefix suffix")
        for key in ("quote", "prefix", "suffix"):
            text(anchor[key], empty=True)
        if anchor["quote"] != value["quote"]:
            raise ValueError("Passage quote and text anchor disagree")
        for key in ("start", "end"):
            if anchor[key] is not None and (type(anchor[key]) is not int or anchor[key] < 0):
                raise ValueError("Text anchor offsets must be nonnegative integers or null")
        if anchor["start"] is not None and anchor["end"] is not None and anchor["end"] < anchor["start"]:
            raise ValueError("Text anchor end precedes start")
    if not isinstance(value["rects"], list):
        raise ValueError("Passage rects must be an array")
    for rect in value["rects"]:
        fields(rect, "x y width height")
        if any(type(n) not in (int, float) or not math.isfinite(n) for n in rect.values()):
            raise ValueError("Passage rectangles must be finite numbers")
        if rect["width"] < 0 or rect["height"] < 0:
            raise ValueError("Passage rectangle dimensions must be nonnegative")


def validate_bundle(bundle: dict, workspace_id: str) -> None:
    fields(bundle, "schema workspace_id paper_id source document exported_at items")
    if bundle["schema"] != SCHEMA:
        raise ValueError("Unsupported evidence schema")
    if not re.fullmatch(NAME, workspace_id) or bundle["workspace_id"] != workspace_id:
        raise ValueError("Evidence does not match the explicitly selected workspace_id")
    if not isinstance(bundle["paper_id"], str) or not re.fullmatch(r"p_[0-9]+", bundle["paper_id"]):
        raise ValueError("Invalid RKS paper ID")
    source, document = bundle["source"], bundle["document"]
    fields(source, "system source_id paper_ref session_id")
    fields(document, "path sha256 size_bytes")
    sha256(document["sha256"])
    text(source["source_id"])
    text(source["session_id"])
    expected_ref = f"rks:{workspace_id}:{bundle['paper_id']}:sha256:{document['sha256']}"
    if source["system"] != "apw" or not re.fullmatch(NAME, source["source_id"]) or source["paper_ref"] != expected_ref:
        raise ValueError("APW source identity does not match the paper/document identity")
    text(document["path"])
    if not Path(document["path"]).is_absolute():
        raise ValueError("Evidence PDF path must be absolute")
    if type(document["size_bytes"]) is not int or document["size_bytes"] < 1:
        raise ValueError("Evidence PDF size must be a positive integer")
    timestamp(bundle["exported_at"])
    if not isinstance(bundle["items"], list) or not bundle["items"]:
        raise ValueError("Select at least one evidence item")
    seen = set()
    for item in bundle["items"]:
        fields(item, "kind id content passages content_revision review provenance revision")
        text(item["id"])
        if item["kind"] not in ("annotation", "note"):
            raise ValueError("Evidence must be an annotation or note; deletions are not supported")
        key = (item["kind"], item["id"])
        if key in seen:
            raise ValueError("Duplicate external identity in batch")
        seen.add(key)
        content = item["content"]
        if item["kind"] == "annotation":
            fields(content, "id page type quote anchor comment tags rects createdAt updatedAt")
            if content["type"] not in ("highlight", "underline"):
                raise ValueError("Unknown annotation type")
            text(content["comment"], empty=True)
            if not isinstance(content["tags"], list):
                raise ValueError("Annotation tags must be an array")
            for tag in content["tags"]:
                text(tag)
            expected_passages = [{"annotation_id": content["id"], **{
                key: content[key] for key in ("page", "quote", "anchor", "rects")
            }}]
            if item["passages"] != expected_passages:
                raise ValueError("Annotation passage disagrees with its content")
        else:
            fields(content, "id title markdown linkedAnnotationIds createdAt updatedAt")
            text(content["title"], empty=True)
            text(content["markdown"], empty=True)
            if not isinstance(content["linkedAnnotationIds"], list):
                raise ValueError("Linked annotation IDs must be an array")
            for key in content["linkedAnnotationIds"]:
                text(key)
        if content["id"] != item["id"]:
            raise ValueError("Item ID disagrees with its content")
        timestamp(content["createdAt"])
        timestamp(content["updatedAt"])
        if not isinstance(item["passages"], list):
            raise ValueError("Passages must be an array")
        for value in item["passages"]:
            passage(value)
        if item["kind"] == "note" and [p["annotation_id"] for p in item["passages"]] != content["linkedAnnotationIds"]:
            raise ValueError("Note must preserve every linked passage")
        fields(item["provenance"], "session_id created_at updated_at")
        text(item["provenance"]["session_id"])
        timestamp(item["provenance"]["created_at"])
        timestamp(item["provenance"]["updated_at"])
        basis = {"source_id": source["source_id"], "paper_ref": source["paper_ref"], **{
            key: item[key] for key in ("kind", "id", "content", "passages")
        }}
        if item["content_revision"] != digest(basis):
            raise ValueError("Content revision digest mismatch")
        review = item["review"]
        if review != {"status": "unreviewed"}:
            fields(review, "status reviewer reviewed_at method content_revision statement")
            if review["status"] != "reviewed" or review["method"] != "human":
                raise ValueError("Reviewed evidence requires an explicit human review")
            text(review["reviewer"])
            text(review["statement"])
            timestamp(review["reviewed_at"])
            if review["content_revision"] != item["content_revision"]:
                raise ValueError("Review refers to a different content revision")
        if item["revision"] != digest({key: value for key, value in item.items() if key != "revision"}):
            raise ValueError("Evidence revision digest mismatch")


def verify_document(document: dict) -> None:
    sha = hashlib.sha256()
    size = 0
    with Path(document["path"]).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(block)
            size += len(block)
    if (sha.hexdigest(), size) != (document["sha256"], document["size_bytes"]):
        raise ValueError("Evidence snapshot changed; restore the exact PDF before import")


def source_key(bundle: dict, item: dict) -> str:
    return canonical([bundle["workspace_id"], bundle["source"]["source_id"], bundle["paper_id"],
                      bundle["document"]["sha256"], item["kind"], item["id"]])


def note_content(item: dict) -> str:
    review = item["review"]
    label = "UNREVIEWED APW material" if review["status"] == "unreviewed" else (
        f"APW material reviewed by {review['reviewer']} at {review['reviewed_at']}: {review['statement']}"
    )
    content = item["content"]
    body = content["comment"] if item["kind"] == "annotation" else content["title"] + "\n" + content["markdown"]
    passages = "\n".join(f"Page {p['page']}: {p['quote']}" for p in item["passages"])
    return f"{label}\n{body}\n{passages}".strip()
