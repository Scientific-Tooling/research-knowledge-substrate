# Design vs Implementation Comparison

## Purpose

This document compares the current RKS implementation against the original design documents now archived under `docs/archive/original-design/`.

Scope:

- included: the original design and architecture documents
- excluded as primary comparison targets: status/rollup documents such as `progress.md` and archived plan/status records under `docs/archive/completed-plans/`

Reference date:

- 2026-03-15

## Executive Summary

The current implementation is strongly aligned with the original RKS design direction.

What is now broadly aligned:

- RKS is implemented as an agent-first local research substrate rather than a PDF manager
- the minimal research graph is present in practice: `Paper`, `Claim`, `Method`, `Dataset`, and `Concept`
- the system uses stable object IDs, artifact-first extraction, graph edges, local semantic retrieval, and traceable reasoning outputs
- the dual-track LLM contract is implemented and extended with task/status/schema tracking
- the system has moved beyond the original MVP and now includes batch workflows, graph snapshots, config, migrations, and a local service/UI surface

What remains only partially aligned:

- concept hierarchy is still shallow and heuristic rather than a richer ontology
- claim-to-claim structure is partially materialized through the candidate layer and review promotion, but most relations are still inferred at query time
- the reasoning layer is implemented as deterministic query templates, not a full natural-language query planner
- extraction quality is much stronger than the MVP, but still far simpler than the most ambitious reading of the pipeline documents

What is intentionally different:

- the implementation remains much more pragmatic than some design docs suggest
- several “logical layers” are still collapsed into a local `SQLite + filesystem` deployment model
- the stack differs from the original MVP recommendations in several places, especially CLI, validation, HTTP, and test tooling
- reference ingestion is intentionally bounded to stable identifiers, canonical reference URLs, direct PDF URLs, and local files rather than general web crawling

## Comparison Scale

- `Aligned`: the current implementation matches the document's core claims
- `Mostly aligned`: the current implementation follows the design, with some simplifications
- `Partially aligned`: the design direction is visible, but important parts are still simplified or absent
- `Code ahead of document`: implementation has materially exceeded the original design document

## 1. Positioning and System Shape

Primary docs:

- `archive/original-design/project-positioning.md`
- `archive/original-design/research-knowledge-substrate-overview.md`

Status:

- `Aligned`

Where the implementation matches:

- the system center is no longer the raw paper file; structured research objects are first-class
- papers behave as evidence containers rather than the only meaningful unit
- the repository is clearly agent-first and CLI/API-driven
- graph structure and semantic retrieval both exist

Current implementation evidence:

- object model and IDs: `src/rks/domain/models.py`, `src/rks/ids.py`
- graph persistence: `src/rks/storage/schema.py`, `src/rks/storage/edge_repository.py`
- hybrid retrieval and reasoning: `src/rks/query/service.py`, `src/rks/query/semantic.py`
- local service surface: `src/rks/service/server.py`

Where code has gone beyond the original framing:

- the system now includes a lightweight local web UI and HTTP service
- the repository has explicit task tracking, batch workflows, and graph snapshot export/import
- the implementation now includes productization and workflow surfaces that were outside the original conceptual framing

Conclusion:

- the product identity described in these documents is now reflected in the codebase, not just in the narrative

## 2. Minimal Research Graph

Primary doc:

- `archive/original-design/minimal-research-graph.md`

Status:

- `Mostly aligned`

Aligned parts:

- all five core node types are implemented: `Paper`, `Claim`, `Method`, `Dataset`, `Concept`
- the following key edge families are implemented: `cites`, `contains`, `proposes`, `uses`, `about`, `supported_by`, `evaluated_on`
- the repository structure now behaves like a minimal research graph rather than a claim-only MVP

Current implementation evidence:

- schema: `src/rks/storage/schema.py`
- graph edge writes for claims and concepts: `src/rks/concepts/service.py`
- graph edge writes for methods/datasets/citations: `src/rks/extraction/entities.py`

Gaps relative to the document:

- `Claim --contradicts--> Claim` is not persisted as an edge; contradiction is inferred at query time in `src/rks/query/service.py`
- `Claim --supports--> Claim` and `Claim --refines--> Claim` are also query-time inferences rather than durable stored graph edges
- `Method -> Concept` semantics are represented mainly through `about_concept_id`, not as a first-class edge in `edges`
- the document hints at a fuller claim network, but the current graph remains paper-grounded and query-driven rather than densely interlinked

Conclusion:

- the implemented graph now matches the intended minimal graph shape closely, but claim-to-claim graph materialization is still lighter than the design ideal

## 3. Structured Claim Model

Primary doc:

- `archive/original-design/structured-claim-model.md`

Status:

- `Mostly aligned`

Aligned parts:

- claims are no longer free text only; they include `predicate`, `object_text`, `context`, `evidence`, `confidence`, and `paper_id`
- subject/object linking to concepts exists
- evidence is traceable and now includes extraction metadata and offsets

Current implementation evidence:

