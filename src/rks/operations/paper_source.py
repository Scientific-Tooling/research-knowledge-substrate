"""Read-only identification of the local document behind a paper."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rks.domain.models import PaperRecord


def describe_paper_source(paper: PaperRecord) -> dict:
    """Describe the bytes read, without extracting text or changing paper state."""
    if not paper.pdf_path:
        raise ValueError(f"Paper {paper.id} has no local PDF; acquire one before opening it for reading.")
    path = Path(paper.pdf_path).expanduser()
    if not path.is_absolute():
        raise ValueError(f"Paper {paper.id} has a relative PDF path; repair it to an absolute path first.")
    path = path.resolve(strict=True)
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return {
        "schema": "rks.paper-source.v1",
        "paper_id": paper.id,
        "title": paper.title,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "source_type": paper.source_type,
        "source_ref": paper.source_ref,
        "pdf": {"path": str(path), "sha256": digest.hexdigest(), "size_bytes": size},
    }
