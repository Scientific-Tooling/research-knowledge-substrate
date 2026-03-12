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

## Why These Skills Exist

Without explicit repository-specific skills, a general agent has to rediscover:

- which RKS commands to run
- when to use `heuristic`, `llm-api`, or `agent`
- how to validate results
- which docs and tests must move with code changes

These skills make that behavior explicit and reusable.
