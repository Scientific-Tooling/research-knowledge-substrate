---
name: rks-maintain-worktree
description: Use this skill when updating the RKS codebase itself so the agent follows the repository's delivery discipline: keep docs current, run verification, and commit coherent milestones.
---

# RKS Maintain Worktree

Use this skill when modifying the RKS repository itself rather than operating the already-built CLI.

## Trigger

Use this skill for tasks such as:

- implement an RKS feature
- refactor the extraction pipeline
- add a new query or reasoning task
- update the dual-track contract
- improve tests or documentation

## Working Rules

When making code changes:

1. update the most relevant docs in the same pass
2. run local verification before closing the work
3. commit coherent milestones instead of leaving large uncommitted batches

## Minimum Verification

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

If the change affects CLI shape, also inspect:

```bash
.venv/bin/rks --help
```

## Documentation Targets

Update whichever of these applies:

- `README.md`
- `docs/progress.md`
- `docs/mvp-status.md`
- `docs/dual-track-llm-contract.md`
- `docs/implementation-plan.md`

## Commit Discipline

Prefer commits that correspond to one meaningful milestone, for example:

- new extraction mode
- new query surface
- artifact stability improvement
- documentation/status update

Do not mix unrelated repository cleanup into the same commit unless it is required for the milestone.
