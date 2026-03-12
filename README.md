# Research Knowledge Substrate

Research Knowledge Substrate (RKS) is an agent-first local research graph system for ingesting papers, extracting research objects, querying evidence, and serving a local research workspace.

## Current Capabilities

The current implementation supports:

- ingesting local PDFs
- ingesting DOI and arXiv references
- attempting source PDF acquisition during DOI and arXiv ingestion when provider metadata exposes PDF candidates
- persisting papers and extraction artifacts to SQLite plus local disk
- generating inspectable pipeline artifacts such as extracted text, sections, and structured claims
- extracting heuristic structured claims, methods, and datasets
- normalizing and linking concepts
- creating graph edges for `contains`, `supported_by`, `about`, `proposes`, `uses`, `evaluated_on`, and `cites`
- querying claims, methods, datasets, evidence views, and claim relations
- promoting reviewed claim relations into durable graph edges while keeping inferred relations separate
- indexing local embeddings and running hybrid lexical/semantic search
- two LLM integration modes for text extraction and claim parsing:
  API mode and agent-assisted mode
- the same dual-track pattern for paper summarization
- batch ingest and extraction workflows
- task queue and paper status inspection for agent-mode operations
- config initialization, migration/version reporting, and graph snapshot export/import
- stable agent-facing operations for paper status and claim-relation review over CLI and HTTP
- a local HTTP service and lightweight UI

Progress is tracked in [docs/progress.md](docs/progress.md).

## Quick Start

Create a virtual environment and install the package in editable mode:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Initialize the local database:

```bash
rks config init
rks init-db
rks migrate
```

Ingest a PDF:

```bash
rks ingest pdf path/to/paper.pdf
```

Extract claims for a paper:

```bash
rks extract claims p_000001
```

Use an API-backed LLM:

```bash
export RKS_LLM_API_KEY=...
export RKS_LLM_MODEL=gpt-4.1-mini
rks extract text p_000001 --mode llm-api
rks extract claims p_000001 --mode llm-api
```

Use an external agent such as Codex or Claude Code:

```bash
rks extract text p_000001 --mode agent
rks import text p_000001 path/to/agent_text.json
rks extract claims p_000001 --mode agent
rks import claims p_000001 path/to/agent_claims.json
```

Inspect the graph:

```bash
rks show paper p_000001
rks claims p_000001
rks concepts p_000001
rks show claim c_000001
```

Run deterministic queries:

```bash
rks index embeddings
rks search Transformer
rks search "translation quality benchmark" --mode semantic
rks query claims-about Transformer
rks query papers-supporting c_000001
rks query evidence-for Transformer
rks query claim-relations c_000001
rks review promote-claim-relation c_000001 supports c_000014 --reviewed-by agent:review
rks review retract-claim-relation c_000001 supports c_000014
```

Generate a paper summary:

```bash
rks summarize paper p_000001
rks summarize paper p_000001 --mode llm-api
rks summarize paper p_000001 --mode agent
rks import summary p_000001 path/to/agent_summary.json
```

Run batch workflows:

```bash
rks batch ingest manifest.json
rks batch extract claims manifest.json
rks tasks list
rks status paper p_000001
```

Export, import, and serve the workspace:

```bash
rks export graph snapshot.json
rks import graph snapshot.json
rks serve --host 127.0.0.1 --port 8765
```

## Reference Ingestion

The CLI can also ingest metadata references:

```bash
rks ingest doi 10.48550/arXiv.1706.03762
rks ingest arxiv 1706.03762
```

These flows create paper records and metadata artifacts and, when an abstract is available, generate text artifacts that can feed claim extraction.
When a provider exposes PDF candidates, RKS also attempts to persist a local `source.pdf` and records acquisition status for later inspection.

## Design Docs

- [docs/project-positioning.md](docs/project-positioning.md)
- [docs/design-implementation-comparison.md](docs/design-implementation-comparison.md)
- [docs/implementation-plan.md](docs/implementation-plan.md)
- [docs/manual-testing-guide-zh.md](docs/manual-testing-guide-zh.md)
- [docs/product-priorities.md](docs/product-priorities.md)
- [docs/progress.md](docs/progress.md)
- [docs/mvp-status.md](docs/mvp-status.md)
- [docs/roadmap.md](docs/roadmap.md)
- [docs/agent-skills.md](docs/agent-skills.md)
