# Revision-bound comparisons (unreleased)

Schema migration 0015 adds native append-only comparisons, content versions,
human review records and idempotent request receipts. Comparisons assemble selected
external evidence; they do not create graph claims or change imported review status.

All operations require `--workspace-id`, `--source-id` and repeated
`--paper-source PAPER_ID:DOCUMENT_SHA256`. The caller supplies its exact project
scope. Namespaces, canonical paper resolution, source hashes, current note content
and selected evidence revisions are validated inside the transaction.

- `rks comparison list` returns definitions within that scope.
- `rks comparison evidence` returns current scoped imported records with availability.
- `rks comparison show ID [--history]` returns the matrix and review history.
- `rks comparison apply REQUEST.json` performs a create, set or review transaction.

Append scope flags to each command. Reads use `connect_db_readonly` and an explicit
read transaction. Writes open an existing database in `mode=rw` and require prior
explicit `rks migrate`; they own `BEGIN IMMEDIATE`, CAS, append history, receipt and
commit/rollback. Graph snapshots and workspace backups preserve all four tables.

The strict `rks.comparison-request.v1` envelope has `request_id` (32 lowercase hex
UUID), `action`, `comparison_id`, `expected_revision`, and `payload`. Create uses
null comparison/revision and payload `title`, `question`, `criteria` (1–20 unique
nonblank strings). Its fixed paper set is the supplied scope; criteria receive
stable IDs `c1`, `c2`, etc. Other actions require a current `show` revision:

- `set`: `paper_source`, `criterion_id`, `text`, `conditions`, `origin` (`human` or
  `agent`), `evidence` (explicit `{note_id, revision}` records from this paper).
- `review`: `paper_source`, `criterion_id`, `reviewer`, `scope`, `decision`
  (`accepted` or `needs_changes`), `statement`. The caller must supply a real,
  authorized human assertion. Identity strings are not authenticated credentials.

The result contains `replayed` and `comparison` (`rks.comparison.v1`). Exact request
replay under unchanged scope returns the current comparison without appending
another version or review. Reusing a request ID with changed content/scope fails.

Each cell retains immutable evidence records, interpretation and conditions.
Blank interpretations are gaps; nonblank text lacking a source quote is unsupported.
Changed or unavailable evidence is stale. Only entries linked to current quoted
evidence can be accepted. Reviews retain cell/evidence revisions, human scope,
statement, decision and server timestamp. Every subsequent edit to that cell
invalidates its older review, even when text is restored to an earlier value.
Other cells' edits do not invalidate an unchanged cell. History is retained.

RKS verifies retained document bytes and native note/evidence consistency. APW
owns annotation resolution; an embedding workflow must also check those passages.
The sci adapter does so before acceptance and when rendering. A link is a
traceability assertion, not a scientific endorsement. Domain validation remains
an independent acceptance gate; tests use synthetic reviewer identities only.
