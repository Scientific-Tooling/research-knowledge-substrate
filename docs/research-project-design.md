# ResearchProject Design

## Status

Accepted and implemented through the March 12, 2026 project-output and planner extension.

## Summary

RKS needs a first-class `ResearchProject` object so users and agents can organize research work that is not reducible to a single paper. A project is the durable container for:

- a research question or investigation goal
- user and agent notes scoped to that investigation
- an explicit set of in-scope or key-evidence papers

This design keeps paper-grounded extraction semantics intact:

- `paper` remains an independent evidence source
- `claim` remains a paper-grounded structured statement
- `ResearchProject` becomes the research workspace layer above papers

Implemented:

- `ResearchProject`
- project notes
- project links for `paper`, `claim`, `method`, `dataset`, and `concept`
- project hypotheses
- hypothesis-to-evidence links
- project-scoped output generation
- deterministic request planning for topic and project scopes

## Problem

Current RKS supports:

- workspace-wide search and topic outputs
- paper records
- paper-grounded claims
- paper notes

Current RKS does not support a persistent research object representing a concrete investigation such as:

- "Sparse attention for long-context evaluation"
- "CRISPR base editing off-target risk review"
- "Thermostable enzyme redesign for PET depolymerization"

Without a project entity:

- user ideas have no durable home unless they are forced onto a paper note
- project context is mixed with evidence provenance
- the system cannot express that several papers belong to the same investigation

## Goals

- Add a first-class `ResearchProject` object.
- Preserve existing paper-grounded note and claim behavior.
- Allow a project to collect multiple papers without changing paper ownership semantics.
- Reuse the existing note model cleanly for project notes.
- Support project-scoped outputs without changing paper or claim ownership rules.
- Add a lightweight planner that can map research requests to deterministic RKS commands.
- Keep the project model simple and easy to verify.

## Non-Goals

- Reworking claims to become project-owned
- Reworking extracted claims to become project-owned hypotheses
- Making papers belong to exactly one project
- Replacing the existing topic outputs with a separate project-only reasoning stack
- Building a fully agentic planner before a deterministic planner exists

## Core Model

### ResearchProject

`ResearchProject` is a durable research workspace object. It stores the user or agent's investigation context, not extracted evidence itself.

Fields:

- `id`
- `name`
- `description`
- `research_question`
- `status`
- `created_by`
- `created_at`
- `updated_at`

### Project-Paper Association

Projects must be able to associate with papers, but the association must be:

- optional
- many-to-many
- non-owning

Therefore papers do not get a `project_id` column. Instead, project membership is represented by a separate `project_links` table.

This keeps provenance and organization separate:

- provenance: "this claim came from paper p_..."
- organization: "project rp_... considers paper p_... in scope"

### Project Notes

The current note storage model is already generic:

- `target_id`
- `target_type`

Phase 1 extends official note support to `target_type="project"` while preserving `target_type="paper"`.

### Project Hypotheses

`Hypothesis` is a project-owned object representing a research idea, expectation, or conjecture under active investigation.

Fields:

- `id`
- `project_id`
- `text`
- `status`
- `confidence`
- `context_json`
- `created_by`
- `created_at`
- `updated_at`

Hypotheses are intentionally distinct from extracted claims:

- a claim is grounded in a paper
- a hypothesis is grounded in a project
- support or contradiction is expressed through explicit evidence links

### Hypothesis Evidence Links

Hypothesis evidence links attach already-stored graph objects to a hypothesis with an explicit relation.

Phase 2 officially supports:

- `paper`
- `claim`

Each evidence link stores:

- the evidence target
- a `relation_type` such as `supported_by`, `contradicted_by`, or `refined_by`
- optional metadata such as a note

## Why Projects Should Link to Papers

`ResearchProject` should support links to papers because a project needs an explicit evidence boundary. That boundary is necessary for:

- curated reading lists
- key evidence sets
- scoped project review
- future project-level synthesis

However, the link must not change the ontology of papers:

- papers are independent evidence objects
- a paper may support multiple projects
- a project may include zero, one, or many papers

## Schema

### `research_projects`

Columns:

- `id TEXT PRIMARY KEY`
- `name TEXT NOT NULL`
- `description TEXT`
- `research_question TEXT`
- `status TEXT NOT NULL`
- `created_by TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

### `project_links`

Columns:

- `id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `object_id TEXT NOT NULL`
- `object_type TEXT NOT NULL`
- `link_type TEXT NOT NULL`
- `metadata_json TEXT`
- `created_by TEXT NOT NULL`
- `created_at TEXT NOT NULL`

The implemented CLI and HTTP surfaces expose:

- `object_type="paper"`
- `object_type="claim"`
- `object_type="method"`
- `object_type="dataset"`
- `object_type="concept"`

### `hypotheses`

Columns:

- `id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `text TEXT NOT NULL`
- `status TEXT NOT NULL`
- `confidence REAL`
- `context_json TEXT`
- `created_by TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

### `hypothesis_evidence_links`

Columns:

