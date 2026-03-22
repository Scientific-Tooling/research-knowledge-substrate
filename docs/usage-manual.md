# RKS Usage Manual

This manual provides a practical, end-to-end operating guide for RKS.
It is intended for daily usage in local research workflows.

## 1. Prerequisites

- Python 3.10+ available in shell
- Access to this repository
- Local filesystem write permission for workspace data

Optional for LLM modes:

- `RKS_LLM_API_KEY`
- `RKS_LLM_MODEL`
- `RKS_LLM_BASE_URL` (if not using default OpenAI-compatible endpoint)

## 2. Installation and Initialization

From repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Set your data directory and initialize local RKS state:

```bash
rks init ~/rks-data
rks config show
```

The `rks init <path>` command writes `~/.rks/config.json` and initializes the database. Run `rks` from any directory after this.

To wipe all data and start fresh (keeps global config):

```bash
rks clear --yes
```

Without `--yes`, the command prints what would be deleted and exits safely.

## 3. Quick Start (10-minute path)

```bash
rks ingest pdf path/to/paper.pdf
rks extract claims <paper_id>
rks claims <paper_id>
rks query claims-about Transformer
rks output brief "Transformer"
```

If you only need one thing to remember:
always capture IDs from command output and reuse them in next commands.

## 4. Ingest Sources

### 4.1 Local PDF

```bash
rks ingest pdf path/to/paper.pdf
rks show paper <paper_id>
rks status paper <paper_id>
```

### 4.2 DOI / arXiv / PMID

```bash
rks ingest doi 10.48550/arXiv.1706.03762
rks ingest arxiv 1706.03762
rks ingest pmid 31452104
```

After ingestion, verify:

- metadata artifact exists
- `source_pdf.acquisition.status`
- required next actions from `rks status paper <paper_id>`

### 4.3 Canonical URLs

```bash
rks ingest url https://doi.org/10.48550/arXiv.1706.03762
rks ingest url https://pubmed.ncbi.nlm.nih.gov/31452104/
rks ingest url https://example.org/paper.pdf
```

### 4.4 Duplicate paper detection and merge

```bash
rks papers find-duplicates
rks papers find-duplicates --mode identifiers
rks papers merge <target_paper_id> <source_paper_id> --prefer target
```

## 5. Extraction Workflows

### 5.1 Text extraction

```bash
rks extract text <paper_id>
rks extract text <paper_id> --mode llm-api
rks extract text <paper_id> --mode agent
```

### 5.2 Claim extraction

```bash
rks extract claims <paper_id>
rks extract claims <paper_id> --mode llm-api
rks extract claims <paper_id> --mode agent
```

### 5.3 Method and dataset extraction

```bash
rks extract methods <paper_id>
rks extract datasets <paper_id>
```

### 5.4 Summarization

```bash
rks summarize paper <paper_id>
rks summarize paper <paper_id> --mode llm-api
rks summarize paper <paper_id> --mode agent
```

## 6. Inspect and Explore

### 6.1 Object inspection

```bash
rks papers list --limit 20
rks papers mark <paper_id> --tag read_later
rks papers mark <paper_id> --tag survey
rks papers list --tag survey
rks papers unmark <paper_id> --tag read_later
rks papers tags <paper_id>
rks papers read-later
rks papers find-duplicates
rks papers find-duplicates --mode identifiers
rks papers merge <target_paper_id> <source_paper_id> --prefer target
rks show paper <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
rks methods <paper_id>
rks datasets <paper_id>
rks show claim <claim_id>
rks concept add-alias <concept_id> <alias>
rks concept merge <source_concept_id> <target_concept_id>
```

### 6.2 Search and deterministic query

```bash
rks stats
rks search Transformer
rks search "translation quality benchmark" --mode semantic
rks query claims-about Transformer
rks query papers-supporting <claim_id>
rks query evidence-for Transformer
rks query claim-relations <claim_id>
```

## 7. Review and Persist Claim Relations

Inspect inferred relations first:

```bash
rks query claim-relations <claim_id>
```

Promote reviewed relation:

```bash
rks review promote-claim-relation <from_claim_id> supports <to_claim_id> --reviewed-by human:analyst
```

Retract reviewed relation:

```bash
rks review retract-claim-relation <from_claim_id> supports <to_claim_id>
```

## 8. Research Project Workflow

Create project and link evidence:

