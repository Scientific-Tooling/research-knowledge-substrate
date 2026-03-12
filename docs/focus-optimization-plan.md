# Focus Optimization Plan

This document turns the current product-direction discussion into an execution plan for the next rounds of RKS work.

The main goal is to move RKS from a substrate that can absorb and structure literature into an agent-driven research workbench that can also produce grounded content, inspiration, and clear next steps.

## Priority Order

1. improve research output quality
2. strengthen the agent operation loop
3. expand direct user-facing content and inspiration surfaces
4. stabilize skills, installation flows, and PyPI release operations

## 1. Improve Research Output Quality

Goal:

- make `rks output ...` feel like a credible research assistant response rather than a light wrapper around graph objects

Work items:

- [x] define stronger output contracts for `answer`, `brief`, `disagreements`, and `opportunities`
- [x] add explicit evidence assessment, confidence, and counterevidence structure to answer outputs
- [x] add topic assessment, reading list, and evidence-gap structure to topic briefs
- [x] add disagreement kind, possible causes, and review priorities to disagreement outputs
- [x] add evidence basis, grounding strength, and validation plans to opportunity outputs
- [x] add benchmark-style fixtures for multiple topic patterns beyond the current sparse-attention test
- [x] improve claim clustering and duplicate evidence reduction
- [x] prefer reviewed relations and stronger evidence when ranking findings

Exit criteria:

- answer outputs contain conclusion, confidence, evidence assessment, and next actions
- brief outputs contain a readable topic assessment plus a reading path
- disagreement outputs distinguish direct conflict from context-sensitive refinement
- opportunity outputs read like evidence-backed hypotheses with validation plans

## 2. Strengthen The Agent Operation Loop

Goal:

- make agent execution more closed-loop, auditable, and easier to recover when partial failures occur

Work items:

- [x] define paper readiness levels such as `ingested`, `claims_ready`, `output_ready`, and `review_pending`
- [x] enrich `status paper` with missing steps, blockers, and suggested next commands
- [x] introduce higher-level operations such as `prepare_paper_for_output`
- [x] persist agent execution reports as artifacts
- [x] add clearer failure-recovery guidance for queued or partially completed tasks
- [x] add batch-level audit summaries across ingest, extract, summarize, and output workflows

Exit criteria:

- an agent can decide the next step from `status` output instead of reconstructing state manually
- failures are visible and recoverable without manual database inspection
- batch runs can be audited at a glance

## 3. Expand Direct User-Facing Content And Inspiration

Goal:

- let users directly consume research content, reading guidance, and evidence-backed idea generation

Work items:

- [x] add a `reading-list` output surface
- [x] add a `compare` surface for methods, claims, or papers
- [x] add `open-questions` or unresolved-topic outputs
- [x] add replication-risk and review-priority outputs
- [x] improve topic brief reading navigation: entry papers, representative papers, contradiction papers
- [x] improve opportunity outputs with experiment-oriented validation suggestions

Exit criteria:

- users can ask not only "what is in the graph" but also "what should I read, compare, or test next"
- the content layer is visibly more useful than raw retrieval alone

## 4. Stabilize Skills, Install, And Release Operations

Goal:

- make repository-specific agent behavior and release workflows easy to ship and hard to break

Work items:

- [x] bundle repository skills into the installed distribution
- [x] add `rks skills list` and `rks skills export`
- [x] export `AGENTS.md`, `CLAUDE.md`, and `skills-index.json`
- [x] verify bundled skills match repository skill docs
- [x] add bundle versioning for exported skills
- [x] add install smoke checks for `rks --help`, `rks skills list`, and `rks init-db`
- [x] add a `doctor` or `self-check` command
- [x] harden the published-package smoke test in CI

Exit criteria:

- users can install RKS and immediately hand bundled skills to Codex, Claude Code, or another agent runtime
- release steps are reproducible and validated through CI

## Current Round

This round completed the focused optimization plan end to end.

Delivered now:

- stronger answer, brief, disagreement, and opportunity payload structure
- clustered and evidence-ranked research output findings with broader fixture coverage
- readiness-aware paper status, prepare-for-output planning/execution, and persisted agent task reports
- batch audit summaries across ingest, extract, and output workflows
- bundled skills export from installed CLI distributions with install-time self-checks

Next recommended implementation step:

- continue hardening real-world provider fixtures and larger-scale corpora
