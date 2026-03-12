---
name: rks-agent-operations
description: Use this skill when an agent needs to run repeated RKS workflows, inspect queued work, recover from failures, or audit extraction status across papers.
---

# RKS Agent Operations

Use this skill when the task is to operate RKS as a repeatable agent workflow instead of performing a one-off extraction.

## Trigger

Use this skill for requests such as:

- ingest these papers in batch
- run extraction for a manifest of papers
- check which agent requests are still queued
- mark an agent task as failed
- inspect extraction status for a paper

## Core Commands

Batch ingest:

```bash
rks batch ingest manifest.json
```

Batch extraction:

```bash
rks batch extract claims manifest.json
rks batch extract summary manifest.json --mode agent
```

Inspect the task queue:

```bash
rks tasks list
rks tasks list --paper-id <paper_id>
rks tasks show <task_id>
```

Record a task failure:

```bash
rks tasks fail <task_id> "reason"
```

Inspect paper workflow status:

```bash
rks status paper <paper_id>
```

## Agent Mode Discipline

When using `--mode agent`, do not stop at the request artifact. Confirm that:

1. the returned payload includes a `task_id`
2. the task is visible through `rks tasks show <task_id>`
3. the result import transitions the task to `completed`, or explicitly mark it `failed`

## Expected Outcome

A healthy paper or batch run should have:

- explicit queued/completed/failed task records
- visible artifact stage status
- no hidden failures outside the task table
