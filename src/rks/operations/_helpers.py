"""Shared payload formatters used across operations sub-services."""

from __future__ import annotations

import json


# ------------------------------------------------------------------
# Payload formatters
# ------------------------------------------------------------------


def paper_payload(paper) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": json.loads(paper.authors_json),
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "source_type": paper.source_type,
        "source_ref": paper.source_ref,
        "pdf_path": paper.pdf_path,
        "text_artifact_id": paper.text_artifact_id,
        "created_at": paper.created_at,
        "updated_at": paper.updated_at,
    }


def project_payload(project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "research_question": project.research_question,
        "status": project.status,
        "created_by": project.created_by,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def claim_payload(concepts, claim) -> dict:
    context = json.loads(claim.context_json or "{}")
    subject_name = context.get("subject_text")
    object_name = claim.object_text
    if claim.subject_concept_id:
        subject_name = concepts.get_concept(claim.subject_concept_id).name
    if claim.object_concept_id:
        object_name = concepts.get_concept(claim.object_concept_id).name
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
        "created_by": claim.created_by,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
    }


def method_payload(concepts, method) -> dict:
    about_concept = None
    if method.about_concept_id:
        concept = concepts.get_concept(method.about_concept_id)
        about_concept = {"id": concept.id, "name": concept.name}
    return {
        "id": method.id,
        "paper_id": method.paper_id,
        "name": method.name,
        "description": method.description,
        "about_concept": about_concept,
        "created_at": method.created_at,
        "updated_at": method.updated_at,
    }


def dataset_payload(dataset) -> dict:
    return {
        "id": dataset.id,
        "paper_id": dataset.paper_id,
        "name": dataset.name,
        "description": dataset.description,
        "source": dataset.source,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def concept_payload(concept) -> dict:
    return {
        "id": concept.id,
        "name": concept.name,
        "aliases": json.loads(concept.aliases_json or "[]"),
        "domain": concept.domain,
        "parent_concept_id": concept.parent_concept_id,
        "description": concept.description,
        "status": concept.status,
        "created_at": concept.created_at,
        "updated_at": concept.updated_at,
    }


def hypothesis_payload(hypothesis) -> dict:
    return {
        "id": hypothesis.id,
        "project_id": hypothesis.project_id,
        "text": hypothesis.text,
        "status": hypothesis.status,
        "confidence": hypothesis.confidence,
        "context": json.loads(hypothesis.context_json or "{}"),
        "created_by": hypothesis.created_by,
        "created_at": hypothesis.created_at,
        "updated_at": hypothesis.updated_at,
    }


def snapshot_payload(s) -> dict:
    return {
        "id": s.id,
        "snapshot_at": s.snapshot_at,
        "support_count": s.support_count,
        "contradiction_count": s.contradiction_count,
        "refine_count": s.refine_count,
        "paper_count": s.paper_count,
        "claim_count": s.claim_count,
        "consensus_score": s.consensus_score,
        "controversy_score": s.controversy_score,
        "time_bucket": s.time_bucket,
        "basis_layer": s.basis_layer,
    }


def task_payload(task) -> dict:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "paper_id": task.paper_id,
        "mode": task.mode,
        "status": task.status,
        "request_artifact_id": task.request_artifact_id,
        "result_artifact_id": task.result_artifact_id,
        "spec_version": task.spec_version,
        "schema_version": task.schema_version,
        "error": json.loads(task.error_json or "null"),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def edge_payload(edge) -> dict:
    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "source_type": edge.source_type,
        "relation_type": edge.relation_type,
        "target_id": edge.target_id,
        "target_type": edge.target_type,
        "confidence": edge.confidence,
        "created_by": edge.created_by,
        "metadata": json.loads(edge.metadata_json or "{}"),
    }


def note_payload(note) -> dict:
    return {
        "id": note.id,
        "target_id": note.target_id,
        "target_type": note.target_type,
        "content": note.content,
        "created_by": note.created_by,
        "created_at": note.created_at,
    }


