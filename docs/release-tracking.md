# Release Tracking

This document tracks work since the latest release tag so it is clear when to cut the next tag.

## Baseline

- Last release tag: `v0.1.0`
- Release tag commit: `c037ea7` (2026-03-19)
- Current `HEAD`: `8fad606` (2026-03-21)

## Delta Since `v0.1.0`

- Commit count: 7
- Diff summary: 51 files changed, ~2000+ insertions

## Work Log

| Date | Commit | Type | Summary | Release Impact |
| --- | --- | --- | --- | --- |
| 2026-03-19 | `6ec827c` | docs | Added GitHub ZIP download installation path in EN/ZH install guides. | Documentation only; does not require release alone. |
| 2026-03-20 | `27ecb46` | feature | Added `rks stats`, `rks papers list/mark/unmark/tags/read-later`, new `paper_tags` table, and `reading_status` schema support. Updated docs/skills/tests. | User-facing CLI features plus schema migrations; strong release signal. |
| 2026-03-20 | `5b586b7` | fix | Made migration flow resilient when `papers.reading_status` exists but migration history is missing. Added regression test. | Stability fix for migration path; release-worthy with the feature set above. |
| 2026-03-21 | `ea1e555` | feature | Added `rks papers find-duplicates` (`heuristic` / `identifiers`) and first-class `rks papers merge`. Re-homing logic now consolidates notes, links, tags, tasks, and paper-scoped references; docs and tests updated (EN/ZH). | User-facing paper-management capability expansion; strengthens `v0.2.0` release signal. |
| 2026-03-21 | `8fad606` | feature | Added `rks init <path>` and global config at `~/.rks/config.json`. Data directory is now globally configured so `rks` works from any directory. Replaced CWD-based root fallback with explicit `ConfigError`. Added `rks config set data-dir`. Updated all EN/ZH docs. | User-facing usability fix; `rks` is now truly portable across directories. |

## Release Decision Rules

Use this quick rubric after each merge:

1. If there are user-facing CLI/API features, prefer a new minor tag (`vX.Y.0`).
2. If schema migrations are added, prefer a new minor tag and call out migration notes.
3. If only docs or internal refactors changed, no new tag is required.
4. If only backward-compatible bug fixes changed, prefer a patch tag (`vX.Y.Z`).

## Current Recommendation

- Recommended next tag: `v0.2.0`
- Why:
  - New paper-management and stats commands are user-visible.
  - Duplicate detection and merge workflows are now first-class user surfaces.
  - New migrations (`0008`, `0009`) change storage schema.
  - A migration resilience fix is already included and tested.

## How To Update This File

Run these commands and refresh the sections above:

```bash
git log --date=short --pretty=format:'%h|%ad|%s' v0.1.0..HEAD
git diff --shortstat v0.1.0..HEAD
```

After creating the next release tag, reset the baseline section to that new tag.
