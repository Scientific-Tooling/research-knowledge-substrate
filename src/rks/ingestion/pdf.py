from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from rks.config import AppPaths
from rks.storage import PaperRepository
from rks.utils import ensure_dir


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

    paper_preview_id = _peek_next_paper_id(repo)
    paper_dir = ensure_dir(paths.papers_dir / paper_preview_id)
    stored_pdf = paper_dir / "source.pdf"
    shutil.copy2(source_pdf, stored_pdf)
    return repo.create_paper_from_pdf(source_pdf=source_pdf, stored_pdf=stored_pdf, title=title)


def _peek_next_paper_id(repo: PaperRepository) -> str:
    row = repo.conn.execute(
        "SELECT next_value FROM counters WHERE kind = 'paper'"
    ).fetchone()
    next_value = 1 if row is None else int(row[0])
    return f"p_{next_value:06d}"
