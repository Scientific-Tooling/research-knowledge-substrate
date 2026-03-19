# System Constraints

This document records the architectural boundaries that should remain stable as RKS evolves.

These are not feature ideas or short-term implementation preferences.
They are system constraints.

## 1. Evidence Is Paper-Grounded

`Paper` is the primary evidence anchor in RKS.

Implications:

- claims, methods, and datasets must remain traceable to a paper
- projects and hypotheses are workspace or reasoning objects, not evidence sources
- project context must not replace paper provenance

RKS should not introduce project-owned extracted evidence or free-floating semantic facts without a paper anchor.

## 2. Inference Is Not Durable Truth

Query-time inference is allowed, but inferred results are candidates, not stored truth.

Implications:

- inferred claim relations must remain distinguishable from reviewed graph facts
- durable graph updates require explicit review or promotion flows
- extraction reruns must not silently turn heuristics into facts

RKS should prefer explicit review over automatic semantic persistence.

## 3. LLM Work Must Cross An Explicit Boundary

Any LLM-backed capability must expose the standard RKS integration boundary.

Required paths:

- `llm-api`
- `agent`
- `heuristic` only when a real local fallback exists

Implications:

- agent mode must emit explicit request artifacts
- agent results must come back through explicit import flows
- direct API results and agent results must pass the same validation contract

RKS should not add one-off hidden LLM calls that bypass the request/import boundary.

## 4. Reads Must Not Mutate State

Read-oriented commands and endpoints must not perform hidden writes.

Examples of read-oriented surfaces:

- status inspection
- query and search
- output generation
- HTTP `GET` endpoints

Implications:

- these surfaces must not create papers, claims, edges, notes, artifacts, or tasks as side effects
- they must not trigger ingestion, extraction, downloads, or retries implicitly

If state needs to change, that change should happen through an explicit ingest, extract, import, review, or write endpoint.

## 5. RKS Is Not A Crawler Or Autonomous Orchestrator

RKS is an agent-first substrate, not a general web retrieval system and not an autonomous research agent.

Implications:

- external literature discovery belongs to the surrounding agent
- non-canonical page resolution and ad hoc web scraping belong to the surrounding agent
- RKS should accept stable inputs such as local PDFs, stable identifiers, canonical reference URLs, and direct PDF URLs
- orchestration may exist outside RKS, but RKS itself should keep each state transition explicit and auditable

RKS should not grow toward opaque “give me a topic and I will fetch and decide everything” behavior.

## 6. Artifacts Come Before Opaque State

Important processing steps should leave inspectable artifacts and stable object state.

Implications:

- ingest and extraction stages should preserve visible intermediate outputs when practical
- failures should remain diagnosable from stored artifacts and status surfaces
- replay and recovery should rely on explicit files and records rather than hidden in-memory transitions

RKS should favor artifact-first workflows over black-box mutation.

## 7. Product Logic Must Have A Single Home

High-level product behavior should be assembled in one layer, not duplicated across interfaces.

Implications:

- CLI should be the canonical external transport surface; local HTTP (when present) should remain a mirror transport surface
- status assembly, review actions, and similar product behaviors should live in shared operations or service layers
- interface-specific code should not independently reconstruct business rules

RKS should avoid logic drift between CLI, HTTP, and agent-facing workflows.

## 8. Input Normalization Happens Outside The Boundary

RKS should consume normalized inputs, not guess the user intent from messy external material.

Implications:

- the surrounding agent should resolve ambiguous or messy sources before handing them to RKS
- RKS should stay narrow in the kinds of accepted ingest references
- adding new ingest inputs should require a stable normalization rule, not a one-off parser

This keeps the ingest boundary simple, testable, and durable.

## 9. CLI Is The Only External Interface

RKS should expose one canonical external interface for agent runtimes: the `rks` CLI.

Implications:

- external agent tools (Codex, Claude Code, OpenClaw, or others) should integrate through CLI commands
- optional adapters or wrappers must remain thin compatibility layers over CLI behavior, not independent product surfaces
- new agent-facing capabilities should be defined first as CLI semantics, then optionally mirrored elsewhere
- interface documentation and skills should treat CLI as the source of truth for read, search, and write-back operations

RKS should avoid introducing additional external control planes that compete with CLI semantics.

## Summary

The intended long-term shape of RKS is:

- paper-grounded
- review-gated
- artifact-first
- agent-friendly
- CLI-first at the external boundary
- explicit at boundaries
- narrow in responsibilities
