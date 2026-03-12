from __future__ import annotations

import hashlib
import json
import sqlite3

from rks.domain.models import MethodRecord
from rks.ids import next_id
from rks.utils import utc_now


class MethodRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def replace_methods_for_paper(self, paper_id: str, methods: list[dict]) -> list[MethodRecord]:
        timestamp = utc_now()
        existing_by_fingerprint = self._existing_methods_by_fingerprint(paper_id)
        self.conn.execute("DELETE FROM methods WHERE paper_id = ?", (paper_id,))
        created: list[MethodRecord] = []

        for method in methods:
            fingerprint = self._method_fingerprint(method)
            existing = existing_by_fingerprint.get(fingerprint, [])
            prior = existing.pop(0) if existing else None
            method_id = prior.id if prior is not None else next_id(self.conn, "method")
            created_at = prior.created_at if prior is not None else timestamp
            self.conn.execute(
                """
                INSERT INTO methods(
                    id, paper_id, name, description, about_concept_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    method_id,
                    paper_id,
                    method["name"],
                    method.get("description"),
                    method.get("about_concept_id"),
                    created_at,
                    timestamp,
                ),
            )
            created.append(self.get_method(method_id))

        self.conn.commit()
        return created

    def list_methods_for_paper(self, paper_id: str) -> list[MethodRecord]:
        rows = self.conn.execute(
            "SELECT * FROM methods WHERE paper_id = ? ORDER BY created_at ASC, id ASC",
            (paper_id,),
        ).fetchall()
        return [MethodRecord(**dict(row)) for row in rows]

    def get_method(self, method_id: str) -> MethodRecord:
        row = self.conn.execute("SELECT * FROM methods WHERE id = ?", (method_id,)).fetchone()
        if row is None:
            raise KeyError(f"Method not found: {method_id}")
        return MethodRecord(**dict(row))

    def search_methods(self, query: str) -> list[MethodRecord]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT *
            FROM methods
            WHERE name LIKE ? OR description LIKE ?
            ORDER BY updated_at DESC, id DESC
            """,
            (like, like),
        ).fetchall()
        return [MethodRecord(**dict(row)) for row in rows]

    def _existing_methods_by_fingerprint(self, paper_id: str) -> dict[str, list[MethodRecord]]:
        records: dict[str, list[MethodRecord]] = {}
        for method in self.list_methods_for_paper(paper_id):
            fingerprint = self._method_fingerprint(
                {
                    "name": method.name,
                    "description": method.description,
                    "about_concept_id": method.about_concept_id,
                }
            )
            records.setdefault(fingerprint, []).append(method)
        return records

    def _method_fingerprint(self, method: dict) -> str:
        payload = {
            "name": method.get("name"),
            "description": method.get("description"),
            "about_concept_id": method.get("about_concept_id"),
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
