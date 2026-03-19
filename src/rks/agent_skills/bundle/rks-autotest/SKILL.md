---
name: rks-autotest
description: "Use this skill when an agent should automatically validate RKS behavior as a product surface: set up a workspace, run repeatable CLI and HTTP checks, verify artifacts and IDs, and report failures with concrete reproduction steps."
---

# RKS Autotest

Use this skill when the goal is automated product verification, not a user-facing demonstration.

## Trigger

Use this skill for requests such as:

- automatically test RKS
- run an end-to-end verification of the product
- validate the CLI and HTTP surfaces
- check that review flows and artifacts still behave correctly
- regress the current agent-facing operations
- regress the new research output layer

## Test Principles

- Prefer deterministic, minimal fixtures
- Verify both command output and persisted state
- Capture all generated IDs from outputs instead of guessing them
- Check one success path and, when possible, one mutation path
- Report failures as product regressions, not just command errors

## Recommended Coverage

### 1. Workspace bootstrap

```bash
rks config init
rks init-db
rks migrate
rks config show
```

Verify:

- commands succeed
- config fields are sensible

### 2. Input completeness

Run at least one local PDF ingest:

```bash
rks ingest pdf <path>
rks show paper <paper_id>
rks status paper <paper_id>
```

Run at least one DOI or arXiv ingest when feasible:

```bash
rks ingest doi <doi>
```

or:

```bash
rks ingest arxiv <id>
```

Verify:

- `metadata` artifact exists for reference ingestion
- `source_pdf_acquisition` artifact exists
- `source_pdf.available` and `source_pdf.acquisition.status` agree with on-disk state

### 3. Graph-building path

For at least one paper:

```bash
rks extract claims <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
```

Verify:

- claims exist
- concepts exist when claims were extracted
- status stages are updated

### 4. Claim-relation review path

Construct or import claims that can yield a relation candidate, then run:

```bash
rks query claim-relations <claim_id>
```

Promote:

```bash
rks review promote-claim-relation <source_claim_id> <relation_type> <target_claim_id> --reviewed-by agent:test
```

Re-read:

```bash
rks query claim-relations <source_claim_id>
rks show claim <source_claim_id>
```

Retract:

```bash
rks review retract-claim-relation <source_claim_id> <relation_type> <target_claim_id>
```

Verify:

- `reviewed_relations` changes after promote
- `reviewed_relations` changes after retract
- `inferred_relations` and `reviewed_relations` remain distinct

### 5. HTTP surface consistency

Start the server:

```bash
rks serve --host 127.0.0.1 --port 8765
```

Check:

```bash
curl -s http://127.0.0.1:8765/health
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote -H 'Content-Type: application/json' -d '{...}'
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract -H 'Content-Type: application/json' -d '{...}'
```

Verify:

- HTTP read surfaces match CLI semantics
- HTTP write surfaces mutate state as expected
- POST with missing required fields returns `400` with a `Missing required fields` message
- POST with malformed JSON returns `400`
- requests are logged to stderr

### 6. Research output layer

Check:

```bash
rks output answer "<question>"
rks output brief "<topic>"
rks output disagreements "<topic>"
rks output opportunities "<topic>"
curl -s "http://127.0.0.1:8765/api/output/answer?q=<encoded-question>"
curl -s "http://127.0.0.1:8765/api/output/brief?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/disagreements?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=<encoded-topic>"
```

Verify:

- outputs include grounded evidence objects rather than only prose
- answer and brief surfaces are not empty for a grounded topic
- disagreement and opportunity outputs remain auditable from claims, papers, methods, or datasets
- CLI and HTTP output semantics match

## Required Report Format

At the end, report:

1. environment setup result
2. fixtures used
3. generated IDs
4. passed checks
5. failed checks
6. exact reproduction commands for failures
7. likely fault domain:
   CLI shape, storage/artifact persistence, query logic, output generation, review mutation, or HTTP surface

## Important Constraints

- Do not patch the database manually to force a passing result
- Do not stop after the first successful command; verify persisted state
- Do not claim success if CLI and HTTP diverge semantically
- If a server cannot be started in the current environment, state that explicitly and continue with non-socket checks where possible

## When To Switch Skills

- If the task is interactive explanation to a user, switch to `rks-user-demo`
- If the task is general external-agent operation, switch to `rks-codex-operator`
- If the task is repository implementation work, switch to `rks-maintain-worktree`
