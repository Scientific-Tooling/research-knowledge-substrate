from __future__ import annotations

def build_research_answer(query_service, question: str) -> dict:
    context = _topic_context(query_service, question)
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=3)
    key_claims = context["claims"][:5]
    key_findings = [claim["text"] for claim in key_claims[:3]]
    uncertainties = []
    if not key_claims:
        uncertainties.append("No grounded claims matched the question yet.")
    if disagreements:
        uncertainties.append("Relevant claims include disagreement signals that need review or replication.")
    if len(context["papers"]) < 2:
        uncertainties.append("The answer is grounded in a narrow paper set.")

    next_steps = _next_steps_from_context(context, disagreements)
    answer = _compose_answer_text(question, context, key_findings, disagreements, uncertainties, next_steps)
    return {
        "question": question,
        "answer": answer,
        "key_findings": key_findings,
        "supporting_claims": key_claims,
        "supporting_papers": context["papers"][:5],
        "methods": context["methods"][:5],
        "datasets": context["datasets"][:5],
        "disagreements": disagreements,
        "uncertainties": uncertainties,
        "next_steps": next_steps,
    }


def build_topic_brief(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=4)
    overview = _compose_brief_overview(topic, context, disagreements)
    open_questions = []
    if disagreements:
        open_questions.append("Why do the strongest claims for this topic disagree?")
    if context["methods"] and not context["datasets"]:
        open_questions.append("Which datasets should the observed methods be evaluated on next?")
    if not context["claims"]:
        open_questions.append("Which papers should be extracted next to ground this topic better?")
    return {
        "topic": topic,
        "overview": overview,
        "representative_papers": context["papers"][:5],
        "key_claims": context["claims"][:6],
        "methods": context["methods"][:6],
        "datasets": context["datasets"][:6],
        "disagreements": disagreements,
        "open_questions": open_questions,
    }


def build_topic_disagreements(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=6)
    summary = (
        f"{topic} currently has {len(disagreements)} surfaced disagreement signals."
        if disagreements
        else f"No contradictions or refinements were surfaced for {topic}."
    )
    return {
        "topic": topic,
        "summary": summary,
        "disagreements": disagreements,
        "claim_count_considered": len(context["claim_ids"]),
    }


def build_research_opportunities(query_service, topic: str) -> dict:
    context = _topic_context(query_service, topic)
    disagreements = _collect_disagreements(query_service, context["claim_ids"], limit=6)
    opportunities = []
    for disagreement in disagreements[:3]:
        opportunities.append(
            {
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
                    "kind": "evaluate_method",
                    "title": f"Evaluate {method['name']} on a grounded dataset",
                    "reasoning": f"{method['name']} appears in the topic context without an explicit evaluated_on dataset edge.",
                    "method_ids": [method["id"]],
                    "dataset_ids": [],
                    "paper_ids": [method["paper_id"]],
                    "next_step": "Run dataset extraction review or add evaluation evidence for this method.",
                }
            )
            continue
        missing_dataset_ids = sorted(all_topic_dataset_ids - evaluated_dataset_ids)
        if missing_dataset_ids:
            opportunities.append(
                {
                    "kind": "broaden_evaluation",
                    "title": f"Broaden evaluation for {method['name']}",
                    "reasoning": f"{method['name']} is linked to only {len(evaluated_dataset_ids)} dataset(s) while the topic context includes additional datasets.",
                    "method_ids": [method["id"]],
                    "dataset_ids": missing_dataset_ids[:3],
                    "paper_ids": [method["paper_id"]],
                    "next_step": "Check whether this method should be compared on additional datasets already discussed in the topic.",
                }
            )

    if not context["claims"]:
        opportunities.append(
            {
                "kind": "expand_grounding",
                "title": f"Expand extracted grounding for {topic}",
                "reasoning": "The topic has too little extracted claim structure to support synthesis.",
                "claim_ids": [],
                "paper_ids": [paper["id"] for paper in context["papers"][:3]],
                "next_step": "Ingest more relevant papers or run claim extraction on already-ingested sources.",
            }
        )

    if context["claims"] and not context["methods"]:
        opportunities.append(
            {
                "kind": "extract_methods",
                "title": f"Extract method structure for {topic}",
                "reasoning": "Claims exist, but method coverage is thin in the current topic view.",
                "claim_ids": [claim["id"] for claim in context["claims"][:3]],
                "paper_ids": [claim["paper_id"] for claim in context["claims"][:3]],
                "next_step": "Run or review method extraction to enrich comparisons and future opportunity generation.",
            }
        )

    if context["claims"] and not context["datasets"]:
        opportunities.append(
            {
                "kind": "extract_datasets",
                "title": f"Extract dataset structure for {topic}",
                "reasoning": "Claim evidence exists, but dataset coverage is sparse.",
                "claim_ids": [claim["id"] for claim in context["claims"][:3]],
                "paper_ids": [claim["paper_id"] for claim in context["claims"][:3]],
                "next_step": "Run or review dataset extraction to support better benchmarking and opportunity analysis.",
            }
        )

    summary = (
        f"{topic} has {len(opportunities)} surfaced research opportunities."
        if opportunities
        else f"No grounded research opportunities were surfaced for {topic}."
    )
    return {
        "topic": topic,
        "summary": summary,
        "opportunities": opportunities[:8],
        "disagreements": disagreements,
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

    claims = _dedupe_objects(concept_claims + search["claims"] + semantic_claims)
    claim_ids = [claim["id"] for claim in claims[:8]]

    papers = _dedupe_objects(search["papers"] + semantic_papers)
    for claim in claims[:5]:
        support = query_service.papers_supporting(claim["id"])
        papers = _dedupe_objects(papers + support.get("papers", []))

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
                    "summary": _disagreement_summary(anchor_claim, related_claim, relation),
                }
            )
            if len(disagreements) >= limit:
                return disagreements
    return disagreements


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
