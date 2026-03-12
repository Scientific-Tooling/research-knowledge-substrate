# Progress

## Current Status

The repository now has a hardened post-MVP base for extraction quality:

- local SQLite initialization
- PDF ingestion into stable paper IDs
- metadata and extracted text artifacts on disk
- stronger local PDF text recovery through a stream-aware backend
- section detection artifacts with paragraph offsets on disk
- heuristic structured claim extraction with more stable subject/object parsing
- optional `llm-api` claim/text extraction when the user provides an API key
- optional `agent` extraction workflow for Codex, Claude Code, or other external agents
- a formal dual-track contract for all LLM-backed tasks
- concept normalization and persistence
- graph edge persistence for `contains`, `supported_by`, and `about`
- deterministic CLI queries for `claims-about` and `papers-supporting`
- local search across papers, claims, and concepts
- normalized evidence payloads with section and character offsets
- replay-stable claim IDs when extraction output is unchanged
- artifact lineage metadata including extractor version and mode

## Implemented Milestones

- Milestone 0: project skeleton
- Milestone 1: paper ingestion and inspection
- Milestone 2: extracted text artifacts and claim persistence
- Milestone 3: concept linking and edge persistence
- Milestone 4: first deterministic query templates
- Phase 1: Quality Hardening

## Remaining Work

- add first-class method and dataset extraction
- expand graph edges beyond claims and concepts
- add semantic retrieval and claim-relation reasoning
- add batch and queue-based agent workflows
- add config, migrations, export/import, and service surfaces

## Latest Architectural Direction

RKS remains intentionally local and inspectable.

Every ingestion flow should create filesystem artifacts first, then persist structured rows and graph edges. This keeps the debugging surface visible and avoids hiding extraction failures inside opaque database state.

All LLM-backed capabilities now also follow a mandatory dual-track rule:

- direct provider execution through `llm-api`
- external agent execution through `agent`

See [dual-track-llm-contract.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/dual-track-llm-contract.md).
