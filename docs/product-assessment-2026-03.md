# RKS Product Assessment (2026-03-29)

## Executive Summary

RKS is a technically excellent project that has not yet validated product-market fit. The architecture, code quality, and engineering discipline are genuinely impressive. But product success requires users, and every signal says the project has optimized for building over shipping. The gap between "feature-complete Alpha" and "useful to anyone" is not more code -- it is contact with reality.

---

## What We Did Right

### 1. Architecture is genuinely excellent

The local-first, agent-first, evidence-grounded design is clean and principled. The system constraints document (`docs/system-constraints.md`) is the best piece of product thinking in the repo -- it defines what RKS *is not*, which is harder than defining what it is. Few solo projects have this level of architectural discipline.

### 2. Dual-track LLM is a real insight

Separating "call the LLM directly" (`llm-api`) from "ask an external agent to do LLM work" (`agent`) is forward-thinking. Most tools assume one or the other. This design means RKS can be operated by Claude Code, Codex, or a human with an API key -- genuinely flexible.

### 3. Artifact-first extraction is the right call

Writing files to disk before touching the database means every operation is inspectable and debuggable. This is the kind of decision that pays compound interest during development.

### 4. Development discipline is high

Conventional commits, CI with smoke tests, schema migrations, golden set regression, 126 tests. The codebase is well-maintained by any standard.

### 5. The confirmation rule is smart product design

"Never create a research object as a side effect" prevents the knowledge graph from being polluted by accidental agent operations. This shows understanding of the failure mode of agent-operated systems.

---

## What Is Wrong

### 1. Zero users, not acting like it

This is the fundamental problem. The project has 17K lines of source, 47 docs, 10 agent skills, bilingual documentation, PyPI publishing, a CI/CD pipeline -- and no evidence that anyone besides the developer has ever used it. Every hour spent on bilingual docs, skill exports, and PyPI packaging is an hour not spent finding out if the core idea works for real people.

The project has symptoms of **building to avoid shipping**: adding more features, more documentation, more infrastructure, because that feels productive. But the hardest question -- "does anyone need this?" -- remains unanswered.

**Evidence**:
- No GitHub issues from external users
- No deployment case studies or testimonials
- No usage analytics or telemetry
- No user onboarding documentation that targets actual researchers (vs. developers)

### 2. God object in the operations layer

`ResearchOperations` in `src/rks/operations/service.py` is 3,313 lines with 126+ methods. It is imported everywhere and does everything from paper ingestion to concept merging to hypothesis evolution to batch audit summaries. This is the classic sign of feature accretion without refactoring. The architecture has lost its layered discipline at the most important layer.

### 3. The hard problem is being avoided

The *entire value proposition* of RKS is: "ingest papers -> extract structured claims -> build a queryable knowledge graph." The extraction quality determines whether the graph is useful or garbage. Yet after 96 commits, there are exactly **2 golden papers** (one synthetic, one real at F1=0.788). The roadmap says "5-10 papers" as a target.

For a product whose value is extraction quality, this is the thing that should have 50 papers, not 2.

Meanwhile, 47 different reasoning output generators exist in `reasoning/output.py`. Output quality is *downstream* of extraction quality. If the claims are wrong, every brief/disagreement/opportunity built on them is wrong too.

### 4. Feature sprawl without validation

What exists today:
- 47 reasoning output generators
- 10 agent skills (with significant overlap: `codex-operator` vs `agent-operations` vs `autotest`)
- 18 CLI command modules
- Hypothesis evolution, conflict clustering, concept timelines, review priorities
- HTTP endpoints for all of the above
- Workspace export/import

How many of these are used regularly? Which ones deliver the most value? Unknown, because there are no users to provide signal. The project builds a Swiss Army knife when it should be proving the blade is sharp.

### 5. No onboarding path exists

A researcher who finds RKS on PyPI today faces: `pip install`, then what? There is no Docker "try in 5 minutes" path. No sample workspace with pre-ingested papers to explore. No web UI (the "lightweight web UI" mentioned in progress.md is a bare `ThreadingHTTPServer`). The manual testing guide is written for the developer, not a user.

The agent skills work -- if you already have Claude Code or Codex set up. But there is no path for the researcher who just wants to try it.

### 6. Documentation quantity != documentation effectiveness

47 markdown files, ~9,500 lines, English + Chinese. But:
- No quickstart that gets a user to "aha!" in under 3 minutes
- No architecture diagram (the text descriptions are good but not skimmable)
- The product introduction explains the philosophy before showing what it does
- Archived design docs in the tree create confusion about what is current

Docs are written for completeness. They need to be written for conversion.

### 7. Roadmap grows without external validation

The project has gone through 6 phases of internal milestones, and is now planning Phases 1-4 of a *new* roadmap. Each phase adds more capabilities. But no phase includes "get 5 real users" or "validate extraction quality on 20 diverse papers" or "measure task completion rate for a real research question."

The roadmap is engineering-driven, not user-driven.

---

## Quantitative Snapshot

| Metric | Value | Concern |
|--------|-------|---------|
| Source LoC | 17,502 | Large for zero users |
| Test count | 126 | Good coverage |
| Doc files | 47 (~9,500 LoC) | Over-documented relative to usage |
| Agent skills | 10 | Overlapping; consolidate to 3-4 |
| Golden papers | 2 (1 real) | Far too few for core value prop |
| Reasoning output funcs | 47 | Premature feature sprawl |
| `ResearchOperations` methods | 126+ (3,313 LoC) | God object; needs splitting |
| External users | 0 (evidenced) | Fundamental product risk |
| PyPI version | 0.2.0 | Alpha; no external adoption signal |

---

## Action Items

These are merged into the roadmap (`docs/roadmap-zh.md`) as Phase 0 priority items. See that document for task tracking.
