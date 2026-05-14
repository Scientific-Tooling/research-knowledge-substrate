from __future__ import annotations

import json
from pathlib import Path

from rks.agent import (
    create_claims_request,
    create_datasets_request,
    create_methods_request,
    create_summary_request,
    create_text_request,
    record_task_report,
)
from rks.config import (
    load_app_config,
    load_llm_config,
    load_paths,
)
from rks.extraction import (
    extract_claims_with_llm,
    extract_datasets_with_llm,
    extract_methods_with_llm,
    extract_text_with_llm,
)
from rks.ingestion.pipeline import run_post_ingest_pipeline
from rks.operations import ResearchOperations
from rks.providers import (
    LocalHashEmbeddingProvider,
    OpenAICompatibleLlmProvider,
)
from rks.reasoning.summary import build_summary_input, persist_summary_artifact
from rks.storage import (
    CandidateRepository,
    ClaimRepository,
    ConceptRepository,
    ConflictClusterRepository,
    DatasetRepository,
    EmbeddingRepository,
    EdgeRepository,
    EvolutionRepository,
    HypothesisRepository,
    MethodRepository,
    NoteRepository,
    PaperRepository,
    ProjectRepository,
    TaskRepository,
    connect_db,
    initialize_db,
)


class _RepositoryContext:
    def __enter__(self) -> PaperRepository:
        paths = load_paths()
        self.conn = connect_db(paths.db_path)
        initialize_db(self.conn)
        return PaperRepository(self.conn)

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.conn.rollback()
        self.conn.close()


def _open_repository() -> _RepositoryContext:
    return _RepositoryContext()


class _Session:
    def __init__(
        self,
        papers: PaperRepository,
        projects: ProjectRepository,
        hypotheses: HypothesisRepository,
        claims: ClaimRepository,
        concepts: ConceptRepository,
        notes: NoteRepository,
        edges: EdgeRepository,
        methods: MethodRepository,
        datasets: DatasetRepository,
        embeddings: EmbeddingRepository,
        tasks: TaskRepository,
        candidates: CandidateRepository | None = None,
        evolution: EvolutionRepository | None = None,
        conflict_clusters: ConflictClusterRepository | None = None,
    ):
        self.papers = papers
        self.projects = projects
        self.hypotheses = hypotheses
        self.claims = claims
        self.concepts = concepts
        self.notes = notes
        self.edges = edges
        self.methods = methods
        self.datasets = datasets
        self.embeddings = embeddings
        self.tasks = tasks
        self.candidates = candidates
        self.evolution = evolution
        self.conflict_clusters = conflict_clusters


class _SessionContext:
    def __enter__(self) -> _Session:
        paths = load_paths()
        self.conn = connect_db(paths.db_path)
        initialize_db(self.conn)
        return _Session(
            papers=PaperRepository(self.conn),
            projects=ProjectRepository(self.conn),
            hypotheses=HypothesisRepository(self.conn),
            claims=ClaimRepository(self.conn),
            concepts=ConceptRepository(self.conn),
            notes=NoteRepository(self.conn),
            edges=EdgeRepository(self.conn),
            methods=MethodRepository(self.conn),
            datasets=DatasetRepository(self.conn),
            embeddings=EmbeddingRepository(self.conn),
            tasks=TaskRepository(self.conn),
            candidates=CandidateRepository(self.conn),
            evolution=EvolutionRepository(self.conn),
            conflict_clusters=ConflictClusterRepository(self.conn),
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.conn.rollback()
        self.conn.close()


def _open_session() -> _SessionContext:
    return _SessionContext()


def _operations(session: _Session) -> ResearchOperations:
    return ResearchOperations(
        papers=session.papers,
        projects=session.projects,
        hypotheses=session.hypotheses,
        claims=session.claims,
        concepts=session.concepts,
        notes=session.notes,
        edges=session.edges,
        methods=session.methods,
        datasets=session.datasets,
        embeddings=session.embeddings,
        tasks=session.tasks,
        candidates=session.candidates,
        evolution=session.evolution,
        conflict_clusters=session.conflict_clusters,
    )


def _paper_to_payload(paper) -> dict:
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


def _paper_with_tags_payload(paper_repo: PaperRepository, paper) -> dict:
    payload = _paper_to_payload(paper)
    payload["tags"] = paper_repo.list_tags_for_paper(paper.id)
    return payload


def _project_to_payload(project) -> dict:
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


def _claim_subject(concepts: ConceptRepository, claim) -> str | None:
    context = json.loads(claim.context_json or "{}")
    if claim.subject_concept_id:
        return concepts.get_concept(claim.subject_concept_id).name
    return context.get("subject_text")


def _claim_object(concepts: ConceptRepository, claim) -> str | None:
    if claim.object_concept_id:
        return concepts.get_concept(claim.object_concept_id).name
    return claim.object_text


def _artifact_payload(paper_id: str, mode: str, artifact) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "path": artifact.path,
    }


