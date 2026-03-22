-- Migration 0012: Remove reverse-edge relation types (supported_by, contradicted_by).
--
-- Design: edges were originally written in both directions.  The canonical
-- direction is now always source→relation→target with the forward verb.
--
--   OLD: claim --supported_by--> paper
--   NEW: paper --supports-------> claim
--
--   OLD: claim --contradicted_by--> paper  (rare / legacy)
--   NEW: paper --contradicts------> claim
--
-- SQLite evaluates the right-hand side of SET clauses using pre-update values,
-- so the simultaneous swap of source_id/target_id is safe.
UPDATE edges
SET
    source_id    = target_id,
    source_type  = target_type,
    target_id    = source_id,
    target_type  = source_type,
    relation_type = 'supports'
WHERE relation_type = 'supported_by';

UPDATE edges
SET
    source_id    = target_id,
    source_type  = target_type,
    target_id    = source_id,
    target_type  = source_type,
    relation_type = 'contradicts'
WHERE relation_type = 'contradicted_by';
