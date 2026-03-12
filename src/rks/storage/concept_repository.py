from __future__ import annotations

import json
import sqlite3

from rks.concepts.normalize import alias_candidates, canonicalize_term
from rks.domain.models import ConceptRecord
from rks.ids import next_id
from rks.utils import utc_now


class ConceptRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_or_create(self, term: str) -> ConceptRecord:
        existing = self.find_by_name_or_alias(term)
        if existing is not None:
            return existing

        timestamp = utc_now()
        concept_id = next_id(self.conn, "concept")
        canonical = canonicalize_term(term)
        aliases = sorted(set(alias_candidates(term)))
        self.conn.execute(
            """
            INSERT INTO concepts(
                id, name, aliases_json, domain, parent_concept_id, description,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                concept_id,
                canonical,
                json.dumps(aliases, sort_keys=True),
                None,
                None,
                None,
                "system",
                timestamp,
                timestamp,
            ),
        )
        self.conn.commit()
        return self.get_concept(concept_id)

    def find_by_name_or_alias(self, term: str):
        canonical = canonicalize_term(term)
        rows = self.conn.execute("SELECT * FROM concepts ORDER BY name ASC").fetchall()
        for row in rows:
            aliases = json.loads(row["aliases_json"] or "[]")
            if row["name"] == canonical or canonical in aliases or canonical.lower() in aliases:
                return ConceptRecord(**dict(row))
        return None

    def get_concept(self, concept_id: str) -> ConceptRecord:
        row = self.conn.execute(
            "SELECT * FROM concepts WHERE id = ?",
            (concept_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Concept not found: {concept_id}")
        return ConceptRecord(**dict(row))

    def list_for_paper(self, paper_id: str) -> list[ConceptRecord]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT c.*
            FROM concepts c
            JOIN claims cl
              ON c.id = cl.subject_concept_id OR c.id = cl.object_concept_id
            WHERE cl.paper_id = ?
            ORDER BY c.name ASC
            """,
            (paper_id,),
        ).fetchall()
        return [ConceptRecord(**dict(row)) for row in rows]
