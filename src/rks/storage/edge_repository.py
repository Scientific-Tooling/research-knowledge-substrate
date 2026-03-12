from __future__ import annotations

import json
import sqlite3

from rks.domain.models import EdgeRecord
from rks.ids import next_id
from rks.utils import utc_now


class EdgeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def clear_graph_for_paper(self, paper_id: str) -> None:
        self.conn.execute("DELETE FROM edges WHERE evidence_paper_id = ?", (paper_id,))
        self.conn.commit()

    def clear_edges_for_paper_relations(self, paper_id: str, relation_types: list[str]) -> None:
        if not relation_types:
            return
        placeholders = ", ".join("?" for _ in relation_types)
        self.conn.execute(
            f"DELETE FROM edges WHERE evidence_paper_id = ? AND relation_type IN ({placeholders})",
            (paper_id, *relation_types),
        )
        self.conn.commit()

    def create_edge(
        self,
        source_id: str,
        source_type: str,
        relation_type: str,
        target_id: str,
        target_type: str,
        evidence_paper_id: str | None,
        confidence: float | None,
        metadata: dict | None,
    ) -> EdgeRecord:
        edge_id = next_id(self.conn, "edge")
        timestamp = utc_now()
        self.conn.execute(
            """
            INSERT INTO edges(
                id, source_id, source_type, relation_type, target_id, target_type,
                evidence_paper_id, confidence, metadata_json, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge_id,
                source_id,
                source_type,
                relation_type,
                target_id,
                target_type,
                evidence_paper_id,
                confidence,
                json.dumps(metadata or {}, sort_keys=True),
                "system:heuristic",
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_edge(edge_id)

    def get_edge(self, edge_id: str) -> EdgeRecord:
        row = self.conn.execute(
            "SELECT * FROM edges WHERE id = ?",
            (edge_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Edge not found: {edge_id}")
        return EdgeRecord(**dict(row))

    def list_edges_for_claim(self, claim_id: str) -> list[EdgeRecord]:
        return self.list_edges_for_object(claim_id)

    def list_edges_for_object(self, object_id: str) -> list[EdgeRecord]:
        rows = self.conn.execute(
            "SELECT * FROM edges WHERE source_id = ? OR target_id = ? ORDER BY created_at ASC, id ASC",
            (object_id, object_id),
        ).fetchall()
        return [EdgeRecord(**dict(row)) for row in rows]

    def list_papers_supporting_claim(self, claim_id: str, paper_repo) -> list:
        rows = self.conn.execute(
            """
            SELECT target_id
            FROM edges
            WHERE source_id = ? AND relation_type = 'supported_by' AND target_type = 'paper'
            ORDER BY target_id ASC
            """,
            (claim_id,),
        ).fetchall()
        return [paper_repo.get_paper(row["target_id"]) for row in rows]
