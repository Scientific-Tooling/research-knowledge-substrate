---
name: rks-paper-discussion
description: Use this skill when an agent should discuss one paper with a user by grounding every answer in RKS evidence and writing discussion outcomes back through CLI.
---

# RKS Paper Discussion

Use this skill when the user wants to discuss a specific paper with an agent, and RKS should be the evidence source plus memory sink.

## Hard Constraint

- `rks` CLI is the only external interface.
- Do not require MCP, direct DB access, or ad hoc filesystem parsing.

## Trigger

Use this skill for requests such as:

- discuss this paper with me
- summarize and critique paper `<paper_id>`
- find related evidence for this paper and answer my questions
- persist our discussion notes into RKS

## Discussion Protocol (Read -> Search -> Write-Back)

### 1. Resolve Anchor Paper

If the user already gives a `paper_id`, use it directly.

Otherwise resolve it:

```bash
rks search "<title/keyword>"
rks show paper <paper_id>
```

Never guess IDs; always parse from command output.

### 2. Build Evidence Context

Load the paper context:

```bash
rks show paper <paper_id>
rks status paper <paper_id>
rks claims <paper_id>
rks concepts <paper_id>
rks methods <paper_id>
rks datasets <paper_id>
rks note list paper <paper_id>
```

If `status` shows missing extraction stages, complete them before deep discussion:

```bash
rks extract text <paper_id>
rks extract claims <paper_id>
rks extract methods <paper_id>
rks extract datasets <paper_id>
rks summarize paper <paper_id>
```

### 3. Expand Related Evidence For User Questions

For each key concept or claim that appears in discussion:

```bash
rks query claims-about <concept_or_concept_id>
rks query papers-supporting <claim_id>
rks query claim-relations <claim_id>
rks query evidence-for <concept_or_claim_id>
rks search "<follow-up query>"
```

When synthesis is requested, use output-layer surfaces:

```bash
rks output answer "<question>"
rks output brief "<topic>"
rks output disagreements "<topic>"
rks output open-questions "<topic>"
rks output review-priorities "<topic>"
```

### 4. Grounded Reply Discipline

Every substantive answer should cite at least one of:

- `claim_id`
- `paper_id`
- relation evidence from `claim-relations`

Always separate:

- grounded findings
- uncertainty or disagreement
- recommended next steps

Do not present `inferred_relations` as durable truth.

### 5. Write Back Discussion Outcomes

Persist user-relevant conclusions as notes:

```bash
rks note add paper <paper_id> --content "<summary or action item>" --created-by agent:discussion
rks note list paper <paper_id>
```

If the user discussion is project-scoped, persist to project/hypothesis:

```bash
rks note add project <project_id> --content "<discussion decision>" --created-by agent:discussion
rks hypothesis create <project_id> --text "<testable hypothesis>" --status draft --created-by agent:discussion
rks hypothesis add-evidence <hypothesis_id> claim <claim_id> --relation-type supported_by --created-by agent:discussion
```

Promote or retract claim relations only in explicit review mode:

```bash
rks query claim-relations <source_claim_id>
rks review promote-claim-relation <source_claim_id> <supports|refines|contradicts> <target_claim_id> --reviewed-by agent:review --note "<why>"
```

## Output Contract To User

After each major discussion step, report:

1. anchor paper and IDs used
2. evidence used (`claim_id`, `paper_id`, relation type)
3. unresolved questions or contradictions
4. what was written back to RKS

## Failure Handling

- If a read command fails, verify ID existence via `rks show`/`rks search` before retry.
- If extraction artifacts are missing, run extraction commands instead of inventing context.
- If a write fails, do not assume success; re-read with the corresponding list/show command.