# ------------------------------------------------------------------
# Project link helpers
# ------------------------------------------------------------------


def project_link_payload(link) -> dict:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "object_id": link.object_id,
        "object_type": link.object_type,
        "link_type": link.link_type,
        "metadata": json.loads(link.metadata_json or "{}"),
        "created_by": link.created_by,
        "created_at": link.created_at,
    }


def project_paper_entry(link, paper) -> dict:
    return {
        "link": project_link_payload(link),
        "paper": paper_payload(paper),
    }


def project_paper_entries(papers, links: list) -> list[dict]:
    entries = []
    for link in links:
        if link.object_type != "paper":
            continue
        entries.append(project_paper_entry(link, papers.get_paper(link.object_id)))
    return entries


def project_link_entry(link, target_payload: dict) -> dict:
    return {
        "link": project_link_payload(link),
        **target_payload,
    }


def project_link_entries(papers, claims, methods, datasets, concepts, query, links: list) -> list[dict]:
    return [
        project_link_entry(
            link,
            resolve_project_link_target(papers, claims, methods, datasets, concepts, query, link.object_type, link.object_id),
        )
        for link in links
    ]


def resolve_project_link_target(papers, claims, methods, datasets, concepts, query, object_type: str, object_id: str) -> dict:
    if object_type == "paper":
        return {"paper": paper_payload(papers.get_paper(object_id))}
    if object_type == "claim":
        return {"claim": claim_payload(concepts, claims.get_claim(object_id))}
    if object_type == "method":
        return {"method": method_payload(concepts, methods.get_method(object_id))}
    if object_type == "dataset":
        return {"dataset": dataset_payload(datasets.get_dataset(object_id))}
    if object_type == "concept":
        concept = concepts.get_concept(object_id)
        evidence = query.evidence_for(object_id)
        return {
            "concept": {
                **concept_payload(concept),
                "claim_count": len(evidence.get("claims", [])),
                "paper_count": len(evidence.get("papers", [])),
                "method_count": len(evidence.get("methods", [])),
                "dataset_count": len(evidence.get("datasets", [])),
            }
        }
    raise ValueError(f"Unsupported project link object type: {object_type}")


# ------------------------------------------------------------------
# Hypothesis evidence helpers
# ------------------------------------------------------------------


def hypothesis_evidence_link_payload(link) -> dict:
    return {
        "id": link.id,
        "hypothesis_id": link.hypothesis_id,
        "object_id": link.object_id,
        "object_type": link.object_type,
        "relation_type": link.relation_type,
        "metadata": json.loads(link.metadata_json or "{}"),
        "created_by": link.created_by,
        "created_at": link.created_at,
    }


def hypothesis_evidence_entry(link, target_payload: dict) -> dict:
    return {
        "link": hypothesis_evidence_link_payload(link),
        **target_payload,
    }


def hypothesis_evidence_entries(papers, claims, links: list) -> list[dict]:
    return [hypothesis_evidence_entry(link, resolve_hypothesis_evidence_target(papers, claims, link.object_type, link.object_id)) for link in links]


def resolve_hypothesis_evidence_target(papers, claims, object_type: str, object_id: str) -> dict:
    if object_type == "paper":
        return {"paper": paper_payload(papers.get_paper(object_id))}
    if object_type == "claim":
        claim = claims.get_claim(object_id)
        return {
            "claim": {
                "id": claim.id,
                "paper_id": claim.paper_id,
                "text": claim.text,
                "predicate": claim.predicate,
                "confidence": claim.confidence,
                "evidence": json.loads(claim.evidence_json or "{}"),
            }
        }
    raise ValueError(f"Unsupported hypothesis evidence object type: {object_type}")


# ------------------------------------------------------------------
# Misc helpers
# ------------------------------------------------------------------


def optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
