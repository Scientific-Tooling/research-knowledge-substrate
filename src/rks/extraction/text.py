from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rks.config import AppPaths
from rks.domain.models import ArtifactRecord, PaperRecord
from rks.storage import PaperRepository
from rks.utils import ensure_dir, utc_now


def extract_text_for_paper(repo: PaperRepository, paths: AppPaths, paper: PaperRecord) -> ArtifactRecord:
    payload = _build_text_payload(Path(paper.pdf_path) if paper.pdf_path else None)
    return write_text_artifact(repo=repo, paths=paths, paper_id=paper.id, payload=payload)


def extract_text_with_llm(repo: PaperRepository, paths: AppPaths, paper: PaperRecord, provider) -> ArtifactRecord:
    payload = provider.extract_text(build_text_source_input(paper))
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
    normalized_payload["paragraphs"] = [
        paragraph for paragraph in normalized_payload.get("paragraphs", []) if paragraph
    ]
    output_path.write_text(json.dumps(normalized_payload, indent=2), encoding="utf-8")
    artifact = repo.create_artifact(
        paper_id=paper_id,
        artifact_type="extracted_text",
        path=output_path,
        format_name="json",
        metadata={
            "extractor": normalized_payload["extractor"],
            "paragraph_count": len(normalized_payload["paragraphs"]),
            "warnings": normalized_payload["warnings"],
        },
    )
    repo.set_text_artifact(paper_id, artifact.id)
    return artifact


def _build_text_payload(pdf_path: Path | None) -> dict:
    warnings: list[str] = []
    extracted_text = ""
    extractor = "strings_fallback"

    if pdf_path is None or not pdf_path.exists():
        extractor = "unavailable"
        warnings.append("PDF path is missing; no text could be extracted.")
    else:
        try:
            result = subprocess.run(
                ["strings", "-n", "6", str(pdf_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            extracted_text = result.stdout.strip()
            if not extracted_text:
                warnings.append("The strings fallback did not recover readable text from the PDF.")
        except FileNotFoundError:
            extractor = "unavailable"
            warnings.append("The `strings` command is not available in this environment.")
        except subprocess.CalledProcessError as exc:
            extractor = "unavailable"
            warnings.append(f"Text extraction failed with exit code {exc.returncode}.")

    paragraphs = [
        line.strip()
        for line in extracted_text.splitlines()
        if line.strip() and not _looks_like_pdf_scaffolding(line.strip())
    ]
    extracted_text = "\n".join(paragraphs)
    return {
        "created_at": utc_now(),
        "extractor": extractor,
        "source_pdf": str(pdf_path) if pdf_path else None,
        "text": extracted_text,
        "paragraphs": paragraphs,
        "warnings": warnings,
    }


def _looks_like_pdf_scaffolding(line: str) -> bool:
    lowered = line.lower()
    return lowered.startswith("%pdf-") or lowered in {
        "endobj",
        "stream",
        "endstream",
        "xref",
        "trailer",
        "%%eof",
    }
