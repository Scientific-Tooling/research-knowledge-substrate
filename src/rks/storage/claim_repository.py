from __future__ import annotations

import json
import sqlite3

from rks.domain.models import ClaimRecord
from rks.ids import next_id
from rks.utils import utc_now


class ClaimRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def replace_claims_for_paper(self, paper_id: str, claims: list[dict]) -> list[ClaimRecord]:
        timestamp = utc_now()
        self.conn.execute("DELETE FROM claims WHERE paper_id = ?", (paper_id,))
        created: list[ClaimRecord] = []

        for claim in claims:
            claim_id = next_id(self.conn, "claim")
            self.conn.execute(
                """
                INSERT INTO claims(
                    id, paper_id, text, subject_concept_id, predicate, object_concept_id,
                    object_text, context_json, evidence_json, confidence, status,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    paper_id,
                    claim["text"],
                    claim.get("subject_concept_id"),
                    claim["predicate"],
                    claim.get("object_concept_id"),
                    claim.get("object_text"),
                    json.dumps(claim.get("context", {}), sort_keys=True),
                    json.dumps(claim.get("evidence", {}), sort_keys=True),
                    claim.get("confidence"),
                    "extracted",
                    "system:heuristic",
                    timestamp,
                    timestamp,
                ),
            )
            created.append(self.get_claim(claim_id))

        self.conn.commit()
        return created

    def update_claim_links(
        self,
        claim_id: str,
        subject_concept_id: str | None,
        object_concept_id: str | None,
    ) -> None:
        timestamp = utc_now()
        self.conn.execute(
            """
            UPDATE claims
            SET subject_concept_id = ?, object_concept_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (subject_concept_id, object_concept_id, timestamp, claim_id),
        )
        self.conn.commit()

    def list_claims_for_paper(self, paper_id: str) -> list[ClaimRecord]:
        rows = self.conn.execute(
            "SELECT * FROM claims WHERE paper_id = ? ORDER BY created_at ASC, id ASC",
            (paper_id,),
        ).fetchall()
        return [ClaimRecord(**dict(row)) for row in rows]

    def list_claims_for_concept(self, concept_id: str) -> list[ClaimRecord]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT *
            FROM claims
            WHERE subject_concept_id = ? OR object_concept_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (concept_id, concept_id),
        ).fetchall()
        return [ClaimRecord(**dict(row)) for row in rows]

    def get_claim(self, claim_id: str) -> ClaimRecord:
        row = self.conn.execute(
            "SELECT * FROM claims WHERE id = ?",
            (claim_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Claim not found: {claim_id}")
        return ClaimRecord(**dict(row))

    def search_claims(self, query: str) -> list[ClaimRecord]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT *
            FROM claims
            WHERE text LIKE ? OR object_text LIKE ? OR context_json LIKE ?
            ORDER BY updated_at DESC, id DESC
            """,
            (like, like, like),
        ).fetchall()
        return [ClaimRecord(**dict(row)) for row in rows]
