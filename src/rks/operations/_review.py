"""Claim relation promotion, retraction, and candidate management."""

from __future__ import annotations

from rks.operations._helpers import edge_payload


class ReviewOps:
    def __init__(self, *, claims, edges, candidates, evolution, query):
        self.claims = claims
        self.edges = edges
        self.candidates = candidates
        self.evolution = evolution
        self.query = query

    def promote_claim_relation(
        self,
        source_claim_id: str,
        relation_type: str,
        target_claim_id: str,
        *,
        confidence: float = 1.0,
        reviewed_by: str = "agent:review",
        note: str | None = None,
    ) -> dict:
        source_claim = self.claims.get_claim(source_claim_id)
        target_claim = self.claims.get_claim(target_claim_id)
        metadata = {
            "source_paper_id": source_claim.paper_id,
            "target_paper_id": target_claim.paper_id,
        }
        if note:
            metadata["note"] = note
        edge = self.edges.upsert_claim_relation_edge(
            source_id=source_claim.id,
            relation_type=relation_type,
            target_id=target_claim.id,
            confidence=confidence,
            metadata=metadata,
            created_by=reviewed_by,
        )
        return edge_payload(edge)

    def retract_claim_relation(self, source_claim_id: str, relation_type: str, target_claim_id: str) -> dict:
        deleted = self.edges.delete_claim_relation_edge(
            source_id=source_claim_id,
            relation_type=relation_type,
            target_id=target_claim_id,
        )
        return {
            "source_claim_id": source_claim_id,
            "relation_type": relation_type,
            "target_claim_id": target_claim_id,
            "deleted": deleted,
        }

    def materialize_claim_relation_candidates(self, claim_id: str | None = None) -> dict:
        if self.candidates is None:
            return {"error": "candidate repository not available", "materialized": 0}

        from rks.operations._paper import PaperOps  # avoid circular at module level

        claims_to_process = []
        if claim_id:
            claims_to_process.append(self.claims.get_claim(claim_id))
        else:
            # We need papers repo to list all papers — access via edges.conn
            # But ReviewOps doesn't have papers repo. Use claim query instead.
            conn = self.claims.conn
            rows = conn.execute("SELECT id FROM claims").fetchall()
            for row in rows:
                claims_to_process.append(self.claims.get_claim(row["id"]))

        materialized = 0
        for anchor in claims_to_process:
            relations = self.query.claim_relations(anchor.id)
            for rel in relations.get("inferred_relations", []):
                target_id = rel["claim"]["id"]
                self.candidates.upsert_candidate(
                    source_claim_id=anchor.id,
                    target_claim_id=target_id,
                    relation_type=rel["relation_type"],
                    score=rel["claim"].get("confidence"),
                    metadata={
                        "anchor_paper_id": anchor.paper_id,
                        "target_paper_id": rel["claim"].get("paper_id"),
                    },
                )
                materialized += 1
        self.query.clear_relation_cache()
        return {"claim_id": claim_id, "materialized": materialized}

    def list_relation_candidates(self, claim_id: str | None = None, status: str | None = None) -> list[dict]:
        if self.candidates is None:
            return []
        if claim_id:
            records = self.candidates.list_for_claim(claim_id, status=status)
        else:
            records = self.candidates.list_pending()
        return [
            {
                "id": r.id,
                "source_claim_id": r.source_claim_id,
                "target_claim_id": r.target_claim_id,
                "relation_type": r.relation_type,
                "score": r.score,
                "algorithm_version": r.algorithm_version,
                "status": r.status,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in records
        ]

    def promote_candidate(self, candidate_id: str, reviewed_by: str = "agent:review") -> dict:
        if self.candidates is None:
            return {"error": "candidate repository not available"}
        candidate = self.candidates.get_candidate(candidate_id)
        result = self.promote_claim_relation(
            source_claim_id=candidate.source_claim_id,
            relation_type=candidate.relation_type,
            target_claim_id=candidate.target_claim_id,
            reviewed_by=reviewed_by,
        )
        self.candidates.update_status(candidate_id, "promoted")
        result["candidate_id"] = candidate_id
        return result

    def reject_candidate(self, candidate_id: str) -> dict:
        if self.candidates is None:
            return {"error": "candidate repository not available"}
        record = self.candidates.update_status(candidate_id, "rejected")
        return {"candidate_id": candidate_id, "status": record.status}
