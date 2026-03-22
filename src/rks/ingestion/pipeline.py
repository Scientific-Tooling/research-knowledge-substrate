"""Post-ingest extraction pipeline.

After a paper is ingested (record created, text extracted), this module runs the
full extraction pipeline — claims, methods, datasets, summary — in whichever mode
is configured via ``auto_extract_mode``.

Pipeline order
--------------
1. text    — skip if paper already has a text artifact (ingestion already ran it)
2. claims  — requires text
3. methods — requires text
4. datasets — requires text
5. summary  — requires claims + concepts

Modes
-----
- ``none``             — do nothing (default; preserves existing behaviour)
- ``llm-api``          — run every stage synchronously via the configured LLM provider
- ``llm-api-combined`` — run all stages in a single LLM call (paper.v1)
- ``agent``            — queue a task for every stage; an external agent completes them
"""
from __future__ import annotations

from rks.agent.workflow import (
    create_claims_request,
    create_datasets_request,
    create_methods_request,
    create_summary_request,
    record_task_report,
)
from rks.config import AppPaths
from rks.extraction import (
    extract_all_with_llm,
    extract_claims_with_llm,
    extract_datasets_with_llm,
    extract_methods_with_llm,
    extract_text_with_llm,
)
from rks.storage import (
    ClaimRepository,
    ConceptRepository,
    DatasetRepository,
    EdgeRepository,
    MethodRepository,
    PaperRepository,
    TaskRepository,
)


