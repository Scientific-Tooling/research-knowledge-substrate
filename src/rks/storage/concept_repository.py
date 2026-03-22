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

        # Split "Full Name (ABBREV)" into base name and rigid designator (Kripke).
        # The abbreviation is stored in canonical_abbrev for O(1) priority lookup,
        # and also added to aliases so all surface forms remain searchable.
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
                status, created_at, updated_at, canonical_abbrev
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                inline_abbrev,
            ),
        )
        # Maintain the alias reverse-index so future lookups are O(1).
        _upsert_alias_index(self.conn, concept_id, canonical, inline_abbrev, aliases)
        self.conn.commit()
        return self.get_concept(concept_id)

    def find_by_name_or_alias(self, term: str):
        """Look up a concept by any of its surface forms.

        Fast path (O(1)): concept_alias_index reverse-lookup table.
        Slow path (O(n)): full aliases_json scan, only reached when the index
        table does not exist (pre-migration databases).
        """
        _, abbrev = extract_abbreviation(term)
        canonical = canonicalize_term(term)

        # Build the set of keys to probe, ordered from most-specific to least.
        probe_keys = []
        if abbrev:
            probe_keys.append(abbrev)          # rigid designator (Kripke)
            probe_keys.append(abbrev.lower())
        probe_keys.append(canonical)           # normalised full name
        probe_keys.append(canonical.lower())

        # Fast path: single indexed lookup per key.
        if _alias_index_exists(self.conn):
            for key in probe_keys:
                row = self.conn.execute(
                    "SELECT concept_id FROM concept_alias_index WHERE alias_key = ? LIMIT 1",
                    (key,),
                ).fetchone()
                if row is not None:
                    return self.get_concept(row["concept_id"])
            return None

        # Slow path: legacy full-table scan (pre-migration databases only).
        rows = self.conn.execute("SELECT * FROM concepts ORDER BY name ASC").fetchall()
        for row in rows:
            aliases = json.loads(row["aliases_json"] or "[]")
            if (
                row["name"] == canonical
                or row["canonical_abbrev"] == canonical
                or canonical in aliases
                or canonical.lower() in aliases
            ):
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
            haystacks = [record.name, record.canonical_abbrev, *aliases]
            if any(canonical.lower() in value.lower() for value in haystacks if value):
                matches.append(record)
        return matches

    def add_aliases(self, concept_id: str, new_aliases: list[str]) -> ConceptRecord:
        concept = self.get_concept(concept_id)
        existing: set[str] = set(json.loads(concept.aliases_json or "[]"))
        new_abbrev = concept.canonical_abbrev

        for alias in new_aliases:
            # If a new alias contains an inline abbreviation, promote it to
            # canonical_abbrev when the concept doesn't already have one.
            _, abbrev = extract_abbreviation(alias)
            if abbrev and new_abbrev is None:
                new_abbrev = abbrev
            for candidate in alias_candidates(alias):
                existing.add(candidate)

        update_fields = "aliases_json = ?, updated_at = ?"
        params: list = [json.dumps(sorted(existing), sort_keys=True), utc_now()]
        if new_abbrev != concept.canonical_abbrev:
            update_fields += ", canonical_abbrev = ?"
            params.append(new_abbrev)
        params.append(concept_id)

        self.conn.execute(
            f"UPDATE concepts SET {update_fields} WHERE id = ?",
            params,
        )
        # Keep alias index in sync.
        _upsert_alias_index(self.conn, concept_id, concept.name, new_abbrev, list(existing))
        self.conn.commit()
        return self.get_concept(concept_id)

    def merge_into(self, source_id: str, target_id: str) -> dict:
        source = self.get_concept(source_id)
        target = self.get_concept(target_id)
        timestamp = utc_now()

        absorbed = [source.name] + json.loads(source.aliases_json or "[]")
        # Absorb source aliases; also promote source's canonical_abbrev to target
        # if target doesn't already have one (rigid designator inheritance).
        if source.canonical_abbrev and not target.canonical_abbrev:
            self.conn.execute(
                "UPDATE concepts SET canonical_abbrev = ?, updated_at = ? WHERE id = ?",
                (source.canonical_abbrev, timestamp, target_id),
            )
        self.add_aliases(target_id, absorbed)
        # Re-point all alias index entries that still reference the source to target,
        # then delete any residual source-only entries.
        if _alias_index_exists(self.conn):
            self.conn.execute(
                "UPDATE concept_alias_index SET concept_id = ? WHERE concept_id = ?",
                (target_id, source_id),
            )

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

    def find_duplicate_candidates(
        self, threshold: float = 0.75, limit: int = 20
    ) -> list[dict]:
        """Return pairs of concepts whose names are suspiciously similar.

        Uses trigram (Jaccard) similarity on lowercased names so that
        'Self Attention' and 'Self-Attention' score near 1.0 while
        unrelated concepts score near 0.  Operates entirely in Python;
        no external deps required (Wittgenstein: family resemblance).

        Returns a list of dicts ordered by score descending, capped at *limit*.
        Each dict carries both ConceptRecords and a ready-made merge hint.
        """
        concepts = self.list_concepts()
        results: list[dict] = []

        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                a, b = concepts[i], concepts[j]
                score = _trigram_similarity(a.name, b.name)
                if score >= threshold:
                    # Suggest keeping the concept with lower id (earlier created)
                    # as target; user can override.
                    target, source = (a, b) if a.id < b.id else (b, a)
                    results.append(
                        {
                            "score": round(score, 4),
                            "concept_a": _concept_summary(a),
                            "concept_b": _concept_summary(b),
                            "merge_hint": f"rks concept merge {source.id} {target.id}",
                        }
                    )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]


