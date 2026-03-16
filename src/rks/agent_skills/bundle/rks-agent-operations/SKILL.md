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
- operate the research output layer repeatedly across topics

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
curl -s http://127.0.0.1:8765/api/papers/<paper_id>/notes
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
curl -s "http://127.0.0.1:8765/api/output/brief?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=<encoded-topic>"
curl -s -X POST http://127.0.0.1:8765/api/papers/<paper_id>/notes -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract -H 'Content-Type: application/json' -d '{...}'
```

All POST endpoints validate required fields. Missing fields return `400` with a message like `Missing required fields: name`. Malformed JSON also returns `400`. Unhandled server errors return `500`. All requests are logged to stderr.

Persist operator context as a paper note when it needs to survive beyond the current session:

```bash
rks note add paper <paper_id> --content "Needs manual review of the benchmark split." --created-by agent:review
rks note list paper <paper_id>
```

Generate direct output surfaces:

```bash
rks output answer "<question>"
rks output brief "<topic>"
rks output disagreements "<topic>"
rks output open-questions "<topic>"
rks output review-priorities "<topic>"
rks output opportunities "<topic>"
```

Materialize claim relation candidates:

```bash
rks evolution materialize-candidates [<claim_id>]
```

Cluster conflicts across concepts:

```bash
rks evolution cluster-conflicts [--concept-id <concept_id>]
```

Build concept timelines:

```bash
rks evolution build-timeline <concept_id>
rks evolution build-timeline-bucketed <concept_id>
```

Query evolution analytics:

```bash
rks query review-priorities [--scope-type project --scope-id <project_id>]
rks query open-questions [--scope-type project --scope-id <project_id>]
rks query concept-controversies [--min-score 0.3] [--limit 20]
rks evolution project-summary <project_id>
```

HTTP evolution endpoints:

```bash
curl -s "http://127.0.0.1:8765/api/evolution/concept-controversies?min_score=0.3"
curl -s "http://127.0.0.1:8765/api/evolution/concept-consensus/<concept_id>"
curl -s "http://127.0.0.1:8765/api/evolution/conflict-clusters/<concept_id>"
curl -s "http://127.0.0.1:8765/api/evolution/project/<project_id>"
curl -s "http://127.0.0.1:8765/api/query/review-priorities"
curl -s "http://127.0.0.1:8765/api/query/open-questions"
curl -s -X POST http://127.0.0.1:8765/api/evolution/cluster-conflicts -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "http://127.0.0.1:8765/api/evolution/build-timeline/<concept_id>" -H 'Content-Type: application/json' -d '{}'
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

When operating the output layer:

1. preserve the topic or question used to generate the output
2. verify that supporting claims and papers are present for grounded topics
3. treat opportunities as evidence-backed suggestions, not free-form invention
4. cross-check important output surfaces through both CLI and HTTP when consistency matters

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
