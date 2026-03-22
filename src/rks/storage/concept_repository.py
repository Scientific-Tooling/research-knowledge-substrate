from __future__ import annotations

import json
import sqlite3

from rks.concepts.normalize import alias_candidates, canonicalize_term, extract_abbreviation
from rks.domain.models import ConceptRecord
from rks.ids import next_id
from rks.utils import utc_now


class ConceptRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_or_create(self, term: str, allow_parent: bool = True) -> ConceptRecord:
        existing = self.find_by_name_or_alias(term)
        if existing is not None:
            return existing

        timestamp = utc_now()
        concept_id = next_id(self.conn, "concept")
        # If the term contains a trailing abbreviation like "Long Short-Term Memory (LSTM)",
        # strip it from the canonical name and register the abbreviation as an alias so
        # that both forms resolve to the same node without extra manual steps.
        _, inline_abbrev = extract_abbreviation(term)
        canonical = canonicalize_term(term)
        alias_set: set[str] = set(alias_candidates(term))
        if inline_abbrev:
            alias_set.update(alias_candidates(inline_abbrev))
        aliases = sorted(alias_set)
        parent_concept_id = None
        if allow_parent:
            parent_term = _infer_parent_term(canonical)
            if parent_term:
                parent_concept_id = self.get_or_create(parent_term, allow_parent=False).id
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
                parent_concept_id,
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

    def search_concepts(self, query: str) -> list[ConceptRecord]:
        canonical = canonicalize_term(query)
        rows = self.conn.execute("SELECT * FROM concepts ORDER BY updated_at DESC, id DESC").fetchall()
        matches = []
        for row in rows:
            record = ConceptRecord(**dict(row))
            aliases = json.loads(record.aliases_json or "[]")
            haystacks = [record.name, *aliases]
            if any(canonical.lower() in value.lower() for value in haystacks if value):
                matches.append(record)
        return matches

    def add_aliases(self, concept_id: str, new_aliases: list[str]) -> ConceptRecord:
        concept = self.get_concept(concept_id)
        existing: set[str] = set(json.loads(concept.aliases_json or "[]"))
        for alias in new_aliases:
            for candidate in alias_candidates(alias):
                existing.add(candidate)
        self.conn.execute(
            "UPDATE concepts SET aliases_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(sorted(existing), sort_keys=True), utc_now(), concept_id),
        )
        self.conn.commit()
        return self.get_concept(concept_id)

    def merge_into(self, source_id: str, target_id: str) -> dict:
        source = self.get_concept(source_id)
        target = self.get_concept(target_id)
        timestamp = utc_now()

        absorbed = [source.name] + json.loads(source.aliases_json or "[]")
        self.add_aliases(target_id, absorbed)

        moved_subject = self.conn.execute(
            "UPDATE claims SET subject_concept_id = ?, updated_at = ? WHERE subject_concept_id = ?",
            (target_id, timestamp, source_id),
        ).rowcount
        moved_object = self.conn.execute(
            "UPDATE claims SET object_concept_id = ?, updated_at = ? WHERE object_concept_id = ?",
            (target_id, timestamp, source_id),
        ).rowcount
        moved_edge_sources = self.conn.execute(
            "UPDATE edges SET source_id = ? WHERE source_type = 'concept' AND source_id = ?",
            (target_id, source_id),
        ).rowcount
        moved_edge_targets = self.conn.execute(
            "UPDATE edges SET target_id = ? WHERE target_type = 'concept' AND target_id = ?",
            (target_id, source_id),
        ).rowcount
        self.conn.execute(
            "DELETE FROM embeddings WHERE object_id = ? AND object_type = 'concept'",
            (source_id,),
        )
        self.conn.execute("DELETE FROM concepts WHERE id = ?", (source_id,))
        self.conn.commit()

        return {
            "source_id": source_id,
            "target_id": target_id,
            "source_name": source.name,
            "target_name": target.name,
            "absorbed_aliases": absorbed,
            "moves": {
                "claims_subject": moved_subject,
                "claims_object": moved_object,
                "edge_source_nodes": moved_edge_sources,
                "edge_target_nodes": moved_edge_targets,
            },
        }

    def list_concepts(self) -> list[ConceptRecord]:
        rows = self.conn.execute("SELECT * FROM concepts ORDER BY created_at ASC, id ASC").fetchall()
        return [ConceptRecord(**dict(row)) for row in rows]


def _infer_parent_term(term: str) -> str | None:
    parts = term.split()
    if len(parts) < 2:
        return None
    candidate = canonicalize_term(parts[-1])
    if candidate.lower() in {"model", "method", "system", "approach", "dataset", "task"}:
        return None
    return candidate
