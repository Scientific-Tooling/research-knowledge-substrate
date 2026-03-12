---
name: rks-build-paper-graph
description: Use this skill when the task is to ingest a paper or reference into RKS, run extraction, build claims/concepts/edges, and leave the paper in a queryable graph state.
---

# RKS Build Paper Graph

Use this skill when an agent needs to move a paper from source material into the local RKS graph.

## Trigger

Use this skill for requests such as:

- ingest this PDF into RKS
- add this DOI or arXiv paper
- extract claims from this paper
- build the graph for this paper
- process this paper so it can be queried later

## Workflow

Run the smallest complete path needed for the request.

### PDF source

```bash
rks ingest pdf <path>
```

### DOI source

```bash
rks ingest doi <doi>
```

### arXiv source

```bash
rks ingest arxiv <id>
```

After ingestion, extract claims if the request implies graph construction:

```bash
rks extract claims <paper_id>
```

If the paper needs a summary:

```bash
rks summarize paper <paper_id>
```

## Mode Selection

For `extract text`, `extract claims`, and `summarize paper`, always choose a mode explicitly when context matters:

- `heuristic`: use for local fallback or tests
- `llm-api`: use when the user provides or expects direct provider usage
- `agent`: use when the surrounding agent should do the LLM work

When using `agent` mode, do not invent your own format. Follow the request/import loop exactly:

```bash
rks extract text <paper_id> --mode agent
rks import text <paper_id> <json_path>

rks extract claims <paper_id> --mode agent
rks import claims <paper_id> <json_path>

rks summarize paper <paper_id> --mode agent
rks import summary <paper_id> <json_path>
```

## Completion Check

Before declaring success, inspect the result:

```bash
rks show paper <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
```

The expected paper state is:

- stable `paper_id`
- text artifact present
- sections artifact present
- structured claims present when extraction was requested
- concepts present when claims were extracted

## Important Constraints

- Prefer rerunning the same artifact-producing command over inventing manual file edits
- RKS artifacts are replaceable per paper/type; reruns are acceptable
- If the task needs LLM work, follow the dual-track contract in `docs/dual-track-llm-contract.md`
