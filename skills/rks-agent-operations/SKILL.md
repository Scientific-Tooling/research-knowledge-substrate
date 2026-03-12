---
name: rks-agent-operations
description: Use this skill when an agent needs to run repeated RKS workflows, inspect queued work, recover from failures, or audit extraction status across papers.
---

# RKS Agent Operations

Use this skill when the task is to operate RKS as a repeatable agent workflow instead of performing a one-off extraction.

## Trigger

Use this skill for requests such as:

- ingest these papers in batch
- run extraction for a manifest of papers
- check which agent requests are still queued
- mark an agent task as failed
- inspect extraction status for a paper
- verify CLI and HTTP product operations agree
- promote or retract reviewed claim relations

## Core Commands

Batch ingest:

```bash
rks batch ingest manifest.json
```

Batch extraction:

```bash
rks batch extract claims manifest.json
rks batch extract summary manifest.json --mode agent
```

Inspect the task queue:

```bash
rks tasks list
rks tasks list --paper-id <paper_id>
rks tasks show <task_id>
```

Record a task failure:

```bash
rks tasks fail <task_id> "reason"
```

Inspect paper workflow status:

```bash
rks status paper <paper_id>
```

Inspect claim relation state:

```bash
rks query claim-relations <claim_id>
rks show claim <claim_id>
```

Promote a reviewed relation:

```bash
rks review promote-claim-relation <source_claim_id> <relation_type> <target_claim_id> --reviewed-by agent:review
```

Retract a reviewed relation:

```bash
rks review retract-claim-relation <source_claim_id> <relation_type> <target_claim_id>
```

HTTP inspection and review endpoints:

```bash
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract -H 'Content-Type: application/json' -d '{...}'
```

## Agent Mode Discipline

When using `--mode agent`, do not stop at the request artifact. Confirm that:

1. the returned payload includes a `task_id`
2. the task is visible through `rks tasks show <task_id>`
3. the result import transitions the task to `completed`, or explicitly mark it `failed`

When operating claim relations:

1. inspect `inferred_relations` before promoting anything
2. record the exact `source_claim_id` and `target_claim_id` from command output
3. after promote or retract, re-run both CLI and HTTP inspection to confirm consistency
4. do not treat `inferred_relations` as durable truth

When operating reference ingestion:

1. check `source_pdf.available`
2. inspect `source_pdf.acquisition.status`
3. verify `source_pdf_acquisition` artifact exists even when acquisition failed or was skipped

## Expected Outcome

A healthy paper or batch run should have:

- explicit queued/completed/failed task records
- visible artifact stage status
- no hidden failures outside the task table
- consistent paper status across CLI and HTTP
- reviewed claim relations changing only through explicit promote or retract operations
