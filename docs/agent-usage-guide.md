# RKS Agent Usage Guide

This document is for external AI agents such as Codex, Claude Code, or similar runtimes that can execute terminal commands and HTTP requests. The focus is how to operate RKS as a product surface.

## 1. Intended Agent Tasks

This guide is suitable when an agent needs to:

- ingest research material and build graph state
- answer questions from the existing graph
- run a claim-relation review loop
- drive the `agent` request/import workflow
- use HTTP endpoints for reads, writes, and consistency checks
- run demos or automated verification flows

If you are a human operator, use [user-usage-guide.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/user-usage-guide.md).

## 2. Core Rules For Agents

When operating RKS, an external agent should:

- work from the repository root
- prefer `rks` CLI first, then use HTTP for cross-checking
- always read `paper_id`, `claim_id`, and `task_id` from command output
- never patch the database manually
- re-read state after every write operation
- distinguish `inferred_relations` from `reviewed_relations`
- inspect `source_pdf_acquisition` after reference ingestion

## 3. Initialize the Workspace

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Initialize RKS:

```bash
rks config init
rks init-db
rks migrate
rks config show
```

Important fields for agents:

- `data_dir`
- `reference_pdf_acquisition`
- `llm` configuration

## 4. Standard Agent Workflow

A normal agent workflow is:

1. initialize the environment
2. ingest data
3. inspect artifacts and status
4. extract claims or import agent-produced results
5. run search, query, output generation, or summarize
6. review claim relations
7. cross-check through HTTP
8. return a structured report

## 5. Ingest and Graph Construction

### 5.1 Local PDF

```bash
rks ingest pdf <path>
```

After receiving `paper_id`:

```bash
rks show paper <paper_id>
rks status paper <paper_id>
rks extract claims <paper_id>
```

### 5.2 DOI or arXiv

```bash
rks ingest doi <doi>
rks ingest arxiv <id>
```

After receiving `paper_id`, always inspect:

```bash
rks show paper <paper_id>
rks status paper <paper_id>
```

Critical checks:

- `metadata` artifact
- `source_pdf_acquisition` artifact
- `source_pdf.available`
- `source_pdf.acquisition.status`

If acquisition succeeds, also verify:

- `data/papers/<paper_id>/source.pdf` exists

If the paper needs operator context or a pending follow-up, persist that as a paper note instead of leaving it only in the agent transcript:

```bash
rks note add paper <paper_id> --content "Need manual comparison against the follow-up reproduction." --created-by agent:review
rks note list paper <paper_id>
```

The HTTP equivalents are:

```bash
curl -s http://127.0.0.1:8765/api/papers/<paper_id>/notes
curl -s -X POST http://127.0.0.1:8765/api/papers/<paper_id>/notes -H 'Content-Type: application/json' -d '{"content":"Need manual comparison against the follow-up reproduction.","created_by":"agent:review"}'
```

## 6. Agent Request / Import Loops

For tasks that rely on an external agent, RKS exposes an `agent` mode with a request/import boundary.

### 6.1 Text

```bash
rks extract text <paper_id> --mode agent
rks import text <paper_id> <json_path>
```

### 6.2 Claims

```bash
rks extract claims <paper_id> --mode agent
rks import claims <paper_id> <json_path>
```

### 6.3 Summary

```bash
rks summarize paper <paper_id> --mode agent
rks import summary <paper_id> <json_path>
```

Requirements:

- do not bypass the import path
- record the `task_id`
- re-check `tasks show` and `status paper` after import

## 7. Query and Answering

### 7.1 Common read commands

```bash
rks show paper <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
rks show claim <claim_id>
rks methods <paper_id>
rks datasets <paper_id>
```

### 7.2 Search and deterministic queries

```bash
rks search <query>
rks search <query> --mode semantic
rks query claims-about <concept>
rks query papers-supporting <claim_id>
rks query evidence-for <target>
rks query claim-relations <claim_id>
```

Recommended order when answering user questions:

1. `rks search`
2. `rks query claims-about`
3. `rks show claim`
4. `rks query claim-relations`
5. `rks output answer`
6. `rks summarize paper`

### 7.3 Direct output surfaces

Answer a question:

```bash
rks output answer "What does the graph say about Sparse Attention?"
```