def _run_pipeline_if_configured(session, paths, paper_id: str) -> dict | None:
    """Run post-ingest pipeline when auto_extract_mode != 'none'."""
    app_config = load_app_config()
    mode = app_config.auto_extract_mode
    if mode == "none":
        return None
    provider = OpenAICompatibleLlmProvider(load_llm_config()) if mode == "llm-api" else None
    return run_post_ingest_pipeline(
        paths=paths,
        paper_repo=session.papers,
        claim_repo=session.claims,
        concept_repo=session.concepts,
        edge_repo=session.edges,
        method_repo=session.methods,
        dataset_repo=session.datasets,
        task_repo=session.tasks,
        paper_id=paper_id,
        mode=mode,
        provider=provider,
    )


def _claims_payload(paper_id: str, mode: str, claims: list) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "claim_count": len(claims),
        "claim_ids": [claim.id for claim in claims],
    }


def _methods_payload(paper_id: str, mode: str, methods: list) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "method_count": len(methods),
        "method_ids": [method.id for method in methods],
    }


def _datasets_payload(paper_id: str, mode: str, datasets: list) -> dict:
    return {
        "paper_id": paper_id,
        "mode": mode,
        "dataset_count": len(datasets),
        "dataset_ids": [dataset.id for dataset in datasets],
    }


def _method_payload(concepts: ConceptRepository, method) -> dict:
    about_concept = concepts.get_concept(method.about_concept_id).name if method.about_concept_id else None
    return {
        "id": method.id,
        "paper_id": method.paper_id,
        "name": method.name,
        "description": method.description,
        "about_concept": about_concept,
        "created_at": method.created_at,
    }


def _dataset_payload(dataset) -> dict:
    return {
        "id": dataset.id,
        "paper_id": dataset.paper_id,
        "name": dataset.name,
        "description": dataset.description,
        "source": dataset.source,
        "created_at": dataset.created_at,
    }


def _edge_payload(edge) -> dict:
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


def _note_payload(note) -> dict:
    return {
        "id": note.id,
        "target_id": note.target_id,
        "target_type": note.target_type,
        "content": note.content,
        "created_by": note.created_by,
        "created_at": note.created_at,
    }


