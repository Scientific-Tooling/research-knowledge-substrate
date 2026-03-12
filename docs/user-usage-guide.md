# RKS User Usage Guide

This document explains how a human user can operate RKS directly through the CLI. It is about day-to-day usage, not regression testing.

## 1. Typical Use Cases

This guide is suitable when you want to:

- ingest local PDFs, DOI references, or arXiv references
- inspect papers, claims, concepts, methods, and datasets
- run search, query, and summarization flows
- manually review claim relations
- inspect paper status and agent tasks

If your goal is regression verification, use [manual-testing-guide.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/manual-testing-guide.md).

## 2. Setup

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Initialize the local workspace:

```bash
rks config init
rks init-db
rks migrate
```

Inspect the active configuration:

```bash
rks config show
```

Important fields:

- `data_dir`
- `reference_pdf_acquisition`
- `llm.base_url`
- `llm.model`

## 3. Basic Workflow

A normal RKS usage loop is:

1. ingest material
2. extract text, claims, methods, or datasets
3. inspect papers and graph objects
4. run search, query, output generation, or summarization
5. review and persist important claim relations

## 4. Ingest Sources

### 4.1 Local PDF

```bash
rks ingest pdf path/to/paper.pdf
```

The most important value in the output is `paper_id`.

Then inspect:

```bash
rks show paper <paper_id>
rks status paper <paper_id>
```

Add a user note when you want to keep reading context with the paper:

```bash
rks note add paper <paper_id> --content "Focus on the benchmark split and evaluation caveats."
rks note list paper <paper_id>
```

`show paper` also includes a `notes` field so you can review the paper record and your notes together.

Create a research project when you want a durable investigation scope above individual papers:

```bash
rks project create --name "Sparse Attention Review" --research-question "Which sparse attention papers matter most for long-context evaluation?"
rks note add project <project_id> --content "Track benchmark realism separately from headline wins."
rks project add-paper <project_id> <paper_id> --link-type key_evidence
rks project papers <project_id>
rks hypothesis create <project_id> --text "Sparse attention gains hold only under realistic long-context benchmarks."
rks hypothesis add-evidence <hypothesis_id> paper <paper_id> --relation-type supported_by
rks hypothesis add-evidence <hypothesis_id> claim <claim_id> --relation-type refined_by
rks hypothesis evidence <hypothesis_id>
rks show hypothesis <hypothesis_id>
rks show project <project_id>
```

Use projects for your working context and curated evidence set. Use hypotheses for your own research ideas. Keep extracted claims bound to papers so provenance remains explicit.

### 4.2 DOI

```bash
rks ingest doi 10.48550/arXiv.1706.03762
```

This path can create:

- paper metadata
- a metadata artifact
- a text artifact when an abstract is available
- a local `source.pdf` when the provider exposes usable PDF candidates

### 4.3 arXiv

```bash
rks ingest arxiv 1706.03762
```

After DOI or arXiv ingestion, inspect:

```bash
rks status paper <paper_id>
```

Important fields:

- `source_pdf.available`
- `source_pdf.acquisition.status`
- `artifacts`

## 5. Extract Research Objects

### 5.1 Extract text

```bash
rks extract text <paper_id>
```

Explicit modes:

```bash
rks extract text <paper_id> --mode heuristic
rks extract text <paper_id> --mode llm-api
rks extract text <paper_id> --mode agent
```

### 5.2 Extract claims

```bash
rks extract claims <paper_id>
```

Common modes:

```bash
rks extract claims <paper_id> --mode heuristic
rks extract claims <paper_id> --mode llm-api
rks extract claims <paper_id> --mode agent
```

### 5.3 Extract methods and datasets

```bash
rks extract methods <paper_id>
rks extract datasets <paper_id>
```

### 5.4 Summarize a paper

```bash
rks summarize paper <paper_id>
```

Alternative modes:

```bash
rks summarize paper <paper_id> --mode llm-api
rks summarize paper <paper_id> --mode agent
```

## 6. Inspect Objects

### 6.1 Papers

```bash
rks show paper <paper_id>
```

Useful for:

- title and source information
- `pdf_path`
- artifact inventory

### 6.2 Claims

```bash
rks claims <paper_id>
rks show claim <claim_id>
```

`show claim` is the better command for:

- evidence
- context
- related edges
- reviewed relations

### 6.3 Concepts, methods, and datasets

```bash
rks concepts <paper_id>
rks methods <paper_id>
rks datasets <paper_id>
```

If you already know the object ID:

```bash
rks show method <method_id>
rks show dataset <dataset_id>
```

## 7. Search and Query

### 7.1 Search

```bash
rks search Transformer
rks search "translation quality benchmark" --mode semantic
rks search "Sparse Attention" --mode hybrid
```

Available modes:

- `lexical`
- `semantic`
- `hybrid`

### 7.2 Deterministic query commands

```bash
rks query claims-about Transformer
rks query papers-supporting <claim_id>
rks query evidence-for Transformer
rks query methods-for <paper_id>
rks query datasets-for <paper_id>
```

### 7.3 Claim relation queries

```bash
rks query claim-relations <claim_id>
```

The key distinction is:

- `inferred_relations`: query-time candidate relations
- `reviewed_relations`: persisted reviewed relations

Do not treat `inferred_relations` as durable truth.

