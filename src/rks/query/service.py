from __future__ import annotations

import json
import math

from rks.concepts.normalize import canonicalize_term
from rks.providers import LocalHashEmbeddingProvider
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    DatasetRepository,
    EmbeddingRepository,
    EdgeRepository,
    MethodRepository,
    PaperRepository,
)


class QueryService:
    def __init__(
        self,
        papers: PaperRepository,
        claims: ClaimRepository,
        concepts: ConceptRepository,
        edges: EdgeRepository,
        methods: MethodRepository | None = None,
        datasets: DatasetRepository | None = None,
        embeddings: EmbeddingRepository | None = None,
        embedding_provider: LocalHashEmbeddingProvider | None = None,
    ):
        self.papers = papers
        self.claims = claims
        self.concepts = concepts
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.embeddings = embeddings
        self.embedding_provider = embedding_provider or LocalHashEmbeddingProvider()
        self._claim_relations_cache: dict[str, dict] = {}

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

    def search(self, query: str, mode: str = "hybrid") -> dict:
        papers = self.papers.search_papers(query)
        claims = self.claims.search_claims(query)
        concepts = self.concepts.search_concepts(query)
        methods = self.methods.search_methods(query) if self.methods is not None else []
        datasets = self.datasets.search_datasets(query) if self.datasets is not None else []
        semantic = self._semantic_matches(query) if mode in {"semantic", "hybrid"} else {}
        return {
            "query": query,
            "mode": mode,
            "papers": [
                {**self._paper_payload(paper), **semantic.get(("paper", paper.id), {})}
                for paper in papers
            ],
            "claims": [{**self._claim_payload(claim), **semantic.get(("claim", claim.id), {})} for claim in claims],
            "concepts": [
                {
                    "id": concept.id,
                    "name": concept.name,
                    **semantic.get(("concept", concept.id), {}),
                }
                for concept in concepts
            ],
            "methods": [
                {
                    "id": method.id,
                    "paper_id": method.paper_id,
                    "name": method.name,
                    "description": method.description,
                    **semantic.get(("method", method.id), {}),
                }
                for method in methods
            ],
            "datasets": [
                {
                    "id": dataset.id,
                    "paper_id": dataset.paper_id,
                    "name": dataset.name,
                    "description": dataset.description,
                    **semantic.get(("dataset", dataset.id), {}),
                }
                for dataset in datasets
            ],
            "semantic_matches": self._semantic_results(semantic, query) if mode in {"semantic", "hybrid"} else [],
        }

    def evidence_for(self, target: str) -> dict:
        if target.startswith("c_"):
            claim = self.claims.get_claim(target)
            support = self.papers_supporting(target)
            relations = self.claim_relations(target)
            return {
                "target_type": "claim",
                "claim": self._claim_payload(claim),
                "supporting_papers": support["papers"],
                "related_claims": relations["relations"],
            }

        concept = self._resolve_concept(target)
        if concept is None:
            return {"target_type": "concept", "concept": None, "claims": [], "papers": [], "methods": [], "datasets": []}

        concept_claims = self.claims.list_claims_for_concept(concept.id)
        paper_ids = sorted({claim.paper_id for claim in concept_claims})
        papers = [self._paper_payload(self.papers.get_paper(paper_id)) for paper_id in paper_ids]
        methods = []
        datasets = []
        if self.methods is not None:
            methods = [
                {
                    "id": method.id,
                    "paper_id": method.paper_id,
                    "name": method.name,
                    "description": method.description,
                }
                for paper_id in paper_ids
                for method in self.methods.list_methods_for_paper(paper_id)
                if canonicalize_term(method.name) == canonicalize_term(concept.name)
            ]
        if self.datasets is not None:
            datasets = [
                {
                    "id": dataset.id,
                    "paper_id": dataset.paper_id,
                    "name": dataset.name,
                    "description": dataset.description,
                }
                for paper_id in paper_ids
                for dataset in self.datasets.list_datasets_for_paper(paper_id)
            ]
        return {
            "target_type": "concept",
            "concept": {"id": concept.id, "name": concept.name},
            "claims": [self._claim_payload(claim) for claim in concept_claims],
            "papers": papers,
            "methods": methods,
            "datasets": datasets,
        }

    def claim_relations(self, claim_id: str) -> dict:
        cached = self._claim_relations_cache.get(claim_id)
        if cached is not None:
            return cached

        anchor = self.claims.get_claim(claim_id)
        reviewed_relations = self._reviewed_claim_relations(anchor.id)
        reviewed_keys = {
            (relation["relation_type"], relation["claim"]["id"], relation["direction"])
            for relation in reviewed_relations
        }

        # Narrow candidate set: only compare claims sharing a concept with the anchor
        candidate_claims = self._related_candidate_claims(anchor, claim_id)

        inferred_relations = []
        for candidate in candidate_claims:
            relation = self._infer_claim_relation(anchor, candidate)
            if relation is None:
                continue
            dedupe_key = (relation, candidate.id, "outgoing")
            if dedupe_key in reviewed_keys:
                continue
            inferred_relations.append(
                {
                    "relation_type": relation,
                    "relation_source": "inferred",
                    "direction": "outgoing",
                    "claim": self._claim_payload(candidate),
                    "paper": self._paper_payload(self.papers.get_paper(candidate.paper_id)),
                }
            )
        result = {
            "claim": self._claim_payload(anchor),
            "reviewed_relations": reviewed_relations,
            "inferred_relations": inferred_relations,
            "relations": reviewed_relations + inferred_relations,
        }
        self._claim_relations_cache[claim_id] = result
        return result

    def clear_relation_cache(self) -> None:
        """Clear the per-request claim relations cache."""
        self._claim_relations_cache.clear()

    def _related_candidate_claims(self, anchor, claim_id: str) -> list:
        """Return claims that share a concept with the anchor, falling back to all claims."""
        concept_ids = set()
        if anchor.subject_concept_id:
            concept_ids.add(anchor.subject_concept_id)
        if anchor.object_concept_id:
            concept_ids.add(anchor.object_concept_id)

        if concept_ids:
            seen = set()
            candidates = []
            for cid in concept_ids:
                for claim in self.claims.list_claims_for_concept(cid):
                    if claim.id != claim_id and claim.id not in seen:
                        seen.add(claim.id)
                        candidates.append(claim)
            if candidates:
                return candidates

        # Fallback: scan all claims (preserves original behavior for unlinked claims)
        candidates = []
        for paper in self.papers.list_papers():
            for claim in self.claims.list_claims_for_paper(paper.id):
                if claim.id != claim_id:
                    candidates.append(claim)
        return candidates

    def methods_for(self, target: str) -> dict:
        if target.startswith("p_"):
            methods = self.methods.list_methods_for_paper(target) if self.methods is not None else []
            return {
                "paper": self._paper_payload(self.papers.get_paper(target)),
                "methods": [
                    {"id": method.id, "name": method.name, "description": method.description}
                    for method in methods
                ],
            }
        concept = self._resolve_concept(target)
        methods = []
        if self.methods is not None and concept is not None:
            for paper in self.papers.list_papers():
                methods.extend(
                    method
                    for method in self.methods.list_methods_for_paper(paper.id)
                    if canonicalize_term(method.name) == canonicalize_term(concept.name)
                )
        return {
            "concept": None if concept is None else {"id": concept.id, "name": concept.name},
            "methods": [
                {"id": method.id, "paper_id": method.paper_id, "name": method.name, "description": method.description}
                for method in methods
            ],
        }

    def datasets_for(self, target: str) -> dict:
        if target.startswith("p_"):
            datasets = self.datasets.list_datasets_for_paper(target) if self.datasets is not None else []
            return {
                "paper": self._paper_payload(self.papers.get_paper(target)),
                "datasets": [
                    {"id": dataset.id, "name": dataset.name, "description": dataset.description}
                    for dataset in datasets
                ],
            }
        if target.startswith("m_"):
            edges = self.edges.list_edges_for_object(target)
            datasets = []
            if self.datasets is not None:
                for edge in edges:
                    if edge.source_id == target and edge.relation_type == "evaluated_on":
                        datasets.append(self.datasets.get_dataset(edge.target_id))
            return {
                "method_id": target,
                "datasets": [
                    {"id": dataset.id, "paper_id": dataset.paper_id, "name": dataset.name, "description": dataset.description}
                    for dataset in datasets
                ],
            }
        return {"datasets": []}

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
            "context": context,
            "evidence": json.loads(claim.evidence_json or "{}"),
        }

    def _reviewed_claim_relations(self, claim_id: str) -> list[dict]:
        relations = []
        for edge in self.edges.list_claim_relation_edges(claim_id):
            related_claim_id = edge.target_id if edge.source_id == claim_id else edge.source_id
            related_claim = self.claims.get_claim(related_claim_id)
            metadata = json.loads(edge.metadata_json or "{}")
            relations.append(
                {
                    "edge_id": edge.id,
                    "relation_type": edge.relation_type,
                    "relation_source": "reviewed",
                    "direction": "outgoing" if edge.source_id == claim_id else "incoming",
                    "claim": self._claim_payload(related_claim),
                    "paper": self._paper_payload(self.papers.get_paper(related_claim.paper_id)),
                    "confidence": edge.confidence,
                    "created_by": edge.created_by,
                    "metadata": metadata,
                }
            )
        return relations

    def _paper_payload(self, paper) -> dict:
        return {
            "id": paper.id,
            "title": paper.title,
            "source_type": paper.source_type,
            "source_ref": paper.source_ref,
        }

    def _semantic_matches(self, query: str) -> dict[tuple[str, str], dict]:
        if self.embeddings is None:
            return {}
        vector = self.embedding_provider.embed(query)
        matches: dict[tuple[str, str], dict] = {}
        for row in self.embeddings.list_embeddings(["paper", "claim", "concept"], self.embedding_provider.model_name):
            candidate = json.loads(row["vector_json"])
            score = self.embedding_provider.cosine_similarity(vector, candidate)
            if score < 0.2:
                continue
            matches[(row["object_type"], row["object_id"])] = {"semantic_score": round(score, 4)}

        if self.methods is not None:
            for method in self.methods.search_methods(query):
                score = self.embedding_provider.cosine_similarity(
                    vector, self.embedding_provider.embed(" ".join(part for part in (method.name, method.description or "") if part))
                )
                if score >= 0.2:
                    matches[("method", method.id)] = {"semantic_score": round(score, 4)}

        if self.datasets is not None:
            for dataset in self.datasets.search_datasets(query):
                score = self.embedding_provider.cosine_similarity(
                    vector, self.embedding_provider.embed(" ".join(part for part in (dataset.name, dataset.description or "") if part))
                )
                if score >= 0.2:
                    matches[("dataset", dataset.id)] = {"semantic_score": round(score, 4)}
        return matches

    def _semantic_results(self, semantic: dict[tuple[str, str], dict], query: str) -> list[dict]:
        results = []
        for (object_type, object_id), payload in sorted(
            semantic.items(), key=lambda item: item[1]["semantic_score"], reverse=True
        )[:10]:
            label = object_id
            if object_type == "paper":
                label = self.papers.get_paper(object_id).title
            elif object_type == "claim":
                label = self.claims.get_claim(object_id).text
            elif object_type == "concept":
                label = self.concepts.get_concept(object_id).name
            elif object_type == "method" and self.methods is not None:
                label = self.methods.get_method(object_id).name
            elif object_type == "dataset" and self.datasets is not None:
                label = self.datasets.get_dataset(object_id).name
            results.append(
                {
                    "object_type": object_type,
                    "object_id": object_id,
                    "label": label,
                    "semantic_score": payload["semantic_score"],
                    "query": query,
                }
            )
        return results

    def _infer_claim_relation(self, anchor, candidate) -> str | None:
        anchor_context = json.loads(anchor.context_json or "{}")
        candidate_context = json.loads(candidate.context_json or "{}")
        anchor_subject = canonicalize_term(anchor_context.get("subject_text", "")) if anchor_context.get("subject_text") else ""
        candidate_subject = (
            canonicalize_term(candidate_context.get("subject_text", "")) if candidate_context.get("subject_text") else ""
        )
        anchor_object = canonicalize_term(anchor.object_text or "")
        candidate_object = canonicalize_term(candidate.object_text or "")

        if anchor_subject and anchor_subject == candidate_subject:
            if _claim_polarity(anchor.text) * _claim_polarity(candidate.text) < 0:
                return "contradicts"

        if anchor_subject and anchor_subject == candidate_subject and anchor.predicate == candidate.predicate:
            if anchor_context.get("dataset") != candidate_context.get("dataset") and (
                anchor_context.get("dataset") or candidate_context.get("dataset")
            ):
                return "refines"
            if anchor_object == candidate_object or (anchor_object and candidate_object and anchor_object in candidate_object):
                return "supports"
        return None


def _claim_polarity(text: str) -> int:
    lowered = text.lower()
    if "not improve" in lowered or "does not improve" in lowered or "did not improve" in lowered:
        return -1
    positive = any(token in lowered for token in ("improv", "outperform", "increase", "support"))
    negative = any(token in lowered for token in ("fail", "hurt", "degrade", "worse", "not"))
    if positive and not negative:
        return 1
    if negative and not positive:
        return -1
    return 0
