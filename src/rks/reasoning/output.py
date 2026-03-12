from __future__ import annotations

from rks.concepts.normalize import canonicalize_term


def build_research_answer(query_service, question: str) -> dict:
    context = _topic_context(query_service, question)
    return build_scoped_answer(query_service, "topic", question, context)


def build_scoped_answer(query_service, scope_type: str, scope_label: str, context: dict, *, question: str | None = None) -> dict:
    resolved_question = question or scope_label
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=3)
    key_claims = context["claims"][:5]
    key_findings = [claim["text"] for claim in key_claims[:3]]
    evidence_assessment = _evidence_assessment(context, disagreements)
    confidence = _answer_confidence(evidence_assessment)
    uncertainties = []
    if not key_claims:
        uncertainties.append(f"No grounded claims matched the current {scope_type} yet.")
    if disagreements:
        uncertainties.append("Relevant claims include disagreement signals that need review or replication.")
    if len(context["papers"]) < 2:
        uncertainties.append("The answer is grounded in a narrow paper set.")

    recommendations = _next_steps_from_context(context, disagreements)
    answer = _compose_answer_text(resolved_question, context, key_findings, disagreements, uncertainties, recommendations)
    conclusion = _compose_conclusion(resolved_question, context, key_claims, disagreements, confidence)
    return {
        "scope_type": scope_type,
        "scope_label": scope_label,
        "question": resolved_question,
        "conclusion": conclusion,
        "confidence": confidence,
        "answer": answer,
        "key_findings": key_findings,
        "supporting_claims": key_claims,
        "supporting_papers": context["papers"][:5],
        "methods": context["methods"][:5],
        "datasets": context["datasets"][:5],
        "evidence_assessment": evidence_assessment,
        "counterevidence": _counterevidence_payload(disagreements),
        "disagreements": disagreements,
        "uncertainties": uncertainties,
        "next_steps": recommendations,
        "recommendations": recommendations,
    }


def build_scoped_brief(
    query_service,
    scope_type: str,
    scope_label: str,
    context: dict,
    *,
    hypotheses: list[dict] | None = None,
    research_question: str | None = None,
) -> dict:
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=4)
    evidence_assessment = _evidence_assessment(context, disagreements)
    overview = _compose_brief_overview(scope_label, context, disagreements)
    open_questions = []
    if disagreements:
        open_questions.append(f"Why do the strongest claims for {scope_label} disagree?")
    if context["methods"] and not context["datasets"]:
        open_questions.append("Which datasets should the observed methods be evaluated on next?")
    if not context["claims"]:
        open_questions.append(f"Which papers should be extracted next to ground {scope_label} better?")
    payload = {
        "scope_type": scope_type,
        "scope_label": scope_label,
        "overview": overview,
        "state_of_topic": {
            "evidence_strength": evidence_assessment["evidence_strength"],
            "paper_count": evidence_assessment["paper_count"],
            "claim_count": evidence_assessment["claim_count"],
            "method_count": evidence_assessment["method_count"],
            "dataset_count": evidence_assessment["dataset_count"],
            "reviewed_disagreement_count": evidence_assessment["reviewed_disagreement_count"],
            "inferred_disagreement_count": evidence_assessment["inferred_disagreement_count"],
        },
        "representative_papers": context["papers"][:5],
        "reading_list": _reading_list(context, disagreements),
        "reading_navigation": _reading_navigation(context, disagreements),
        "key_claims": context["claims"][:6],
        "methods": context["methods"][:6],
        "datasets": context["datasets"][:6],
        "disagreements": disagreements,
        "evidence_gaps": _evidence_gaps(context, disagreements),
        "open_questions": open_questions,
    }
    if hypotheses is not None:
        payload["hypotheses"] = hypotheses
    if research_question is not None:
        payload["research_question"] = research_question
    return payload


