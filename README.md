# Research Knowledge Substrate

Research Knowledge Substrate (RKS) is an agent-first local research graph system for ingesting papers, extracting structured claims, linking concepts, and querying evidence through a CLI.

## Current MVP

The current MVP supports:

- ingesting local PDFs
- ingesting DOI and arXiv references
- persisting papers and extraction artifacts to SQLite plus local disk
- extracting heuristic structured claims
- normalizing and linking concepts
- creating graph edges for `contains`, `supported_by`, and `about`
- querying claims about a concept and papers supporting a claim
- two LLM integration modes for text extraction and claim parsing:
  API mode and agent-assisted mode
- the same dual-track pattern for paper summarization

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
rks init-db
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
rks query claims-about Transformer
rks query papers-supporting c_000001
```

Generate a paper summary:

```bash
rks summarize paper p_000001
rks summarize paper p_000001 --mode llm-api
rks summarize paper p_000001 --mode agent
rks import summary p_000001 path/to/agent_summary.json
```

## Reference Ingestion

The CLI can also ingest metadata references:

```bash
rks ingest doi 10.48550/arXiv.1706.03762
rks ingest arxiv 1706.03762
```

These flows create paper records and metadata artifacts and, when an abstract is available, generate text artifacts that can feed claim extraction.

## Design Docs

- [docs/project-positioning.md](docs/project-positioning.md)
- [docs/implementation-plan.md](docs/implementation-plan.md)
- [docs/progress.md](docs/progress.md)
