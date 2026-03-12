from __future__ import annotations

import json
import sqlite3

from rks.ids import next_id
from rks.utils import utc_now


class EmbeddingRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_embedding(self, object_id: str, object_type: str, embedding_model: str, vector: list[float]) -> None:
        self.conn.execute(
            """
            DELETE FROM embeddings
            WHERE object_id = ? AND object_type = ? AND embedding_model = ?
            """,
            (object_id, object_type, embedding_model),
        )
        self.conn.execute(
            """
            INSERT INTO embeddings(id, object_id, object_type, embedding_model, vector_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                next_id(self.conn, "artifact"),
                object_id,
                object_type,
                embedding_model,
                json.dumps(vector),
                utc_now(),
            ),
        )
        self.conn.commit()

    def list_embeddings(self, object_types: list[str], embedding_model: str) -> list[dict]:
        if not object_types:
            return []
        placeholders = ", ".join("?" for _ in object_types)
        rows = self.conn.execute(
            f"""
            SELECT object_id, object_type, embedding_model, vector_json, created_at
            FROM embeddings
            WHERE embedding_model = ? AND object_type IN ({placeholders})
            """,
            (embedding_model, *object_types),
        ).fetchall()
        return [dict(row) for row in rows]
