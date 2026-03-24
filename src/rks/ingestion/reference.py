from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from rks.config import AppPaths
from rks.extraction import persist_citations_for_paper
from rks.extraction.text import write_text_artifact
from rks.ingestion.pdf import ingest_pdf_url
from rks.storage import EdgeRepository, PaperRepository
from rks.utils import ensure_dir

_DEFAULT_TIMEOUT = 30


def ingest_doi_reference(repo: PaperRepository, paths: AppPaths, doi: str, provider, acquire_pdf: bool = True, downloader=None) -> object:
    metadata = provider.fetch(doi)
    return _ingest_reference(
        repo=repo,
        edge_repo=EdgeRepository(repo.conn),
        paths=paths,
        source_type="doi",
        source_ref=doi,
        metadata=metadata,
        metadata_format="json",
        metadata_payload=metadata.get("raw", metadata),
        acquire_pdf=acquire_pdf,
        downloader=downloader or _download_binary,
    )


def ingest_arxiv_reference(
    repo: PaperRepository,
    paths: AppPaths,
    arxiv_id: str,
    provider,
    acquire_pdf: bool = True,
    downloader=None,
) -> object:
    metadata = provider.fetch(arxiv_id)
    return _ingest_reference(
        repo=repo,
        edge_repo=EdgeRepository(repo.conn),
        paths=paths,
        source_type="arxiv",
        source_ref=arxiv_id,
        metadata=metadata,
        metadata_format="xml" if isinstance(metadata.get("raw"), str) else "json",
        metadata_payload=metadata.get("raw", metadata),
        acquire_pdf=acquire_pdf,
        downloader=downloader or _download_binary,
    )


def ingest_pmid_reference(
    repo: PaperRepository,
    paths: AppPaths,
    pmid: str,
    provider,
    acquire_pdf: bool = True,
    downloader=None,
) -> object:
    metadata = provider.fetch(pmid)
    return _ingest_reference(
        repo=repo,
        edge_repo=EdgeRepository(repo.conn),
        paths=paths,
        source_type="pmid",
        source_ref=pmid,
        metadata=metadata,
        metadata_format="xml" if isinstance(metadata.get("raw"), str) else "json",
        metadata_payload=metadata.get("raw", metadata),
        acquire_pdf=acquire_pdf,
        downloader=downloader or _download_binary,
    )


def ingest_url_reference(
    repo: PaperRepository,
    paths: AppPaths,
    url: str,
    *,
    crossref_provider,
    arxiv_provider,
    pubmed_provider,
    acquire_pdf: bool = True,
    downloader=None,
):
    resolved = resolve_reference_url(url)
    if resolved.kind == "doi":
        return ingest_doi_reference(
            repo=repo,
            paths=paths,
            doi=resolved.value,
            provider=crossref_provider,
            acquire_pdf=acquire_pdf,
            downloader=downloader,
        )
    if resolved.kind == "arxiv":
        return ingest_arxiv_reference(
            repo=repo,
            paths=paths,
            arxiv_id=resolved.value,
            provider=arxiv_provider,
            acquire_pdf=acquire_pdf,
            downloader=downloader,
        )
    if resolved.kind == "pmid":
        return ingest_pmid_reference(
            repo=repo,
            paths=paths,
            pmid=resolved.value,
            provider=pubmed_provider,
            acquire_pdf=acquire_pdf,
            downloader=downloader,
        )
    return ingest_pdf_url(
        repo=repo,
        paths=paths,
        url=resolved.value,
        downloader=downloader,
    )