def _task_payload(task) -> dict:
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
        "error": json.loads(task.error_json) if task.error_json else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _load_json_object(path: Path, label: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return payload


def _normalize_baseline_checks(spec: dict) -> dict:
    checks = spec.get("checks")
    if checks is None:
        checks = {
            key: value
            for key, value in spec.items()
            if key not in {"name", "description", "version"}
        }
    if not isinstance(checks, dict) or not checks:
        raise ValueError("Baseline spec must define at least one check under `checks`.")
    allowed = {
        "min_paper_count",
        "min_total_claims",
        "min_mean_claims_per_paper",
        "max_zero_claim_rate",
        "required_predicates",
        "required_extraction_modes",
        "min_predicate_counts",
        "min_extraction_mode_counts",
        "per_paper_min_claims",
    }
    unknown = sorted(set(checks) - allowed)
    if unknown:
        raise ValueError(f"Unsupported baseline check keys: {', '.join(unknown)}")
    return checks


def _evaluate_baseline_metrics(metrics: dict, checks: dict) -> dict:
    paper_count = int(metrics.get("paper_count", 0))
    total_claims = int(metrics.get("total_claims", 0))
    mean_claims = float((metrics.get("claims_per_paper") or {}).get("mean", 0.0))
    zero_claim_count = len(metrics.get("zero_claim_papers", []))
    zero_claim_rate = (zero_claim_count / paper_count) if paper_count else 0.0
    predicate_distribution = metrics.get("predicate_distribution") or {}
    mode_distribution = metrics.get("extraction_mode_distribution") or {}
    per_paper_claims = {
        item["paper_id"]: int(item.get("claim_count", 0))
        for item in metrics.get("per_paper", [])
        if isinstance(item, dict) and "paper_id" in item
    }
    # Fallback when per-paper details are not returned by metrics payload.
    if not per_paper_claims:
        per_paper_claims = {}

    results: list[dict] = []

    def record(check: str, expected, actual, passed: bool) -> None:
        results.append(
            {
                "check": check,
                "expected": expected,
                "actual": actual,
                "passed": bool(passed),
            }
        )

    if "min_paper_count" in checks:
        threshold = int(checks["min_paper_count"])
        record("min_paper_count", {">=": threshold}, paper_count, paper_count >= threshold)
    if "min_total_claims" in checks:
        threshold = int(checks["min_total_claims"])
        record("min_total_claims", {">=": threshold}, total_claims, total_claims >= threshold)
    if "min_mean_claims_per_paper" in checks:
        threshold = float(checks["min_mean_claims_per_paper"])
        record("min_mean_claims_per_paper", {">=": threshold}, mean_claims, mean_claims >= threshold)
    if "max_zero_claim_rate" in checks:
        threshold = float(checks["max_zero_claim_rate"])
        record("max_zero_claim_rate", {"<=": threshold}, round(zero_claim_rate, 4), zero_claim_rate <= threshold)
    if "required_predicates" in checks:
        required = list(checks["required_predicates"])
        missing = [name for name in required if predicate_distribution.get(name, 0) <= 0]
        record("required_predicates", {"present": required}, {"missing": missing}, len(missing) == 0)
    if "required_extraction_modes" in checks:
        required = list(checks["required_extraction_modes"])
        missing = [name for name in required if mode_distribution.get(name, 0) <= 0]
        record("required_extraction_modes", {"present": required}, {"missing": missing}, len(missing) == 0)
    if "min_predicate_counts" in checks:
        expected = dict(checks["min_predicate_counts"])
        for predicate, threshold in expected.items():
            actual = int(predicate_distribution.get(predicate, 0))
            record(
                f"min_predicate_counts.{predicate}",
                {">=": int(threshold)},
                actual,
                actual >= int(threshold),
            )
    if "min_extraction_mode_counts" in checks:
        expected = dict(checks["min_extraction_mode_counts"])
        for mode, threshold in expected.items():
            actual = int(mode_distribution.get(mode, 0))
            record(
                f"min_extraction_mode_counts.{mode}",
                {">=": int(threshold)},
                actual,
                actual >= int(threshold),
            )
    if "per_paper_min_claims" in checks:
        expected = dict(checks["per_paper_min_claims"])
        for paper_id, threshold in expected.items():
            actual = int(per_paper_claims.get(paper_id, 0))
            record(
                f"per_paper_min_claims.{paper_id}",
                {">=": int(threshold)},
                actual,
                actual >= int(threshold),
            )

    failed = [item for item in results if not item["passed"]]
    return {
        "passed": len(failed) == 0,
        "checks": results,
        "failed_checks": failed,
    }


def _evaluate_claims_against_golden(
    actual_texts: list[str],
    golden_texts: list[str],
    match_threshold: float = 0.3,
) -> dict:
    """Fuzzy precision/recall/F1 of actual claims against a golden set.

    Uses token-set Jaccard similarity to decide if a golden claim is matched
    by any actual claim.  A pair is counted as a true positive when their
    Jaccard score meets *match_threshold*.
    """
    import re

    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def _jaccard(a: set[str], b: set[str]) -> float:
        union = a | b
        return len(a & b) / len(union) if union else 0.0

    actual_token_sets = [_tokens(t) for t in actual_texts]
    matched_pairs: list[dict] = []
    true_positive_actual: set[int] = set()

    for golden_text in golden_texts:
        golden_tokens = _tokens(golden_text)
        best_score = 0.0
        best_idx = -1
        for idx, actual_tokens in enumerate(actual_token_sets):
            score = _jaccard(golden_tokens, actual_tokens)
            if score > best_score:
                best_score = score
                best_idx = idx
        matched = best_score >= match_threshold
        matched_pairs.append(
            {
                "golden": golden_text,
                "best_match": actual_texts[best_idx] if best_idx >= 0 else None,
                "score": round(best_score, 4),
                "matched": matched,
            }
        )
        if matched and best_idx >= 0:
            true_positive_actual.add(best_idx)

    tp = sum(1 for p in matched_pairs if p["matched"])
    precision = tp / len(actual_texts) if actual_texts else 0.0
    recall = tp / len(golden_texts) if golden_texts else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "matched_pairs": matched_pairs,
    }


