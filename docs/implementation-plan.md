# Research Knowledge Substrate: Implementation Plan

## Purpose

This document turns the current design documents into a concrete implementation plan for an MVP.

The goal is to build a local, agent-first research knowledge substrate that can:

1. ingest a paper
2. extract structured research objects
3. persist them as a stable research graph
4. support traceable query and inspection through a CLI

This plan prioritizes structural stability and debuggability over breadth.

## MVP Scope

The MVP should prove one narrow but important loop:

`paper -> structured text -> structured claims -> concept links -> graph persistence -> CLI query`

The MVP does not need:

- a web UI
- distributed infrastructure
- multi-agent orchestration
- a large ontology system
- full natural-language query planning
- automated contradiction detection across the whole corpus

## Success Criteria

The MVP is successful if the system can reliably do the following for a small local corpus:

- ingest a PDF, DOI, or arXiv paper reference
- persist paper metadata and source artifacts
- extract 3 to 10 structured claims from a paper
- link major terms to normalized concepts
- persist graph edges with provenance and confidence
- answer a small set of stable CLI queries
- show evidence trails for extracted claims

## Why Python For The MVP

Python is the recommended implementation language for the first version because the hard part of this system is not high-throughput serving. The hard part is building and debugging a research extraction pipeline.

Python is a good fit because it minimizes the cost of:

- PDF and text processing
- LLM integration
- structured extraction experiments
- embedding and retrieval experiments
- local CLI tooling
- rapid schema and pipeline iteration

This is a pragmatic MVP choice, not a permanent commitment for every future subsystem.

## Core Architectural Decisions

The implementation should follow these decisions from the start:

1. `Claim` is the primary knowledge unit.
2. `Paper` is an evidence container, not the center of the model.
3. Object data, graph edges, document artifacts, and embeddings are stored separately but connected by stable IDs.
4. Every extraction stage produces intermediate artifacts that can be inspected and replayed.
5. Predicates and edge types are controlled vocabularies, not free text.
6. Concept creation is conservative to avoid graph fragmentation.

## Recommended Stack

- Language: Python 3.12+
- CLI: `Typer`
- Data validation: `Pydantic`
- Storage: `SQLite`
- Migrations: plain SQL migration files
- HTTP: `httpx`
- PDF text extraction: adapter interface, default implementation can start with `PyMuPDF`
- LLM provider: provider adapter layer
- Embeddings: provider adapter layer
- Testing: `pytest`

The MVP should avoid adding a graph database or a dedicated vector database until the local graph loop is proven.

## Repository Structure

Suggested source layout:

```text
src/rks/
  cli/
  domain/
  storage/
  ingestion/
  extraction/
  concepts/
  query/
  reasoning/
  providers/
  utils/

data/
  papers/
  artifacts/

migrations/

tests/
  domain/
  storage/
  ingestion/
  extraction/
  query/
```

Suggested responsibility split:

- `cli/`: command definitions and output formatting
- `domain/`: object models, enums, IDs, schema contracts
- `storage/`: SQLite repositories, migrations, persistence helpers
- `ingestion/`: DOI, arXiv, PDF import workflows
- `extraction/`: text extraction, sectioning, claim detection, normalization, structured parsing
- `concepts/`: concept lookup, alias matching, normalization workflow
- `query/`: graph queries and semantic retrieval
- `reasoning/`: query templates and evidence synthesis
- `providers/`: metadata, LLM, and embedding adapters

## ID System

All persisted objects should use stable prefixed IDs:

- `p_000001` for papers
- `c_000001` for claims
- `m_000001` for methods
- `d_000001` for datasets
- `k_000001` for concepts
- `n_000001` for notes
- `e_000001` for edges
- `a_000001` for artifacts

IDs should be generated in application code, not inferred from row IDs.

## Storage Design

The MVP storage model has four layers:

1. object tables in SQLite
2. graph edges in SQLite
3. source and intermediate artifacts on the filesystem
4. optional embedding records in SQLite

Suggested filesystem layout:

```text
data/
  papers/
    p_000001/
      source.pdf
      metadata.json
      extracted_text.json
      sections.json
      claim_candidates.json
      normalized_claims.json
      structured_claims.json
```

This is intentionally redundant. The system should favor inspectability over compactness in the MVP.

## SQLite Schema

The schema should start small and explicit.

### `papers`

