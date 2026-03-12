---
name: rks-query-substrate
description: Use this skill when the task is to inspect, search, query, or reason over papers, claims, concepts, summaries, and evidence already stored in the local RKS graph.
---

# RKS Query Substrate

Use this skill when an agent needs to answer questions from the current local RKS graph instead of ingesting new material.

## Trigger

Use this skill for requests such as:

- what claims do we have about X
- which papers support this claim
- summarize this paper from stored evidence
- inspect the evidence trail for this claim
- search the local research graph

## Core Commands

Inspect one paper:

```bash
rks show paper <paper_id>
```

Inspect one claim:

```bash
rks show claim <claim_id>
```

List claims for a paper:

```bash
rks claims <paper_id>
```

List concepts for a paper:

```bash
rks concepts <paper_id>
```

Run local lexical search:

```bash
rks search <query>
```

Run deterministic graph queries:

```bash
rks query claims-about <concept>
rks query papers-supporting <claim_id>
rks query claim-relations <claim_id>
```

Generate a summary:

```bash
rks summarize paper <paper_id>
```

## Recommended Query Order

For ambiguous research questions, prefer:

1. `rks search <query>`
2. `rks query claims-about <concept>`
3. `rks show claim <claim_id>` for evidence validation
4. `rks query claim-relations <claim_id>` when relationship structure matters
5. `rks summarize paper <paper_id>` if a concise synthesis is needed

## Claim Relation Discipline

`rks query claim-relations <claim_id>` returns two layers:

- `inferred_relations`: query-time candidates
- `reviewed_relations`: durable graph facts promoted by an agent or human

Do not report inferred relations as durable truth.

If the task is to modify relation state rather than inspect it, switch to `rks-agent-operations` or `rks-codex-operator`.

## Evidence Discipline

When reporting an answer back to the user:

- prefer claim IDs and paper IDs over paraphrased memory
- inspect `rks show claim <claim_id>` before asserting support
- distinguish `reviewed_relations` from `inferred_relations` when discussing claim-to-claim structure
- treat summary outputs as convenience artifacts, not stronger evidence than claims

## Important Constraints

- This skill is for already-ingested graph data
- If the answer requires missing papers or missing claims, switch to `rks-build-paper-graph`
