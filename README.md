# Research Knowledge Substrate

Research Knowledge Substrate (RKS) is an agent-first local research graph system for ingesting papers, extracting research objects, querying evidence, and serving a local research workspace.

The repository is now packaged for formal PyPI distribution, including a PyPI-specific README, packaged schema migrations, and GitHub Actions workflows for package validation and publishing.

## Current Capabilities

The current implementation supports:

- ingesting local PDFs
- ingesting DOI, arXiv, and PMID references
- ingesting canonical paper URLs for DOI, arXiv, PubMed, and direct PDF sources
- attempting source PDF acquisition during DOI, arXiv, and PMID ingestion when provider metadata exposes PDF candidates
- persisting papers and extraction artifacts to SQLite plus local disk
- generating inspectable pipeline artifacts such as extracted text, sections, and structured claims
- extracting heuristic structured claims, methods, and datasets
- normalizing and linking concepts
- creating graph edges for `contains`, `supported_by`, `about`, `proposes`, `uses`, `evaluated_on`, and `cites`
- organizing research projects with links to papers, claims, methods, datasets, and concepts
- tracking project-owned hypotheses and evidence links
- querying claims, methods, datasets, evidence views, and claim relations
- promoting reviewed claim relations into durable graph edges while keeping inferred relations separate
- generating direct research outputs for topic and project answers, briefs, disagreements, opportunities, reading lists, and review guidance
- planning deterministic next-step command sequences for research requests
- indexing local embeddings and running hybrid lexical/semantic search
- two LLM integration modes for text extraction and claim parsing:
  API mode and agent-assisted mode
- the same dual-track pattern for paper summarization
- batch ingest and extraction workflows
- task queue and paper status inspection for agent-mode operations
- workspace inventory stats for tracked papers, stored PDFs, artifacts, tasks, and graph object counts
- listing recent papers and managing paper tags (for example `read_later`, `survey`, `replication`)
- config initialization, migration/version reporting, and graph snapshot export/import
- stable agent-facing operations for paper status and claim-relation review over CLI and HTTP
- bundled skill export for Codex, Claude Code, and other external agent tools
- a local HTTP service and lightweight UI with request logging, input validation, and structured error responses

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

Export bundled skills for an external agent runtime:

```bash
rks skills list
rks skills export ./rks-agent-kit
```

CLI is the canonical external interface for RKS.  
Use the exported skills to drive Codex, Claude Code, or other agent runtimes through CLI commands.

Inspect the graph:

```bash
rks papers list --limit 20
rks papers mark p_000001 --tag read_later
rks papers mark p_000001 --tag survey
rks papers list --tag survey
rks papers unmark p_000001 --tag read_later
rks papers tags p_000001
rks papers read-later
rks show paper p_000001
rks note add paper p_000001 --content "Revisit the evaluation protocol."
rks note list paper p_000001
rks project create --name "Sparse Attention Review" --research-question "Which papers matter most for long-context evaluation?"
rks note add project rp_000001 --content "Track benchmark realism separately from raw headline results."
rks project add-paper rp_000001 p_000001 --link-type key_evidence
rks project add-link rp_000001 claim c_000001 --link-type key_evidence
rks project links rp_000001 --object-type claim
rks hypothesis create rp_000001 --text "Sparse attention gains hold only under realistic long-context benchmarks."
rks hypothesis add-evidence h_000001 paper p_000001 --relation-type supported_by
rks output project-brief rp_000001
rks output project-review-priorities rp_000001
rks plan query "What should we review next?" --project-id rp_000001
rks show project rp_000001
rks show hypothesis h_000001
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

Run a quality baseline check:

```bash
cat > quality-baseline.json <<'JSON'
{
  "name": "team-baseline-v1",
  "checks": {
    "min_paper_count": 5,
    "min_total_claims": 20,
    "max_zero_claim_rate": 0.3,
    "min_mean_claims_per_paper": 2.0,
    "required_extraction_modes": ["heuristic"]
  }
}
JSON
rks evaluate baseline quality-baseline.json
```

Generate direct research outputs:

```bash
rks output answer "What does the graph say about Sparse Attention?"
rks output brief "Sparse Attention"
rks output reading-list "Sparse Attention"
rks output compare p_000001 p_000002
rks output open-questions "Sparse Attention"
rks output review-priorities "Sparse Attention"
rks output disagreements "Sparse Attention"
rks output opportunities "Sparse Attention"
rks output project-answer rp_000001 --question "What does the current project evidence say?"
rks output project-reading-list rp_000001
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
rks stats
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
rks ingest pmid 31452104
rks ingest url https://pubmed.ncbi.nlm.nih.gov/31452104/
rks ingest url https://example.org/paper.pdf
```

These flows create paper records and metadata artifacts and, when an abstract is available, generate text artifacts that can feed claim extraction.
When a provider exposes PDF candidates, RKS also attempts to persist a local `source.pdf` and records acquisition status for later inspection.

## Reference Acquisition Boundary

RKS treats external literature discovery and ad hoc web retrieval as agent responsibilities, not substrate responsibilities.

The ingest layer should accept only stable, explicit inputs such as:

- local PDF files
- DOI, arXiv ID, and PMID identifiers
- canonical DOI/arXiv/PubMed URLs
- direct PDF URLs

RKS should not grow into a general web crawler or landing-page scraper. If an input must be discovered, resolved, or fetched from a non-canonical page, the external agent should do that work first and then pass a stable identifier, canonical URL, direct PDF URL, or local file into RKS.

For the broader architectural boundaries that should remain stable as RKS evolves, see [docs/system-constraints.md](docs/system-constraints.md).

## Design Docs

- [docs/README.md](docs/README.md)
- [docs/product-introduction.md](docs/product-introduction.md)
- [docs/product-introduction-zh.md](docs/product-introduction-zh.md)
- [docs/usage-manual.md](docs/usage-manual.md)
- [docs/usage-manual-zh.md](docs/usage-manual-zh.md)
- [docs/system-constraints.md](docs/system-constraints.md)
- [docs/design-implementation-comparison.md](docs/design-implementation-comparison.md)
- [docs/research-output-roadmap.md](docs/research-output-roadmap.md)
- [docs/focus-optimization-plan.md](docs/focus-optimization-plan.md)
- [docs/installation-guide.md](docs/installation-guide.md)
- [docs/installation-guide-zh.md](docs/installation-guide-zh.md)
- [docs/pypi-publishing-guide.md](docs/pypi-publishing-guide.md)
- [docs/pypi-publishing-guide-zh.md](docs/pypi-publishing-guide-zh.md)
- [docs/user-usage-guide.md](docs/user-usage-guide.md)
- [docs/user-usage-guide-zh.md](docs/user-usage-guide-zh.md)
- [docs/agent-usage-guide.md](docs/agent-usage-guide.md)
- [docs/agent-usage-guide-zh.md](docs/agent-usage-guide-zh.md)
- [docs/manual-testing-guide.md](docs/manual-testing-guide.md)
- [docs/manual-testing-guide-zh.md](docs/manual-testing-guide-zh.md)
- [docs/product-priorities.md](docs/product-priorities.md)
- [docs/progress.md](docs/progress.md)
- [docs/agent-skills.md](docs/agent-skills.md)

Archived design and completed plan documents live under `docs/archive/`.
