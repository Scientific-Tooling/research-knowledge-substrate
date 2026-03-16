---
name: rks-codex-operator
description: Use this skill when Codex itself should act as the external agent operating RKS end-to-end through CLI and HTTP: ingesting sources, validating artifacts, driving review flows, and checking agent-facing product behavior.
---

# RKS Codex Operator

Use this skill when Codex is not modifying the RKS codebase, but is instead operating the built product as an external agent.

## Trigger

Use this skill for requests such as:

- use Codex to test RKS
- run RKS end-to-end as an agent
- validate the agent workflow with Codex
- ingest, query, review, and verify RKS through terminal commands
- compare CLI and HTTP behavior for the same research operation

## Operating Rules

- Work from the repository root
- Prefer `rks` CLI first, then use HTTP to cross-check agent-facing behavior
- Never invent `paper_id`, `claim_id`, or `task_id`; always parse them from command output
- When relation review is involved, inspect `inferred_relations` before promote or retract
- After any write operation, re-read the affected object through at least one read path

## Standard Workflow

### 1. Initialize

```bash
rks config init
rks init-db
rks migrate
rks config show
```

Confirm:

- `data_dir` resolves correctly
- `reference_pdf_acquisition` is set as expected

### 2. Build or ingest data

Use one of:

```bash
rks ingest pdf <path>
rks ingest doi <doi>
rks ingest arxiv <id>
```

For graph-ready state:

```bash
rks extract claims <paper_id>
```

Inspect:

```bash
rks show paper <paper_id>
rks status paper <paper_id>
```

### 3. Validate artifacts

For every important paper, check:

- artifact presence through `rks show paper`
- stage state through `rks status paper`
- filesystem artifacts under `data/papers/<paper_id>/`

For DOI or arXiv ingestion, explicitly inspect:

- `source_pdf.available`
- `source_pdf.acquisition.status`
- `source_pdf_acquisition` artifact

When a paper needs follow-up context, persist it as a paper note instead of leaving it only in the chat transcript:

```bash
rks note add paper <paper_id> --content "Need manual comparison with the contradiction case." --created-by agent:review
rks note list paper <paper_id>
```

When the task is organized around a concrete research investigation, create a project and keep working hypotheses there:

```bash
rks project create --name "Sparse Attention Review" --research-question "Which papers matter most for realistic long-context evaluation?"
rks note add project <project_id> --content "Separate benchmark realism from headline wins." --created-by agent:review
rks project add-paper <project_id> <paper_id> --link-type key_evidence --created-by agent:review
rks project add-link <project_id> claim <claim_id> --link-type key_evidence --created-by agent:review
rks project add-link <project_id> method <method_id> --link-type focus --created-by agent:review
rks project add-link <project_id> dataset <dataset_id> --link-type benchmark --created-by agent:review
rks project add-link <project_id> concept <concept_id> --link-type focus --created-by agent:review
rks project links <project_id>
rks hypothesis create <project_id> --text "Sparse attention gains shrink under realistic evaluation." --status active --created-by agent:review
rks hypothesis add-evidence <hypothesis_id> paper <paper_id> --relation-type supported_by --created-by agent:review
rks output project-brief <project_id>
rks output project-review-priorities <project_id>
rks plan query "What should we review next?" --project-id <project_id>
```

### 4. Run query and review flows

Inspect graph state:

```bash
rks search <query>
rks output answer "<question>"
rks output brief "<topic>"
rks output disagreements "<topic>"
rks output open-questions "<topic>"
rks output review-priorities "<topic>"
rks output opportunities "<topic>"
rks claims <paper_id>
rks show claim <claim_id>
rks query claim-relations <claim_id>
```

Promote a relation only after reading candidate output:

```bash
rks review promote-claim-relation <source_claim_id> <relation_type> <target_claim_id> --reviewed-by agent:review
```

Retract when needed:

```bash
rks review retract-claim-relation <source_claim_id> <relation_type> <target_claim_id>
```

### 5. Run evolution workflows (optional, after claim relations are reviewed)

```bash
# Materialize candidates and build timelines
rks evolution materialize-candidates
rks evolution build-timeline <concept_id>
rks evolution build-timeline-bucketed <concept_id>

# Cluster conflicts to detect disputed areas
rks evolution cluster-conflicts

# Inspect the full contradiction graph for a concept
rks evolution conflict-graph <concept_id>

# Inspect hypothesis and project evolution over time
rks evolution hypothesis-bucketed <hypothesis_id>
rks evolution project-timeline <project_id>

# Query ranked controversies and priorities
rks query concept-controversies --min-score 0.2
rks query review-priorities
rks query open-questions
rks evolution project-summary <project_id>
```

`open-questions` detects five signal types: `evidence_sparse_controversy`, `trend_shift`, `unsupported_hypothesis`, `unreviewed_conflict_cluster`, `hypothesis_concept_divergence`.

Evolution output is also embedded in standard output surfaces:

- `rks output disagreements "<topic>"` → includes `conflict_clusters`
- `rks output open-questions "<topic>"` → includes `evolution_questions`
- `rks output review-priorities "<topic>"` → includes `evolution_priorities`

### 6. Cross-check HTTP behavior

Start the local service:

```bash
rks serve --host 127.0.0.1 --port 8765
```

Then inspect:

```bash
curl -s http://127.0.0.1:8765/health
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
curl -s http://127.0.0.1:8765/api/projects
curl -s http://127.0.0.1:8765/api/projects/<project_id>
curl -s http://127.0.0.1:8765/api/projects/<project_id>/links
curl -s http://127.0.0.1:8765/api/hypotheses/<hypothesis_id>
curl -s "http://127.0.0.1:8765/api/evolution/conflict-graph/<concept_id>"
curl -s "http://127.0.0.1:8765/api/evolution/hypothesis-bucketed/<hypothesis_id>"
curl -s "http://127.0.0.1:8765/api/evolution/project-timeline/<project_id>"
curl -s "http://127.0.0.1:8765/api/output/answer?q=<encoded-question>"
curl -s "http://127.0.0.1:8765/api/output/brief?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/disagreements?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=<encoded-topic>"
curl -s http://127.0.0.1:8765/api/output/projects/<project_id>/brief
curl -s "http://127.0.0.1:8765/api/output/projects/<project_id>/answer?q=<encoded-question>"
curl -s "http://127.0.0.1:8765/api/plan/query?q=<encoded-request>&project_id=<project_id>"
```

For relation writes:

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/projects -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/projects/<project_id>/links -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/projects/<project_id>/hypotheses -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/hypotheses/<hypothesis_id>/evidence -H 'Content-Type: application/json' -d '{...}'
```

All POST endpoints validate required fields and return `400` with a clear message on missing fields or malformed JSON. Unhandled errors return `500`. Requests are logged to stderr.

## Required Output Discipline

When reporting back, include:

1. environment and config state
2. all key IDs used
3. artifact and status findings
4. answer or brief findings
5. inferred versus reviewed relation findings
6. CLI versus HTTP consistency findings
7. failures, anomalies, and likely causes

## Failure Handling

If a step fails:

- inspect the relevant paper or task state before retrying
- prefer rerunning the RKS command over manual database edits
- if the issue is schema-shaped, use the documented import path instead of patching rows directly

## When To Switch Skills

- If you need to change the RKS codebase, switch to `rks-maintain-worktree`
- If the task is only graph inspection, switch to `rks-query-substrate`
- If the task is only ingest/build, switch to `rks-build-paper-graph`
