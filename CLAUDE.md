# RKS Claude Code Instructions

This workspace includes exported RKS skill markdown files under `./agent-kit/skills`.

Suggested usage:

- Match the user task to one or more skills in this bundle.
- Read only the needed `SKILL.md` files before acting.
- Treat the skill text as repository-specific operating instructions.
- Prefer `rks` CLI commands first, then use HTTP when the skill explicitly asks for a cross-check.
- **Confirmation rule**: never create a research object (paper, project, hypothesis, concept, etc.) as a side effect of another operation. If fulfilling a request requires an object that does not yet exist, report the missing object to the user and ask for explicit permission before creating it.

Available skills:

- `rks-agent-operations`: Use this skill when an agent needs to run repeated RKS workflows, inspect queued work, recover from failures, or audit extraction status across papers.
  - `./agent-kit/skills/rks-agent-operations/SKILL.md`
- `rks-autotest`: Use this skill when an agent should automatically validate RKS behavior as a product surface: set up a workspace, run repeatable CLI and HTTP checks, verify artifacts and IDs, and report failures with concrete reproduction steps.
  - `./agent-kit/skills/rks-autotest/SKILL.md`
- `rks-build-paper-graph`: Use this skill when the task is to ingest a paper or reference into RKS, run extraction, build claims/concepts/edges, and leave the paper in a queryable graph state.
  - `./agent-kit/skills/rks-build-paper-graph/SKILL.md`
- `rks-codex-operator`: Use this skill when Codex itself should act as the external agent operating RKS end-to-end through CLI and HTTP: ingesting sources, validating artifacts, driving review flows, and checking agent-facing product behavior.
  - `./agent-kit/skills/rks-codex-operator/SKILL.md`
- `rks-dual-track-llm`: Use this skill when a task involves any LLM-backed RKS operation and you need to choose or execute the correct dual-track mode: llm-api or agent.
  - `./agent-kit/skills/rks-dual-track-llm/SKILL.md`
- `rks-maintain-worktree`: Use this skill when updating the RKS codebase itself so the agent follows the repository's delivery discipline: keep docs current, run verification, and commit coherent milestones.
  - `./agent-kit/skills/rks-maintain-worktree/SKILL.md`
- `rks-paper-discussion`: Use this skill when an agent should discuss one paper with a user by grounding every answer in RKS evidence and writing discussion outcomes back through CLI.
  - `./agent-kit/skills/rks-paper-discussion/SKILL.md`
- `rks-query-substrate`: Use this skill when the task is to inspect, search, query, or reason over papers, claims, concepts, summaries, and evidence already stored in the local RKS graph.
  - `./agent-kit/skills/rks-query-substrate/SKILL.md`
- `rks-research-output`: Use this skill when an agent should produce directly consumable research outputs from the local RKS graph: answer a question, brief a topic, surface disagreements, or suggest evidence-backed research opportunities.
  - `./agent-kit/skills/rks-research-output/SKILL.md`
- `rks-user-demo`: Use this skill when an agent should demonstrate RKS to a user end-to-end: preparing a small workspace, ingesting a paper or reference, showing graph outputs, and narrating the product behavior in a clear sequence.
  - `./agent-kit/skills/rks-user-demo/SKILL.md`
