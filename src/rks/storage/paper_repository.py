from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from rks.domain.models import ArtifactRecord, PaperRecord
from rks.ids import next_id
from rks.utils import utc_now


class PaperRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_paper_from_pdf(
        self,
        source_pdf: Path,
        stored_pdf: Path,
        title: Optional[str] = None,
    ) -> PaperRecord:
        timestamp = utc_now()
        paper_id = next_id(self.conn, "paper")
        artifact_id = next_id(self.conn, "artifact")
        paper_title = title or source_pdf.stem

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
                str(source_pdf.resolve()),
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
                json.dumps({"source_ref": str(source_pdf.resolve())}, sort_keys=True),
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_paper(paper_id)

    def create_artifact(
        self,
        paper_id: str,
        artifact_type: str,
        path: Path,
        format_name: str,
        metadata: dict,
    ) -> ArtifactRecord:
        artifact_id = next_id(self.conn, "artifact")
        timestamp = utc_now()
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
                json.dumps(metadata, sort_keys=True),
                timestamp,
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