def build_topic_brief(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    return build_scoped_brief(query_service, "topic", topic, context)


def build_topic_reading_list(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    return build_scoped_reading_list(query_service, "topic", topic, context)


def build_scoped_reading_list(query_service, scope_type: str, scope_label: str, context: dict) -> dict:
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=4)
    navigation = _reading_navigation(context, disagreements)
    summary = (
        f"{scope_label} has {len(navigation['reading_sequence'])} prioritized reading step(s) in the current graph."
        if navigation["reading_sequence"]
        else f"No grounded reading path could be assembled for {scope_label} yet."
    )
    return {
        "scope_type": scope_type,
        "scope_label": scope_label,
        "summary": summary,
        "entry_papers": navigation["entry_papers"],
        "representative_papers": navigation["representative_papers"],
        "contradiction_papers": navigation["contradiction_papers"],
        "reading_sequence": navigation["reading_sequence"],
    }


def build_topic_disagreements(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    return build_scoped_disagreements(query_service, "topic", topic, context)


def build_scoped_disagreements(query_service, scope_type: str, scope_label: str, context: dict) -> dict:
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=6)
    summary = (
        f"{scope_label} currently has {len(disagreements)} surfaced disagreement signals."
        if disagreements
        else f"No contradictions or refinements were surfaced for {scope_label}."
    )
    return {
        "scope_type": scope_type,
        "scope_label": scope_label,
        "summary": summary,
        "disagreements": disagreements,
        "claim_count_considered": len(context["claim_ids"]),
        "review_priorities": _review_priorities(disagreements),
    }


def build_topic_open_questions(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    return build_scoped_open_questions(query_service, "topic", topic, context)


def build_scoped_open_questions(
    query_service,
    scope_type: str,
    scope_label: str,
    context: dict,
    *,
    hypotheses: list[dict] | None = None,
) -> dict:
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=6)
    questions = []
    if disagreements:
        first = disagreements[0]
        questions.append(
            {
                "kind": "disagreement_resolution",
                "question": f"Why does {first['related_claim']['text']} conflict with {first['anchor_claim']['text']}?",
                "why_it_matters": "A resolved contradiction changes whether the topic supports a stable conclusion or a replication target.",
                "grounding": {
                    "claim_ids": [first["anchor_claim"]["id"], first["related_claim"]["id"]],
                    "paper_ids": sorted({first["anchor_claim"]["paper_id"], first["related_claim"]["paper_id"]}),
                },
                "next_step": first["recommended_review"],
            }
        )
    if context["methods"] and not context["datasets"]:
        questions.append(
            {
                "kind": "evaluation_gap",
                "question": f"Which datasets should the visible {scope_label} methods be evaluated on next?",
                "why_it_matters": "Method coverage without evaluation coverage makes it hard to compare results or plan experiments.",
                "grounding": {
                    "method_ids": [method["id"] for method in context["methods"][:3]],
                    "paper_ids": [method["paper_id"] for method in context["methods"][:3]],
                },
                "next_step": "Run dataset extraction or inspect evaluation evidence for the leading method papers.",
            }
        )
    if len(context["papers"]) < 3:
        questions.append(
            {
                "kind": "coverage_gap",
                "question": f"Which additional papers should be ingested to broaden the evidence base for {scope_label}?",
                "why_it_matters": "A narrow paper set weakens synthesis and often hides counterexamples or alternative methods.",
                "grounding": {
                    "paper_ids": [paper["id"] for paper in context["papers"][:3]],
                },
                "next_step": "Search for more papers on the topic and ingest the strongest missing anchors.",
            }
        )
    if context["claims"] and not context["methods"]:
        questions.append(
            {
                "kind": "structure_gap",
                "question": f"Which method entities still need to be extracted or normalized for {scope_label}?",
                "why_it_matters": "Claims without method structure are hard to compare and reason about experimentally.",
                "grounding": {
                    "claim_ids": [claim["id"] for claim in context["claims"][:3]],
                    "paper_ids": [claim["paper_id"] for claim in context["claims"][:3]],
                },
                "next_step": "Run method extraction on the lead papers and review the resulting entities.",
            }
        )
    if hypotheses:
        questions.append(
            {
                "kind": "hypothesis_review",
                "question": f"Which project hypotheses for {scope_label} still lack strong claim-level review?",
                "why_it_matters": "Project hypotheses are only useful when they stay explicitly connected to inspectable evidence.",
                "grounding": {
                    "hypothesis_ids": [item["id"] for item in hypotheses[:4]],
                    "paper_ids": [paper["id"] for paper in context["papers"][:3]],
                },
                "next_step": "Inspect the leading hypotheses and add claim-level support or contradiction links where evidence is still paper-only.",
            }
        )
    summary = (
        f"{scope_label} currently has {len(questions)} grounded open question(s)."
        if questions
        else f"No grounded open questions were surfaced for {scope_label}."
    )
    payload = {
        "scope_type": scope_type,
        "scope_label": scope_label,
        "summary": summary,
        "open_questions": questions[:6],
        "evidence_gaps": _evidence_gaps(context, disagreements),
    }
    if hypotheses is not None:
        payload["hypotheses"] = hypotheses
    return payload


def build_topic_review_priorities(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    return build_scoped_review_priorities(query_service, "topic", topic, context)


def build_scoped_review_priorities(query_service, scope_type: str, scope_label: str, context: dict) -> dict:
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=6)
    review_priorities = _review_priorities(disagreements)
    replication_risks = _replication_risks(disagreements)
    summary = (
        f"{scope_label} currently has {len(review_priorities)} review priority item(s) and {len(replication_risks)} replication risk(s)."
        if review_priorities or replication_risks
        else f"No review-priority signals were surfaced for {scope_label}."
    )
    return {
        "scope_type": scope_type,
        "scope_label": scope_label,
        "summary": summary,
        "review_priorities": review_priorities,
        "replication_risks": replication_risks,
    }


def build_research_opportunities(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    return build_scoped_opportunities(query_service, "topic", topic, context)


def build_scoped_opportunities(query_service, scope_type: str, scope_label: str, context: dict) -> dict:
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=6)
    opportunities = []
    for disagreement in disagreements[:3]:
        opportunities.append(
            {
                "suggestion_type": "conflict_resolution",
                "kind": "resolve_disagreement",
                "title": f"Resolve {disagreement['relation_type']} around {disagreement['anchor_claim']['text']}",
                "reasoning": disagreement["summary"],
                "claim_ids": [disagreement["anchor_claim"]["id"], disagreement["related_claim"]["id"]],
                "paper_ids": sorted(
                    {
                        disagreement["anchor_claim"]["paper_id"],
                        disagreement["related_claim"]["paper_id"],
                    }
                ),
                "grounding_strength": "reviewed" if disagreement["relation_source"] == "reviewed" else "inferred",
                "evidence_basis": {
                    "signal": "claim_relation",
                    "relation_type": disagreement["relation_type"],
                    "relation_source": disagreement["relation_source"],
                    "claim_ids": [disagreement["anchor_claim"]["id"], disagreement["related_claim"]["id"]],
                    "paper_ids": sorted(
                        {
                            disagreement["anchor_claim"]["paper_id"],
                            disagreement["related_claim"]["paper_id"],
                        }
                    ),
                },
                "validation_plan": [
                    "Compare the datasets and evaluation setup attached to each claim.",
                    "Review the evidence sections or extracted context for both papers.",
                    "Promote a reviewed relation only after the conflict cause is understood.",
                ],
                "next_step": "Compare datasets, evaluation setup, and evidence sections across the conflicting claims.",
            }
        )

    all_topic_dataset_ids = {dataset["id"] for dataset in context["datasets"]}
    for method in context["methods"][:5]:
        method_datasets_payload = query_service.datasets_for(method["id"])
        evaluated_dataset_ids = {dataset["id"] for dataset in method_datasets_payload.get("datasets", [])}
        if not evaluated_dataset_ids:
            opportunities.append(
                {
                    "suggestion_type": "coverage_gap",
                    "kind": "evaluate_method",
                    "title": f"Evaluate {method['name']} on a grounded dataset",
                    "reasoning": f"{method['name']} appears in the topic context without an explicit evaluated_on dataset edge.",
                    "method_ids": [method["id"]],
                    "dataset_ids": [],
                    "paper_ids": [method["paper_id"]],
                    "grounding_strength": "medium",
                    "evidence_basis": {
                        "signal": "method_without_dataset",
                        "method_ids": [method["id"]],
                        "paper_ids": [method["paper_id"]],
                    },
                    "validation_plan": [
                        "Check whether dataset extraction missed an evaluation edge for this method.",
                        "Read the method paper to confirm whether evaluation data is actually present.",
                    ],
                    "next_step": "Run dataset extraction review or add evaluation evidence for this method.",
                }
            )
            continue
        missing_dataset_ids = sorted(all_topic_dataset_ids - evaluated_dataset_ids)
        if missing_dataset_ids:
            opportunities.append(
                {
                    "suggestion_type": "coverage_gap",
                    "kind": "broaden_evaluation",
                    "title": f"Broaden evaluation for {method['name']}",
                    "reasoning": f"{method['name']} is linked to only {len(evaluated_dataset_ids)} dataset(s) while the topic context includes additional datasets.",
                    "method_ids": [method["id"]],
                    "dataset_ids": missing_dataset_ids[:3],
                    "paper_ids": [method["paper_id"]],
                    "grounding_strength": "medium",
                    "evidence_basis": {
                        "signal": "topic_dataset_gap",
                        "method_ids": [method["id"]],
                        "dataset_ids": missing_dataset_ids[:3],
                        "paper_ids": [method["paper_id"]],
                    },
                    "validation_plan": [
                        "Check whether the method has been evaluated on the missing topic datasets elsewhere in the graph.",
                        "If not, prioritize a comparison on one of the uncovered datasets.",
                    ],
                    "next_step": "Check whether this method should be compared on additional datasets already discussed in the topic.",
                }
            )

    if not context["claims"]:
        opportunities.append(
            {
                "suggestion_type": "grounding_gap",
                "kind": "expand_grounding",
                "title": f"Expand extracted grounding for {scope_label}",
                "reasoning": "The topic has too little extracted claim structure to support synthesis.",
                "claim_ids": [],
                "paper_ids": [paper["id"] for paper in context["papers"][:3]],
                "grounding_strength": "low",
                "evidence_basis": {
                    "signal": "missing_claim_structure",
                    "paper_ids": [paper["id"] for paper in context["papers"][:3]],
                },
                "validation_plan": [
                    "Run claim extraction on the most relevant paper set.",
                    "Re-run the output surfaces after the graph has non-empty claim structure.",
                ],
                "next_step": "Ingest more relevant papers or run claim extraction on already-ingested sources.",
            }
        )

    if context["claims"] and not context["methods"]:
        opportunities.append(
            {
                "suggestion_type": "structure_gap",
                "kind": "extract_methods",
                "title": f"Extract method structure for {scope_label}",
                "reasoning": "Claims exist, but method coverage is thin in the current topic view.",
                "claim_ids": [claim["id"] for claim in context["claims"][:3]],
                "paper_ids": [claim["paper_id"] for claim in context["claims"][:3]],
                "grounding_strength": "medium",
                "evidence_basis": {
                    "signal": "missing_method_structure",
                    "claim_ids": [claim["id"] for claim in context["claims"][:3]],
                    "paper_ids": [claim["paper_id"] for claim in context["claims"][:3]],
                },
                "validation_plan": [
                    "Run method extraction on the leading papers for this topic.",
                    "Check whether method entities need manual review or promotion.",
                ],
                "next_step": "Run or review method extraction to enrich comparisons and future opportunity generation.",
            }
        )

    if context["claims"] and not context["datasets"]:
        opportunities.append(
            {
                "suggestion_type": "structure_gap",
                "kind": "extract_datasets",
                "title": f"Extract dataset structure for {scope_label}",
                "reasoning": "Claim evidence exists, but dataset coverage is sparse.",
                "claim_ids": [claim["id"] for claim in context["claims"][:3]],
                "paper_ids": [claim["paper_id"] for claim in context["claims"][:3]],
                "grounding_strength": "medium",
                "evidence_basis": {
                    "signal": "missing_dataset_structure",
                    "claim_ids": [claim["id"] for claim in context["claims"][:3]],
                    "paper_ids": [claim["paper_id"] for claim in context["claims"][:3]],
                },
                "validation_plan": [
                    "Run dataset extraction on the anchor papers for this topic.",
                    "Review whether dataset references were missed in current artifacts.",
                ],
                "next_step": "Run or review dataset extraction to support better benchmarking and opportunity analysis.",
            }
        )

    summary = (
        f"{scope_label} has {len(opportunities)} surfaced research opportunities."
        if opportunities
        else f"No grounded research opportunities were surfaced for {scope_label}."
    )
    return {
        "scope_type": scope_type,
        "scope_label": scope_label,
        "summary": summary,
        "opportunities": opportunities[:8],
        "disagreements": disagreements,
        "opportunity_count": len(opportunities[:8]),
    }


def build_comparison(query_service, left: str, right: str) -> dict:
    left_target = _resolve_target(query_service, left)
    right_target = _resolve_target(query_service, right)
    shared_points = _shared_points(left_target, right_target)
    differences = _differences(left_target, right_target)
    recommendations = _comparison_recommendations(left_target, right_target, differences)
    return {
        "left": left_target,
        "right": right_target,
        "comparison_type": f"{left_target['type']}_vs_{right_target['type']}",
        "summary": _comparison_summary(left_target, right_target, shared_points, differences),
        "shared_points": shared_points,
        "differences": differences,
        "recommendations": recommendations,
    }


def _topic_context(query_service, topic: str) -> dict:
    search = query_service.search(topic, mode="hybrid")
    semantic_claims = []
    semantic_papers = []
    semantic_concepts = []
    semantic_methods = []
    semantic_datasets = []
    for match in search.get("semantic_matches", []):
        object_type = match["object_type"]
        object_id = match["object_id"]
        if object_type == "claim":
            semantic_claims.append(query_service._claim_payload(query_service.claims.get_claim(object_id)))
        elif object_type == "paper":
            semantic_papers.append(query_service._paper_payload(query_service.papers.get_paper(object_id)))
        elif object_type == "concept":
            concept = query_service.concepts.get_concept(object_id)
            semantic_concepts.append({"id": concept.id, "name": concept.name})
        elif object_type == "method" and query_service.methods is not None:
            method = query_service.methods.get_method(object_id)
            semantic_methods.append(
                {"id": method.id, "paper_id": method.paper_id, "name": method.name, "description": method.description}
            )
        elif object_type == "dataset" and query_service.datasets is not None:
            dataset = query_service.datasets.get_dataset(object_id)
            semantic_datasets.append(
                {
                    "id": dataset.id,
                    "paper_id": dataset.paper_id,
                    "name": dataset.name,
                    "description": dataset.description,
                }
            )

    concept = search["concepts"][0] if search["concepts"] else (semantic_concepts[0] if semantic_concepts else None)
    concept_claims = []
    concept_methods = []
    if concept is not None:
        concept_claims = query_service.claims_about(concept["id"]).get("claims", [])
        concept_methods = query_service.methods_for(concept["id"]).get("methods", [])

    claims = _cluster_and_rank_claims(query_service, _dedupe_objects(concept_claims + search["claims"] + semantic_claims))
    claim_ids = [claim["id"] for claim in claims[:8]]

    papers = _dedupe_objects(search["papers"] + semantic_papers)
    for claim in claims[:5]:
        support = query_service.papers_supporting(claim["id"])
        papers = _dedupe_objects(papers + support.get("papers", []))
    disagreements = _collect_disagreements(query_service, claim_ids, limit=6)
    papers = _rank_papers(papers, claims, disagreements)

    methods = _dedupe_objects(concept_methods + search["methods"] + semantic_methods)
    datasets = _dedupe_objects(search["datasets"] + semantic_datasets)
    for method in methods[:5]:
        datasets = _dedupe_objects(datasets + query_service.datasets_for(method["id"]).get("datasets", []))

    return {
        "search": search,
        "concept": concept,
        "claims": claims,
        "claim_ids": claim_ids,
        "papers": papers,
        "methods": methods,
        "datasets": datasets,
    }


def _collect_disagreements(query_service, claim_ids: list[str], limit: int) -> list[dict]:
    disagreements = []
    seen = set()
    for claim_id in claim_ids[:6]:
        payload = query_service.claim_relations(claim_id)
        anchor_claim = payload["claim"]
        for relation in payload["reviewed_relations"] + payload["inferred_relations"]:
            if relation["relation_type"] not in {"contradicts", "refines"}:
                continue
            related_claim = relation["claim"]
            pair_key = tuple(sorted((anchor_claim["id"], related_claim["id"]))) + (relation["relation_type"],)
            if pair_key in seen:
                continue
            seen.add(pair_key)
            disagreements.append(
                {
                    "relation_type": relation["relation_type"],
                    "relation_source": relation["relation_source"],
                    "anchor_claim": anchor_claim,
                    "related_claim": related_claim,
                    "paper": relation["paper"],
                    "disagreement_kind": _disagreement_kind(anchor_claim, related_claim, relation),
                    "possible_causes": _possible_causes(anchor_claim, related_claim, relation),
                    "recommended_review": _recommended_review(anchor_claim, related_claim, relation),
                    "summary": _disagreement_summary(anchor_claim, related_claim, relation),
                }
            )
            if len(disagreements) >= limit:
                return disagreements
    return disagreements


def _cluster_and_rank_claims(query_service, claims: list[dict]) -> list[dict]:
    relation_cache = {}
    groups: dict[str, list[dict]] = {}
    for claim in claims:
        enriched = {**claim, **_claim_relation_stats(query_service, claim["id"], relation_cache)}
        groups.setdefault(_claim_cluster_signature(claim), []).append(enriched)

    representatives = []
    for group in groups.values():
        ranked_group = sorted(group, key=_claim_rank_key, reverse=True)
        representative = dict(ranked_group[0])
        representative["cluster_size"] = len(ranked_group)
        representative["corroborating_claim_ids"] = [item["id"] for item in ranked_group]
        representative["evidence_paper_ids"] = sorted({item["paper_id"] for item in ranked_group})
        representative["cluster_confidences"] = [item.get("confidence") for item in ranked_group if item.get("confidence") is not None]
        representatives.append(representative)
    return sorted(representatives, key=_claim_rank_key, reverse=True)


def _claim_relation_stats(query_service, claim_id: str, cache: dict[str, dict]) -> dict:
    if claim_id in cache:
        return cache[claim_id]
    relations = query_service.claim_relations(claim_id)
    reviewed_relation_count = len(relations["reviewed_relations"])
    inferred_relation_count = len(relations["inferred_relations"])
    stats = {
        "reviewed_relation_count": reviewed_relation_count,
        "inferred_relation_count": inferred_relation_count,
    }
    cache[claim_id] = stats
    return stats


def _claim_cluster_signature(claim: dict) -> str:
    return "|".join(
        [
            canonicalize_term(claim.get("subject") or ""),
            canonicalize_term(claim.get("predicate") or ""),
            canonicalize_term(claim.get("object") or ""),
            canonicalize_term(_claim_dataset(claim) or ""),
            str(_claim_polarity(claim.get("text", ""))),
        ]
    )


def _claim_rank_key(claim: dict) -> tuple:
    confidence = claim.get("confidence") or 0.0
    cluster_size = claim.get("cluster_size") or 1
    evidence_span = len(claim.get("evidence_paper_ids") or [claim.get("paper_id")])
    return (
        claim.get("reviewed_relation_count", 0),
        cluster_size,
        confidence,
        evidence_span,
        -claim.get("inferred_relation_count", 0),
    )


def _rank_papers(papers: list[dict], claims: list[dict], disagreements: list[dict]) -> list[dict]:
    scores = {paper["id"]: 0.0 for paper in papers}
    for index, claim in enumerate(claims[:6]):
        weight = max(1, 6 - index)
        for paper_id in claim.get("evidence_paper_ids") or [claim.get("paper_id")]:
            scores[paper_id] = scores.get(paper_id, 0.0) + weight + (claim.get("cluster_size", 1) - 1)
            scores[paper_id] += float(claim.get("reviewed_relation_count", 0)) * 1.5
            scores[paper_id] += float(claim.get("confidence") or 0.0)
    for disagreement in disagreements:
        for paper_id in {
            disagreement["anchor_claim"]["paper_id"],
            disagreement["related_claim"]["paper_id"],
            disagreement["paper"]["id"],
        }:
            scores[paper_id] = scores.get(paper_id, 0.0) + (2.0 if disagreement["relation_source"] == "reviewed" else 1.0)
    return sorted(papers, key=lambda paper: (scores.get(paper["id"], 0.0), paper["title"]), reverse=True)


def _compose_answer_text(
    question: str,
    context: dict,
    key_findings: list[str],
    disagreements: list[dict],
    uncertainties: list[str],
    next_steps: list[str],
) -> str:
    parts = [f"Question: {question}."]
    if key_findings:
        parts.append("Grounded findings: " + "; ".join(key_findings[:3]) + ".")
    elif context["papers"]:
        parts.append("The topic is present in the graph, but extracted claims are still sparse.")
    else:
        parts.append("The current graph does not contain enough relevant evidence to answer confidently.")
    if context["methods"]:
        parts.append("Methods in scope: " + ", ".join(method["name"] for method in context["methods"][:3]) + ".")
    if context["datasets"]:
        parts.append("Datasets in scope: " + ", ".join(dataset["name"] for dataset in context["datasets"][:3]) + ".")
    if disagreements:
        parts.append("Disagreement signals are present and should be considered before taking the answer as settled.")
    if uncertainties:
        parts.append("Uncertainties: " + "; ".join(uncertainties[:3]) + ".")
    if next_steps:
        parts.append("Suggested next steps: " + "; ".join(next_steps[:3]) + ".")
    return " ".join(parts)


def _compose_conclusion(question: str, context: dict, key_claims: list[dict], disagreements: list[dict], confidence: str) -> str:
    if key_claims:
        leading = key_claims[0]["text"]
        if disagreements:
            return (
                f"{question} is best answered with {confidence} confidence: the strongest grounded claim is "
                f"'{leading}', but disagreement signals remain unresolved."
            )
        return f"{question} is best answered with {confidence} confidence: {leading}"
    if context["papers"]:
        return f"{question} has relevant papers in scope, but extracted claim structure is still too thin for a confident conclusion."
    return f"{question} cannot be answered confidently from the current graph yet."


def _compose_brief_overview(topic: str, context: dict, disagreements: list[dict]) -> str:
    parts = [
        f"{topic} currently spans {len(context['papers'])} representative paper(s), {len(context['claims'])} grounded claim(s), {len(context['methods'])} method(s), and {len(context['datasets'])} dataset(s) in the local graph."
    ]
    if context["claims"]:
        parts.append("Leading claims include " + "; ".join(claim["text"] for claim in context["claims"][:3]) + ".")
    if disagreements:
        parts.append(f"There are {len(disagreements)} surfaced contradiction or refinement signals in this topic.")
    return " ".join(parts)


def _next_steps_from_context(context: dict, disagreements: list[dict]) -> list[str]:
    steps = []
    if disagreements:
        steps.append("Review the contradictory or refining claims before acting on a single conclusion.")
    if context["methods"] and not context["datasets"]:
        steps.append("Run dataset extraction or review evaluation edges for the visible methods.")
    if len(context["papers"]) < 3:
        steps.append("Ingest more papers to widen the evidence base for this topic.")
    if not context["claims"] and context["papers"]:
        steps.append("Run claim extraction on the most relevant papers.")
    if not steps:
        steps.append("Compare the leading claims across methods and datasets to decide the next experiment or reading step.")
    return steps


def _disagreement_summary(anchor_claim: dict, related_claim: dict, relation: dict) -> str:
    if relation["relation_type"] == "contradicts":
        return f"{anchor_claim['text']} is contradicted by {related_claim['text']}."
    return f"{related_claim['text']} appears to refine {anchor_claim['text']} under different context or evidence."


def _evidence_assessment(context: dict, disagreements: list[dict]) -> dict:
    reviewed = sum(1 for item in disagreements if item["relation_source"] == "reviewed")
    inferred = sum(1 for item in disagreements if item["relation_source"] == "inferred")
    evidence_strength = "low"
    if len(context["papers"]) >= 3 and len(context["claims"]) >= 3:
        evidence_strength = "high" if reviewed == 0 else "medium"
    elif len(context["papers"]) >= 2 and len(context["claims"]) >= 2:
        evidence_strength = "medium"
    return {
        "paper_count": len(context["papers"]),
        "claim_count": len(context["claims"]),
        "method_count": len(context["methods"]),
        "dataset_count": len(context["datasets"]),
        "reviewed_disagreement_count": reviewed,
        "inferred_disagreement_count": inferred,
        "evidence_strength": evidence_strength,
    }


def _answer_confidence(evidence_assessment: dict) -> str:
    if evidence_assessment["evidence_strength"] == "high":
        return "high"
    if evidence_assessment["evidence_strength"] == "medium":
        return "medium"
    return "low"


def _counterevidence_payload(disagreements: list[dict]) -> list[dict]:
    payload = []
    for item in disagreements:
        if item["relation_type"] != "contradicts":
            continue
        payload.append(
            {
                "relation_type": item["relation_type"],
                "relation_source": item["relation_source"],
                "claim": item["related_claim"],
                "summary": item["summary"],
            }
        )
    return payload


def _reading_list(context: dict, disagreements: list[dict]) -> list[dict]:
    recommendations = []
    seen = set()

    for paper in context["papers"][:3]:
        if paper["id"] in seen:
            continue
        seen.add(paper["id"])
        recommendations.append(
            {
                "paper_id": paper["id"],
                "title": paper["title"],
                "reason": "topic_anchor",
            }
        )

    for disagreement in disagreements[:2]:
        paper = disagreement["paper"]
        if paper["id"] in seen:
            continue
        seen.add(paper["id"])
        recommendations.append(
            {
                "paper_id": paper["id"],
                "title": paper["title"],
                "reason": "conflict_check",
            }
        )
    return recommendations[:5]


def _reading_navigation(context: dict, disagreements: list[dict]) -> dict:
    entry_papers = []
    representative_papers = []
    contradiction_papers = []
    seen_entry = set()
    seen_representative = set()
    seen_contradiction = set()

    for paper in context["papers"][:2]:
        if paper["id"] in seen_entry:
            continue
        seen_entry.add(paper["id"])
        entry_papers.append(
            {
                "paper_id": paper["id"],
                "title": paper["title"],
                "reason": "entry_anchor",
            }
        )

    for paper in context["papers"][:5]:
        if paper["id"] in seen_representative:
            continue
        seen_representative.add(paper["id"])
        representative_papers.append(
            {
                "paper_id": paper["id"],
                "title": paper["title"],
                "reason": "representative_evidence",
            }
        )

    for disagreement in disagreements:
        if disagreement["relation_type"] != "contradicts":
            continue
        anchor_paper = next(
            (paper for paper in context["papers"] if paper["id"] == disagreement["anchor_claim"]["paper_id"]),
            None,
        )
        for paper in (disagreement["paper"], anchor_paper):
            if paper is None:
                continue
            if paper["id"] in seen_contradiction:
                continue
            seen_contradiction.add(paper["id"])
            contradiction_papers.append(
                {
                    "paper_id": paper["id"],
                    "title": paper["title"],
                    "reason": "contradiction_check",
                }
            )

    reading_sequence = entry_papers + [
        paper for paper in representative_papers if paper["paper_id"] not in seen_entry
    ] + [paper for paper in contradiction_papers if paper["paper_id"] not in seen_entry]
    return {
        "entry_papers": entry_papers[:3],
        "representative_papers": representative_papers[:5],
        "contradiction_papers": contradiction_papers[:4],
        "reading_sequence": reading_sequence[:8],
    }


def _evidence_gaps(context: dict, disagreements: list[dict]) -> list[str]:
    gaps = []
    if len(context["papers"]) < 3:
        gaps.append("Broaden paper coverage so the topic is not grounded in a narrow literature slice.")
    if not context["claims"]:
        gaps.append("Claim extraction is too sparse for stable synthesis.")
    if context["claims"] and not context["methods"]:
        gaps.append("Method structure is thin relative to the claim coverage.")
    if context["claims"] and not context["datasets"]:
        gaps.append("Dataset structure is thin relative to the claim coverage.")
    if disagreements and all(item["relation_source"] == "inferred" for item in disagreements):
        gaps.append("Disagreement signals are still inferred only; they should be reviewed before becoming durable guidance.")
    return gaps


def _review_priorities(disagreements: list[dict]) -> list[dict]:
    priorities = []
    for item in disagreements[:4]:
        priorities.append(
            {
                "title": f"Review {item['relation_type']} between {item['anchor_claim']['id']} and {item['related_claim']['id']}",
                "claim_ids": [item["anchor_claim"]["id"], item["related_claim"]["id"]],
                "paper_ids": sorted({item["anchor_claim"]["paper_id"], item["related_claim"]["paper_id"]}),
                "priority": "high" if item["relation_source"] == "reviewed" else "medium",
                "reason": item["recommended_review"],
            }
        )
    return priorities


def _replication_risks(disagreements: list[dict]) -> list[dict]:
    risks = []
    for item in disagreements[:4]:
        if item["relation_type"] != "contradicts":
            continue
        risks.append(
            {
                "risk_level": "high" if item["relation_source"] == "reviewed" else "medium",
                "summary": item["summary"],
                "claim_ids": [item["anchor_claim"]["id"], item["related_claim"]["id"]],
                "paper_ids": sorted({item["anchor_claim"]["paper_id"], item["related_claim"]["paper_id"]}),
                "recommended_action": item["recommended_review"],
            }
        )
    return risks


def _disagreement_kind(anchor_claim: dict, related_claim: dict, relation: dict) -> str:
    anchor_dataset = _claim_dataset(anchor_claim)
    related_dataset = _claim_dataset(related_claim)
    if relation["relation_type"] == "contradicts":
        if anchor_dataset and related_dataset and anchor_dataset != related_dataset:
            return "cross_dataset_tension"
        return "direct_conflict"
    if anchor_dataset and related_dataset and anchor_dataset != related_dataset:
        return "contextual_refinement"
    return "scope_refinement"


def _possible_causes(anchor_claim: dict, related_claim: dict, relation: dict) -> list[str]:
    causes = []
    anchor_dataset = _claim_dataset(anchor_claim)
    related_dataset = _claim_dataset(related_claim)
    if anchor_dataset and related_dataset and anchor_dataset != related_dataset:
        causes.append(f"Different dataset context: {anchor_dataset} vs {related_dataset}.")
    if relation["relation_source"] == "inferred":
        causes.append("The relation is inferred at query time and has not been reviewed yet.")
    if relation["relation_type"] == "refines":
        causes.append("The later claim may be narrowing scope, conditions, or evaluation framing.")
    if not causes:
        causes.append("Review the claim evidence and evaluation framing to explain the tension.")
    return causes


def _recommended_review(anchor_claim: dict, related_claim: dict, relation: dict) -> str:
    anchor_dataset = _claim_dataset(anchor_claim)
    related_dataset = _claim_dataset(related_claim)
    if anchor_dataset and related_dataset and anchor_dataset != related_dataset:
        return "Check whether dataset differences fully explain the disagreement before treating it as a direct conflict."
    if relation["relation_source"] == "inferred":
        return "Inspect the two claims manually and decide whether the inferred relation should be promoted or discarded."
    return "Review the evidence sections for both claims and verify whether the relation should remain durable."


def _claim_dataset(claim: dict) -> str | None:
    context = claim.get("context", {}) or {}
    dataset = context.get("dataset")
    return dataset if isinstance(dataset, str) and dataset else None


def _dedupe_objects(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        item_id = item.get("id")
        if item_id is None or item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return deduped


def _resolve_target(query_service, target: str) -> dict:
    if target.startswith("p_"):
        paper = query_service.papers.get_paper(target)
        claims = [query_service._claim_payload(claim) for claim in query_service.claims.list_claims_for_paper(target)]
        methods = query_service.methods_for(target).get("methods", [])
        datasets = query_service.datasets_for(target).get("datasets", [])
        return {
            "type": "paper",
            "id": paper.id,
            "label": paper.title,
            "paper": query_service._paper_payload(paper),
            "claim_count": len(claims),
            "method_count": len(methods),
            "dataset_count": len(datasets),
            "claims": claims[:5],
            "methods": methods[:5],
            "datasets": datasets[:5],
        }
    if target.startswith("c_"):
        claim = query_service.claims.get_claim(target)
        claim_payload = query_service._claim_payload(claim)
        relations = query_service.claim_relations(target)
        return {
            "type": "claim",
            "id": claim.id,
            "label": claim.text,
            "claim": claim_payload,
            "paper": query_service._paper_payload(query_service.papers.get_paper(claim.paper_id)),
            "reviewed_relation_count": len(relations["reviewed_relations"]),
            "inferred_relation_count": len(relations["inferred_relations"]),
        }
    if target.startswith("m_") and query_service.methods is not None:
        method = query_service.methods.get_method(target)
        datasets = query_service.datasets_for(target).get("datasets", [])
        return {
            "type": "method",
            "id": method.id,
            "label": method.name,
            "method": {
                "id": method.id,
                "paper_id": method.paper_id,
                "name": method.name,
                "description": method.description,
            },
            "paper": query_service._paper_payload(query_service.papers.get_paper(method.paper_id)),
            "datasets": datasets[:5],
        }
    if target.startswith("d_") and query_service.datasets is not None:
        dataset = query_service.datasets.get_dataset(target)
        return {
            "type": "dataset",
            "id": dataset.id,
            "label": dataset.name,
            "dataset": {
                "id": dataset.id,
                "paper_id": dataset.paper_id,
                "name": dataset.name,
                "description": dataset.description,
                "source": dataset.source,
            },
            "paper": query_service._paper_payload(query_service.papers.get_paper(dataset.paper_id)),
        }
    if target.startswith("k_"):
        concept = query_service.concepts.get_concept(target)
        claims = query_service.claims_about(target).get("claims", [])
        methods = query_service.methods_for(target).get("methods", [])
        return {
            "type": "concept",
            "id": concept.id,
            "label": concept.name,
            "concept": {"id": concept.id, "name": concept.name},
            "claim_count": len(claims),
            "method_count": len(methods),
        }

    search = query_service.search(target, mode="hybrid")
    candidates = (
        [("method", item) for item in search.get("methods", [])]
        + [("paper", item) for item in search.get("papers", [])]
        + [("claim", item) for item in search.get("claims", [])]
        + [("dataset", item) for item in search.get("datasets", [])]
        + [("concept", item) for item in search.get("concepts", [])]
    )
    normalized_target = canonicalize_term(target)
    chosen_type = None
    chosen_id = None
    for candidate_type, candidate in candidates:
        label = _candidate_label(candidate_type, candidate)
        if canonicalize_term(label) == normalized_target:
            chosen_type = candidate_type
            chosen_id = candidate["id"]
            break
    if chosen_type is None and candidates:
        chosen_type, candidate = candidates[0]
        chosen_id = candidate["id"]
    if chosen_type is None or chosen_id is None:
        return {
            "type": "unresolved",
            "id": None,
            "label": target,
            "query": target,
        }
    return _resolve_target(query_service, chosen_id)


def _candidate_label(candidate_type: str, candidate: dict) -> str:
    if candidate_type == "paper":
        return candidate["title"]
    if candidate_type == "claim":
        return candidate["text"]
    return candidate["name"]


def _shared_points(left: dict, right: dict) -> list[str]:
    if left["type"] == "claim" and right["type"] == "claim":
        shared = []
        if left["claim"]["subject"] == right["claim"]["subject"]:
            shared.append(f"Both claims are about {left['claim']['subject']}.")
        if left["claim"]["predicate"] == right["claim"]["predicate"]:
            shared.append(f"Both claims use the predicate {left['claim']['predicate']}.")
        if _claim_dataset(left["claim"]) and _claim_dataset(left["claim"]) == _claim_dataset(right["claim"]):
            shared.append(f"Both claims reference the dataset {_claim_dataset(left['claim'])}.")
        return shared
    if left["type"] == "paper" and right["type"] == "paper":
        shared = []
        if left["method_count"] and right["method_count"]:
            shared.append("Both papers have extracted method structure.")
        if left["dataset_count"] and right["dataset_count"]:
            shared.append("Both papers have extracted dataset structure.")
        return shared
    if left["type"] == "method" and right["type"] == "method":
        left_datasets = {dataset["name"] for dataset in left.get("datasets", [])}
        right_datasets = {dataset["name"] for dataset in right.get("datasets", [])}
        return [f"Both methods are evaluated on {name}." for name in sorted(left_datasets & right_datasets)]
    return []


def _differences(left: dict, right: dict) -> list[str]:
    if left["type"] == "claim" and right["type"] == "claim":
        differences = []
        if _claim_dataset(left["claim"]) != _claim_dataset(right["claim"]):
            differences.append(
                f"Dataset context differs: {_claim_dataset(left['claim']) or 'unspecified'} vs {_claim_dataset(right['claim']) or 'unspecified'}."
            )
        if _claim_polarity(left["claim"]["text"]) != _claim_polarity(right["claim"]["text"]):
            differences.append("The claims have different polarity and may directly conflict.")
        if left["claim"]["paper_id"] != right["claim"]["paper_id"]:
            differences.append("The claims come from different source papers.")
        return differences
    if left["type"] == "paper" and right["type"] == "paper":
        differences = []
        if left["claim_count"] != right["claim_count"]:
            differences.append(f"Claim coverage differs: {left['claim_count']} vs {right['claim_count']}.")
        if left["method_count"] != right["method_count"]:
            differences.append(f"Method coverage differs: {left['method_count']} vs {right['method_count']}.")
        if left["dataset_count"] != right["dataset_count"]:
            differences.append(f"Dataset coverage differs: {left['dataset_count']} vs {right['dataset_count']}.")
        return differences
    if left["type"] == "method" and right["type"] == "method":
        left_datasets = {dataset["name"] for dataset in left.get("datasets", [])}
        right_datasets = {dataset["name"] for dataset in right.get("datasets", [])}
        differences = []
        if left_datasets - right_datasets:
            differences.append("The left method covers datasets not seen on the right method.")
        if right_datasets - left_datasets:
            differences.append("The right method covers datasets not seen on the left method.")
        return differences
    return [f"Comparing {left['type']} against {right['type']} requires inspecting different evidence surfaces."]


def _comparison_recommendations(left: dict, right: dict, differences: list[str]) -> list[str]:
    recommendations = []
    if left["type"] == "claim" and right["type"] == "claim":
        recommendations.append("Inspect the evidence and context for both claims before merging them into one conclusion.")
        if any("polarity" in item for item in differences):
            recommendations.append("Review whether the claim relation should be promoted as a reviewed contradiction.")
        return recommendations
    if left["type"] == "paper" and right["type"] == "paper":
        recommendations.append("Read the higher-coverage paper first, then inspect the weaker paper for missing structure.")
        return recommendations
    if left["type"] == "method" and right["type"] == "method":
        recommendations.append("Compare the dataset coverage and run a side-by-side evaluation on one uncovered dataset.")
        return recommendations
    recommendations.append("Use the comparison output as a routing step, then inspect the underlying paper or claim records directly.")
    return recommendations


def _comparison_summary(left: dict, right: dict, shared_points: list[str], differences: list[str]) -> str:
    parts = [f"Comparing {left['label']} against {right['label']}."]
    if shared_points:
        parts.append("Shared points: " + "; ".join(shared_points[:3]) + ".")
    if differences:
        parts.append("Key differences: " + "; ".join(differences[:3]) + ".")
    else:
        parts.append("No strong differences were surfaced from the current local graph.")
    return " ".join(parts)


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
