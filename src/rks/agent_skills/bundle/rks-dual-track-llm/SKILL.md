---
name: rks-dual-track-llm
description: "Use this skill when a task involves any LLM-backed RKS operation and you need to choose or execute the correct dual-track mode: llm-api or agent."
---

# RKS Dual-Track LLM

Use this skill whenever an RKS task can invoke an LLM.

## Rule

All LLM-backed RKS tasks must use the dual-track contract:

- `llm-api`
- `agent`

There is no `heuristic` mode. The only valid modes are `llm-api` and `agent`.

Do not create task-specific ad hoc LLM flows.

## Current Covered Tasks

- text extraction
- claim parsing
- paper summarization

## How To Choose

Use `llm-api` when:

- the user wants RKS itself to call a provider
- API credentials are available
- a direct provider-backed run is acceptable

Use `agent` when:

- the surrounding agent should do the reasoning work
- the environment already has access to Codex, Claude Code, or another agent runtime
- you want a visible request/import boundary

## Agent Mode Workflow

Agent mode is always two-step:

1. create request artifact
2. import result artifact

### MUST: Read the paper directly as a multimodal AI

**When operating in agent mode, you MUST read the source document yourself using your own multimodal reading capability. This is mandatory and non-negotiable.**

- Use the Read tool (or equivalent) on the source PDF path (e.g. `data/papers/<paper_id>/source.pdf`).
- Read all pages of the document directly as an AI agent.
- Extract claims, text, and summaries from what you read.
- **NEVER** use Python scripts, subprocess calls, or programmatic text extraction to read the paper content.
- **NEVER** read from heuristic artifacts (e.g. `extracted_text.json`) as a substitute for direct document reading.
- **NEVER** pipe the paper through any local text processing tool.

The entire purpose of agent mode is that **the AI reads and reasons over the document directly**. Using heuristic extraction defeats the purpose and bypasses the AI's own reading capability. If you catch yourself writing a Python script to read the paper, stop immediately and use the Read tool on the PDF instead.

Examples:

```bash
rks extract text <paper_id> --mode agent
rks import text <paper_id> <json_path>

rks extract claims <paper_id> --mode agent
rks import claims <paper_id> <json_path>

rks summarize paper <paper_id> --mode agent
rks import summary <paper_id> <json_path>
```

## API Mode Workflow

Use provider-backed execution directly:

```bash
rks extract text <paper_id> --mode llm-api
rks extract claims <paper_id> --mode llm-api
rks summarize paper <paper_id> --mode llm-api
```

Required environment variables usually include:

- `RKS_LLM_API_KEY` or `OPENAI_API_KEY`
- optionally `RKS_LLM_MODEL`
- optionally `RKS_LLM_BASE_URL`

## Validation Requirement

Do not bypass RKS import paths.

Both `llm-api` and `agent` outputs are expected to conform to the contract and are validated before persistence. If a result does not match the expected schema, fix the result and re-import; do not patch database rows manually.

## Reference

For the contract details, read `docs/dual-track-llm-contract.md`.
