# Release Tracking

This document tracks work since the latest release tag so it is clear when to cut the next tag.

## Baseline

- Last release tag: `v0.2.0`
- Release tag commit: `97bb275` (2026-03-22)
- Current `HEAD`: `97bb275` (2026-03-22)

## Delta Since `v0.2.0`

- Commit count: 3 (+ 1 pending commit)
- Diff summary: 18 files changed, 620 insertions(+), 78 deletions(-) (pending additions not yet counted)

## Work Log

| Date | Commit | Type | Summary | Release Impact |
| --- | --- | --- | --- | --- |
| 2026-03-19 | `6ec827c` | docs | Added GitHub ZIP download installation path in EN/ZH install guides. | Documentation only; does not require release alone. |
| 2026-03-20 | `27ecb46` | feature | Added `rks stats`, `rks papers list/mark/unmark/tags/read-later`, new `paper_tags` table, and `reading_status` schema support. Updated docs/skills/tests. | User-facing CLI features plus schema migrations; strong release signal. |
| 2026-03-20 | `5b586b7` | fix | Made migration flow resilient when `papers.reading_status` exists but migration history is missing. Added regression test. | Stability fix for migration path; release-worthy with the feature set above. |
| 2026-03-21 | `ea1e555` | feature | Added `rks papers find-duplicates` (`heuristic` / `identifiers`) and first-class `rks papers merge`. Re-homing logic now consolidates notes, links, tags, tasks, and paper-scoped references; docs and tests updated (EN/ZH). | User-facing paper-management capability expansion; strengthens `v0.2.0` release signal. |
| 2026-03-21 | `8fad606` | feature | Added `rks init <path>` and global config at `~/.rks/config.json`. Data directory is now globally configured so `rks` works from any directory. Replaced CWD-based root fallback with explicit `ConfigError`. Added `rks config set data-dir`. Updated all EN/ZH docs. | User-facing usability fix; `rks` is now truly portable across directories. |
| 2026-03-21 | (unreleased) | feature | Implemented full AI extraction pipeline: fixed citation stubs polluting papers list; added `methods.v1` / `datasets.v1` schemas; LLM+agent paths for methods/datasets; `claims.v2` with `context.section`, `context.dataset`, `evidence.quote`; `auto_extract_mode` config field (`none`/`heuristic`/`llm-api`/`llm-api-combined`/`agent`); `run_post_ingest_pipeline` auto-triggered after each ingest; `paper.v1` single-pass combined extraction (`rks extract all`, `rks import all`, `llm-api-combined` mode). | Major LLM extraction capability expansion; included in `v0.2.0`. |
| 2026-03-21 | (unreleased) | fix | Fixed test isolation: all `run_cli` helpers now set `RKS_DATA_DIR=cwd` so tests use a throwaway DB instead of the user's production database. Also fixed hardcoded DB path in migration resilience test. | Bug fix; prevents test runs from polluting the user's real data. |
| 2026-03-21 | (unreleased) | fix+feature | Removed workspace-level `rks.json` / `RKS_ROOT` env var — `~/.rks/config.json` is now the single config location. Added `rks clear [--yes]` to wipe all papers, artifacts, and the database while preserving global config. Timestamps now display in local time with UTC offset instead of bare UTC. | Simplification + new maintenance command. |
| 2026-03-21 | `0abd310` | docs | Added confirmation rule to agent skills: agents must never auto-create a research object (paper, project, hypothesis, etc.) as a side effect of another operation — they must stop and ask the user first. Rule added globally to exported `AGENTS.md`/`CLAUDE.md` and explicitly to `rks-paper-discussion`, `rks-codex-operator`, and `rks-agent-operations`. | Documentation/behavior constraint; no release required alone. |
| 2026-03-22 | (unreleased) | fix+feature | Structured JSON errors from CLI (`config_error`, `internal_error` to stderr); added `rks tasks wait <task_id> [--timeout] [--interval]` to block until task completes instead of requiring agent polling loops. Updated agent-usage guide (EN/ZH) and skill bundle. | Agent-facing reliability improvement; no schema change. |
| 2026-03-22 | `e871ad0` | feature | Added `rks evaluate claims <paper_id> --golden <path> [--min-f1 N]` command with token-set Jaccard precision/recall/F1. Added `tests/test_e2e_pipeline.py` covering full agent-mode pipeline: ingest → import text → import claims → query → output answer → evaluate claims. CI-safe (no API key required). | Roadmap Phase 1 P0 feature; strong signal toward `v0.3.0`. |
| 2026-03-22 | `0db7317` | feature | Refined `rks evaluate claims` command and `_evaluate_claims_against_golden` in `cli/_context.py`; exit 0/1 based on F1 threshold for CI gate use. | Complements `e871ad0`; included in same release signal. |
| 2026-03-23 | `af37789` | fix | Fixed 19 broken tests after heuristic extraction removal and global-config migration: replaced heuristic-mode calls with `import` + agent-mode fixtures; wrapped dispatch calls with `RKS_DATA_DIR` env isolation; updated stale assertions for doctor, datasets schema, and sparse output. | Test stability fix; no user-facing behavior change. |
| 2026-03-23 | (unreleased) | feature | Added `tests/test_claim_quality_regression.py` — auto-discovers golden files in `tests/golden/`, sets up paper fixtures, and gates CI on F1 threshold per paper. Added `tests/golden/sample_transformer_paper.json` as the first golden entry (synthetic fixture, min_f1=0.5). Added `docs/evaluation-methodology.md` documenting the golden-set format, metrics, annotation workflow, and CI wiring. | Completes roadmap Phase 1 P0-1 (CI regression + methodology docs); included in `v0.3.0` signal. |
| 2026-03-24 | (unreleased) | feature | Annotated first real-paper golden set: `tests/golden/globocan_2020.json` (Sung et al. 2021, GLOBOCAN 2020; 13 claims, min_f1=0.75). Registered matching fixture in `test_claim_quality_regression.py`. Baseline F1=0.788 (precision 0.65, recall 1.0) using agent-mode extraction. Updated evaluation-methodology baseline table. Ingested paper as `p_000001` with 20 extracted claims and 38 concepts. | Advances roadmap Phase 1 P0-1 (real-paper golden annotation); partial progress toward 5–10 paper target. |

## Release Decision Rules

Use this quick rubric after each merge:

1. If there are user-facing CLI/API features, prefer a new minor tag (`vX.Y.0`).
2. If schema migrations are added, prefer a new minor tag and call out migration notes.
3. If only docs or internal refactors changed, no new tag is required.
4. If only backward-compatible bug fixes changed, prefer a patch tag (`vX.Y.Z`).

## Current Recommendation

- `v0.3.0` when Phase 1 P0 is complete (golden set annotated + CI regression wired). The `rks evaluate claims` command and E2E pipeline test from `e871ad0`/`0db7317` are user-facing features that qualify for a minor bump. The `af37789` test fix can be bundled in the same tag.

## How To Update This File

Run these commands and refresh the sections above:

```bash
git log --date=short --pretty=format:'%h|%ad|%s' v0.2.0..HEAD
git diff --shortstat v0.2.0..HEAD
```

After creating the next release tag, reset the baseline section to that new tag.