- `id TEXT PRIMARY KEY`
- `hypothesis_id TEXT NOT NULL`
- `object_id TEXT NOT NULL`
- `object_type TEXT NOT NULL`
- `relation_type TEXT NOT NULL`
- `metadata_json TEXT`
- `created_by TEXT NOT NULL`
- `created_at TEXT NOT NULL`

## Domain Rules

- A project is not an evidence source.
- Claims remain paper-grounded.
- Project notes are workspace context, not evidence.
- Project-to-paper links do not replace paper citations or claim support edges.
- Duplicate project-to-paper links with the same `link_type` should be idempotent at the repository layer.
- Hypotheses are project-owned reasoning objects, not extracted evidence.
- Hypothesis evidence links must point to already-existing graph objects.
- Duplicate hypothesis evidence links with the same target and relation should be idempotent at the repository layer.

## Repository Responsibilities

### `ProjectRepository`

Responsibilities:

- create a project
- get a project
- list projects
- update project timestamp
- add a project link
- list papers linked to a project
- list raw links for a project

Notes remain in `NoteRepository` because note ownership is already generic.

### `HypothesisRepository`

Responsibilities:

- create a hypothesis
- get a hypothesis
- list hypotheses for a project
- update hypothesis timestamp
- add a hypothesis evidence link
- list evidence links for a hypothesis

## CLI Surface

Implemented CLI surface:

- `rks project create --name ...`
- `rks project list`
- `rks project add-paper <project_id> <paper_id>`
- `rks project papers <project_id>`
- `rks project add-link <project_id> <object_type> <object_id>`
- `rks project links <project_id> [--object-type ...]`
- `rks show project <project_id>`
- `rks note add project <project_id> --content ...`
- `rks note list project <project_id>`
- `rks hypothesis create <project_id> --text ...`
- `rks hypothesis list <project_id>`
- `rks hypothesis add-evidence <hypothesis_id> paper <paper_id>`
- `rks hypothesis add-evidence <hypothesis_id> claim <claim_id>`
- `rks hypothesis evidence <hypothesis_id>`
- `rks show hypothesis <hypothesis_id>`
- `rks output project-answer <project_id> [--question ...]`
- `rks output project-brief <project_id>`
- `rks output project-disagreements <project_id>`
- `rks output project-opportunities <project_id>`
- `rks output project-reading-list <project_id>`
- `rks output project-open-questions <project_id>`
- `rks output project-review-priorities <project_id>`
- `rks plan query "<request>" [--project-id <project_id>]`

`rks show project` returns:

- project fields
- project notes
- linked papers
- linked claims
- linked methods
- linked datasets
- linked concepts
- project hypotheses

## HTTP Surface

Implemented HTTP surface:

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/<project_id>`
- `GET /api/projects/<project_id>/papers`
- `POST /api/projects/<project_id>/papers`
- `GET /api/projects/<project_id>/links`
- `POST /api/projects/<project_id>/links`
- `GET /api/projects/<project_id>/notes`
- `POST /api/projects/<project_id>/notes`
- `GET /api/projects/<project_id>/hypotheses`
- `POST /api/projects/<project_id>/hypotheses`
- `GET /api/hypotheses/<hypothesis_id>`
- `GET /api/hypotheses/<hypothesis_id>/evidence`
- `POST /api/hypotheses/<hypothesis_id>/evidence`
- `GET /api/output/projects/<project_id>/answer`
- `GET /api/output/projects/<project_id>/brief`
- `GET /api/output/projects/<project_id>/disagreements`
- `GET /api/output/projects/<project_id>/opportunities`
- `GET /api/output/projects/<project_id>/reading-list`
- `GET /api/output/projects/<project_id>/open-questions`
- `GET /api/output/projects/<project_id>/review-priorities`
- `GET /api/plan/query?q=...&project_id=...`

## Snapshot and Migration Requirements

`research_projects`, `project_links`, `hypotheses`, and `hypothesis_evidence_links` must be included in:

- schema migrations
- schema bootstrap SQL
- graph snapshot export/import
- packaged migrations

## Phasing

### Phase 1

Implemented:

- `ResearchProject`
- project notes
- project-paper links
- CLI and HTTP support
- tests and docs

### Phase 2

Implemented:

- `Hypothesis` as a project-owned object
- hypothesis-to-paper or hypothesis-to-claim evidence links

### Follow-on Extensions

Implemented:

- generic project links for `claim`, `method`, `dataset`, and `concept`
- project-scoped output surfaces
- deterministic planner routing requests to topic or project output commands

## Rejected Alternatives

### Add `project_id` directly to `papers`

Rejected because:

- it incorrectly implies ownership
- it blocks many-to-many use cases
- it mixes evidence provenance with organizational context

### Reuse `edges` for project-paper membership

Rejected because:

- `edges` currently encode graph facts and reviewed claim relations
- project organization is not the same kind of fact as evidence graph structure
- a dedicated association table keeps semantics clear

### Store project context as free-text workspace notes only

Rejected because:

- it does not give projects stable IDs
- it does not support scoped paper membership
- it would force later migration from an underspecified model
