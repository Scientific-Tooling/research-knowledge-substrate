# Research Knowledge Substrate

Research Knowledge Substrate (RKS) is an agent-first local research graph system for ingesting papers, extracting structured research objects, querying evidence, and generating grounded research outputs.

RKS is designed for local, inspectable workflows:

- ingest local PDFs, DOI references, and arXiv references
- persist papers, graph objects, embeddings, and artifacts in SQLite plus local disk
- extract claims, methods, datasets, concepts, and summaries
- run lexical, semantic, and hybrid search over the local substrate
- expose the same operations through CLI and local HTTP endpoints
- support both direct `llm-api` execution and external agent execution

## Installation

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install research-knowledge-substrate
```

Initialize a workspace:

```bash
rks config init
rks init-db
rks migrate
```

## Quick Start

Ingest a PDF:

```bash
rks ingest pdf path/to/paper.pdf
```

Extract claims:

```bash
rks extract claims p_000001
```

Run local search and output surfaces:

```bash
rks search Transformer
rks output answer "What does the graph say about Sparse Attention?"
rks output brief "Sparse Attention"
```

Persist paper notes or reviewed relations:

```bash
rks note add paper p_000001 --content "Revisit the evaluation protocol."
rks review promote-claim-relation c_000001 supports c_000014 --reviewed-by agent:review
```

Serve the local API:

```bash
rks serve --host 127.0.0.1 --port 8765
```

## Links

- Repository: https://github.com/Scientific-Tooling/research-knowledge-substrate
- Documentation Index: https://github.com/Scientific-Tooling/research-knowledge-substrate/blob/main/docs/README.md
- Installation Guide: https://github.com/Scientific-Tooling/research-knowledge-substrate/blob/main/docs/installation-guide.md
- User Guide: https://github.com/Scientific-Tooling/research-knowledge-substrate/blob/main/docs/user-usage-guide.md
- Agent Guide: https://github.com/Scientific-Tooling/research-knowledge-substrate/blob/main/docs/agent-usage-guide.md
