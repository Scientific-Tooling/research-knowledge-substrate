-- Migration 0013: Merge hypothesis_evidence_links into the edges table.
--
-- hypothesis_evidence_links(id, hypothesis_id, object_id, object_type,
--                            relation_type, metadata_json, created_by, created_at)
-- maps directly onto edges with:
--   source_id   = hypothesis_id
--   source_type = 'hypothesis'
--   target_id   = object_id
--   target_type = object_type
--   evidence_paper_id = NULL
--   confidence        = NULL
--
-- Existing `hel_*` IDs are preserved as-is (edges.id is TEXT, no prefix
-- constraint).  New evidence links created after this migration use the
-- standard edge counter (e_NNNNNN).
--
-- Snapshot imports of old graph files that contain a 'hypothesis_evidence_links'
-- section will silently ignore that section, since the table no longer exists
-- in the TABLES list used by snapshot.py.
INSERT OR IGNORE INTO edges (
    id, source_id, source_type, relation_type,
    target_id, target_type,
    evidence_paper_id, confidence, metadata_json, created_by, created_at
)
SELECT
    id,
    hypothesis_id               AS source_id,
    'hypothesis'                AS source_type,
    relation_type,
    object_id                   AS target_id,
    object_type                 AS target_type,
    NULL                        AS evidence_paper_id,
    NULL                        AS confidence,
    COALESCE(metadata_json, '{}') AS metadata_json,
    created_by,
    created_at
FROM hypothesis_evidence_links;

DROP TABLE IF EXISTS hypothesis_evidence_links;