- claim schema: `src/rks/storage/schema.py`
- claim extraction and normalization: `src/rks/extraction/claims.py`
- claim persistence and stable replay IDs: `src/rks/storage/claim_repository.py`

Gaps relative to the document:

- there is still no fully normalized object model where `subject` and `object` are always first-class graph references
- predicate control is improved, but still heuristic and not a rigorously governed ontology
- context remains flexible JSON rather than a stricter typed structure
- there is no first-class claim type such as `observation`, `result`, or `hypothesis`
- evidence does not yet model figures, tables, or experiments as separate provenance objects

Conclusion:

- the implementation has reached a practical structured claim model, but not a fully formal semantic claim representation

## 4. Concept System

Primary doc:

- `archive/original-design/concept-system.md`

Status:

- `Partially aligned`

Aligned parts:

- concepts have stable IDs, aliases, optional `parent_concept_id`, and normalization
- concept linking is conservative and claim-driven

Current implementation evidence:

- concept schema and persistence: `src/rks/storage/schema.py`, `src/rks/storage/concept_repository.py`
- normalization rules: `src/rks/concepts/normalize.py`

Gaps relative to the document:

- the document describes a richer `Domain -> Concept -> Instance` system; current code does not implement that model
- concept hierarchy exists only as a minimal parent pointer with simple heuristic inference
- there is no explicit `is_a`, `part_of`, or `related_to` concept relation system
- there is no concept governance or richer domain taxonomy
- `domain` is present structurally in schema but is not a strong organizing behavior in extraction or querying

Conclusion:

- concept normalization is real and useful, but the broader semantic backbone envisioned by the design docs remains simplified

## 5. Claim Extraction Pipeline

Primary doc:

- `archive/original-design/claim-extraction-pipeline.md`

Status:

- `Mostly aligned`

Aligned parts:

- the pipeline is explicitly multi-stage and artifact-producing
- there are concrete stages for text extraction, section detection, candidate generation, normalization, and structured claim persistence
- the system preserves intermediate artifacts for replay and inspection

Current implementation evidence:

- PDF/text extraction: `src/rks/extraction/pdf_backend.py`, `src/rks/extraction/text.py`
- claim stages: `src/rks/extraction/claims.py`
- artifact registration: `src/rks/storage/paper_repository.py`

Where the implementation is simpler than the design:

- claim candidate detection is still mostly heuristic sentence/pattern matching
- normalization is lightweight rather than a more advanced scientific parsing pipeline
- section handling is stronger than before, but still not a full document structure model
- methods and datasets are extracted heuristically rather than by a richer research object pipeline
- there is no first-class experiment extraction stage

Code ahead of the document:

- replay-safe claim IDs and artifact lineage metadata are now implemented
- evidence records include section and character offsets

Conclusion:

- the staged extraction architecture from the design docs is now real, but its internal logic remains intentionally pragmatic

## 6. Reasoning Engine

Primary doc:

- `archive/original-design/reasoning-engine.md`

Status:

- `Mostly aligned`

Aligned parts:

- the system now has all three intended layers in practical form:
  graph query
  semantic retrieval
  reasoning templates
- deterministic graph queries exist for claims, papers, methods, datasets, evidence aggregation, and claim relations
- local embeddings and hybrid retrieval are implemented
- reasoning outputs cite specific claim IDs and paper IDs

Current implementation evidence:

- hybrid retrieval and evidence/relations queries: `src/rks/query/service.py`
- embedding indexing: `src/rks/query/semantic.py`, `src/rks/providers/embeddings.py`
- summary grounding: `src/rks/reasoning/summary.py`

Gaps relative to the document:

- there is no general natural-language query planner
- the “Research Query DSL” is represented as CLI subcommands, not as a separate query language
- trend analysis and broader cross-corpus reasoning patterns are still absent
- comparative synthesis and contradiction reconciliation remain simpler than the document's fuller reasoning ambition

Conclusion:

- the implementation now fulfills the practical core of the reasoning-engine design, but not its most ambitious planner-oriented layer

## 7. Interaction Model and Agent Operations

Primary docs:

- `archive/original-design/rks-interaction-model.md`
- `dual-track-llm-contract.md`
- `agent-skills.md`

Status:

- `Mostly aligned`, with parts now `Code ahead of document`

Aligned parts:

- agents operate through stable commands and request/import contracts rather than direct DB mutation
- `llm-api` and `agent` modes exist for all current LLM-backed features
- validation is shared across direct provider and agent-imported outputs
- repository-specific skills exist and cover graph building, querying, maintenance, and operations

Current implementation evidence:

- dual-track contract: `src/rks/llm/contract.py`
- request/import flows: `src/rks/agent/workflow.py`
- CLI surfaces: `src/rks/cli/main.py`
- skill docs: `skills/`

Code ahead of the original interaction docs:

- explicit task queue lifecycle now exists through `tasks`
- there are batch operations and paper-level status reporting
- request/result schema versions are tracked in addition to the original `spec_version`
- the HTTP service now includes structured request logging, input validation on all POST endpoints, and proper error responses (400 for bad requests, 500 for server errors)

Remaining gaps:

- the document imagines a clearer standalone “Research API / Skill Layer”; today that layer is mostly embodied by CLI commands and repository code rather than a separate internal operations API
- graph write review/versioning semantics are still lighter than the stronger governance implied by the interaction model
- `Method` and `Dataset` extraction have not yet adopted the same dual-track LLM contract pattern as text extraction, claim parsing, and summarization

Conclusion:

- the interaction model is substantially realized, and in workflow auditing it now exceeds the original design writeup

## 8. Storage Architecture

Primary doc:

- `archive/original-design/storage-architecture.md`

Status:

- `Mostly aligned`

Aligned parts:

- object storage, graph storage, document storage, and vector storage all exist as logical layers
- stable IDs connect all layers
- original files and artifacts live in the filesystem rather than in database blobs

Current implementation evidence:

- schema: `src/rks/storage/schema.py`
- DB/migrations: `src/rks/storage/db.py`
- artifact paths and file-backed storage: `src/rks/storage/paper_repository.py`
- snapshot export/import: `src/rks/storage/snapshot.py`

Key implementation simplification:

- the current deployment model is still `SQLite + filesystem`, not four independent physical backends

Code ahead of the document:

- the repository now has a task store and artifact index model that were not explicit in the original storage architecture doc
- six schema migrations now exist (up from the original three): query performance indexes, claim relation candidates, and evolution events

Conclusion:

- the storage design is architecturally faithful, but physically more compact and pragmatic than the conceptual diagram

## 9. Implementation Plan and MVP Docs

Primary docs:

- `archive/original-design/implementation-plan.md`
- `archive/original-design/rks-mvp.md`
- `archive/completed-plans/mvp-status.md`

Status:

- `Partially aligned` on tooling details
- `Code ahead of document` on feature scope

Aligned parts:

- local SQLite implementation
- artifact-first extraction
- stable IDs
- CLI-first operation
- the original MVP loop was built and then extended

Important implementation differences from the recommended stack:

- CLI uses `argparse`, not `Typer`
- domain models use dataclasses, not `Pydantic`
- HTTP/provider layer uses `urllib` and stdlib HTTP server, not `httpx`
- tests are written with `unittest`, not `pytest`
- PDF extraction uses a local stream-decoding path instead of the originally suggested `PyMuPDF`

Why this matters:

- these are tooling deviations, not architectural reversals
- the current design intent still holds, but the codebase chose a lower-dependency implementation path

Code ahead of the MVP documents:

- methods and datasets are implemented
- embeddings and hybrid search are implemented
- batch/task/status operations exist
- config, migration tracking, snapshot import/export, and a service/UI layer now exist

Gaps relative to early conceptual framing:

- DOI and arXiv ingestion can now attempt source PDF acquisition, but provider coverage and robustness still remain limited
- early conceptual docs mention richer node families such as `Experiment` or `Idea`; these do not exist as first-class stored/queryable types
- `Note` exists in schema but remains lightly surfaced in user-facing workflows

Conclusion:

- the implementation has moved beyond the original MVP plan, but not always using the exact tools originally proposed

## 10. Docs That Now Lag the Code

The following original design docs are directionally correct but now under-specify the real implementation:

- `archive/original-design/project-positioning.md`
  because the code now includes a service/UI surface and stronger workflow machinery
- `archive/original-design/research-knowledge-substrate-overview.md`
  because the code now has more than the original three-component picture
- `archive/original-design/concept-system.md`
  because it still describes a richer hierarchy than what was actually implemented
- `archive/original-design/reasoning-engine.md`
  because it does not distinguish between implemented deterministic query templates and the still-missing planner layer
- `archive/original-design/implementation-plan.md`
  because the current toolchain and repo shape differ from the recommended MVP stack
- `archive/original-design/rks-mvp.md`
  because the project is no longer at MVP scope

## 11. Practical Conclusions

The original design docs were not misleading. In broad architectural terms, they predicted the implemented system well.

The main pattern across the repository is:

- the high-level product, graph, extraction, and agent ideas were correct
- the current implementation chose simpler local mechanisms than some documents implied
- several later-phase features are now implemented and have surpassed the original MVP-era documents

The biggest remaining design-to-code gap is not the core graph anymore.

It is now:

- richer concept semantics
- persisted claim-to-claim graph structure
- a more general query planner layer
- stronger real-world extraction quality and provider robustness
- fuller non-local source acquisition for DOI/arXiv references

## Suggested Next Documentation Work

If the repository should keep its design docs authoritative, the next doc updates should be:

1. rewrite `archive/original-design/implementation-plan.md` into a concise historical note plus a pointer to current architecture docs
2. split the archived `archive/original-design/reasoning-engine.md` concept into “implemented query/retrieval layer” and “future planner layer” if it is ever promoted back to active docs
3. revise `archive/original-design/concept-system.md` if it should become an active design reference again
4. keep `archive/original-design/rks-mvp.md` and `archive/completed-plans/mvp-status.md` clearly marked as historical records
5. add a single top-level architecture index that points readers to “design intent”, “current architecture”, and “progress status” separately
