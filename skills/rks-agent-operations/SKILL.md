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
- run a persistent user-agent discussion loop around one anchor paper

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

Manage paper tags for reading queues or workflow buckets:

```bash
rks papers list --limit 20 --sort created_at --order desc
rks papers mark <paper_id> --tag read_later
rks papers mark <paper_id> --tag triage
rks papers list --tag read_later
rks papers unmark <paper_id> --tag read_later
rks papers tags <paper_id>
rks papers read-later
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

Inspect the full contradiction graph for a concept (nodes + enriched edges):

```bash
rks evolution conflict-graph <concept_id>
```

`conflict-graph` returns nodes (claims with text, predicate, paper title/year, confidence) and edges (all `contradicts` relations between them). Each node also includes its cluster membership (`cluster_id`, `stance`, `role`) when a conflict cluster exists. Use this instead of making separate claim lookups when you need to reason about the full controversy structure for a concept.

`list-clusters` members are also enriched: each member now includes `claim_text`, `claim_predicate`, `claim_confidence`, `paper_title`, and `paper_year`.

Inspect hypothesis and project timelines:

```bash
rks evolution hypothesis-bucketed <hypothesis_id>
rks evolution project-timeline <project_id>
```

`hypothesis-bucketed` groups each evidence link by the publication year of its linked paper and returns per-bucket support/contradiction counts, consensus/controversy scores, and a trend label. `project-timeline` aggregates these buckets across all project hypotheses.

Query evolution analytics:

```bash
rks query review-priorities [--scope-type project --scope-id <project_id>]
rks query open-questions [--scope-type project --scope-id <project_id>]
rks query concept-controversies [--min-score 0.3] [--limit 20]
rks evolution project-summary <project_id>
```

`review-priorities` ranks pending candidates by a five-factor score: `candidate_score` (0.25), `controversy` (0.25), `hypothesis_relevant` (0.25), `recency` (0.15), `cluster_member` (0.10). The `cluster_member` factor elevates candidates whose source or target claim belongs to an active conflict cluster.

`open-questions` detects five signal types:

- `evidence_sparse_controversy` — controversy score > 0.3 with ≤ 5 claims
- `trend_shift` — concept consensus shifted > 0.3 across snapshots
- `unsupported_hypothesis` — a project hypothesis with no supporting evidence links
- `unreviewed_conflict_cluster` — conflict cluster where no member relation has been reviewed yet
- `hypothesis_concept_divergence` — hypothesis trend contradicts the concept timeline trend

HTTP evolution endpoints:

```bash
curl -s "http://127.0.0.1:8765/api/evolution/concept-controversies?min_score=0.3"
curl -s "http://127.0.0.1:8765/api/evolution/concept-consensus/<concept_id>"
curl -s "http://127.0.0.1:8765/api/evolution/conflict-clusters/<concept_id>"
curl -s "http://127.0.0.1:8765/api/evolution/conflict-graph/<concept_id>"
curl -s "http://127.0.0.1:8765/api/evolution/hypothesis/<hypothesis_id>"
curl -s "http://127.0.0.1:8765/api/evolution/hypothesis-bucketed/<hypothesis_id>"
curl -s "http://127.0.0.1:8765/api/evolution/project/<project_id>"
curl -s "http://127.0.0.1:8765/api/evolution/project-timeline/<project_id>"
curl -s "http://127.0.0.1:8765/api/query/review-priorities"
curl -s "http://127.0.0.1:8765/api/query/open-questions"
curl -s -X POST http://127.0.0.1:8765/api/evolution/cluster-conflicts -H 'Content-Type: application/json' -d '{}'
curl -s -X POST "http://127.0.0.1:8765/api/evolution/build-timeline/<concept_id>" -H 'Content-Type: application/json' -d '{}'
```

## Agent Mode Discipline

### MUST: Read the paper directly as a multimodal AI

**This is a hard constraint. When operating in agent mode, you MUST read the source document yourself using your own multimodal reading capability.**

- Locate the source PDF via `rks status paper <paper_id>` or directly at `data/papers/<paper_id>/source.pdf`.
- Read the PDF directly using the Read tool — all pages, as an AI agent.
- **NEVER** extract or process the paper text using Python scripts, subprocess calls, or shell commands.
- **NEVER** use heuristic artifacts (e.g. `extracted_text.json`) as a substitute for direct reading.
- **NEVER** pipe paper content through any local text processing tool.

Agent mode exists so the AI reasons over the document itself. Any programmatic text extraction defeats this purpose entirely.

### Task lifecycle

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

## When To Switch Skills

- If the task is specifically user-facing discussion for one paper, prefer `rks-paper-discussion`.
