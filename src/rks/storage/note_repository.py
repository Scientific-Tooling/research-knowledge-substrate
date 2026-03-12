from __future__ import annotations

import sqlite3

from rks.domain.models import NoteRecord
from rks.ids import next_id
from rks.utils import utc_now


class NoteRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_note(self, *, target_id: str, target_type: str, content: str, created_by: str) -> NoteRecord:
        timestamp = utc_now()
        note_id = next_id(self.conn, "note")
        self.conn.execute(
            """
            INSERT INTO notes(id, target_id, target_type, content, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (note_id, target_id, target_type, content, created_by, timestamp),
        )
        self.conn.commit()
        return self.get_note(note_id)

    def get_note(self, note_id: str) -> NoteRecord:
        row = self.conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise KeyError(f"Note not found: {note_id}")
        return NoteRecord(**dict(row))

    def list_notes_for_target(self, *, target_id: str, target_type: str) -> list[NoteRecord]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM notes
            WHERE target_id = ? AND target_type = ?
            ORDER BY created_at ASC, id ASC
            """,
            (target_id, target_type),
        ).fetchall()
        return [NoteRecord(**dict(row)) for row in rows]
