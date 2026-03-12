from __future__ import annotations

import json
from pathlib import Path

from rks.config import AppPaths
from rks.domain.models import ArtifactRecord, PaperRecord
from rks.extraction.pdf_backend import PDF_EXTRACTOR_VERSION, build_paragraph_records, extract_pdf_text
from rks.storage import PaperRepository
from rks.utils import ensure_dir, utc_now


def extract_text_for_paper(repo: PaperRepository, paths: AppPaths, paper: PaperRecord) -> ArtifactRecord:
    payload = _build_text_payload(Path(paper.pdf_path) if paper.pdf_path else None)
    payload["extraction_mode"] = "heuristic"
    return write_text_artifact(repo=repo, paths=paths, paper_id=paper.id, payload=payload)


def extract_text_with_llm(repo: PaperRepository, paths: AppPaths, paper: PaperRecord, provider) -> ArtifactRecord:
    payload = provider.extract_text(build_text_source_input(paper))
    payload["extraction_mode"] = "llm-api"
    return write_text_artifact(repo=repo, paths=paths, paper_id=paper.id, payload=payload)


def build_text_source_input(paper: PaperRecord) -> dict:
    if paper.pdf_path:
        rough_payload = _build_text_payload(Path(paper.pdf_path))
        return {
            "paper_id": paper.id,
            "source_type": paper.source_type,
            "source_pdf": paper.pdf_path,
            "rough_text": rough_payload["text"],
            "rough_paragraphs": rough_payload["paragraphs"],
            "warnings": rough_payload["warnings"],
        }

    return {
        "paper_id": paper.id,
        "source_type": paper.source_type,
        "source_pdf": None,
        "rough_text": paper.abstract or paper.title,
        "rough_paragraphs": [value for value in (paper.abstract, paper.title) if value],
        "warnings": [],
    }


def write_text_artifact(
    repo: PaperRepository,
    paths: AppPaths,
    paper_id: str,
    payload: dict,
) -> ArtifactRecord:
    paper_dir = ensure_dir(paths.papers_dir / paper_id)
    output_path = paper_dir / "extracted_text.json"
    normalized_payload = dict(payload)
    normalized_payload["created_at"] = normalized_payload.get("created_at") or utc_now()
    normalized_payload["paragraphs"] = [paragraph for paragraph in normalized_payload.get("paragraphs", []) if paragraph]
    normalized_payload["extractor_version"] = normalized_payload.get("extractor_version") or PDF_EXTRACTOR_VERSION
    normalized_payload["extraction_mode"] = normalized_payload.get("extraction_mode") or "heuristic"
    normalized_payload["schema_version"] = normalized_payload.get("schema_version")
    normalized_payload["paragraph_records"] = _normalize_paragraph_records(normalized_payload)
    normalized_payload["lineage"] = {
        "paper_id": paper_id,
        "extractor": normalized_payload["extractor"],
        "extractor_version": normalized_payload["extractor_version"],
        "mode": normalized_payload["extraction_mode"],
        "source_pdf": normalized_payload.get("source_pdf"),
    }
    normalized_payload["text"] = "\n\n".join(
        paragraph_record["text"] for paragraph_record in normalized_payload["paragraph_records"]
    )
    output_path.write_text(json.dumps(normalized_payload, indent=2), encoding="utf-8")
    artifact = repo.create_artifact(
        paper_id=paper_id,
        artifact_type="extracted_text",
        path=output_path,
        format_name="json",
        metadata={
            "extractor": normalized_payload["extractor"],
            "extractor_version": normalized_payload["extractor_version"],
            "mode": normalized_payload["extraction_mode"],
            "schema_version": normalized_payload.get("schema_version"),
            "paragraph_count": len(normalized_payload["paragraph_records"]),
            "text_length": len(normalized_payload["text"]),
            "warnings": normalized_payload["warnings"],
            "lineage": normalized_payload["lineage"],
        },
    )
    repo.set_text_artifact(paper_id, artifact.id)
    _write_sections_artifact(repo=repo, paper_id=paper_id, paper_dir=paper_dir, payload=normalized_payload)
    return artifact


def _build_text_payload(pdf_path: Path | None) -> dict:
    payload = extract_pdf_text(pdf_path)
    return {
        "created_at": utc_now(),
        "extractor": payload["extractor"],
        "extractor_version": payload["extractor_version"],
        "source_pdf": str(pdf_path) if pdf_path else None,
        "text": payload["text"],
        "paragraphs": payload["paragraphs"],
        "paragraph_records": payload["paragraph_records"],
        "warnings": payload["warnings"],
    }


def _write_sections_artifact(repo: PaperRepository, paper_id: str, paper_dir: Path, payload: dict) -> None:
    sections = detect_sections(payload)
    sections_path = paper_dir / "sections.json"
    sections_path.write_text(json.dumps(sections, indent=2), encoding="utf-8")
    repo.create_artifact(
        paper_id=paper_id,
        artifact_type="sections",
        path=sections_path,
        format_name="json",
        metadata={
            "section_count": len(sections["sections"]),
            "extractor": payload.get("extractor"),
            "extractor_version": payload.get("extractor_version"),
            "mode": payload.get("extraction_mode"),
        },
    )


def detect_sections(payload: dict) -> dict:
    paragraph_records = payload.get("paragraph_records") or build_paragraph_records(payload.get("paragraphs", []))
    sections = []
    current_name = "abstract"
    current_paragraphs: list[dict] = []

    for paragraph_record in paragraph_records:
        paragraph = paragraph_record["text"]
        heading = _match_heading(paragraph)
        if heading is not None:
            if current_paragraphs:
                sections.append(_section_record(current_name, current_paragraphs))
            current_name = heading
            current_paragraphs = []
            continue
        current_paragraphs.append(paragraph_record)

    if current_paragraphs:
        sections.append(_section_record(current_name, current_paragraphs))

    if not sections and payload.get("text"):
        fallback_records = build_paragraph_records([payload["text"]])
        sections = [_section_record("abstract", fallback_records)]

    return {
        "extractor": payload.get("extractor"),
        "extractor_version": payload.get("extractor_version"),
        "mode": payload.get("extraction_mode"),
        "sections": sections,
    }


def _match_heading(paragraph: str) -> str | None:
    normalized = paragraph.strip().lower().rstrip(":")
    heading_map = {
        "abstract": "abstract",
        "introduction": "introduction",
        "background": "background",
        "related work": "related_work",
        "method": "method",
        "methods": "method",
        "approach": "method",
        "experiment": "experiments",
        "experiments": "experiments",
        "evaluation": "experiments",
        "results": "results",
        "discussion": "discussion",
        "conclusion": "conclusion",
    }
    return heading_map.get(normalized)


def _normalize_paragraph_records(payload: dict) -> list[dict]:
    paragraph_records = payload.get("paragraph_records")
    if paragraph_records:
        return [
            {
                "index": int(record["index"]),
                "text": record["text"],
                "char_start": int(record["char_start"]),
                "char_end": int(record["char_end"]),
            }
            for record in paragraph_records
            if record.get("text")
        ]
    return build_paragraph_records(payload.get("paragraphs", []))


def _section_record(name: str, paragraph_records: list[dict]) -> dict:
    return {
        "name": name,
        "paragraphs": [record["text"] for record in paragraph_records],
        "paragraph_indexes": [record["index"] for record in paragraph_records],
        "char_start": paragraph_records[0]["char_start"],
        "char_end": paragraph_records[-1]["char_end"],
    }
