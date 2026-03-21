# RKS Manual Testing Guide

This document explains how to manually verify the current RKS product surface. It focuses on:

- input completeness
- semantic review and persistence
- agent-facing CLI and HTTP operations

It is not a frontend visual QA guide and not a guide for complex autonomous orchestration.

## 1. Testing Goals

The highest-priority checks are:

1. after reference ingestion, metadata and text are preserved and source PDF acquisition is visible when applicable
2. claim relations clearly distinguish `inferred` from `reviewed`, and can be promoted or retracted
3. CLI and HTTP expose the same product semantics rather than assembling different views

## 2. Test Setup

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Initialize the workspace:

```bash
rks config init
rks init-db
rks migrate
```

Inspect configuration:

```bash
rks config show
```

Pay attention to:

- `data_dir`
- `reference_pdf_acquisition`, which should normally be `auto`

## 3. Scenario 1: Local PDF Ingest and Basic Extraction

Create a minimal PDF-like file:

```bash
printf '%s\n' '%PDF-1.4' 'Sparse Attention improves translation accuracy on WMT14.' > sample.pdf
```

Ingest it:

```bash
rks ingest pdf sample.pdf
```

Record the returned `paper_id`, for example `p_000001`.

Then run:

```bash
rks show paper p_000001
rks extract claims p_000001
rks claims p_000001
rks status paper p_000001
```

Expected result:

- `show paper` includes a `source_pdf` artifact
- `extract claims` returns a non-zero `claim_count`
- `claims` lists at least one claim
- `status paper` shows `stages.text=true` and `stages.claims=true`

Also inspect the filesystem:

- `data/papers/p_000001/source.pdf`
- `data/papers/p_000001/extracted_text.json`
- `data/papers/p_000001/structured_claims.json`

## 4. Scenario 2: DOI or arXiv Reference Ingest

Test DOI:

```bash
rks ingest doi 10.48550/arXiv.1706.03762
```

Or test arXiv:

```bash
rks ingest arxiv 1706.03762
```

Record the returned `paper_id`, then run:

```bash
rks show paper <paper_id>
rks status paper <paper_id>
```

Expected result:

- `metadata` artifact exists
- `extracted_text` often exists when abstract metadata is available
- `source_pdf_acquisition` artifact always exists
- when PDF acquisition succeeds, `pdf_path` is set and `source_pdf.available=true`

Important fields in `status paper`:

- `source_pdf.available`
- `source_pdf.path`
- `source_pdf.acquisition.status`

Expected acquisition states include:

- `downloaded`
- `unavailable`
- `failed`
- `skipped`

Filesystem checks:

- `data/papers/<paper_id>/metadata.json` or `metadata.xml`
- `data/papers/<paper_id>/source_pdf_acquisition.json`
- `data/papers/<paper_id>/source.pdf` when acquisition succeeded

## 4.5 Optional: Paper notes

After any paper is ingested, verify note entry and retrieval:

```bash
rks note add paper <paper_id> --content "Manual test note" --created-by human:test
rks note list paper <paper_id>
rks show paper <paper_id>
```

Expected result:

- `note add` returns a new `n_...` ID
- `note list` returns the stored note
- `show paper` includes the note under `notes`

## 4.6 Optional: Duplicate detection and merge

Prepare two records for the same paper title:

```bash
printf '%s\n' '%PDF-1.4' 'duplicate paper A' > duplicate-a.pdf
printf '%s\n' '%PDF-1.4' 'duplicate paper B' > duplicate-b.pdf
rks ingest pdf duplicate-a.pdf --title "NCBI Conserved Domain Database"
rks ingest pdf duplicate-b.pdf --title "NCBI conserved-domain database"
```

Then detect duplicates:

```bash
rks papers find-duplicates
rks papers find-duplicates --mode identifiers
```

Expected result:

- `heuristic` mode reports a duplicate group for the two paper IDs
- `identifiers` mode may return zero groups when DOI/arXiv IDs are missing

Then merge:

```bash
rks papers merge <target_paper_id> <source_paper_id> --prefer target
rks show paper <target_paper_id>
rks show paper <source_paper_id>
```

Expected result:

- merge output sets `source_deleted=true`
- `show paper <target_paper_id>` succeeds
- `show paper <source_paper_id>` returns `Paper not found`

## 5. Scenario 3: Claim Relation Candidate and Review Loop

Use two or three papers to build comparable claims.

### 5.1 Prepare three placeholder PDFs

```bash
printf '%s\n' '%PDF-1.4' 'placeholder' > paper-1.pdf
printf '%s\n' '%PDF-1.4' 'placeholder' > paper-2.pdf
printf '%s\n' '%PDF-1.4' 'placeholder' > paper-3.pdf
```

Ingest them:

```bash
rks ingest pdf paper-1.pdf
rks ingest pdf paper-2.pdf
rks ingest pdf paper-3.pdf
```

### 5.2 Import claims for each paper

For the first paper, create:

```json
{
  "claims": [
    {
      "text": "Sparse Attention improves translation accuracy on WMT14.",
      "predicate": "improves",
      "object_text": "translation accuracy",
      "context": {
        "subject_text": "Sparse Attention",
        "dataset": "WMT14"
      },
      "evidence": {
        "paper_id": "p_000001"
      },
      "confidence": 0.9
    }
  ]
}
```

