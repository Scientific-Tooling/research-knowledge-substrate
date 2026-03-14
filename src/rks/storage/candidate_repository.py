from __future__ import annotations

import json
import sqlite3

from rks.domain.models import ClaimRelationCandidateRecord
from rks.ids import next_id
from rks.utils import utc_now

CANDIDATE_ALGORITHM_VERSION = "1.0"


class CandidateRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_candidate(
        self,
        source_claim_id: str,
        target_claim_id: str,
        relation_type: str,
        score: float | None = None,
        algorithm_version: str = CANDIDATE_ALGORITHM_VERSION,
        metadata: dict | None = None,
    ) -> ClaimRelationCandidateRecord:
        timestamp = utc_now()
        existing = self._find_existing(source_claim_id, target_claim_id, relation_type)
        if existing is not None:
            self.conn.execute(
                """
                UPDATE claim_relation_candidates
                SET score = ?, algorithm_version = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (score, algorithm_version, json.dumps(metadata or {}, sort_keys=True), timestamp, existing.id),
            )
            self.conn.commit()
            return self.get_candidate(existing.id)

        candidate_id = next_id(self.conn, "claim_relation_candidate")
        self.conn.execute(
            """
            INSERT INTO claim_relation_candidates(
                id, source_claim_id, target_claim_id, relation_type,
                score, algorithm_version, status, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                source_claim_id,
                target_claim_id,
                relation_type,
                score,
                algorithm_version,
                "pending",
                json.dumps(metadata or {}, sort_keys=True),
                timestamp,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_candidate(candidate_id)

    def get_candidate(self, candidate_id: str) -> ClaimRelationCandidateRecord:
        row = self.conn.execute(
            "SELECT * FROM claim_relation_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Candidate not found: {candidate_id}")
        return ClaimRelationCandidateRecord(**dict(row))

    def list_for_claim(self, claim_id: str, status: str | None = None) -> list[ClaimRelationCandidateRecord]:
        if status is not None:
            rows = self.conn.execute(
                """
                SELECT * FROM claim_relation_candidates
                WHERE (source_claim_id = ? OR target_claim_id = ?) AND status = ?
                ORDER BY score DESC, created_at ASC
                """,
                (claim_id, claim_id, status),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM claim_relation_candidates
                WHERE source_claim_id = ? OR target_claim_id = ?
                ORDER BY score DESC, created_at ASC
                """,
                (claim_id, claim_id),
            ).fetchall()
        return [ClaimRelationCandidateRecord(**dict(row)) for row in rows]

    def list_pending(self, limit: int = 50) -> list[ClaimRelationCandidateRecord]:
        rows = self.conn.execute(
            """
            SELECT * FROM claim_relation_candidates
            WHERE status = 'pending'
            ORDER BY score DESC, created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [ClaimRelationCandidateRecord(**dict(row)) for row in rows]

    def update_status(self, candidate_id: str, status: str) -> ClaimRelationCandidateRecord:
        if status not in {"pending", "promoted", "rejected", "superseded"}:
            raise ValueError(f"Invalid candidate status: {status}")
        timestamp = utc_now()
        self.conn.execute(
            "UPDATE claim_relation_candidates SET status = ?, updated_at = ? WHERE id = ?",
            (status, timestamp, candidate_id),
        )
        self.conn.commit()
        return self.get_candidate(candidate_id)

    def _find_existing(
        self, source_claim_id: str, target_claim_id: str, relation_type: str
    ) -> ClaimRelationCandidateRecord | None:
        row = self.conn.execute(
            """
            SELECT * FROM claim_relation_candidates
            WHERE source_claim_id = ? AND target_claim_id = ? AND relation_type = ?
            """,
            (source_claim_id, target_claim_id, relation_type),
        ).fetchone()
        return ClaimRelationCandidateRecord(**dict(row)) if row is not None else None
