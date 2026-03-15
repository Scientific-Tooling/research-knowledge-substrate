# Dual-Track LLM Contract

## Rule

Any RKS feature that can invoke an LLM must expose the same two LLM-facing integration paths:

- `llm-api`
- `agent`

If the feature also has a local non-LLM fallback, it may additionally expose `heuristic`.

This is not optional. It is a system contract.

## Why

RKS is intended to work in two different environments:

1. a standalone CLI where the user provides an API key and RKS calls an LLM provider directly
2. an agent environment such as Codex or Claude Code where the surrounding agent performs the LLM work and hands results back to RKS

If a capability only supports one of these paths, it is incomplete.

## Required Modes

For any LLM-capable task:

- `--mode llm-api`
- `--mode agent`

If a local fallback exists:

- `--mode heuristic`

## Standard Request Artifact

Agent mode must emit a request artifact that follows this structure:

```json
{
  "spec_version": "v1",
  "task": "extract_text",
  "paper_id": "p_000001",
  "instruction": "...",
  "input": {},
  "expected_output_schema": {}
}
```

This request artifact is the stable handshake between RKS and an external agent.

## Standard Import Contract

Agent-produced results must be imported back into RKS through explicit import commands.

This keeps the boundary visible and auditable:

- `rks import text ...`
- `rks import claims ...`

## Validation Rule

Both `llm-api` and `agent` results must be validated against the same task contract before persistence.

That means:

- direct API results are not trusted implicitly
- agent-produced JSON is not trusted implicitly
- both go through the same schema-level checks

## Provider Reliability

The `llm-api` track includes:

- retry logic with exponential backoff (up to 3 attempts)
- a 60-second timeout per request
- direct PDF-to-LLM: the source PDF is sent as base64 alongside the text prompt so the LLM can read the actual document even when heuristic extraction fails

The `agent` track now surfaces the source PDF path at the top level of text extraction requests so the external agent can read the PDF directly.

## Current Tasks Covered

The contract is currently implemented for:

- text extraction
- claim parsing
- paper summarization

Future LLM-backed tasks must adopt the same interface pattern instead of inventing task-specific one-off flows.
