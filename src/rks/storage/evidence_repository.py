"""Persistence only; the caller owns the complete evidence-import transaction."""

from __future__ import annotations

import json

from rks.ids import next_id
from rks.utils import utc_now


class EvidenceRepository:
    def __init__(self, conn):
        self.conn = conn

    def get(self, source_key: str):
        return self.conn.execute("SELECT * FROM external_evidence WHERE source_key = ?", (source_key,)).fetchone()

    def current_records(self):
        """Read current imports with their note state; never expand revision history."""
        return self.conn.execute(
            """SELECT e.*, n.target_id AS paper_id, n.target_type, n.content AS note_content, n.created_by
               FROM external_evidence e LEFT JOIN notes n ON n.id = e.note_id ORDER BY e.source_key"""
        )

    def save(self, *, source_key: str, record: dict, paper_id: str, content: str) -> str:
        if not self.conn.in_transaction:
            raise RuntimeError("Evidence writes require a caller-owned transaction")
        existing = self.get(source_key)
        timestamp = utc_now()
        if existing is None:
            note_id = next_id(self.conn, "note")
            self.conn.execute(
                "INSERT INTO notes(id, target_id, target_type, content, created_by, created_at) VALUES (?, ?, 'paper', ?, ?, ?)",
                (note_id, paper_id, content, "external:apw", timestamp),
            )
        else:
            note_id = existing["note_id"]
            self.conn.execute("UPDATE notes SET content = ? WHERE id = ?", (content, note_id))
        revision = record["item"]["revision"]
        encoded = json.dumps(record, sort_keys=True, ensure_ascii=True, allow_nan=False)
        self.conn.execute(
            """INSERT INTO external_evidence(source_key, note_id, revision, record_json, imported_at)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT(source_key) DO UPDATE SET
               revision = excluded.revision, record_json = excluded.record_json, imported_at = excluded.imported_at""",
            (source_key, note_id, revision, encoded, timestamp),
        )
        self.conn.execute(
            """INSERT OR IGNORE INTO external_evidence_history(source_key, revision, record_json, imported_at)
               VALUES (?, ?, ?, ?)""", (source_key, revision, encoded, timestamp),
        )
        self.conn.execute("UPDATE papers SET updated_at = ? WHERE id = ?", (timestamp, paper_id))
        return note_id

    def list_for_paper(self, paper_id: str) -> list[dict]:
        rows = self.conn.execute(
            """SELECT e.*, n.target_id AS paper_id FROM external_evidence e JOIN notes n ON n.id = e.note_id
               WHERE n.target_type = 'paper' AND n.target_id = ? ORDER BY e.source_key""", (paper_id,),
        ).fetchall()
        return [{**{key: value for key, value in dict(row).items() if key != "record_json"},
                 "record": json.loads(row["record_json"]), "history": [
            {"revision": history["revision"], "imported_at": history["imported_at"],
             "record": json.loads(history["record_json"])}
            for history in self.conn.execute(
                "SELECT * FROM external_evidence_history WHERE source_key = ? ORDER BY imported_at, revision",
                (row["source_key"],),
            )
        ]} for row in rows]