def _ingest_reference(
    repo: PaperRepository,
    edge_repo: EdgeRepository,
    paths: AppPaths,
    source_type: str,
    source_ref: str,
    metadata: dict,
    metadata_format: str,
    metadata_payload,
    acquire_pdf: bool,
    downloader,
):
    doi = metadata.get("doi")
    arxiv_id = metadata.get("arxiv_id")
    if doi:
        existing = repo.find_by_doi(doi)
        if existing:
            raise ValueError(
                f"A paper with DOI {doi!r} already exists ({existing.id}). "
                f"Use `rks papers update-metadata {existing.id} --doi {doi}` to refresh its metadata."
            )
    if arxiv_id:
        existing = repo.find_by_arxiv_id(arxiv_id)
        if existing:
            raise ValueError(
                f"A paper with arXiv ID {arxiv_id!r} already exists ({existing.id}). "
                f"Use `rks papers update-metadata {existing.id} --arxiv {arxiv_id}` to refresh its metadata."
            )
    existing = repo.find_by_source_ref(source_type, source_ref)
    if existing:
        raise ValueError(
            f"A paper with {source_type} reference {source_ref!r} already exists ({existing.id}). "
            f"Use `rks papers update-metadata {existing.id}` to refresh its metadata."
        )
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

    _persist_source_pdf_acquisition(
        repo=repo,
        paths=paths,
        paper_id=paper.id,
        pdf_candidates=metadata.get("pdf_candidates", []),
        acquire_pdf=acquire_pdf,
        downloader=downloader,
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

    persist_citations_for_paper(
        paths=paths,
        paper_repo=repo,
        edge_repo=edge_repo,
        paper_id=paper.id,
        citations=metadata.get("references", []),
    )

    return repo.get_paper(paper.id)


def _persist_source_pdf_acquisition(
    repo: PaperRepository,
    paths: AppPaths,
    paper_id: str,
    pdf_candidates: list[dict],
    acquire_pdf: bool,
    downloader,
) -> None:
    paper_dir = ensure_dir(paths.papers_dir / paper_id)
    acquisition_path = paper_dir / "source_pdf_acquisition.json"
    attempted = []

    if not acquire_pdf:
        payload = {
            "status": "skipped",
            "reason": "reference_pdf_acquisition_disabled",
            "candidate_count": len(pdf_candidates),
            "attempted": attempted,
        }
        _write_source_pdf_acquisition_artifact(repo, paper_id, acquisition_path, payload)
        return

    if not pdf_candidates:
        payload = {
            "status": "unavailable",
            "reason": "no_pdf_candidates",
            "candidate_count": 0,
            "attempted": attempted,
        }
        _write_source_pdf_acquisition_artifact(repo, paper_id, acquisition_path, payload)
        return

    for candidate in pdf_candidates:
        url = candidate.get("url")
        if not url:
            continue
        try:
            content = downloader(url)
            if not _looks_like_pdf(content):
                raise ValueError("response was not recognized as PDF content")
        except Exception as exc:  # pragma: no cover - exercised via tests with fake downloader
            attempted.append(
                {
                    "url": url,
                    "source": candidate.get("source"),
                    "status": "failed",
                    "error": str(exc),
                }
            )
            continue

        source_pdf_path = paper_dir / "source.pdf"
        source_pdf_path.write_bytes(content)
        repo.attach_source_pdf(paper_id=paper_id, stored_pdf=source_pdf_path, source_ref=url)
        attempted.append(
            {
                "url": url,
                "source": candidate.get("source"),
                "status": "downloaded",
            }
        )
        payload = {
            "status": "downloaded",
            "candidate_count": len(pdf_candidates),
            "downloaded_from": url,
            "attempted": attempted,
        }
        _write_source_pdf_acquisition_artifact(repo, paper_id, acquisition_path, payload)
        return

    payload = {
        "status": "failed",
        "reason": "all_candidates_failed",
        "candidate_count": len(pdf_candidates),
        "attempted": attempted,
    }
    _write_source_pdf_acquisition_artifact(repo, paper_id, acquisition_path, payload)


def _write_source_pdf_acquisition_artifact(
    repo: PaperRepository,
    paper_id: str,
    path: Path,
    payload: dict,
) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    repo.create_artifact(
        paper_id=paper_id,
        artifact_type="source_pdf_acquisition",
        path=path,
        format_name="json",
        metadata=payload,
    )


def _download_binary(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "RKS/1.0"})
    with urllib.request.urlopen(request, timeout=_DEFAULT_TIMEOUT) as response:
        return response.read()


def _looks_like_pdf(content: bytes) -> bool:
    return b"%PDF" in content[:1024]


@dataclass(frozen=True)
class ResolvedReferenceUrl:
    kind: str
    value: str


def resolve_reference_url(url: str) -> ResolvedReferenceUrl:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme for reference ingestion: {url}")

    host = parsed.netloc.lower()
    path = parsed.path or ""

    doi = _extract_doi_from_url(host, path)
    if doi:
        return ResolvedReferenceUrl(kind="doi", value=doi)

    arxiv_id = _extract_arxiv_id_from_url(host, path)
    if arxiv_id:
        return ResolvedReferenceUrl(kind="arxiv", value=arxiv_id)

    pmid = _extract_pmid_from_url(host, path)
    if pmid:
        return ResolvedReferenceUrl(kind="pmid", value=pmid)

    return ResolvedReferenceUrl(kind="pdf", value=url)


