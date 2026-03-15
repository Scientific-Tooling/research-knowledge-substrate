CREATE INDEX IF NOT EXISTS idx_claims_subject_concept ON claims(subject_concept_id);
CREATE INDEX IF NOT EXISTS idx_claims_object_concept ON claims(object_concept_id);
CREATE INDEX IF NOT EXISTS idx_edges_types ON edges(source_type, target_type, relation_type);
CREATE INDEX IF NOT EXISTS idx_notes_target ON notes(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name);