```bash
rks project create --name "Sparse Attention Review" --research-question "Which papers matter most for realistic long-context evaluation?"
rks project add-paper <project_id> <paper_id> --link-type key_evidence
rks project add-link <project_id> claim <claim_id> --link-type key_evidence
rks project links <project_id>
rks show project <project_id>
```

Create and track a hypothesis:

```bash
rks hypothesis create <project_id> --text "Sparse attention gains hold only under realistic benchmarks."
rks hypothesis add-evidence <hypothesis_id> paper <paper_id> --relation-type supported_by
rks hypothesis evidence <hypothesis_id>
rks show hypothesis <hypothesis_id>
```

## 9. Direct Research Outputs

Topic-scoped outputs:

```bash
rks output answer "What does the graph say about Sparse Attention?"
rks output brief "Sparse Attention"
rks output disagreements "Sparse Attention"
rks output opportunities "Sparse Attention"
rks output reading-list "Sparse Attention"
rks output open-questions "Sparse Attention"
rks output review-priorities "Sparse Attention"
```

Project-scoped outputs:

```bash
rks output project-answer <project_id> --question "What does current evidence support?"
rks output project-brief <project_id>
rks output project-reading-list <project_id>
rks output project-disagreements <project_id>
rks output project-open-questions <project_id>
rks output project-review-priorities <project_id>
```

## 10. Agent Mode Request/Import Loop

For `agent` mode tasks:

```bash
rks extract text <paper_id> --mode agent
rks import text <paper_id> path/to/text_result.json
rks extract claims <paper_id> --mode agent
rks import claims <paper_id> path/to/claims_result.json
rks summarize paper <paper_id> --mode agent
rks import summary <paper_id> path/to/summary_result.json
```

Track task lifecycle:

```bash
rks tasks list
rks tasks show <task_id>
rks status paper <paper_id>
```

## 11. Batch and Export Operations

Batch operations:

```bash
rks batch ingest manifest.json
rks batch extract claims manifest.json
rks batch output brief manifest.json
```

Export/import graph snapshot (DB tables only, no files):

```bash
rks export graph snapshot.json
rks import graph snapshot.json
```

Export/import full workspace (DB tables + all artifact files, machine-portable):

```bash
rks export workspace ~/my_workspace.tar.gz
rks import workspace ~/my_workspace.tar.gz
```

The workspace archive bundles everything — PDFs, extracted text, and all other artifact files — alongside the graph snapshot. File paths are stored as relative paths inside the archive and rewritten to absolute paths under the active `data_dir` on import. Use this to move an entire RKS workspace between machines:

```bash
# Source machine
rks export workspace ~/rks_backup.tar.gz

# Transfer archive (scp, USB, cloud, etc.)
scp ~/rks_backup.tar.gz user@newmachine:~/

# New machine (after rks init)
rks import workspace ~/rks_backup.tar.gz
```

## 12. Local Service and HTTP Mirror

Run local service:

```bash
rks serve --host 127.0.0.1 --port 8765
```

Common endpoints:

```bash
curl -s http://127.0.0.1:8765/health
curl -s http://127.0.0.1:8765/api/status/<paper_id>
curl -s "http://127.0.0.1:8765/api/output/brief?topic=Sparse%20Attention"
```

## 13. Troubleshooting

### 13.1 `rks: command not found`

- activate virtual environment
- install package with `python -m pip install -e .`
- or use `PYTHONPATH=src python3 -m rks ...` in repository root

### 13.2 LLM API failures

- check `RKS_LLM_API_KEY`
- verify provider endpoint (`llm.base_url`)
- retry with `--mode agent` to delegate extraction to the surrounding agent

### 13.3 Missing outputs after ingestion

- run `rks status paper <paper_id>`
- inspect artifacts through `rks show paper <paper_id>`
- verify whether `source_pdf` acquisition was unavailable/failed/skipped

## 14. Operational Best Practices

- never invent IDs; always parse from command outputs
- re-read objects after write operations
- use review commands for durable relation changes
- keep project/hypothesis links explicit for traceable decisions
- use CLI as canonical semantics; use HTTP for integration checks

## 15. Related Guides

- Product introduction: `docs/product-introduction.md`
- User operations: `docs/user-usage-guide.md`
- Agent operations: `docs/agent-usage-guide.md`
- Manual testing: `docs/manual-testing-guide.md`