```text
id TEXT PRIMARY KEY
title TEXT NOT NULL
abstract TEXT
authors_json TEXT
year INTEGER
venue TEXT
doi TEXT
arxiv_id TEXT
source_type TEXT NOT NULL
source_ref TEXT
pdf_path TEXT
text_artifact_id TEXT
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

### `claims`

```text
id TEXT PRIMARY KEY
paper_id TEXT NOT NULL
text TEXT NOT NULL
subject_concept_id TEXT
predicate TEXT NOT NULL
object_concept_id TEXT
object_text TEXT
context_json TEXT
evidence_json TEXT
confidence REAL
status TEXT NOT NULL
created_by TEXT NOT NULL
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

### `methods`

```text
id TEXT PRIMARY KEY
paper_id TEXT NOT NULL
name TEXT NOT NULL
description TEXT
about_concept_id TEXT
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

### `datasets`

```text
id TEXT PRIMARY KEY
name TEXT NOT NULL
description TEXT
source TEXT
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

### `concepts`

```text
id TEXT PRIMARY KEY
name TEXT NOT NULL
aliases_json TEXT
domain TEXT
parent_concept_id TEXT
description TEXT
status TEXT NOT NULL
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

### `notes`

```text
id TEXT PRIMARY KEY
target_id TEXT NOT NULL
target_type TEXT NOT NULL
content TEXT NOT NULL
created_by TEXT NOT NULL
created_at TEXT NOT NULL
```

### `edges`

```text
id TEXT PRIMARY KEY
source_id TEXT NOT NULL
source_type TEXT NOT NULL
relation_type TEXT NOT NULL
target_id TEXT NOT NULL
target_type TEXT NOT NULL
evidence_paper_id TEXT
confidence REAL
metadata_json TEXT
created_by TEXT NOT NULL
created_at TEXT NOT NULL
```

### `artifacts`

```text
id TEXT PRIMARY KEY
paper_id TEXT
artifact_type TEXT NOT NULL
path TEXT NOT NULL
format TEXT NOT NULL
metadata_json TEXT
created_at TEXT NOT NULL
```

### `embeddings`

```text
id TEXT PRIMARY KEY
object_id TEXT NOT NULL
object_type TEXT NOT NULL
embedding_model TEXT NOT NULL
vector_json TEXT NOT NULL
created_at TEXT NOT NULL
```

## Controlled Vocabularies

The MVP should define controlled vocabularies for both claim predicates and edge relations.

Suggested claim predicates:

- `improves`
- `outperforms`
- `reduces`
- `increases`
- `enables`
- `requires`
- `scales_with`
- `replaces`
- `uses`
- `supports`

Suggested edge relations:

- `cites`
- `contains`
- `proposes`
- `uses`
- `about`
- `supported_by`
- `contradicts`
- `evaluated_on`
- `refines`
- `extends`
- `mentions`

The list can expand later, but the MVP should keep it deliberately small.

## Domain Models

The implementation should model these core entities in `domain/`:

- `Paper`
- `Claim`
- `Method`
- `Dataset`
- `Concept`
- `Note`
- `Edge`
- `Artifact`

Important model constraints:

- a `Claim` must always point to a `paper_id`
- a `Claim.predicate` must be an enum
- a `Claim` should use either `object_concept_id` or `object_text`
- every extracted claim should include provenance in `evidence_json`
- every mutable object should have `created_at` and `updated_at`

## Ingestion Pipeline

The ingestion pipeline should be explicit and restartable.

### Stage 1: Source resolution

Input types:

- local PDF
- DOI
- arXiv ID

Outputs:

- normalized source reference
- initial paper metadata
- local source artifact

### Stage 2: Text extraction

Convert the paper into structured text.

Outputs:

- full extracted text
- paragraph records
- section records if available

### Stage 3: Section segmentation

Detect major scientific sections such as:

- abstract
- introduction
- method
- experiments
- conclusion

This stage should persist a `sections.json` artifact even if the segmentation is imperfect.

### Stage 4: Claim candidate detection

Identify candidate sentences or passages likely to contain scientific claims.

Outputs:

- candidate text
- section
- paragraph index
- extraction confidence

### Stage 5: Claim normalization

Rewrite candidate text into concise, objective statements.

Examples:

- remove author-centric phrasing
- remove rhetorical emphasis
- simplify to a stable scientific statement

### Stage 6: Structured claim construction

Parse normalized claims into the structured claim model:

- subject
- predicate
- object
- context
- evidence
- confidence

### Stage 7: Concept linking

Resolve major entities in claims to canonical concepts using:

1. exact name match
2. alias match
3. embedding similarity
4. unresolved queue

The system should avoid automatic concept creation unless confidence is high.

### Stage 8: Graph persistence

Persist objects and edges:

- `Paper`
- `Claim`
- `Concept`
- `Edge`
- optional `Method`
- optional `Dataset`

### Stage 9: Embedding generation

Generate embeddings only after the graph objects exist.

The MVP can embed:

- papers
- claims
- concepts

## Query Layer

The first query layer should be deterministic and template-driven, not fully open-ended.

Supported query patterns:

- claims about a concept
- papers supporting a claim
- methods proposed by a paper
- claims extracted from a paper
- concepts mentioned in a paper
- claims that contradict another claim

This maps well to a local graph query service implemented on top of SQLite repositories.

## Reasoning Layer

The MVP reasoning layer should stay narrow.

It should not be a general-purpose agent planner yet. It should be a synthesis layer built on top of stable query templates.

Initial reasoning outputs:

- evidence summary for a claim
- concept summary from extracted claims
- paper summary based on normalized claims
- comparison summary for a small set of methods or claims

The synthesis output must always include provenance references.

## CLI Specification

The CLI should expose research operations rather than raw CRUD.

### Ingestion commands

```text
rks ingest pdf <path>
rks ingest doi <doi>
rks ingest arxiv <id>
```

### Inspection commands

```text
rks show paper <paper_id>
rks show claim <claim_id>
rks claims <paper_id>
rks concepts <paper_id>
rks methods <paper_id>
```

### Query commands

```text
rks search "<query>"
rks query claims-about "<concept>"
rks query papers-supporting <claim_id>
rks query contradicting <claim_id>
rks query methods-by-paper <paper_id>
```

### Maintenance commands

```text
rks reindex paper <paper_id>
rks extract claims <paper_id>
rks resolve concepts <paper_id>
```

Maintenance commands are important because extraction stages will need replay.

## Provider Interfaces

The code should define narrow interfaces for external dependencies.

Suggested adapters:

- `MetadataProvider`
- `PdfTextExtractor`
- `ClaimExtractor`
- `EmbeddingProvider`
- `ConceptResolver`

This keeps domain logic independent from specific vendors or libraries.

## Testing Strategy

The MVP should emphasize reproducibility and schema correctness.

Priority tests:

- ID generation
- schema validation
- SQLite repository behavior
- ingestion from local PDF fixtures
- claim parsing on fixed text fixtures
- concept resolution on fixed alias cases
- query correctness on a seeded mini-graph

The first integration test should validate the full loop:

`fixture PDF -> paper -> claims -> concepts -> edges -> query result`

## Recommended Milestones

### Milestone 0: Project skeleton

- create package layout
- define domain models
- define enums and IDs
- add SQLite migrations

### Milestone 1: Paper ingestion

- implement `ingest pdf`
- persist paper metadata
- persist source and text artifacts
- implement `show paper`

### Milestone 2: Claim extraction loop

- detect claim candidates
- normalize them
- persist structured claims
- implement `claims <paper_id>`

### Milestone 3: Concept linking and graph edges

- implement concept store
- implement alias-based matching
- persist `about`, `contains`, and `supported_by` edges
- implement `concepts <paper_id>`

### Milestone 4: Query templates

- implement graph query repository
- support `claims-about`
- support `papers-supporting`
- support `contradicting`

### Milestone 5: Embeddings and semantic search

- persist embeddings
- add `search`
- combine semantic retrieval with graph inspection

### Milestone 6: Evidence-aware synthesis

- add narrow reasoning templates
- produce traceable summaries from graph results

## Risks To Control Early

The implementation should actively avoid these failure modes:

- storing claims only as free text
- allowing uncontrolled predicates
- creating too many concepts automatically
- hiding intermediate extraction artifacts
- coupling domain logic directly to one LLM vendor
- overbuilding the reasoning layer before the graph is stable

## Phase 1 Build Order

The recommended build order is:

1. domain models and IDs
2. SQLite schema and repositories
3. `ingest pdf`
4. text extraction artifacts
5. structured claim persistence
6. concept linking
7. graph edges
8. query templates
9. embeddings and synthesis

This ordering keeps the project focused on the core graph loop.

## Immediate Next Step

The next concrete engineering step should be to implement Milestone 0 and Milestone 1:

- package skeleton
- domain models
- SQLite schema
- `rks ingest pdf`
- `rks show paper`

That is the smallest useful slice that turns the project from a document set into an executable system plan.
