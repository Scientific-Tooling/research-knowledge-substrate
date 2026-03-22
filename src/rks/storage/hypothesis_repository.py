from __future__ import annotations

import json
import sqlite3

from rks.domain.models import HypothesisEvidenceLinkRecord, HypothesisRecord
from rks.ids import next_id
from rks.utils import utc_now


class HypothesisRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_hypothesis(
        self,
        *,
        project_id: str,
        text: str,
        status: str,
        confidence: float | None,
        context: dict | None,
        created_by: str,
    ) -> HypothesisRecord:
        timestamp = utc_now()
        hypothesis_id = next_id(self.conn, "hypothesis")
        self.conn.execute(
            """
            INSERT INTO hypotheses(
                id, project_id, text, status, confidence, context_json, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hypothesis_id,
                project_id,
                text,
                status,
                confidence,
                json.dumps(context or {}, sort_keys=True),
                created_by,
                timestamp,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_hypothesis(hypothesis_id)

    def get_hypothesis(self, hypothesis_id: str) -> HypothesisRecord:
        row = self.conn.execute(
            "SELECT * FROM hypotheses WHERE id = ?",
            (hypothesis_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Hypothesis not found: {hypothesis_id}")
        return HypothesisRecord(**dict(row))

    def list_hypotheses_for_project(self, project_id: str) -> list[HypothesisRecord]:
        rows = self.conn.execute(
            "SELECT * FROM hypotheses WHERE project_id = ? ORDER BY created_at ASC, id ASC",
            (project_id,),
        ).fetchall()
        return [HypothesisRecord(**dict(row)) for row in rows]

    def touch_hypothesis(self, hypothesis_id: str) -> None:
        self.conn.execute(
            "UPDATE hypotheses SET updated_at = ? WHERE id = ?",
            (utc_now(), hypothesis_id),
        )
        self.conn.commit()

    def add_evidence_link(
        self,
        *,
        hypothesis_id: str,
        object_id: str,
        object_type: str,
        relation_type: str,
        created_by: str,
        metadata: dict | None = None,
    ) -> HypothesisEvidenceLinkRecord:
        # Idempotent: return existing link if one with the same key already exists.
        existing = self.conn.execute(
            """
            SELECT *
            FROM edges
            WHERE source_id = ? AND source_type = 'hypothesis'
              AND target_id = ? AND target_type = ?
              AND relation_type = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (hypothesis_id, object_id, object_type, relation_type),
        ).fetchone()
        if existing is not None:
            return _edge_row_to_link(existing)

        link_id = next_id(self.conn, "edge")
        timestamp = utc_now()
        self.conn.execute(
            """
            INSERT INTO edges(
                id, source_id, source_type, relation_type,
                target_id, target_type,
                evidence_paper_id, confidence, metadata_json, created_by, created_at
            ) VALUES (?, ?, 'hypothesis', ?, ?, ?, NULL, NULL, ?, ?, ?)
            """,
            (
                link_id,
                hypothesis_id,
                relation_type,
                object_id,
                object_type,
                json.dumps(metadata or {}, sort_keys=True),
                created_by,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_evidence_link(link_id)

    def get_evidence_link(self, link_id: str) -> HypothesisEvidenceLinkRecord:
        row = self.conn.execute(
            "SELECT * FROM edges WHERE id = ? AND source_type = 'hypothesis'",
            (link_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Hypothesis evidence link not found: {link_id}")
        return _edge_row_to_link(row)

    def list_evidence_links_for_hypothesis(self, hypothesis_id: str) -> list[HypothesisEvidenceLinkRecord]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM edges
            WHERE source_id = ? AND source_type = 'hypothesis'
            ORDER BY created_at ASC, id ASC
            """,
            (hypothesis_id,),
        ).fetchall()
        return [_edge_row_to_link(row) for row in rows]


def _edge_row_to_link(row) -> HypothesisEvidenceLinkRecord:
    """Map an edges row (source_type='hypothesis') to HypothesisEvidenceLinkRecord."""
    d = dict(row)
    return HypothesisEvidenceLinkRecord(
        id=d["id"],
        hypothesis_id=d["source_id"],
        object_id=d["target_id"],
        object_type=d["target_type"],
        relation_type=d["relation_type"],
        metadata_json=d.get("metadata_json"),
        created_by=d["created_by"],
        created_at=d["created_at"],
    )
