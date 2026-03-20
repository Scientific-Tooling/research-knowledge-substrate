from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

from rks.domain.models import ArtifactRecord, PaperRecord
from rks.ids import next_id
from rks.utils import utc_now

PAPER_READING_STATUSES = ("unread", "read_later", "reading", "read")


class PaperRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_paper_from_pdf(
        self,
        source_pdf: Path,
        stored_pdf: Path,
        title: Optional[str] = None,
        source_ref: Optional[str] = None,
    ) -> PaperRecord:
        timestamp = utc_now()
        paper_id = next_id(self.conn, "paper")
        artifact_id = next_id(self.conn, "artifact")
        paper_title = title or source_pdf.stem
        effective_source_ref = source_ref or str(source_pdf.resolve())

        self.conn.execute(
            """
            INSERT INTO papers(
                id, title, abstract, authors_json, year, venue, doi, arxiv_id,
                source_type, source_ref, pdf_path, text_artifact_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                paper_title,
                None,
                "[]",
                None,
                None,
                None,
                None,
                "pdf",
                effective_source_ref,
                str(stored_pdf),
                None,
                timestamp,
                timestamp,
            ),
        )
        self.conn.execute(
            """
            INSERT INTO artifacts(
                id, paper_id, artifact_type, path, format, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                paper_id,
                "source_pdf",
                str(stored_pdf),
                "pdf",
                json.dumps({"source_ref": effective_source_ref}, sort_keys=True),
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_paper(paper_id)

    def create_paper_from_reference(
        self,
        title: str,
        abstract: str | None,
        authors: list[str],
        year: int | None,
        venue: str | None,
        doi: str | None,
        arxiv_id: str | None,
        source_type: str,
        source_ref: str,
        pdf_path: str | None,
    ) -> PaperRecord:
        timestamp = utc_now()
        paper_id = next_id(self.conn, "paper")
        self.conn.execute(
            """
            INSERT INTO papers(
                id, title, abstract, authors_json, year, venue, doi, arxiv_id,
                source_type, source_ref, pdf_path, text_artifact_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                title,
                abstract,
                json.dumps(authors, sort_keys=True),
                year,
                venue,
                doi,
                arxiv_id,
                source_type,
                source_ref,
                pdf_path,
                None,
                timestamp,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_paper(paper_id)

    def find_by_doi(self, doi: str) -> PaperRecord | None:
        row = self.conn.execute("SELECT * FROM papers WHERE doi = ? ORDER BY created_at ASC LIMIT 1", (doi,)).fetchone()
        return PaperRecord(**dict(row)) if row is not None else None

    def find_by_arxiv_id(self, arxiv_id: str) -> PaperRecord | None:
        row = self.conn.execute(
            "SELECT * FROM papers WHERE arxiv_id = ? ORDER BY created_at ASC LIMIT 1",
            (arxiv_id,),
        ).fetchone()
        return PaperRecord(**dict(row)) if row is not None else None

    def find_by_title(self, title: str) -> PaperRecord | None:
        row = self.conn.execute(
            "SELECT * FROM papers WHERE title = ? ORDER BY created_at ASC LIMIT 1",
            (title,),
        ).fetchone()
        return PaperRecord(**dict(row)) if row is not None else None

    def create_artifact(
        self,
        paper_id: str,
        artifact_type: str,
        path: Path,
        format_name: str,
        metadata: dict,
    ) -> ArtifactRecord:
        timestamp = utc_now()
        existing = self.conn.execute(
            "SELECT id FROM artifacts WHERE paper_id = ? AND artifact_type = ?",
            (paper_id, artifact_type),
        ).fetchone()
        metadata_json = json.dumps(metadata, sort_keys=True)

        if existing is None:
            artifact_id = next_id(self.conn, "artifact")
            self.conn.execute(
                """
                INSERT INTO artifacts(
                    id, paper_id, artifact_type, path, format, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    paper_id,
                    artifact_type,
                    str(path),
                    format_name,
                    metadata_json,
                    timestamp,
                ),
            )
        else:
            artifact_id = existing["id"]
            self.conn.execute(
                """
                UPDATE artifacts
                SET path = ?, format = ?, metadata_json = ?, created_at = ?
                WHERE id = ?
                """,
                (
                    str(path),
                    format_name,
                    metadata_json,
                    timestamp,
                    artifact_id,
                ),
            )
        self.conn.commit()
        return self.get_artifact(artifact_id)

    def set_text_artifact(self, paper_id: str, artifact_id: str) -> None:
        timestamp = utc_now()
        self.conn.execute(
            "UPDATE papers SET text_artifact_id = ?, updated_at = ? WHERE id = ?",
            (artifact_id, timestamp, paper_id),
        )
        self.conn.commit()

    def attach_source_pdf(self, paper_id: str, stored_pdf: Path, source_ref: str) -> ArtifactRecord:
        timestamp = utc_now()
        self.conn.execute(
            "UPDATE papers SET pdf_path = ?, updated_at = ? WHERE id = ?",
            (str(stored_pdf), timestamp, paper_id),
        )
        self.conn.commit()
        return self.create_artifact(
            paper_id=paper_id,
            artifact_type="source_pdf",
            path=stored_pdf,
            format_name="pdf",
            metadata={"source_ref": source_ref},
        )

    def touch_paper(self, paper_id: str) -> None:
        self.conn.execute(
            "UPDATE papers SET updated_at = ? WHERE id = ?",
            (utc_now(), paper_id),
        )
        self.conn.commit()

    def get_paper(self, paper_id: str) -> PaperRecord:
        row = self.conn.execute(
            "SELECT * FROM papers WHERE id = ?",
            (paper_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Paper not found: {paper_id}")
        return PaperRecord(**dict(row))

    def get_artifacts_for_paper(self, paper_id: str) -> list[ArtifactRecord]:
        rows = self.conn.execute(
            "SELECT * FROM artifacts WHERE paper_id = ? ORDER BY created_at ASC",
            (paper_id,),
        ).fetchall()
        return [ArtifactRecord(**dict(row)) for row in rows]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        row = self.conn.execute(
            "SELECT * FROM artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Artifact not found: {artifact_id}")
        return ArtifactRecord(**dict(row))

    def search_papers(self, query: str) -> list[PaperRecord]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT *
            FROM papers
            WHERE title LIKE ? OR abstract LIKE ? OR source_ref LIKE ?
            ORDER BY updated_at DESC, id DESC
            """,
            (like, like, like),
        ).fetchall()
        return [PaperRecord(**dict(row)) for row in rows]

    def list_papers(self) -> list[PaperRecord]:
        rows = self.conn.execute("SELECT * FROM papers ORDER BY created_at ASC, id ASC").fetchall()
        return [PaperRecord(**dict(row)) for row in rows]

    def count_papers(self, tag: str | None = None) -> int:
        if tag is None:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM papers").fetchone()
        else:
            normalized = self._normalize_tag(tag)
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM papers
                WHERE EXISTS (
                    SELECT 1
                    FROM paper_tags
                    WHERE paper_tags.paper_id = papers.id AND paper_tags.tag = ?
                )
                """,
                (normalized,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def list_recent_papers(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        order: str = "desc",
        tag: str | None = None,
    ) -> list[PaperRecord]:
        if sort_by not in {"created_at", "updated_at"}:
            raise ValueError("sort_by must be one of: created_at, updated_at")
        if order not in {"asc", "desc"}:
            raise ValueError("order must be one of: asc, desc")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        direction = "DESC" if order == "desc" else "ASC"
        query = "SELECT * FROM papers"
        params: list[object] = []
        if tag is not None:
            normalized = self._normalize_tag(tag)
            query += (
                " WHERE EXISTS (SELECT 1 FROM paper_tags WHERE paper_tags.paper_id = papers.id AND paper_tags.tag = ?)"
            )
            params.append(normalized)
        query += f" ORDER BY {sort_by} {direction}, id {direction} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(query, tuple(params)).fetchall()
        return [PaperRecord(**dict(row)) for row in rows]

    def set_reading_status(self, paper_id: str, reading_status: str) -> PaperRecord:
        normalized = self._normalize_reading_status(reading_status)
        self.get_paper(paper_id)
        self.conn.execute(
            "UPDATE papers SET reading_status = ?, updated_at = ? WHERE id = ?",
            (normalized, utc_now(), paper_id),
        )
        self.conn.commit()
        return self.get_paper(paper_id)

    def list_tags_for_paper(self, paper_id: str) -> list[str]:
        self.get_paper(paper_id)
        rows = self.conn.execute(
            "SELECT tag FROM paper_tags WHERE paper_id = ? ORDER BY tag ASC",
            (paper_id,),
        ).fetchall()
        return [str(row["tag"]) for row in rows]

    def add_tag(self, paper_id: str, tag: str) -> bool:
        self.get_paper(paper_id)
        normalized = self._normalize_tag(tag)
        before = self.conn.total_changes
        self.conn.execute(
            "INSERT OR IGNORE INTO paper_tags(paper_id, tag, created_at) VALUES (?, ?, ?)",
            (paper_id, normalized, utc_now()),
        )
        added = self.conn.total_changes > before
        if added:
            self.touch_paper(paper_id)
            return True
        self.conn.commit()
        return False

    def remove_tag(self, paper_id: str, tag: str) -> bool:
        self.get_paper(paper_id)
        normalized = self._normalize_tag(tag)
        before = self.conn.total_changes
        self.conn.execute(
            "DELETE FROM paper_tags WHERE paper_id = ? AND tag = ?",
            (paper_id, normalized),
        )
        deleted = self.conn.total_changes > before
        if deleted:
            self.touch_paper(paper_id)
            return True
        self.conn.commit()
        return False

    def list_tag_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT tag, COUNT(*) AS count
            FROM paper_tags
            GROUP BY tag
            ORDER BY count DESC, tag ASC
            """
        ).fetchall()
        return {str(row["tag"]): int(row["count"]) for row in rows}

    def _normalize_reading_status(self, reading_status: str) -> str:
        normalized = reading_status.strip().lower()
        if normalized not in PAPER_READING_STATUSES:
            supported = ", ".join(PAPER_READING_STATUSES)
            raise ValueError(f"reading_status must be one of: {supported}")
        return normalized

    def _normalize_tag(self, tag: str) -> str:
        normalized = tag.strip().lower()
        if not normalized:
            raise ValueError("tag must not be empty")
        if len(normalized) > 64:
            raise ValueError("tag must be <= 64 characters")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._:-]*", normalized):
            raise ValueError("tag must match [a-z0-9][a-z0-9._:-]*")
        return normalized