# ---------------------------------------------------------------------------
# Alias-index helpers
# ---------------------------------------------------------------------------


def _alias_index_exists(conn: sqlite3.Connection) -> bool:
    """Return True when the concept_alias_index table is present."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='concept_alias_index' LIMIT 1"
    ).fetchone()
    return row is not None


def _upsert_alias_index(
    conn: sqlite3.Connection,
    concept_id: str,
    name: str,
    canonical_abbrev: str | None,
    aliases: list[str],
) -> None:
    """Insert or replace all keys for *concept_id* into concept_alias_index."""
    if not _alias_index_exists(conn):
        return
    keys: set[str] = set()
    if name:
        keys.add(name)
        keys.add(name.lower())
    if canonical_abbrev:
        keys.add(canonical_abbrev)
        keys.add(canonical_abbrev.lower())
    for alias in aliases:
        if alias:
            keys.add(alias)
    conn.executemany(
        "INSERT OR REPLACE INTO concept_alias_index(alias_key, concept_id) VALUES(?, ?)",
        [(k, concept_id) for k in keys if k],
    )


# ---------------------------------------------------------------------------
# Parent-term helpers
# Single-word tokens that are too generic to serve as a parent concept.
# Multi-word entries allow matching a trailing phrase rather than just the
# last token (Aristotle: genus must be a substantive upper category, not an
# accidental last word).
_PARENT_STOPWORDS: frozenset[str] = frozenset({
    # generic methodological nouns
    "model", "method", "system", "approach", "dataset", "task",
    "technique", "framework", "algorithm", "architecture", "strategy",
    "procedure", "mechanism", "process", "pipeline", "module",
    # generic relational nouns that create spurious parents
    "result", "output", "input", "feature", "function", "layer",
    "network", "representation", "embedding", "vector",
    # trailing preposition phrases that should not become parents
    "of", "for", "with", "via", "using", "based",
})

# Multi-word trailing phrases whose last word looks substantive but whose
# full phrase is a functional stopword (e.g. "Mixture of Experts" should
# not yield parent "Experts" — "of Experts" is the differentia, not the genus).
_MULTI_WORD_STOPWORD_SUFFIXES: tuple[str, ...] = (
    "of experts",
    "of attention",
    "of layers",
    "of heads",
    "of tokens",
)


def _infer_parent_term(term: str) -> str | None:
    """Infer the Aristotelian genus for *term* (the substantive upper category).

    Strategy:
    1. Reject single-token terms (no genus possible).
    2. Reject if the full trailing phrase matches a known multi-word stopword
       suffix (e.g. "Sparse Mixture of Experts" → suffix "of Experts" blocked).
    3. Walk tokens right-to-left and return the first token that is not in the
       single-word stopword set.  This recovers "Transformer" from
       "Vision Transformer" while still blocking "Gradient Descent Method"
       (last meaningful word is "Descent", which is not a stopword, so the
       parent becomes "Descent" — a valid narrower category).
    4. Return None if no suitable token is found.
    """
    parts = term.split()
    if len(parts) < 2:
        return None

    lowered = term.lower()
    for suffix in _MULTI_WORD_STOPWORD_SUFFIXES:
        if lowered.endswith(suffix):
            return None

    for token in reversed(parts):
        candidate = canonicalize_term(token)
        if candidate.lower() not in _PARENT_STOPWORDS:
            # Only promote single-token parents to avoid overly broad nodes.
            return candidate

    return None


# ---------------------------------------------------------------------------
# Similarity helpers (used by find_duplicate_candidates)
# ---------------------------------------------------------------------------

def _trigrams(s: str) -> set[str]:
    """Return the set of character trigrams for *s* (padded with spaces)."""
    s = f"  {s.lower()} "
    return {s[i: i + 3] for i in range(len(s) - 2)}


def _trigram_similarity(a: str, b: str) -> float:
    """Jaccard similarity over character trigrams (no external dependencies)."""
    ta = _trigrams(a)
    tb = _trigrams(b)
    union = ta | tb
    if not union:
        return 0.0
    return len(ta & tb) / len(union)


def _concept_summary(c: ConceptRecord) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "canonical_abbrev": c.canonical_abbrev,
    }
