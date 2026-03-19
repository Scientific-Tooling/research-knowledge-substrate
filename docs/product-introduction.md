# RKS Product Introduction

Research Knowledge Substrate (RKS) is an agent-first, local research graph system.
It helps users and AI agents ingest papers, extract structured research objects, review evidence links, and generate grounded research outputs.

This document explains what RKS is, what it is for, and how it is designed.

## 1. Product Positioning

RKS is designed for evidence-grounded research work, not for generic note taking and not for autonomous web crawling.

RKS is especially useful when you need to:

- build a local, inspectable paper graph
- keep paper artifacts and extraction outputs reproducible
- separate inferred relations from reviewed relations
- support both human and agent workflows through stable interfaces

## 2. Target Users

RKS serves two primary user groups:

- human researchers and engineers who operate through CLI
- external AI agents (Codex, Claude Code, and similar runtimes) that execute CLI/HTTP operations

RKS assumes users care about provenance, inspectability, and repeatable operations.

## 3. Core Principles

### 3.1 Local-first and inspectable

RKS stores data locally (SQLite + filesystem artifacts).
Every important step should leave inspectable traces.

### 3.2 Artifact-first ingestion

Ingestion and extraction are not black boxes.
RKS persists source files and generated artifacts before or alongside structured rows.

### 3.3 Review-gated durability

Inferred claim relations are not treated as durable truth by default.
Durable graph facts should come from explicit review actions.

### 3.4 CLI-first external boundary

The `rks` CLI is the canonical external interface.
HTTP surfaces are mirror transports for integration and cross-checking.

### 3.5 Narrow responsibility boundary

RKS focuses on substrate responsibilities:

- ingesting explicit references or local PDFs
- extracting and linking research objects
- serving deterministic query/review/output workflows

RKS intentionally avoids becoming a general web crawler or discovery engine.

## 4. High-level Capability Map

RKS provides capability layers that can be combined in a workflow:

1. Ingestion:
   local PDF, DOI, arXiv, PMID, and canonical URLs
2. Extraction:
   text, claims, methods, datasets, summaries
3. Graph construction:
   papers, concepts, edges, citations, reviewed claim relations
4. Retrieval and reasoning:
   search, deterministic queries, evidence views
5. Research outputs:
   answer, brief, disagreements, opportunities, reading-list, project outputs
6. Operations and governance:
   status inspection, task management, review promotion/retraction

## 5. Data Model Overview

Main object families include:

- `paper`: source document and metadata anchor
- `claim`: structured assertions with evidence payloads
- `concept`: normalized terms linked to claims and papers
- `method` and `dataset`: first-class extracted research objects
- `edge`: typed relations (`about`, `supported_by`, `uses`, `evaluated_on`, etc.)
- `project` and `hypothesis`: user-curated research scope and reasoning tracks
- `task`: agent-mode request/import lifecycle tracking

This model supports both bottom-up evidence exploration and top-down project workflows.

## 6. Interfaces

### 6.1 CLI

The CLI is the source of truth for product semantics.
Examples:

- `rks ingest ...`
- `rks extract ...`
- `rks query ...`
- `rks review ...`
- `rks output ...`

### 6.2 HTTP

RKS includes a local HTTP service for lightweight UI integration and agent cross-checking.
HTTP should mirror CLI behavior rather than invent a separate control plane.

## 7. LLM Integration Model

LLM-backed tasks follow a dual-track contract:

- `llm-api`: RKS calls provider APIs directly
- `agent`: external agent performs the task and imports results back

If a local deterministic fallback exists, `heuristic` mode is also available.

This design keeps automation flexible while maintaining clear boundaries and auditability.

## 8. Typical End-to-end Workflow

1. initialize config and database
2. ingest one or more papers/references
3. inspect paper status and artifacts
4. run extraction and summary steps
5. inspect/search/query graph objects
6. review and persist important claim relations
7. generate outputs for topic/project decisions

## 9. What RKS Is Not

RKS is not:

- a full literature discovery crawler
- a replacement for external agent planning logic
- a publication-grade truth engine without review

It is a durable local substrate for transparent, evidence-grounded research operations.

## 10. Related Docs

- User operations: `docs/user-usage-guide.md`
- Agent operations: `docs/agent-usage-guide.md`
- Manual verification: `docs/manual-testing-guide.md`
- Constraints: `docs/system-constraints.md`
- Progress and milestones: `docs/progress.md`
