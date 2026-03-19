from __future__ import annotations

import json

from rks.storage.claim_repository import ClaimRepository
from rks.storage.concept_repository import ConceptRepository
from rks.storage.edge_repository import EdgeRepository
from rks.storage.paper_repository import PaperRepository


def link_claims_for_paper(
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    paper_id: str,
) -> None:
    claims = claim_repo.list_claims_for_paper(paper_id)
    edge_repo.clear_graph_for_paper(paper_id)

    for claim in claims:
        context = json.loads(claim.context_json or "{}")
        subject_text = context.get("subject_text")
        object_text = claim.object_text or context.get("object_text")

        subject_concept_id = None
        object_concept_id = None

        if subject_text:
            subject_concept = concept_repo.get_or_create(subject_text)
            subject_concept_id = subject_concept.id

        if object_text:
            object_concept = concept_repo.get_or_create(object_text)
            object_concept_id = object_concept.id

        claim_repo.update_claim_links(
            claim_id=claim.id,
            subject_concept_id=subject_concept_id,
            object_concept_id=object_concept_id,
        )

        edge_repo.create_edge(
            source_id=paper_id,
            source_type="paper",
            relation_type="contains",
            target_id=claim.id,
            target_type="claim",
            evidence_paper_id=paper_id,
            confidence=claim.confidence,
            metadata={"predicate": claim.predicate},
        )
        edge_repo.create_edge(
            source_id=claim.id,
            source_type="claim",
            relation_type="supported_by",
            target_id=paper_id,
            target_type="paper",
            evidence_paper_id=paper_id,
            confidence=claim.confidence,
            metadata={"predicate": claim.predicate},
        )

        if subject_concept_id:
            edge_repo.create_edge(
                source_id=claim.id,
                source_type="claim",
                relation_type="about",
                target_id=subject_concept_id,
                target_type="concept",
                evidence_paper_id=paper_id,
                confidence=claim.confidence,
                metadata={"role": "subject"},
            )

        if object_concept_id:
            edge_repo.create_edge(
                source_id=claim.id,
                source_type="claim",
                relation_type="about",
                target_id=object_concept_id,
                target_type="concept",
                evidence_paper_id=paper_id,
                confidence=claim.confidence,
                metadata={"role": "object"},
            )

    paper_repo.touch_paper(paper_id)