Topic briefing:

```bash
rks output brief "Sparse Attention"
```

Disagreements:

```bash
rks output disagreements "Sparse Attention"
```

Opportunities:

```bash
rks output opportunities "Sparse Attention"
```

These commands are the preferred product-facing output layer when the user expects synthesis, disagreement surfacing, or inspiration rather than raw graph inspection.

## 8. Claim Relation Review Loop

### 8.1 Inspect candidates first

```bash
rks query claim-relations <claim_id>
```

Typical output fields:

- `inferred_relations`
- `reviewed_relations`

The agent must inspect candidates before promoting anything.

### 8.2 Promote

```bash
rks review promote-claim-relation <source_claim_id> <relation_type> <target_claim_id> --reviewed-by agent:review --note "why promoted"
```

### 8.3 Retract

```bash
rks review retract-claim-relation <source_claim_id> <relation_type> <target_claim_id>
```

### 8.4 Re-read after writes

```bash
rks query claim-relations <source_claim_id>
rks show claim <source_claim_id>
```

The agent should confirm:

- `reviewed_relations` changed as expected
- `inferred_relations` remains a separate layer
- `created_by` is correct

## 9. Tasks and Status

Inspect tasks:

```bash
rks tasks list
rks tasks list --paper-id <paper_id>
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

For agents, `status paper` is one of the most important overview surfaces.

## 10. HTTP Usage

### 10.1 Start the service

```bash
rks serve --host 127.0.0.1 --port 8765
```

### 10.2 Read endpoints

```bash
curl -s http://127.0.0.1:8765/health
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
curl -s "http://127.0.0.1:8765/api/output/answer?q=Sparse%20Attention%20outlook"
curl -s "http://127.0.0.1:8765/api/output/brief?topic=Sparse%20Attention"
curl -s "http://127.0.0.1:8765/api/output/disagreements?topic=Sparse%20Attention"
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=Sparse%20Attention"
```

### 10.3 Write endpoints

Promote:

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/promote \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "contradicts",
    "target_claim_id": "c_000003",
    "reviewed_by": "agent:http",
    "note": "promoted through http"
  }'
```

Retract:

```bash
curl -s -X POST http://127.0.0.1:8765/api/review/claim-relations/retract \
  -H 'Content-Type: application/json' \
  -d '{
    "source_claim_id": "c_000001",
    "relation_type": "contradicts",
    "target_claim_id": "c_000003"
  }'
```

### 10.4 CLI / HTTP consistency

After an HTTP write, the agent should cross-check through CLI:

```bash
rks query claim-relations <source_claim_id>
rks show claim <source_claim_id>
```

Do not trust only one surface.

## 11. Recommended Report Structure

At the end of a run, the agent should report:

1. environment state
2. object IDs used
3. ingest result
4. artifact and status result
5. query and retrieval result
6. reviewed relation result
7. CLI / HTTP consistency result
8. failures and causes

## 12. Common Agent Mistakes

### 12.1 Guessing IDs

Wrong:

- assuming `p_000001`
- assuming a claim ID

Right:

- parse IDs from command output

### 12.2 Skipping artifact inspection

Wrong:

- only checking command success

Right:

- inspect `show paper`
- inspect `status paper`
- inspect `data/papers/<paper_id>/` when needed

### 12.3 Treating inferred as durable truth

Wrong:

- telling the user the system has confirmed a relation just because it appears in `inferred_relations`

Right:

- only `reviewed_relations` represents persisted reviewed facts

### 12.4 Bypassing import paths

Wrong:

- inserting tasks, claims, or edges directly via SQL

Right:

- use `import`, `review`, CLI, or HTTP operations

## 13. Minimal Agent Command Set

If an agent only needs the smallest practical subset, cover:

```bash
rks config show
rks ingest pdf <path>
rks show paper <paper_id>
rks status paper <paper_id>
rks extract claims <paper_id>
rks claims <paper_id>
rks query claim-relations <claim_id>
rks review promote-claim-relation <source_claim_id> supports <target_claim_id>
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s http://127.0.0.1:8765/api/claims/<claim_id>/relations
```

This is enough for an agent to:

- ingest
- inspect
- build graph state
- query
- review
- cross-check CLI and HTTP
