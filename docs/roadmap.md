# Post-MVP Roadmap

## Delivery Status

Status as of 2026-03-12:

- [x] Phase 1: Quality Hardening
- [ ] Phase 2: Research Graph Expansion
- [ ] Phase 3: Retrieval and Reasoning Upgrade
- [ ] Phase 4: Agent Workflow Maturity
- [ ] Phase 5: Productization Layer

## Goal

The MVP established the core local substrate:

- ingestion
- artifacts
- structured claims
- concepts
- graph edges
- local queries
- dual-track LLM integration

The next phase is not "add random features." The next phase is to improve the substrate along a controlled path:

1. make extraction quality reliable
2. expand the graph beyond claims and concepts
3. improve retrieval and reasoning
4. prepare the system for sustained agent and researcher use

## Phase 1: Quality Hardening

Objective:

Turn the MVP from "works on good inputs" into "works predictably on real papers."

Priority work:

- [x] replace the current lightweight PDF fallback with a stronger extraction backend
- [x] improve section detection quality and preserve paragraph offsets
- [x] improve claim parsing quality, especially subject/object extraction
- [x] normalize evidence fields more consistently
- [x] add replay-safe artifact lineage metadata such as extractor version and mode
- [x] expand fixture coverage with more realistic paper text and edge cases

Exit criteria:

- [x] extraction produces stable artifacts on a representative fixture set
- [x] claim quality is acceptable without hand-tuning prompts per paper
- [x] rerunning extraction is deterministic enough to compare outputs across versions

## Phase 2: Research Graph Expansion

Objective:

Move from a claim-centric MVP to a fuller minimal research graph.

Priority work:

- [ ] add first-class `Method` extraction and persistence
- [ ] add first-class `Dataset` extraction and persistence
- [ ] add graph edges such as `proposes`, `uses`, and `evaluated_on`
- [ ] improve concept hierarchy support with optional parent concepts
- [ ] add basic citation ingestion and `cites` edges when metadata is available

Exit criteria:

- [ ] a paper can produce claims, methods, datasets, and linked graph edges
- [ ] the stored graph more closely matches the intended minimal research graph design

## Phase 3: Retrieval and Reasoning Upgrade

Objective:

Make the substrate genuinely useful for research questions rather than only inspection.

Priority work:

- [ ] add embeddings for papers, claims, and concepts
- [ ] add semantic retrieval alongside lexical search
- [ ] implement more deterministic query templates
- [ ] add contradiction, refinement, and support patterns between claims
- [ ] improve summary and synthesis artifacts to cite specific claims and papers
- [ ] add evidence aggregation views for concept- or claim-level questions

Exit criteria:

- [ ] local search combines lexical and semantic retrieval
- [ ] users can answer more research-shaped questions without manual graph inspection
- [ ] reasoning outputs are traceable back to stored objects

## Phase 4: Agent Workflow Maturity

Objective:

Make RKS a better substrate for long-running agent work.

Priority work:

- [ ] formalize more agent-facing skills for ingestion, query, and maintenance workflows
- [ ] add batch operations for repeated paper ingestion and extraction
- [ ] add queue-like request/result management for agent-mode tasks
- [ ] add extraction status reporting and failure visibility
- [ ] add schema/version tracking for all dual-track LLM tasks

Exit criteria:

- [ ] an external agent can operate RKS repeatedly without repository-specific improvisation
- [ ] failures and replays are explicit and auditable

## Phase 5: Productization Layer

Objective:

Prepare RKS for broader use beyond a single local repo.

Priority work:

- [ ] define a stable config story for models, providers, and storage paths
- [ ] add migration/version management for stored data
- [ ] add export/import paths for graph snapshots
- [ ] add optional API or service layer above the local CLI
- [ ] add a lightweight UI only after the data and workflows are stable

Exit criteria:

- [ ] the system can be installed, configured, migrated, and operated with less manual setup
- [ ] the local substrate can evolve into a reusable research platform

## Near-Term Priority Order

The recommended order for the next few iterations is:

1. stronger PDF extraction backend
2. better claim parsing and evidence normalization
3. `Method` and `Dataset` node extraction
4. local semantic retrieval
5. richer reasoning/query templates

This order keeps the graph foundation improving before adding higher-level product surfaces.

## What Not To Do Next

Avoid these too early:

- building a web UI before extraction quality improves
- introducing a graph database before the local SQLite model becomes a real bottleneck
- building complex autonomous agent orchestration before task contracts stabilize
- expanding into many node types before `Method` and `Dataset` are solid

## Practical Next Milestone

The best immediate milestone after MVP is:

`Quality Hardening + Method/Dataset extraction`

That milestone preserves the current architecture, improves real usefulness, and sets up the next layer of reasoning work without destabilizing the substrate.
