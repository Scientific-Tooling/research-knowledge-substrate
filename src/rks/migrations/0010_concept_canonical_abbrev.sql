-- Migration 0010: add canonical_abbrev to concepts
--
-- Stores the rigid designator (Kripke) for a concept — typically a well-known
-- abbreviation such as "BERT", "LLM", or "MoE".  Unlike aliases_json (which
-- stores all surface forms as a flat JSON array), canonical_abbrev is a first-
-- class indexed column so that lookup by abbreviation is O(1) and takes
-- priority over the longer canonical name during concept resolution.
ALTER TABLE concepts ADD COLUMN canonical_abbrev TEXT;
CREATE INDEX IF NOT EXISTS idx_concepts_canonical_abbrev ON concepts(canonical_abbrev);
