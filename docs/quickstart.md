# RKS Quickstart (3 minutes)

## What you'll get

A local knowledge graph built from scientific papers. Ask questions, get answers with specific claims and sources:

```
$ rks output answer "What are the leading causes of cancer death globally?"

{
  "conclusion": "Lung cancer remained the leading cause of cancer death globally
  in 2020, with an estimated 1.8 million deaths (18%), followed by colorectal
  (9.4%), liver (8.3%), stomach (7.7%), and female breast (6.9%) cancers.",
  "confidence": "low",
  "evidence_count": 3,
  ...
}
```

---

## Option A: Import a pre-built workspace (fastest)

Download the demo workspace (cancer epidemiology, 5 papers, ~500 claims):

```bash
pip install research-knowledge-substrate
rks init ~/rks-demo
rks import workspace demo-cancer-epi.tar.gz
```

Skip to [Explore the graph](#explore-the-graph).

> **Note:** Demo workspace download coming soon. Use Option B in the meantime.

---

## Option B: Build from a paper you have

**Step 1 — Install and initialize**

```bash
pip install research-knowledge-substrate
rks init ~/rks-demo
```

**Step 2 — Ingest a PDF**

```bash
rks ingest pdf /path/to/your-paper.pdf
# → {"id": "p_000001", "title": "...", ...}
```

Or ingest by DOI (attempts to fetch the PDF automatically):

```bash
rks ingest doi 10.3322/caac.21660
```

**Step 3 — Extract claims (agent mode)**

RKS extracts structured claims from the paper. In agent mode, your AI assistant does the reading. Run this command, then follow the prompt in your AI tool:

```bash
rks extract text p_000001 --mode agent
# → writes a task request; your agent reads the PDF and submits the result

rks extract claims p_000001 --mode agent
# → your agent extracts structured claims; you import the result

rks import claims p_000001 claims-result.json
```

Or if you have an OpenAI-compatible API key:

```bash
export RKS_LLM_API_KEY=sk-...
rks extract text p_000001 --mode llm-api
rks extract claims p_000001 --mode llm-api
```

**Step 4 — Build the graph**

```bash
rks concepts build p_000001
rks embed paper p_000001
```

---

## Explore the graph

```bash
# Ask a research question
rks output answer "What is the global cancer burden?"

# Find claims about a concept
rks query claims-about "breast cancer"

# Get a topic brief
rks output brief "lung cancer mortality"

# Search across all papers
rks query search "incidence rates"

# Show a specific paper's status and claims
rks status paper p_000001
rks show claims p_000001
```

---

## Add more papers

Each additional paper enriches the graph. RKS links concepts across papers automatically:

```bash
rks ingest doi 10.1002/ijc.33524      # another cancer epidemiology paper
rks extract claims p_000002 --mode llm-api
rks concepts build p_000002

# Now cross-paper queries work:
rks query papers-supporting "lung cancer incidence is rising"
```

---

## What's next

- `rks --help` — full command reference
- `docs/usage-manual.md` — detailed usage
- `docs/agent-usage-guide.md` — running extraction with Claude Code or Codex
