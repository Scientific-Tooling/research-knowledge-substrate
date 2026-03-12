from __future__ import annotations

import json
from pathlib import Path

from rks.config import AppPaths
from rks.extraction.text import write_text_artifact
from rks.storage import PaperRepository
from rks.utils import ensure_dir


def ingest_doi_reference(repo: PaperRepository, paths: AppPaths, doi: str, provider) -> object:
    metadata = provider.fetch(doi)
    return _ingest_reference(
        repo=repo,
        paths=paths,
        source_type="doi",
        source_ref=doi,
        metadata=metadata,
        metadata_format="json",
        metadata_payload=metadata.get("raw", metadata),
    )


def ingest_arxiv_reference(repo: PaperRepository, paths: AppPaths, arxiv_id: str, provider) -> object:
    metadata = provider.fetch(arxiv_id)
    return _ingest_reference(
        repo=repo,
        paths=paths,
        source_type="arxiv",
        source_ref=arxiv_id,
        metadata=metadata,
        metadata_format="xml" if isinstance(metadata.get("raw"), str) else "json",
        metadata_payload=metadata.get("raw", metadata),
    )


def _ingest_reference(
    repo: PaperRepository,
    paths: AppPaths,
    source_type: str,
    source_ref: str,
    metadata: dict,
    metadata_format: str,
    metadata_payload,
):
    paper = repo.create_paper_from_reference(
        title=metadata.get("title") or source_ref,
        abstract=metadata.get("abstract"),
        authors=metadata.get("authors", []),
        year=metadata.get("year"),
        venue=metadata.get("venue"),
        doi=metadata.get("doi"),
        arxiv_id=metadata.get("arxiv_id"),
        source_type=source_type,
        source_ref=source_ref,
        pdf_path=None,
    )

    paper_dir = ensure_dir(paths.papers_dir / paper.id)
    metadata_path = paper_dir / "metadata.json"
    if metadata_format == "xml":
        metadata_path = paper_dir / "metadata.xml"
        metadata_path.write_text(str(metadata_payload), encoding="utf-8")
    else:
        metadata_path.write_text(json.dumps(metadata_payload, indent=2), encoding="utf-8")

    repo.create_artifact(
        paper_id=paper.id,
        artifact_type="metadata",
        path=metadata_path,
        format_name=metadata_format,
        metadata={"source_type": source_type, "source_ref": source_ref},
    )

    if metadata.get("abstract"):
        text_payload = {
            "created_at": None,
            "extractor": f"{source_type}_metadata",
            "source_pdf": None,
            "text": metadata.get("abstract"),
            "paragraphs": [metadata.get("abstract")],
            "warnings": [],
        }
        write_text_artifact(repo=repo, paths=paths, paper_id=paper.id, payload=text_payload)

    return repo.get_paper(paper.id)
