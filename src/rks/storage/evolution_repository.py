from __future__ import annotations

import json
import sqlite3

from rks.domain.models import ConceptTimelineSnapshotRecord, EvolutionEventRecord
from rks.ids import next_id
from rks.utils import utc_now


class EvolutionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------------
    # Evolution events
    # ------------------------------------------------------------------

    def record_event(
        self,
        event_type: str,
        subject_id: str,
        subject_type: str,
        detail: dict | None = None,
        created_by: str = "system",
    ) -> EvolutionEventRecord:
        timestamp = utc_now()
        event_id = next_id(self.conn, "evolution_event")
        self.conn.execute(
            """
            INSERT INTO evolution_events(id, event_type, subject_id, subject_type, detail_json, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, event_type, subject_id, subject_type, json.dumps(detail or {}, sort_keys=True), created_by, timestamp),
        )
        self.conn.commit()
        return self.get_event(event_id)

    def get_event(self, event_id: str) -> EvolutionEventRecord:
        row = self.conn.execute("SELECT * FROM evolution_events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(f"Evolution event not found: {event_id}")
        return EvolutionEventRecord(**dict(row))

    def list_events_for_subject(self, subject_id: str, subject_type: str | None = None) -> list[EvolutionEventRecord]:
        if subject_type is not None:
            rows = self.conn.execute(
                "SELECT * FROM evolution_events WHERE subject_id = ? AND subject_type = ? ORDER BY created_at ASC",
                (subject_id, subject_type),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM evolution_events WHERE subject_id = ? ORDER BY created_at ASC",
                (subject_id,),
            ).fetchall()
        return [EvolutionEventRecord(**dict(row)) for row in rows]

    def list_events_by_type(self, event_type: str, limit: int = 50) -> list[EvolutionEventRecord]:
        rows = self.conn.execute(
            "SELECT * FROM evolution_events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
            (event_type, limit),
        ).fetchall()
        return [EvolutionEventRecord(**dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # Concept timeline snapshots
    # ------------------------------------------------------------------

    def create_snapshot(
        self,
        concept_id: str,
        support_count: int,
        contradiction_count: int,
        paper_count: int,
        claim_count: int,
        detail: dict | None = None,
        time_bucket: str | None = None,
        refine_count: int = 0,
        consensus_score: float | None = None,
        controversy_score: float | None = None,
        basis_layer: str = "reviewed",
    ) -> ConceptTimelineSnapshotRecord:
        timestamp = utc_now()
        snapshot_id = next_id(self.conn, "concept_timeline_snapshot")
        self.conn.execute(
            """
            INSERT INTO concept_timeline_snapshots(
                id, concept_id, snapshot_at, support_count, contradiction_count,
                paper_count, claim_count, detail_json, created_at,
                time_bucket, refine_count, consensus_score, controversy_score, basis_layer
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                concept_id,
                timestamp,
                support_count,
                contradiction_count,
                paper_count,
                claim_count,
                json.dumps(detail or {}, sort_keys=True),
                timestamp,
                time_bucket,
                refine_count,
                consensus_score,
                controversy_score,
                basis_layer,
            ),
        )
        self.conn.commit()
        return self.get_snapshot(snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> ConceptTimelineSnapshotRecord:
        row = self.conn.execute("SELECT * FROM concept_timeline_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(f"Snapshot not found: {snapshot_id}")
        return ConceptTimelineSnapshotRecord(**dict(row))

    def list_concept_ids_with_snapshots(self) -> list[str]:
        """Return all concept IDs that have at least one snapshot."""
        rows = self.conn.execute(
            "SELECT DISTINCT concept_id FROM concept_timeline_snapshots ORDER BY concept_id"
        ).fetchall()
        return [row[0] for row in rows]

    def get_latest_snapshot_for_concept(self, concept_id: str) -> ConceptTimelineSnapshotRecord | None:
        """Return the most recent snapshot for a concept, or None if none exist."""
        row = self.conn.execute(
            "SELECT * FROM concept_timeline_snapshots WHERE concept_id = ? ORDER BY snapshot_at DESC LIMIT 1",
            (concept_id,),
        ).fetchone()
        return ConceptTimelineSnapshotRecord(**dict(row)) if row is not None else None

    def list_snapshots_for_concept(self, concept_id: str, time_bucket: str | None = None) -> list[ConceptTimelineSnapshotRecord]:
        if time_bucket is not None:
            rows = self.conn.execute(
                "SELECT * FROM concept_timeline_snapshots WHERE concept_id = ? AND time_bucket = ? ORDER BY snapshot_at ASC",
                (concept_id, time_bucket),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM concept_timeline_snapshots WHERE concept_id = ? ORDER BY snapshot_at ASC",
                (concept_id,),
            ).fetchall()
        return [ConceptTimelineSnapshotRecord(**dict(row)) for row in rows]
