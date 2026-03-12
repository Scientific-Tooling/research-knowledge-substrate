from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rks.config import AppPaths
from rks.domain.models import ArtifactRecord, PaperRecord
from rks.storage import PaperRepository
from rks.utils import ensure_dir, utc_now


def extract_text_for_paper(repo: PaperRepository, paths: AppPaths, paper: PaperRecord) -> ArtifactRecord:
    paper_dir = ensure_dir(paths.papers_dir / paper.id)
    output_path = paper_dir / "extracted_text.json"
    payload = _build_text_payload(Path(paper.pdf_path) if paper.pdf_path else None)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    artifact = repo.create_artifact(
        paper_id=paper.id,
        artifact_type="extracted_text",
        path=output_path,
        format_name="json",
        metadata={
            "extractor": payload["extractor"],
            "paragraph_count": len(payload["paragraphs"]),
            "warnings": payload["warnings"],
        },
    )
    repo.set_text_artifact(paper.id, artifact.id)
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

    paragraphs = [line.strip() for line in extracted_text.splitlines() if line.strip()]
    return {
        "created_at": utc_now(),
        "extractor": extractor,
        "source_pdf": str(pdf_path) if pdf_path else None,
        "text": extracted_text,
        "paragraphs": paragraphs,
        "warnings": warnings,
    }