def _load_manifest(manifest_path: Path):
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Batch manifest must be a JSON array.")
    return payload


def _resolve_manifest_path(manifest_path: Path, candidate: str) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (manifest_path.parent / path).resolve()


def _run_batch_extract_item(stage: str, paper_id: str, mode: str) -> dict:
    with _open_session() as session:
        paths = load_paths()
        if stage == "text":
            paper = session.papers.get_paper(paper_id)
            if mode == "llm-api":
                artifact = extract_text_with_llm(
                    repo=session.papers,
                    paths=paths,
                    paper=paper,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _artifact_payload(paper_id, mode, artifact)
            request = create_text_request(session.papers, paths, paper_id)
            task = session.tasks.create_task(
                "extract_text", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract text --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "claims":
            if mode == "llm-api":
                claims = extract_claims_with_llm(
                    paths, session.papers, session.claims, session.concepts, session.edges, paper_id,
                    OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _claims_payload(paper_id, mode, claims)
            request = create_claims_request(session.papers, paths, paper_id)
            task = session.tasks.create_task(
                "extract_claims", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract claims --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "methods":
            if mode == "llm-api":
                methods = extract_methods_with_llm(
                    paths=paths, paper_repo=session.papers, claim_repo=session.claims,
                    concept_repo=session.concepts, edge_repo=session.edges,
                    method_repo=session.methods, dataset_repo=session.datasets,
                    paper_id=paper_id, provider=OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _methods_payload(paper_id, mode, methods)
            request = create_methods_request(session.papers, paths, paper_id)
            task = session.tasks.create_task(
                "extract_methods", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract methods --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "datasets":
            if mode == "llm-api":
                datasets = extract_datasets_with_llm(
                    paths=paths, paper_repo=session.papers, claim_repo=session.claims,
                    edge_repo=session.edges, dataset_repo=session.datasets,
                    method_repo=session.methods, paper_id=paper_id,
                    provider=OpenAICompatibleLlmProvider(load_llm_config()),
                )
                return _datasets_payload(paper_id, mode, datasets)
            request = create_datasets_request(session.papers, paths, paper_id)
            task = session.tasks.create_task(
                "extract_datasets", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract datasets --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

        if stage == "summary":
            if mode == "llm-api":
                return persist_summary_artifact(
                    session.papers,
                    paths,
                    paper_id,
                    {
                        **OpenAICompatibleLlmProvider(load_llm_config()).summarize_paper(
                            build_summary_input(session.papers, session.claims, session.concepts, paper_id)
                        ),
                        "mode": "llm-api",
                    },
                    "paper_summary",
                    "paper_summary.json",
                )
            request = create_summary_request(
                session.papers, session.claims, session.concepts, paths, paper_id
            )
            task = session.tasks.create_task(
                "summarize_paper", paper_id, "agent", request["artifact_id"], request["spec_version"], request["schema_version"]
            )
            record_task_report(session.papers, paths, task, note="Queued from rks batch extract summary --mode agent.")
            return {**request, "mode": "agent", "task_id": task.id}

    raise ValueError(f"Unsupported batch stage: {stage}")


def _run_batch_output_item(surface: str, item) -> dict:
    with _open_session() as session:
        operations = _operations(session)
        if surface == "answer":
            question = item["question"] if isinstance(item, dict) else str(item)
            payload = operations.answer_question(question)
            return {"surface": surface, "question": question, "payload": payload}
        if surface == "brief":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_brief(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "disagreements":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_disagreements(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "opportunities":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.research_opportunities(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "reading-list":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_reading_list(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "open-questions":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_open_questions(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "review-priorities":
            topic = item["topic"] if isinstance(item, dict) else str(item)
            payload = operations.topic_review_priorities(topic)
            return {"surface": surface, "topic": topic, "payload": payload}
        if surface == "compare":
            if not isinstance(item, dict) or "left" not in item or "right" not in item:
                raise ValueError("Batch compare items must be objects with `left` and `right`.")
            payload = operations.compare_targets(item["left"], item["right"])
            return {"surface": surface, "left": item["left"], "right": item["right"], "payload": payload}
    raise ValueError(f"Unsupported batch output surface: {surface}")


def _batch_ingest_audit(results: list[dict], failures: list[dict]) -> dict:
    source_type_counts = {}
    source_pdf_available = 0
    for paper in results:
        source_type_counts[paper["source_type"]] = source_type_counts.get(paper["source_type"], 0) + 1
        if paper.get("pdf_path"):
            source_pdf_available += 1
    return {
        "success_count": len(results),
        "failure_count": len(failures),
        "source_pdf_available_count": source_pdf_available,
        "source_type_counts": source_type_counts,
    }


def _batch_extract_audit(stage: str, results: list[dict], failures: list[dict]) -> dict:
    audit = {
        "stage": stage,
        "success_count": len(results),
        "failure_count": len(failures),
        "queued_task_count": sum(1 for result in results if result.get("mode") == "agent" and result.get("task_id")),
    }
    if stage == "claims":
        audit["total_claim_count"] = sum(result.get("claim_count", 0) for result in results)
    elif stage == "methods":
        audit["total_method_count"] = sum(result.get("method_count", 0) for result in results)
    elif stage == "datasets":
        audit["total_dataset_count"] = sum(result.get("dataset_count", 0) for result in results)
    elif stage == "summary":
        audit["summary_artifact_count"] = sum(1 for result in results if result.get("artifact_id"))
    elif stage == "text":
        audit["text_artifact_count"] = sum(1 for result in results if result.get("artifact_id"))
    return audit


def _batch_output_audit(surface: str, results: list[dict], failures: list[dict]) -> dict:
    payload_key = {
        "answer": "question",
        "brief": "topic",
        "disagreements": "topic",
        "opportunities": "topic",
        "reading-list": "topic",
        "open-questions": "topic",
        "review-priorities": "topic",
        "compare": "left",
    }[surface]
    return {
        "surface": surface,
        "success_count": len(results),
        "failure_count": len(failures),
        "items": [result[payload_key] for result in results if payload_key in result],
    }


def _artifact_id_for_type(repo: PaperRepository, paper_id: str, artifact_type: str) -> str | None:
    for artifact in repo.get_artifacts_for_paper(paper_id):
        if artifact.artifact_type == artifact_type:
            return artifact.id
    return None


def _doctor_recommended_actions(checks: dict) -> list[str]:
    actions = []
    if not checks["global_config"]["ok"]:
        actions.append("rks init <path>  # set your data directory")
    elif not checks["data_dir"]["ok"] or not checks["database"]["ok"]:
        actions.append("rks init-db")
    elif "database_integrity" in checks and not checks["database_integrity"]["ok"]:
        actions.append("inspect or repair orphaned database rows reported by `rks doctor`")
    if not actions:
        actions.append("rks --help")
    return actions
