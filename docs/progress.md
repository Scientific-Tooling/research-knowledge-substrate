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
- richer research-output contracts with explicit conclusion, confidence, evidence assessment, reading guidance, disagreement causes, and validation plans
- readiness-aware paper status with missing-step, blocker, review, and suggested-command guidance for agents
- direct reading-list, compare, open-question, and review-priority output surfaces for user-facing research workflows
- clustered claim ranking with reviewed-evidence preference and broader research-output fixtures
- `prepare_paper_for_output` planning/execution plus persisted agent execution report artifacts
- batch audit summaries for ingest, extract, summary, and output runs
- install-time skill bundle metadata plus `rks doctor` self-checks and package smoke validation in CI
- package metadata, packaged migrations, and CI workflows for formal PyPI distribution readiness
- installed CLI export of bundled repository skills for Codex, Claude Code, and other agent runtimes
- query performance indexes for concept lookups, edge type filtering, and note targets
- WAL journal mode for concurrent read/write access
- expanded heuristic claim extraction with 30+ predicate patterns (v1.1), improved sentence segmentation, and passive voice handling
- claim relation inference caching and concept-based candidate narrowing to eliminate O(n²) scans
- materialized claim relation candidate layer with promote/reject/supersede lifecycle
- evolution event recording for relation promotions and retractions
- concept timeline snapshots for tracking support and contradiction counts over time
- LLM provider retry logic with exponential backoff and timeout
- loosened method and dataset entity extraction heuristics for better recall
- unit tests for extraction heuristics (sentence splitting, predicate detection, subject-object parsing) and query polarity inference
- HTTP endpoints for candidate materialization, promotion, rejection, evolution events, concept timeline, and hypothesis evolution
- hypothesis evolution views with evidence aggregation, trend indicators, and event history
- extraction quality metrics report with per-paper claim counts, predicate distribution, and mode breakdown
- improved sentence boundary handling for dot-separated acronyms (U.S., i.e., e.g.) and expanded abbreviation set
- fixed normalization regex alternation ordering for proper multi-pass filler stripping
- direct PDF-to-LLM: llm-api track now sends the source PDF as base64 alongside the text prompt, so the LLM can read the actual document even when heuristic extraction fails
- agent track text requests now surface the source PDF path at the top level with updated instructions to read the PDF directly
- request logging to stderr for all HTTP GET and POST handlers with warning and exception levels for errors
- input validation on all POST endpoints with clear missing-field error messages and malformed JSON rejection
- unhandled exception safety in HTTP handlers returning 500 instead of dropping the connection
- first-class `rks papers merge` command to consolidate duplicate paper IDs while re-homing notes, links, tags, tasks, and paper-scoped references
- first-class `rks papers find-duplicates` command with `title` and `identifiers` modes for duplicate-paper discovery
- removed heuristic extraction as a user-facing mode; extraction mode choices are now `llm-api` and `agent` only; internal provenance labels updated to `pdf-extractor` and `regex`
- `rks concept add-alias <concept_id> <alias>` command to register synonym terms so future imports route to an existing concept
- `rks concept merge <source_id> <target_id>` command to consolidate fragmented concept nodes, re-homing all claims and edges and absorbing source aliases into target
- `concept_aliases` optional field in `claims.v3` schema — agents can return canonical-to-synonym mappings alongside claims; import applies them before concept resolution to prevent fragmentation at ingest time
- portable workspace archive (`rks export workspace` / `rks import workspace`) — bundles all DB tables and referenced files into a single `.tar.gz` with relative paths, with path rewriting on import so the archive is machine-independent

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
- Phase 6: Knowledge Evolution Foundation

## Remaining Work

- continue hardening real-world fixtures and provider integrations

## Latest Architectural Direction

RKS remains intentionally local and inspectable.

Every ingestion flow should create filesystem artifacts first, then persist structured rows and graph edges. This keeps the debugging surface visible and avoids hiding extraction failures inside opaque database state.

All LLM-backed capabilities now also follow a mandatory dual-track rule:

- direct provider execution through `llm-api`
- external agent execution through `agent`

See [dual-track-llm-contract.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/dual-track-llm-contract.md).
