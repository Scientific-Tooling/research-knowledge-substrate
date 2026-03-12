---
name: rks-research-output
description: Use this skill when an agent should produce directly consumable research outputs from the local RKS graph: answer a question, brief a topic, surface disagreements, or suggest evidence-backed research opportunities.
---

# RKS Research Output

Use this skill when the goal is not just to inspect graph objects, but to return useful research content, synthesis, or inspiration to a user.

## Trigger

Use this skill for requests such as:

- answer this research question from RKS
- brief me on this topic
- show disagreements around this topic
- suggest research opportunities from the graph
- tell me what I should read or test next

## Core Commands

Answer a question:

```bash
rks output answer "<question>"
```

Generate a topic brief:

```bash
rks output brief "<topic>"
```

Surface disagreements:

```bash
rks output disagreements "<topic>"
```

Generate opportunities and next steps:

```bash
rks output opportunities "<topic>"
```

HTTP equivalents:

```bash
curl -s "http://127.0.0.1:8765/api/output/answer?q=<encoded-question>"
curl -s "http://127.0.0.1:8765/api/output/brief?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/disagreements?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=<encoded-topic>"
```

## Recommended Workflow

1. run the direct output command first
2. inspect returned supporting claims and papers
3. if the output is too sparse, fall back to lower-level graph inspection:
   `rks search`, `rks show claim`, `rks query claims-about`
4. if needed, refine the topic or question and rerun the output command

## Output Discipline

Treat these outputs as grounded synthesis layers over the graph, not as free-form brainstorming.

When reporting back:

- cite the question or topic you used
- preserve the returned `supporting_claims` and `supporting_papers`
- preserve `disagreements`, `uncertainties`, `open_questions`, or `next_steps` when present
- distinguish reviewed relation facts from merely inferred disagreement signals

## When To Switch Skills

- If the task is only low-level object inspection, switch to `rks-query-substrate`
- If the task is ingest or graph-building, switch to `rks-build-paper-graph`
- If the task is a live walkthrough for a human, switch to `rks-user-demo`
- If the task is automated verification, switch to `rks-autotest`