def _extract_doi_from_url(host: str, path: str) -> str | None:
    if host not in {"doi.org", "dx.doi.org", "www.doi.org"}:
        return None
    doi = urllib.parse.unquote(path.lstrip("/")).strip()
    return doi or None


def _extract_arxiv_id_from_url(host: str, path: str) -> str | None:
    if host not in {"arxiv.org", "www.arxiv.org"}:
        return None
    match = re.match(r"^/(abs|pdf)/(.+?)(?:\.pdf)?/?$", path, re.IGNORECASE)
    if not match:
        return None
    return urllib.parse.unquote(match.group(2)).strip() or None


def _extract_pmid_from_url(host: str, path: str) -> str | None:
    if host == "pubmed.ncbi.nlm.nih.gov":
        match = re.match(r"^/(\d+)/?$", path)
        return match.group(1) if match else None
    if host in {"ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
        match = re.match(r"^/pubmed/(\d+)/?$", path)
        return match.group(1) if match else None
    return None


# ---------------------------------------------------------------------------
# In-place metadata update
# ---------------------------------------------------------------------------


def _update_metadata_from_reference(
    repo: PaperRepository,
    paths: AppPaths,
    paper_id: str,
    source_type: str,
    source_ref: str,
    metadata: dict,
    metadata_format: str,
    metadata_payload,
) -> object:
    """Fetch fresh metadata and apply it to an existing paper without creating a new record."""
    paper = repo.get_paper(paper_id)
    if paper is None:
        raise ValueError(f"Paper {paper_id!r} not found.")

    repo.update_paper_metadata(
        paper_id=paper_id,
        title=metadata.get("title") or None,
        abstract=metadata.get("abstract") or None,
        authors=metadata.get("authors") or None,
        year=metadata.get("year") or None,
        venue=metadata.get("venue") or None,
        doi=metadata.get("doi") or None,
        arxiv_id=metadata.get("arxiv_id") or None,
    )

    paper_dir = ensure_dir(paths.papers_dir / paper_id)
    if metadata_format == "xml":
        metadata_path = paper_dir / "metadata.xml"
        metadata_path.write_text(str(metadata_payload), encoding="utf-8")
    else:
        metadata_path = paper_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata_payload, indent=2), encoding="utf-8")

    existing_types = {a.artifact_type for a in repo.get_artifacts_for_paper(paper_id)}
    if "metadata" not in existing_types:
        repo.create_artifact(
            paper_id=paper_id,
            artifact_type="metadata",
            path=metadata_path,
            format_name=metadata_format,
            metadata={"source_type": source_type, "source_ref": source_ref},
        )

    return repo.get_paper(paper_id)


def update_doi_metadata(repo: PaperRepository, paths: AppPaths, paper_id: str, doi: str, provider) -> object:
    metadata = provider.fetch(doi)
    return _update_metadata_from_reference(
        repo=repo,
        paths=paths,
        paper_id=paper_id,
        source_type="doi",
        source_ref=doi,
        metadata=metadata,
        metadata_format="json",
        metadata_payload=metadata.get("raw", metadata),
    )


def update_arxiv_metadata(repo: PaperRepository, paths: AppPaths, paper_id: str, arxiv_id: str, provider) -> object:
    metadata = provider.fetch(arxiv_id)
    return _update_metadata_from_reference(
        repo=repo,
        paths=paths,
        paper_id=paper_id,
        source_type="arxiv",
        source_ref=arxiv_id,
        metadata=metadata,
        metadata_format="xml" if isinstance(metadata.get("raw"), str) else "json",
        metadata_payload=metadata.get("raw", metadata),
    )


def update_pmid_metadata(repo: PaperRepository, paths: AppPaths, paper_id: str, pmid: str, provider) -> object:
    metadata = provider.fetch(pmid)
    return _update_metadata_from_reference(
        repo=repo,
        paths=paths,
        paper_id=paper_id,
        source_type="pmid",
        source_ref=pmid,
        metadata=metadata,
        metadata_format="json",
        metadata_payload=metadata.get("raw", metadata),
    )
