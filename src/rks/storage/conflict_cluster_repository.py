from __future__ import annotations

import json
import sqlite3

from rks.domain.models import ClaimConflictClusterMemberRecord, ClaimConflictClusterRecord
from rks.ids import next_id
from rks.utils import utc_now


class ConflictClusterRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_cluster(
        self,
        anchor_concept_id: str,
        topic_label: str | None = None,
        summary: dict | None = None,
    ) -> ClaimConflictClusterRecord:
        timestamp = utc_now()
        cluster_id = next_id(self.conn, "claim_conflict_cluster")
        self.conn.execute(
            """
            INSERT INTO claim_conflict_clusters(
                id, anchor_concept_id, topic_label, status, summary_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cluster_id,
                anchor_concept_id,
                topic_label,
                "active",
                json.dumps(summary or {}, sort_keys=True),
                timestamp,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_cluster(cluster_id)

    def add_member(
        self,
        cluster_id: str,
        claim_id: str,
        role: str = "member",
        stance: str | None = None,
        confidence: float | None = None,
    ) -> ClaimConflictClusterMemberRecord:
        timestamp = utc_now()
        member_id = next_id(self.conn, "claim_conflict_cluster_member")
        self.conn.execute(
            """
            INSERT INTO claim_conflict_cluster_members(
                id, cluster_id, claim_id, role, stance, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (member_id, cluster_id, claim_id, role, stance, confidence, timestamp),
        )
        self.conn.commit()
        return ClaimConflictClusterMemberRecord(
            id=member_id,
            cluster_id=cluster_id,
            claim_id=claim_id,
            role=role,
            stance=stance,
            confidence=confidence,
            created_at=timestamp,
        )

    def get_cluster(self, cluster_id: str) -> ClaimConflictClusterRecord:
        row = self.conn.execute(
            "SELECT * FROM claim_conflict_clusters WHERE id = ?", (cluster_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Conflict cluster not found: {cluster_id}")
        return ClaimConflictClusterRecord(**dict(row))

    def list_clusters_for_concept(
        self, concept_id: str, status: str | None = None
    ) -> list[ClaimConflictClusterRecord]:
        if status is not None:
            rows = self.conn.execute(
                "SELECT * FROM claim_conflict_clusters WHERE anchor_concept_id = ? AND status = ? ORDER BY created_at DESC",
                (concept_id, status),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM claim_conflict_clusters WHERE anchor_concept_id = ? ORDER BY created_at DESC",
                (concept_id,),
            ).fetchall()
        return [ClaimConflictClusterRecord(**dict(row)) for row in rows]

    def list_members_for_cluster(self, cluster_id: str) -> list[ClaimConflictClusterMemberRecord]:
        rows = self.conn.execute(
            "SELECT * FROM claim_conflict_cluster_members WHERE cluster_id = ? ORDER BY created_at ASC",
            (cluster_id,),
        ).fetchall()
        return [ClaimConflictClusterMemberRecord(**dict(row)) for row in rows]

    def update_cluster_status(self, cluster_id: str, status: str) -> ClaimConflictClusterRecord:
        timestamp = utc_now()
        self.conn.execute(
            "UPDATE claim_conflict_clusters SET status = ?, updated_at = ? WHERE id = ?",
            (status, timestamp, cluster_id),
        )
        self.conn.commit()
        return self.get_cluster(cluster_id)

    def clear_clusters_for_concept(self, concept_id: str) -> int:
        """Remove all clusters and members for a concept. Returns count of clusters removed."""
        clusters = self.list_clusters_for_concept(concept_id)
        for cluster in clusters:
            self.conn.execute(
                "DELETE FROM claim_conflict_cluster_members WHERE cluster_id = ?",
                (cluster.id,),
            )
        cursor = self.conn.execute(
            "DELETE FROM claim_conflict_clusters WHERE anchor_concept_id = ?",
            (concept_id,),
        )
        self.conn.commit()
        return cursor.rowcount
