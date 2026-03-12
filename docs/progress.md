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
- first-class `Method` and `Dataset` persistence
- graph edge persistence for `proposes`, `uses`, `evaluated_on`, and `cites`
- deterministic CLI queries for `claims-about` and `papers-supporting`
- deterministic reasoning queries for evidence aggregation, claim relations, methods, and datasets
- local hybrid search across papers, claims, concepts, methods, and datasets
- normalized evidence payloads with section and character offsets
- replay-stable claim IDs when extraction output is unchanged
- artifact lineage metadata including extractor version and mode
- local embeddings for papers, claims, and concepts
- paper summaries with explicit claim and paper citations
- batch ingest and extraction workflows through manifest files
- task queue tracking for all agent-mode request/result loops
- paper-level status reporting with failure visibility
- dual-track request and result schema/version tracking
- config-file based storage and model configuration
- migration/version tracking for the local database schema
- graph snapshot export and import
- local API plus lightweight web UI service surface
- reference-ingestion source PDF acquisition with inspectable acquisition outcomes
- durable reviewed claim-to-claim relations alongside non-durable inferred candidates
- a dedicated operations layer for paper status and claim-relation review flows
- HTTP review endpoints for claim-relation promotion and retraction
- direct research output surfaces for grounded answers, topic briefs, disagreements, and opportunities

## Implemented Milestones

- Milestone 0: project skeleton
- Milestone 1: paper ingestion and inspection
- Milestone 2: extracted text artifacts and claim persistence
- Milestone 3: concept linking and edge persistence
- Milestone 4: first deterministic query templates
- Phase 1: Quality Hardening
- Phase 2: Research Graph Expansion
- Phase 3: Retrieval and Reasoning Upgrade
- Phase 4: Agent Workflow Maturity
- Phase 5: Productization Layer

## Remaining Work

- continue hardening real-world fixtures and provider integrations

## Latest Architectural Direction

RKS remains intentionally local and inspectable.

Every ingestion flow should create filesystem artifacts first, then persist structured rows and graph edges. This keeps the debugging surface visible and avoids hiding extraction failures inside opaque database state.

All LLM-backed capabilities now also follow a mandatory dual-track rule:

- direct provider execution through `llm-api`
- external agent execution through `agent`

See [dual-track-llm-contract.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/dual-track-llm-contract.md).
