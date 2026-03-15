# Product Priorities

This document turns the current product direction into an execution checklist. The emphasis is agent-first research operations, not UI polish and not autonomous orchestration for its own sake.

## Principles

- Prioritize higher-quality inputs over broader feature surface.
- Persist only reviewed or explicitly promoted semantic facts.
- Keep the system agent-friendly through stable CLI and HTTP operations.
- Avoid spending roadmap capacity on richer frontend presentation unless it directly supports review, recovery, or evidence inspection.
- Keep literature discovery and non-canonical retrieval outside RKS. External agents should resolve messy web inputs into stable identifiers, canonical URLs, direct PDF URLs, or local files before ingestion.

## Priority 0: Input Completeness and Failure Visibility

- [x] Add reference-ingestion source acquisition for DOI and arXiv workflows.
- [x] Let metadata providers return `pdf_candidates` so source acquisition can stay provider-driven.
- [x] Persist acquired reference PDFs as first-class `source_pdf` artifacts.
- [x] Persist acquisition outcomes as inspectable artifacts even when no PDF is downloaded.
- [x] Expose source acquisition state in `status paper` and the local HTTP API.

Exit criteria:

- `rks ingest doi ...` and `rks ingest arxiv ...` can attempt source acquisition.
- Successful acquisitions produce `data/papers/<paper_id>/source.pdf`.
- Skipped, unavailable, and failed acquisition attempts remain inspectable after ingestion.

## Priority 1: Semantic Durability Through Review

- [x] Keep query-time inferred claim relations as candidates, not durable truth.
- [x] Persist reviewed `supports` / `refines` / `contradicts` claim-to-claim relations into the existing graph.
- [x] Add a narrow CLI review flow for promotion and retraction.
- [x] Distinguish reviewed relations from inferred relations in query and service responses.
- [x] Surface reviewed claim relations in `show claim`.

Exit criteria:

- Agent workflows can promote or retract a claim relation without editing the database directly.
- Query responses clearly separate inferred candidates from reviewed graph facts.
- Review persistence survives extraction reruns.

## Priority 2: Stable Agent-Facing Operations

- [x] Introduce a dedicated operations layer for high-level product actions.
- [x] Move paper status assembly and claim-relation review logic behind operations interfaces.
- [x] Expose agent-friendly HTTP endpoints for paper status and claim relation inspection.
- [x] Add HTTP write endpoints for claim-relation promotion and retraction.
- [x] Keep the operations surface narrow and auditable.

Exit criteria:

- CLI and HTTP no longer reconstruct the same product logic independently.
- External agents can inspect paper status and claim relations through stable endpoints.
- Review writes are available without introducing a richer orchestration subsystem.

## Priority 3: Operational Hardening for Local Beta

- [x] Add request logging to the HTTP service (all GET/POST to stderr).
- [x] Validate required fields on all POST endpoints with clear error messages.
- [x] Return structured error responses (400 for bad input, 500 for server errors) instead of dropping connections.
- [x] Sync root and packaged migration directories (0004-0006).
- [x] Register `evolution_event` ID prefix for the Knowledge Evolution System.
- [x] Fix test drift from claim extractor version bump (1.0 to 1.1) and LLM provider timeout parameter.

Exit criteria:

- All 32 unit tests pass.
- Malformed HTTP POST requests return 400 with a descriptive message.
- Server errors do not silently close connections.
- Running from repo checkout or pip install uses the same set of migrations.

## Non-Priorities

- Richer frontend visualization beyond lightweight inspection.
- Additional autonomous orchestration layers.
- Broad expansion of node or edge types without a product need tied to input quality, review, or agent operations.
