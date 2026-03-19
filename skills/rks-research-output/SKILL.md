---
name: rks-research-output
description: "Use this skill when an agent should produce directly consumable research outputs from the local RKS graph: answer a question, brief a topic, surface disagreements, or suggest evidence-backed research opportunities."
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

Surface disagreements (enriched with evolution conflict clusters):

```bash
rks output disagreements "<topic>"
rks output project-disagreements <project_id>
```

Surface open questions (enriched with evolution evidence-gap signals):

```bash
rks output open-questions "<topic>"
rks output project-open-questions <project_id>
```

Surface review priorities (enriched with evolution-derived candidate rankings):

```bash
rks output review-priorities "<topic>"
rks output project-review-priorities <project_id>
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
curl -s "http://127.0.0.1:8765/api/output/open-questions?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/review-priorities?topic=<encoded-topic>"
curl -s "http://127.0.0.1:8765/api/output/opportunities?topic=<encoded-topic>"
```

## Evolution Enrichment

The `disagreements`, `open-questions`, and `review-priorities` output surfaces are **evolution-enriched**:

- `disagreements` response includes `conflict_clusters`: active conflict clusters from the evolution layer (top 5 by concept)
- `open-questions` response includes `evolution_questions`: evidence-gap signals detected from the evolution layer (up to 5 entries)
- `review-priorities` response includes `evolution_priorities`: pending candidates ranked by a five-factor score

**`evolution_questions` signal types:**

| type | meaning |
|------|---------|
| `evidence_sparse_controversy` | controversy score > 0.3 with ≤ 5 claims — needs more evidence |
| `trend_shift` | concept consensus shifted > 0.3 across snapshots — investigate direction |
| `unsupported_hypothesis` | a project hypothesis has no supporting evidence links yet |
| `unreviewed_conflict_cluster` | conflict cluster where no member relation has been reviewed |
| `hypothesis_concept_divergence` | hypothesis trend contradicts its concept's timeline trend |

**`evolution_priorities` scoring factors** (sum to 1.0):

| factor | weight | meaning |
|--------|--------|---------|
| `candidate_score` | 0.25 | inference confidence |
| `controversy` | 0.25 | concept controversy score |
| `hypothesis_relevant` | 0.25 | claim linked to a project hypothesis |
| `recency` | 0.15 | paper published 2022+ |
| `cluster_member` | 0.10 | claim is in an active conflict cluster |

These evolution fields supplement the heuristic output — report both layers to the user when present.

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
