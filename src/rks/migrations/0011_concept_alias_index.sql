-- Migration 0011: concept_alias_index
--
-- Reverse-lookup table that maps every known alias key (canonicalised surface
-- form) to its concept_id.  This replaces the O(n) full-table scan in
-- find_by_name_or_alias with a single O(1) indexed lookup.
--
-- Maintenance contract:
--   INSERT OR REPLACE on get_or_create and add_aliases.
--   UPDATE concept_id (target) then DELETE old source rows on merge_into.
--   The table is backfilled at startup via _ensure_alias_index in db.py so
--   existing databases are migrated transparently.
CREATE TABLE IF NOT EXISTS concept_alias_index (
    alias_key  TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    PRIMARY KEY (alias_key)
);
