# Research Output Roadmap

This roadmap turns RKS from a substrate that mainly absorbs and structures research material into a system that also produces useful research outputs for users and agents.

The product goal is not only:

- ingest
- extract
- persist
- inspect

It is also:

- answer questions
- synthesize a topic
- expose disagreements
- suggest research opportunities
- recommend next actions

## Principles

- Optimize for outputs a user can consume directly, not just internal graph state.
- Keep every output grounded in claim IDs, paper IDs, and artifact-backed evidence.
- Separate durable reviewed facts from query-time inference in all output surfaces.
- Prefer deterministic, inspectable output templates before adding freer-form orchestration.

## Priority 0: Direct Research Outputs

- [x] Add a direct research answer surface for user questions.
- [x] Add a topic briefing surface that summarizes papers, claims, methods, and datasets around a theme.
- [x] Return grounded citations and uncertainties in both outputs.
- [x] Expose the outputs through both CLI and HTTP.

Exit criteria:

- A user can ask a research question and receive a grounded answer summary.
- A user can request a topic brief and receive a structured synthesis.
- Both outputs include evidence objects, not just prose.

## Priority 1: Disagreement and Inspiration Outputs

- [x] Add an output surface for contradictions and disagreements around a topic.
- [x] Add an output surface for research opportunities and next-step guidance.
- [x] Base opportunity suggestions on graph evidence such as contradictions, sparse method-dataset coverage, or missing extracted structure.
- [x] Keep suggestions auditable by linking back to claims, methods, datasets, and papers.

Exit criteria:

- A user can inspect topic-level disagreements without manually traversing claims one by one.
- A user can ask for research opportunities and receive concrete, evidence-backed next steps.
- Suggestions are explainable from current graph structure and not presented as unsupported free-form brainstorming.

## Priority 2: Product Integration

- [x] Route output logic through the operations layer instead of duplicating logic in CLI and HTTP.
- [x] Add user-facing usage documentation for the new output surfaces.
- [x] Add automated tests for answer, brief, disagreement, and opportunity outputs.

Exit criteria:

- CLI and HTTP expose the same output semantics.
- Tests cover the new output layer end to end.
- Usage docs explain how users and agents should consume these outputs.

## Non-Priorities

- Rich frontend dashboards for these outputs.
- Fully autonomous multi-agent research planning.
- Unbounded creative generation without graph grounding.
