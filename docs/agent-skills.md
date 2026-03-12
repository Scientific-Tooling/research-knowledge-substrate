# Agent Skills

The repository now includes dedicated skills for agents that operate or modify RKS.

## Available Skills

### `rks-build-paper-graph`

Purpose:

- ingest papers or references
- run extraction
- leave a paper in a queryable graph state

### `rks-query-substrate`

Purpose:

- inspect papers, claims, concepts, and evidence
- run local search and deterministic graph queries
- produce summaries from already-ingested graph data
- distinguish inferred claim relations from reviewed durable relations
- generate direct output-layer answers and topic syntheses from the local graph

### `rks-dual-track-llm`

Purpose:

- enforce the `llm-api` / `agent` contract for all LLM-backed RKS tasks
- guide the request/import loop for external agents

### `rks-maintain-worktree`

Purpose:

- guide repository development work
- ensure docs, tests, and commits stay synchronized with code changes

### `rks-agent-operations`

Purpose:

- run batch ingest and extraction workflows
- inspect queued/completed/failed agent tasks
- audit paper-level workflow status and failure states
- promote or retract reviewed claim relations
- verify CLI and HTTP operations remain consistent
- operate output-layer commands repeatedly across topics

### `rks-codex-operator`

Purpose:

- let Codex act as the external agent driving RKS end-to-end
- validate ingest, query, review, and HTTP product behavior
- enforce ID capture, artifact inspection, and CLI/HTTP cross-checks

### `rks-research-output`

Purpose:

- produce directly consumable research outputs from the graph
- answer questions, brief topics, surface disagreements, and suggest opportunities
- keep outputs grounded in claims, papers, methods, datasets, and uncertainties

### `rks-user-demo`

Purpose:

- let an agent demonstrate RKS capabilities to a human user in a clear sequence
- show ingest, graph inspection, output generation, query, and review with explicit narration
- optimize for understandable product walkthroughs rather than exhaustive verification

### `rks-autotest`

Purpose:

- let an agent automatically validate the RKS product surface end-to-end
- verify persisted artifacts, IDs, review mutations, and CLI/HTTP consistency
- regress answer, brief, disagreement, and opportunity outputs
- produce concrete failure reports and reproduction steps

## Why These Skills Exist

Without explicit repository-specific skills, a general agent has to rediscover:

- which RKS commands to run
- when to use `heuristic`, `llm-api`, or `agent`
- how to validate results
- which docs and tests must move with code changes

These skills make that behavior explicit and reusable.
