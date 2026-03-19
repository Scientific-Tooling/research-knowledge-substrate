from __future__ import annotations

import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from rks.config import AppPaths
from rks.extraction import extract_text_for_paper
from rks.storage import PaperRepository
from rks.utils import ensure_dir

_DEFAULT_TIMEOUT = 30


def ingest_pdf(
    repo: PaperRepository,
    paths: AppPaths,
    pdf_path: Path,
    title: Optional[str] = None,
):
    source_pdf = pdf_path.expanduser().resolve()
    if not source_pdf.exists():
        raise FileNotFoundError(f"PDF not found: {source_pdf}")
    if not source_pdf.is_file():
        raise ValueError(f"Path is not a file: {source_pdf}")
    if source_pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file: {source_pdf}")

    return _ingest_pdf_file(
        repo=repo,
        paths=paths,
        source_pdf=source_pdf,
        title=title,
    )


def ingest_pdf_url(
    repo: PaperRepository,
    paths: AppPaths,
    url: str,
    title: Optional[str] = None,
    downloader=None,
):
    content = (downloader or _download_binary)(url)
    if not _looks_like_pdf(content):
        raise ValueError(f"URL did not return PDF content: {url}")

    paper_preview_id = _peek_next_paper_id(repo)
    paper_dir = ensure_dir(paths.papers_dir / paper_preview_id)
    stored_pdf = paper_dir / "source.pdf"
    stored_pdf.write_bytes(content)
    return _ingest_pdf_file(
        repo=repo,
        paths=paths,
        source_pdf=stored_pdf,
        title=title or _title_from_url(url),
        source_ref=url,
        copy_source=False,
    )


def _ingest_pdf_file(
    repo: PaperRepository,
    paths: AppPaths,
    source_pdf: Path,
    title: Optional[str],
    source_ref: str | None = None,
    copy_source: bool = True,
):
    paper_preview_id = _peek_next_paper_id(repo)
    paper_dir = ensure_dir(paths.papers_dir / paper_preview_id)
    stored_pdf = paper_dir / "source.pdf"
    if copy_source:
        shutil.copy2(source_pdf, stored_pdf)
    paper = repo.create_paper_from_pdf(
        source_pdf=source_pdf,
        stored_pdf=stored_pdf,
        title=title,
        source_ref=source_ref,
    )
    extract_text_for_paper(repo=repo, paths=paths, paper=paper)
    return repo.get_paper(paper.id)


def _peek_next_paper_id(repo: PaperRepository) -> str:
    row = repo.conn.execute(
        "SELECT next_value FROM counters WHERE kind = 'paper'"
    ).fetchone()
    next_value = 1 if row is None else int(row[0])
    return f"p_{next_value:06d}"


def _download_binary(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "RKS/1.0"})
    with urllib.request.urlopen(request, timeout=_DEFAULT_TIMEOUT) as response:
        return response.read()


def _looks_like_pdf(content: bytes) -> bool:
    return b"%PDF" in content[:1024]


def _title_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    filename = Path(path).name or "remote-paper.pdf"
    if filename.lower().endswith(".pdf"):
        filename = filename[:-4]
    return filename or "remote-paper"
