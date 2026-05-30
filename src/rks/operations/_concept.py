"""Concept management operations: aliases, merging, and duplicate detection."""

from __future__ import annotations

import json


class ConceptOps:
    def __init__(self, *, concepts, evolution):
        self.concepts = concepts
        self.evolution = evolution

    def add_concept_alias(self, concept_id: str, alias: str) -> dict:
        before = self.concepts.get_concept(concept_id)
        before_aliases = json.loads(before.aliases_json or "[]")
        concept = self.concepts.add_aliases(concept_id, [alias])
        after_aliases = json.loads(concept.aliases_json or "[]")
        if self.evolution is not None:
            self.evolution.record_event(
                event_type="concept_aliased",
                subject_id=concept.id,
                subject_type="concept",
                detail={
                    "alias_added": alias,
                    "canonical_abbrev": concept.canonical_abbrev,
                    "alias_count_before": len(before_aliases),
                    "alias_count_after": len(after_aliases),
                },
            )
        return {
            "concept_id": concept.id,
            "name": concept.name,
            "aliases": after_aliases,
        }

    def merge_concepts(self, source_id: str, target_id: str) -> dict:
        if source_id == target_id:
            raise ValueError("source_id and target_id must be different")
        result = self.concepts.merge_into(source_id, target_id)
        if self.evolution is not None:
            self.evolution.record_event(
                event_type="concept_merged",
                subject_id=target_id,
                subject_type="concept",
                detail={
                    "source_id": result["source_id"],
                    "source_name": result["source_name"],
                    "target_name": result["target_name"],
                    "absorbed_alias_count": len(result.get("absorbed_aliases", [])),
                    "moves": result.get("moves", {}),
                },
            )
        return result

    def find_duplicate_concepts(self, threshold: float = 0.75, limit: int = 20) -> list[dict]:
        return self.concepts.find_duplicate_candidates(threshold=threshold, limit=limit)
