---
name: rks-user-demo
description: Use this skill when an agent should demonstrate RKS to a user end-to-end: preparing a small workspace, ingesting a paper or reference, showing graph outputs, and narrating the product behavior in a clear sequence.
---

# RKS User Demo

Use this skill when the goal is to show a human user what RKS can do, not just to operate or test it silently.

## Trigger

Use this skill for requests such as:

- demo RKS to me
- show me how RKS works
- walk through the product with examples
- present an end-to-end RKS flow
- give a live demonstration using the CLI or HTTP API

## Demo Principles

- Prefer a short, coherent scenario over broad feature coverage
- Show visible product value early: ingest, inspect, query, review
- Announce what each step is proving before running it
- Keep IDs, artifacts, and outputs explicit so the user can follow the system state
- If possible, show one read path and one write path

## Recommended Demo Order

### 1. Initialize the workspace

```bash
rks config init
rks init-db
rks migrate
rks config show
```

Explain:

- where data is stored
- whether reference PDF acquisition is enabled

### 2. Ingest one source

Use the simplest relevant path:

```bash
rks ingest pdf <path>
```

or:

```bash
rks ingest doi <doi>
rks ingest arxiv <id>
```

Then inspect:

```bash
rks show paper <paper_id>
rks status paper <paper_id>
```

Explain:

- what artifacts were created
- whether source PDF acquisition succeeded

### 3. Show graph content

```bash
rks extract claims <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
rks show claim <claim_id>
```

Explain:

- how paper text becomes claims and concepts
- how evidence is attached

### 4. Show retrieval or reasoning

```bash
rks search <query>
rks output answer "<question>"
rks output brief "<topic>"
rks query claims-about <concept>
rks query claim-relations <claim_id>
```

If useful:

```bash
rks summarize paper <paper_id>
```

Explain:

- lexical versus semantic or deterministic query surfaces
- direct output surfaces versus low-level graph inspection
- inferred versus reviewed claim relations

### 5. Show one review action

If a claim-relation candidate exists:

```bash
rks review promote-claim-relation <source_claim_id> <relation_type> <target_claim_id> --reviewed-by agent:demo
rks query claim-relations <source_claim_id>
```

This demonstrates that RKS distinguishes:

- candidate inference
- durable reviewed graph facts

### 6. Optionally show the HTTP surface

```bash
rks serve --host 127.0.0.1 --port 8765
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
curl -s "http://127.0.0.1:8765/api/output/brief?topic=<encoded-topic>"
```

Use this only if it adds clarity for the user.

## Narration Discipline

When presenting the demo:

1. say what the next command will prove
2. run the command
3. report the important output, not the full dump
4. connect the result to a product capability

Prefer statements like:

- "This shows the ingest path created durable artifacts."
- "This shows how RKS turns stored graph structure into a user-facing answer."
- "This shows the relation is still inferred, not reviewed."
- "This promote step turns a candidate relation into a persisted graph fact."

## Expected Outcome

A good demo should leave the user with a clear understanding of:

- how RKS ingests and stores research material
- how claims and concepts become queryable
- how review changes the durable graph
- how RKS produces answers, summaries, and inspiration from the graph
- how agents can drive the product through stable operations

## When To Switch Skills

- If the task is silent verification rather than demonstration, switch to `rks-autotest`
- If the task is broad external-agent operation, switch to `rks-codex-operator`
- If the task is code modification, switch to `rks-maintain-worktree`
