from __future__ import annotations

import json

from rks.providers import LocalHashEmbeddingProvider
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    EmbeddingRepository,
    PaperRepository,
)


def index_embeddings(
    papers: PaperRepository,
    claims: ClaimRepository,
    concepts: ConceptRepository,
    embeddings: EmbeddingRepository,
    paper_id: str | None = None,
    provider: LocalHashEmbeddingProvider | None = None,
) -> dict:
    provider = provider or LocalHashEmbeddingProvider()
    indexed = {"papers": 0, "claims": 0, "concepts": 0, "model": provider.model_name}

    paper_records = [papers.get_paper(paper_id)] if paper_id else papers.list_papers()
    for paper in paper_records:
        embeddings.upsert_embedding(
            object_id=paper.id,
            object_type="paper",
            embedding_model=provider.model_name,
            vector=provider.embed(" ".join(part for part in (paper.title, paper.abstract or "") if part)),
        )
        indexed["papers"] += 1

        for claim in claims.list_claims_for_paper(paper.id):
            context = json.loads(claim.context_json or "{}")
            embeddings.upsert_embedding(
                object_id=claim.id,
                object_type="claim",
                embedding_model=provider.model_name,
                vector=provider.embed(
                    " ".join(
                        part
                        for part in (
                            claim.text,
                            context.get("subject_text"),
                            claim.object_text or "",
                        )
                        if part
                    )
                ),
            )
            indexed["claims"] += 1

    concept_records = concepts.list_concepts()
    for concept in concept_records:
        if paper_id and not _concept_is_used_in_paper(claims, concept.id, paper_id):
            continue
        aliases = json.loads(concept.aliases_json or "[]")
        embeddings.upsert_embedding(
            object_id=concept.id,
            object_type="concept",
            embedding_model=provider.model_name,
            vector=provider.embed(" ".join([concept.name, *aliases])),
        )
        indexed["concepts"] += 1

    return indexed


def _concept_is_used_in_paper(claims: ClaimRepository, concept_id: str, paper_id: str) -> bool:
    return any(
        claim.paper_id == paper_id for claim in claims.list_claims_for_concept(concept_id)
    )