def run_post_ingest_pipeline(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    edge_repo: EdgeRepository,
    method_repo: MethodRepository,
    dataset_repo: DatasetRepository,
    task_repo: TaskRepository,
    paper_id: str,
    mode: str,
    provider=None,
) -> dict:
    """Run post-ingest extraction for *paper_id* in the given *mode*.

    Returns a summary dict describing what was executed or queued.
    Errors in individual stages are caught and reported in the summary so that
    one failing stage does not abort the rest.
    """
    if mode == "none":
        return {"paper_id": paper_id, "mode": mode, "stages": {}}

    if mode == "llm-api-combined":
        try:
            counts = extract_all_with_llm(
                paths=paths,
                paper_repo=paper_repo,
                claim_repo=claim_repo,
                concept_repo=concept_repo,
                edge_repo=edge_repo,
                method_repo=method_repo,
                dataset_repo=dataset_repo,
                paper_id=paper_id,
                provider=provider,
            )
            return {
                "paper_id": paper_id,
                "mode": mode,
                "stages": {
                    "text": {"done": True},
                    "claims": {"count": counts["claims"]},
                    "methods": {"count": counts["methods"]},
                    "datasets": {"count": counts["datasets"]},
                    "summary": {"done": True},
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {"paper_id": paper_id, "mode": mode, "stages": {"error": str(exc)}}

    paper = paper_repo.get_paper(paper_id)
    stages: dict[str, object] = {}

    # ── 1. text ──────────────────────────────────────────────────────────────
    # Skip if already extracted (pdf ingest already ran it; reference ingest
    # writes the abstract as text if present).
    if paper.text_artifact_id is None:
        stages["text"] = _run_stage(
            "text",
            mode,
            llm_api=lambda: {"done": True, "count": 1} if extract_text_with_llm(
                repo=paper_repo, paths=paths, paper=paper, provider=provider
            ) else {"done": False},
            agent=lambda: _queue_task(
                task_repo=task_repo,
                paper_repo=paper_repo,
                paths=paths,
                paper_id=paper_id,
                task_type="extract_text",
                request_fn=lambda: None,  # text request not yet in workflow; skip
            ),
        )
    else:
        stages["text"] = {"skipped": True, "reason": "already_extracted"}

    # Reload paper after potential text extraction
    paper = paper_repo.get_paper(paper_id)
    if paper.text_artifact_id is None and mode != "agent":
        # No text available — remaining stages cannot proceed
        stages["claims"] = stages["methods"] = stages["datasets"] = stages["summary"] = {
            "skipped": True, "reason": "no_text_artifact",
        }
        return {"paper_id": paper_id, "mode": mode, "stages": stages}

    # ── 2. claims ─────────────────────────────────────────────────────────────
    stages["claims"] = _run_stage(
        "claims",
        mode,
        llm_api=lambda: {"count": len(extract_claims_with_llm(
            paths=paths,
            paper_repo=paper_repo,
            claim_repo=claim_repo,
            concept_repo=concept_repo,
            edge_repo=edge_repo,
            paper_id=paper_id,
            provider=provider,
        ))},
        agent=lambda: _queue_task(
            task_repo=task_repo,
            paper_repo=paper_repo,
            paths=paths,
            paper_id=paper_id,
            task_type="extract_claims",
            request_fn=lambda: create_claims_request(
                repo=paper_repo, paths=paths, paper_id=paper_id
            ),
        ),
    )

    # ── 3. methods ────────────────────────────────────────────────────────────
    stages["methods"] = _run_stage(
        "methods",
        mode,
        llm_api=lambda: {"count": len(extract_methods_with_llm(
            paths=paths,
            paper_repo=paper_repo,
            claim_repo=claim_repo,
            concept_repo=concept_repo,
            edge_repo=edge_repo,
            method_repo=method_repo,
            dataset_repo=dataset_repo,
            paper_id=paper_id,
            provider=provider,
        ))},
        agent=lambda: _queue_task(
            task_repo=task_repo,
            paper_repo=paper_repo,
            paths=paths,
            paper_id=paper_id,
            task_type="extract_methods",
            request_fn=lambda: create_methods_request(
                repo=paper_repo, paths=paths, paper_id=paper_id
            ),
        ),
    )

    # ── 4. datasets ───────────────────────────────────────────────────────────
    stages["datasets"] = _run_stage(
        "datasets",
        mode,
        llm_api=lambda: {"count": len(extract_datasets_with_llm(
            paths=paths,
            paper_repo=paper_repo,
            claim_repo=claim_repo,
            edge_repo=edge_repo,
            dataset_repo=dataset_repo,
            method_repo=method_repo,
            paper_id=paper_id,
            provider=provider,
        ))},
        agent=lambda: _queue_task(
            task_repo=task_repo,
            paper_repo=paper_repo,
            paths=paths,
            paper_id=paper_id,
            task_type="extract_datasets",
            request_fn=lambda: create_datasets_request(
                repo=paper_repo, paths=paths, paper_id=paper_id
            ),
        ),
    )

    # ── 5. summary ────────────────────────────────────────────────────────────
    stages["summary"] = _run_stage(
        "summary",
        mode,
        llm_api=lambda: _run_llm_summary(
            paths=paths,
            paper_repo=paper_repo,
            claim_repo=claim_repo,
            concept_repo=concept_repo,
            paper_id=paper_id,
            provider=provider,
        ),
        agent=lambda: _queue_task(
            task_repo=task_repo,
            paper_repo=paper_repo,
            paths=paths,
            paper_id=paper_id,
            task_type="summarize_paper",
            request_fn=lambda: create_summary_request(
                repo=paper_repo,
                claim_repo=claim_repo,
                concept_repo=concept_repo,
                paths=paths,
                paper_id=paper_id,
            ),
        ),
    )

    return {"paper_id": paper_id, "mode": mode, "stages": stages}


# ── helpers ───────────────────────────────────────────────────────────────────

def _run_stage(name: str, mode: str, *, llm_api, agent) -> dict:
    """Execute one pipeline stage, catching and recording any exception."""
    try:
        if mode == "llm-api":
            return llm_api()
        if mode == "agent":
            return agent()
        return {"skipped": True, "reason": f"unknown_mode:{mode}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "stage": name}


def _queue_task(
    task_repo: TaskRepository,
    paper_repo: PaperRepository,
    paths: AppPaths,
    paper_id: str,
    task_type: str,
    request_fn,
) -> dict:
    """Write a request artifact and create a queued task record."""
    from rks.llm import (
        CLAIMS_SCHEMA_VERSION,
        DATASETS_SCHEMA_VERSION,
        METHODS_SCHEMA_VERSION,
        SUMMARY_SCHEMA_VERSION,
        TEXT_SCHEMA_VERSION,
    )
    _schema = {
        "extract_text": TEXT_SCHEMA_VERSION,
        "extract_claims": CLAIMS_SCHEMA_VERSION,
        "extract_methods": METHODS_SCHEMA_VERSION,
        "extract_datasets": DATASETS_SCHEMA_VERSION,
        "summarize_paper": SUMMARY_SCHEMA_VERSION,
    }
    request = request_fn()
    artifact_id = request["artifact_id"] if request and "artifact_id" in request else None
    task = task_repo.create_task(
        task_type=task_type,
        paper_id=paper_id,
        mode="agent",
        request_artifact_id=artifact_id,
        spec_version="v1",
        schema_version=_schema.get(task_type),
    )
    record_task_report(paper_repo, paths, task, note="Queued by auto_extract_mode=agent on ingest.")
    return {"task_id": task.id, "queued": True}


def _run_llm_summary(
    paths: AppPaths,
    paper_repo: PaperRepository,
    claim_repo: ClaimRepository,
    concept_repo: ConceptRepository,
    paper_id: str,
    provider,
) -> dict:
    from rks.reasoning.summary import build_summary_input, persist_summary_artifact
    summary_input = build_summary_input(paper_repo, claim_repo, concept_repo, paper_id)
    result = provider.summarize_paper(summary_input)
    result.setdefault("mode", "llm-api")
    persist_summary_artifact(
        paper_repo=paper_repo,
        paths=paths,
        paper_id=paper_id,
        payload=result,
        artifact_type="paper_summary",
        filename="paper_summary.json",
    )
    return {"done": True}
