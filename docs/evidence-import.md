# Selected APW evidence import

RKS imports selected reading material as paper notes with structured provenance.
It does not promote annotations or machine interpretations into claims or reviewed
graph relations. The public boundary is the CLI; product behavior lives in
`operations/evidence_import.py`, and persistence in `storage/evidence_repository.py`.

## Preview and apply

Set `RKS_DATA_DIR` to the intended workspace. Upgrade an older database explicitly
with `rks migrate` (migration `0014_external_evidence.sql`). Neither preview nor
apply creates or migrates a database.

```bash
rks note import-evidence evidence.json --workspace-id review-a > plan.json
rks note import-evidence evidence.json --workspace-id review-a --apply --plan plan.json
rks note evidence p_000001
```

The default command is a read-only dry run. It reports proposed `addition`,
`unchanged`, and `conflict` items, their incoming/current revisions, canonical
paper IDs, and existing note IDs. Exit codes are 0 for a successful preview/apply,
2 for a conflict report on stdout, and 1 for an error on stderr. Preserve a conflict
report even though its exit status is nonzero.

Inspect the evidence bundle alongside the plan. An apply requires that exact
bundle and plan; a new export needs a new preview. Accepted imports report `added`,
`updated`, and `unchanged`. If any item has an unresolved conflict, no item changes.

To deliberately replace an imported revision, inspect both versions using
`rks note evidence`, generate a fresh plan, and add `--accept-updates` when applying.
This only accepts `revision_changed` conflicts. A changed database revision since
the preview produces `plan_stale`, requiring a new preview. Changed sources,
missing/retargeted notes, and local edits cannot be overridden by this flag.

## Version 1 contract

`scientific-tooling.selected-evidence.v1` is one selected batch for one paper and
one exact PDF. Unknown fields are rejected so new semantics require a new version.

| Field | Meaning |
| --- | --- |
| `schema` | `scientific-tooling.selected-evidence.v1` |
| `workspace_id` | Caller-managed RKS namespace; matches the explicit CLI argument |
| `paper_id` | Original RKS paper ID, such as `p_000001` |
| `source` | `system: apw`, caller-managed `source_id`, `paper_ref`, export `session_id` |
| `document` | Absolute local snapshot `path`, lowercase `sha256`, positive `size_bytes` |
| `exported_at` | Timestamp with timezone |
| `items` | Nonempty list of selected annotations and/or notes |

`paper_ref` is `rks:<workspace_id>:<paper_id>:sha256:<document.sha256>`.
The same `source_id` must follow an APW database through moves and restores. Use a
different source ID for an independent APW database. The first successful import
binds this RKS database to `workspace_id`; later mismatches fail. The caller must
select the correct database on the first import; these names are not a global
identity registry or an authentication mechanism.

Each item has exactly:

- `kind` (`annotation` or `note`) and `id` (the APW object's ID).
- `content`: normalized APW annotation or note payload, including its original
  `createdAt`/`updatedAt`. Annotation fields: `id`, `page`, `type`, `quote`, `anchor`,
  `comment`, `tags`, `rects`, `createdAt`, `updatedAt`. Note fields: `id`, `title`,
  `markdown`, `linkedAnnotationIds`, `createdAt`, `updatedAt`.
- `passages`: ordered `{annotation_id, page, quote, anchor, rects}` records. An
  annotation has its own passage; a note embeds every linked annotation's passage
  in link order. Unlinked notes have no passages and make no passage-level claim.
  Pages start at 1. Anchors are null or `{quote, start, end, prefix, suffix}`;
  offsets are nonnegative integers or null. Rectangles have finite numeric
  `x`, `y`, `width`, `height`, with nonnegative dimensions.
- `provenance`: last-writing APW `session_id`, database `created_at` and `updated_at`.
  This identifies the recorded session, not the human author or reviewer.
- `content_revision`, `review`, and `revision` as described below.

Hashes use SHA-256 over UTF-8 JSON serialized with sorted object keys, separators
`,` and `:`, ASCII escaping, and no non-finite numbers (`json.dumps(...,
sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`). Array
order and numeric representation are preserved.

`content_revision` hashes `{source_id, paper_ref, kind, id, content, passages}`.
`revision` hashes the entire item except its `revision` field, so changes to review
or recorded provenance also require an explicit update. The plan's
`bundle_revision` hashes the complete bundle, including export time and PDF path.

`review` defaults to `{"status":"unreviewed"}`. A human review has exactly
`status: reviewed`, `method: human`, nonempty `reviewer` and `statement`, a
`reviewed_at` timestamp with timezone, and the matching `content_revision`.
These are explicit caller assertions of an actual review, not identity-verified
signatures. Never manufacture them for an agent-generated interpretation. An edit
invalidates an older review. The imported note visibly labels review status;
the complete structured record and prior revisions remain inspectable separately.

## Identity, transactions, and changes

The unique external key is the canonical JSON array
`[workspace_id, source_id, original_paper_id, document_sha256, kind, id]`.
SQLite enforces this key and a unique associated RKS note. Note IDs, note contents,
current provenance, immutable revision history, workspace binding, and paper
timestamps commit in one `BEGIN IMMEDIATE` transaction. Readers use a read-only
connection and a consistent read transaction. A lost success response is safe to
retry: the already applied revision is unchanged even with the original plan.
An interruption rolls back the complete batch, including ID counters.

| Change | Behavior |
| --- | --- |
| Same identity and revision | Unchanged; no new note or timestamp update |
| Edited annotation/note, linked passage, or review | Conflict; explicit acceptance updates the same note and preserves prior revisions |
| APW annotation deleted, or omitted from selection | No RKS deletion; a newly selected missing object/link fails export |
| Changed PDF | New document identity; new/edited evidence must match the current RKS paper PDF |
| Current PDF replaced or unavailable after import | Exact historical replay is allowed if its retained snapshot still verifies; new/edited historical evidence is blocked |
| Corrupt/missing retained snapshot | Import fails; restore the exact bytes rather than substituting another PDF |
| Paper merged after migration 0014 | Redirects resolve the original paper ID, notes move with the merge, and original provenance/identity survives |
| Paper merged before redirect tracking existed | Missing original ID fails; resolve the historical mapping explicitly before re-exporting under a canonical paper |
| RKS note locally edited, removed, or retargeted | Conflict; no silent overwrite or recreation |

Both source and packaged migrations are distributed. Graph snapshots and workspace
archives include the evidence tables and merge redirects. APW snapshot files remain
external: retain them with APW backups and keep their paths accessible or explicitly
relocate the bundle and generate a fresh plan. RKS does not copy them on import.

This boundary verifies byte identity, contract consistency, and persistence. It
does not verify that a quote appears in a PDF, that a page exists, or that an
interpretation is scientifically sound. Passage rendering and scientific review
are separate steps.
