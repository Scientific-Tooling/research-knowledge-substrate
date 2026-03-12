# MVP Progress

## Current Status

The repository now has a working local MVP spine:

- local SQLite initialization
- PDF ingestion into stable paper IDs
- metadata and extracted text artifacts on disk
- heuristic structured claim extraction
- concept normalization and persistence
- graph edge persistence for `contains`, `supported_by`, and `about`
- deterministic CLI queries for `claims-about` and `papers-supporting`

## Implemented Milestones

- Milestone 0: project skeleton
- Milestone 1: paper ingestion and inspection
- Milestone 2: extracted text artifacts and claim persistence
- Milestone 3: concept linking and edge persistence
- Milestone 4: first deterministic query templates

## Remaining Work

- improve PDF text extraction beyond the current fallback chain
- harden DOI and arXiv ingestion against network and metadata edge cases
- improve claim parsing quality and context extraction
- add more query templates and evidence summaries
- add better fixtures for realistic paper text

## Latest Architectural Direction

The MVP remains intentionally local and inspectable.

Every ingestion flow should create filesystem artifacts first, then persist structured rows and graph edges. This keeps the debugging surface visible and avoids hiding extraction failures inside opaque database state.