For the second paper, change the dataset to `IWSLT`. For the third paper, change the text to `does not improve`.

Then import:

```bash
rks import claims p_000001 paper-1-claims.json
rks import claims p_000002 paper-2-claims.json
rks import claims p_000003 paper-3-claims.json
```

Inspect the anchor paper:

```bash
rks claims p_000001
```

Take the `c_...` value and run:

```bash
rks query claim-relations <anchor_claim_id>
```

Expected result:

- `reviewed_relations` starts empty
- `inferred_relations` includes at least one `refines`
- `inferred_relations` includes at least one `contradicts`

### 5.3 Promote one reviewed relation

Select a candidate relation and run:

```bash
rks review promote-claim-relation <anchor_claim_id> contradicts <target_claim_id> --reviewed-by agent:review --note "manual verification"
```

Then re-read:

```bash
rks query claim-relations <anchor_claim_id>
rks show claim <anchor_claim_id>
```

Expected result:

- `reviewed_relations` now includes one `contradicts`
- that relation has `relation_source=reviewed`
- `created_by` is `agent:review`
- `metadata.note` contains the note you wrote
- `show claim` also shows `reviewed_relations`

### 5.4 Retract the reviewed relation

```bash
rks review retract-claim-relation <anchor_claim_id> contradicts <target_claim_id>
```

Then re-read:

```bash
rks query claim-relations <anchor_claim_id>
```

Expected result:

- the promoted relation disappears from `reviewed_relations`
- the corresponding candidate may still remain in `inferred_relations`

This is important because it proves candidate inference and durable reviewed facts are separate layers.

## 6. Scenario 4: Agent-Facing Paper Status Operations

Start the local service:

```bash
rks serve --host 127.0.0.1 --port 8765
```

Use another terminal for HTTP calls.

### 6.1 Health check

```bash
curl -s http://127.0.0.1:8765/health
```

Expected result:

```json
{"status":"ok"}
```

### 6.2 Inspect paper status

```bash
curl -s http://127.0.0.1:8765/api/status/<paper_id>
```

Expected result:

- returns `paper`
- returns `artifacts`
- returns `stages`
- returns `source_pdf`
- returns `tasks`

This should stay semantically consistent with:

```bash
rks status paper <paper_id>
```

### 6.3 Inspect claim relations

```bash
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
```

Expected result:

- includes `reviewed_relations`
- includes `inferred_relations`
- keeps the two layers distinct

### 6.4 Promote and retract through HTTP

Promote:

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "contradicts",
    "target_claim_id": "c_000003",
    "reviewed_by": "agent:http",
    "note": "manual api test"
  }'
```

Retract:

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "contradicts",
    "target_claim_id": "c_000003"
  }'
```

Expected result:

- promote returns an edge payload
- retract returns `deleted: true`
- `GET /api/claims/<claim_id>/relations` reflects the state change

## 7. Scenario 5: Agent-Mode Task Lifecycle

Choose one paper and run:

```bash
rks extract text <paper_id> --mode agent
rks extract claims <paper_id> --mode agent
rks summarize paper <paper_id> --mode agent
```

Expected result:

- the commands return `task_id`
- `tasks list` shows queued work
- `status paper <paper_id>` reflects the task state

Then import result files:

```bash
rks import text <paper_id> agent_text.json
rks import claims <paper_id> agent_claims.json
rks import summary <paper_id> agent_summary.json
```

Expected result:

- matching tasks move to `completed`
- `result_artifact_id` is populated
- corresponding artifacts appear on disk and in `show paper`

To simulate failure:

```bash
rks tasks fail <task_id> "manual failure simulation"
```

Expected result:

- task status becomes `failed`
- `status paper` shows increased failure count

## 8. Recommended Consistency Check

After each scenario, verify three layers:

1. CLI output
2. filesystem artifacts under `data/papers/<paper_id>/`
3. HTTP response where applicable

If one layer diverges from the others, that usually indicates the product surface has not fully converged.

## 9. Common Questions

### 9.1 No source PDF after DOI or arXiv ingest. Is that always a failure?

No. As long as `source_pdf_acquisition` exists, the system recorded the outcome. The meaning depends on:

- `unavailable`: no usable PDF candidates were exposed
- `failed`: candidates existed but acquisition failed
- `skipped`: the workflow intentionally skipped acquisition

### 9.2 Why does a relation still appear after retract?

If it still appears under `inferred_relations`, that is expected. Retract removes the reviewed durable edge, not the query-time inference logic.

### 9.3 What are the highest-value regression risks?

- reference ingestion succeeds but does not persist `source_pdf_acquisition`
- reviewed relations are erased by extraction reruns
- CLI and HTTP return different semantics
- `show claim` stops exposing reviewed relations
- `status paper` stops reflecting source PDF acquisition state

## 10. Minimal Acceptance Set

If time is limited, run at least these six steps:

1. `rks ingest pdf sample.pdf`
2. `rks ingest arxiv 1706.03762`
3. `rks status paper <paper_id>`
4. `rks query claim-relations <claim_id>`
5. `rks review promote-claim-relation ...`
6. `curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations`

These six steps already cover the most important product behavior.