## 8. Direct Research Outputs

RKS now also exposes output-oriented commands for users who want content back from the graph rather than only raw objects.

Answer a research question:

```bash
rks output answer "What does the graph say about Sparse Attention?"
```

Generate a topic briefing:

```bash
rks output brief "Sparse Attention"
```

Inspect disagreements:

```bash
rks output disagreements "Sparse Attention"
```

Generate opportunities and next-step guidance:

```bash
rks output opportunities "Sparse Attention"
```

Generate reading, comparison, and review guidance:

```bash
rks output reading-list "Sparse Attention"
rks output compare p_000001 p_000002
rks output open-questions "Sparse Attention"
rks output review-priorities "Sparse Attention"
```

These outputs are grounded in claims, papers, methods, datasets, and reviewed or inferred relation structure. They are intended to be more directly consumable than lower-level query outputs.

## 9. Manually Review Claim Relations

First inspect candidates:

```bash
rks query claim-relations <claim_id>
```

To promote one relation:

```bash
rks review promote-claim-relation <source_claim_id> supports <target_claim_id> --reviewed-by human:review --note "checked manually"
```

Supported relation types:

- `supports`
- `refines`
- `contradicts`

To retract:

```bash
rks review retract-claim-relation <source_claim_id> supports <target_claim_id>
```

After promote or retract, re-run:

```bash
rks query claim-relations <source_claim_id>
rks show claim <source_claim_id>
```

## 10. Agent Mode From a User Perspective

If you want an external agent to perform a task instead of letting RKS call a provider directly, use `--mode agent`.

### 9.1 Text

```bash
rks extract text <paper_id> --mode agent
rks import text <paper_id> path/to/agent_text.json
```

### 9.2 Claims

```bash
rks extract claims <paper_id> --mode agent
rks import claims <paper_id> path/to/agent_claims.json
```

### 9.3 Summary

```bash
rks summarize paper <paper_id> --mode agent
rks import summary <paper_id> path/to/agent_summary.json
```

This pattern means:

- RKS creates the request artifact
- the external agent produces the result
- RKS validates and persists the imported result

## 11. Tasks and Status

List tasks:

```bash
rks tasks list
```

Tasks for one paper:

```bash
rks tasks list --paper-id <paper_id>
```

One task:

```bash
rks tasks show <task_id>
```

Mark failure:

```bash
rks tasks fail <task_id> "reason"
```

Inspect paper status:

```bash
rks status paper <paper_id>
```

`status paper` is one of the most important overview commands because it shows:

- artifacts
- stages
- readiness level
- missing steps
- blockers
- suggested next commands
- source PDF state
- task state
- persisted `agent_reports`
- `recovery_guidance` for queued, running, or failed tasks

## 12. Batch Operations

### 11.1 Batch ingest

```bash
rks batch ingest manifest.json
```

Example manifest:

```json
[
  {"source_type": "pdf", "path": "paper-1.pdf"},
  {"source_type": "doi", "source_ref": "10.48550/arXiv.1706.03762"}
]
```

### 11.2 Batch extract

```bash
rks batch extract claims manifest.json
rks batch extract summary manifest.json --mode agent
rks batch output answer output-manifest.json
```

Example extract manifest:

```json
[
  {"paper_id": "p_000001"},
  {"paper_id": "p_000002", "mode": "agent"}
]
```

Batch commands now return an `audit` block with success, failure, and workflow-specific counts.

For a higher-level local preparation pass, you can also run:

```bash
rks prepare paper-output <paper_id>
rks prepare paper-output <paper_id> --apply
```

## 13. Export, Import, and Service

Export a graph snapshot:

```bash
rks export graph snapshot.json
```

Import a graph snapshot:

```bash
rks import graph snapshot.json
```

Start the local service:

```bash
rks serve --host 127.0.0.1 --port 8765
```

## 14. Basic HTTP Usage

Health check:

```bash
curl -s http://127.0.0.1:8765/health
```

Paper status:

```bash
curl -s http://127.0.0.1:8765/api/status/<paper_id>
```

Claim relations:

```bash
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
```

Promote a relation:

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "supports",
    "target_claim_id": "c_000014",
    "reviewed_by": "human:http",
    "note": "checked from API"
  }'
```

Retract a relation:

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "supports",
    "target_claim_id": "c_000014"
  }'
```

## 15. Minimal Daily Command Set

If you only want the smallest practical command set, remember:

```bash
rks ingest pdf <path>
rks show paper <paper_id>
rks extract claims <paper_id>
rks claims <paper_id>
rks output answer "What does the graph say about this topic?"
rks query claim-relations <claim_id>
rks review promote-claim-relation <source_claim_id> supports <target_claim_id>
rks status paper <paper_id>
```

This already covers:

- ingest
- graph construction
- answer generation
- query
- review
- status inspection
Output answer:

```bash
curl -s "http://127.0.0.1:8765/api/output/answer?q=Sparse%20Attention%20outlook"
```

Output brief:

```bash
curl -s "http://127.0.0.1:8765/api/output/brief?topic=Sparse%20Attention"
```

Output disagreements:

```bash
curl -s "http://127.0.0.1:8765/api/output/disagreements?topic=Sparse%20Attention"
```

Output opportunities:

```bash
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=Sparse%20Attention"
```
