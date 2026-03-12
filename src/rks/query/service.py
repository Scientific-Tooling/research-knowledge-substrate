from __future__ import annotations

import json

from rks.concepts.normalize import canonicalize_term
from rks.storage import ClaimRepository, ConceptRepository, EdgeRepository, PaperRepository


class QueryService:
    def __init__(
        self,
        papers: PaperRepository,
        claims: ClaimRepository,
        concepts: ConceptRepository,
        edges: EdgeRepository,
    ):
        self.papers = papers
        self.claims = claims
        self.concepts = concepts
        self.edges = edges

    def claims_about(self, concept_name_or_id: str) -> dict:
        concept = self._resolve_concept(concept_name_or_id)
        if concept is None:
            return {"concept": None, "claims": []}

        claims = self.claims.list_claims_for_concept(concept.id)
        return {
            "concept": {
                "id": concept.id,
                "name": concept.name,
            },
            "claims": [self._claim_payload(claim) for claim in claims],
        }

    def papers_supporting(self, claim_id: str) -> dict:
        claim = self.claims.get_claim(claim_id)
        papers = self.edges.list_papers_supporting_claim(claim_id, self.papers)
        return {
            "claim": self._claim_payload(claim),
            "papers": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "source_type": paper.source_type,
                    "source_ref": paper.source_ref,
                }
                for paper in papers
            ],
        }

    def concepts_for_paper(self, paper_id: str) -> list[dict]:
        concepts = self.concepts.list_for_paper(paper_id)
        return [{"id": concept.id, "name": concept.name} for concept in concepts]

    def _resolve_concept(self, concept_name_or_id: str):
        if concept_name_or_id.startswith("k_"):
            return self.concepts.get_concept(concept_name_or_id)
        return self.concepts.find_by_name_or_alias(canonicalize_term(concept_name_or_id))

    def _claim_payload(self, claim) -> dict:
        context = json.loads(claim.context_json or "{}")
        subject_name = None
        object_name = claim.object_text
        if claim.subject_concept_id:
            subject_name = self.concepts.get_concept(claim.subject_concept_id).name
        if claim.object_concept_id:
            object_name = self.concepts.get_concept(claim.object_concept_id).name
        if subject_name is None:
            subject_name = context.get("subject_text")

        return {
            "id": claim.id,
            "paper_id": claim.paper_id,
            "text": claim.text,
            "subject": subject_name,
            "predicate": claim.predicate,
            "object": object_name,
            "confidence": claim.confidence,
            "evidence": json.loads(claim.evidence_json or "{}"),
        }
