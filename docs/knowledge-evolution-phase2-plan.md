# Knowledge Evolution Phase 2 — Implementation Plan

## Overview

Phase 2 builds on the existing candidate-relation, evolution-event, and snapshot infrastructure to add:
1. Conflict clustering
2. Consensus/controversy scoring
3. Time-bucketed trend analysis
4. Discovery engine driven by evolution structure
5. Project-scoped evolution tracking

## Implementation Order

```
Step 1: Schema migration + domain models + repositories + ID prefix fixes
Step 2: Consensus/controversy scoring (extends build_concept_timeline)
Step 3: Time-bucketed trend analysis (yearly grouping by paper year)
Step 4: Conflict clustering (connected-component on contradicts edges)
Step 5: Discovery engine (review priority scoring, open-question detection)
Step 6: Project-scoped evolution (aggregate evolution data through project lens)
```

Dependencies: Step 2 → Step 3 → Step 5; Step 4 → Step 5; Steps 1-5 → Step 6.

---

## Step 1: Schema & Infrastructure

### Migration `0007_conflict_clusters_and_timeline_enhancements.sql`

```sql
-- Conflict cluster tables
CREATE TABLE IF NOT EXISTS claim_conflict_clusters (
    id TEXT PRIMARY KEY,
    anchor_concept_id TEXT NOT NULL,
    topic_label TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    summary_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_conflict_cluster_members (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    stance TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conflict_clusters_concept ON claim_conflict_clusters(anchor_concept_id, status);
CREATE INDEX IF NOT EXISTS idx_conflict_cluster_members_cluster ON claim_conflict_cluster_members(cluster_id);
CREATE INDEX IF NOT EXISTS idx_conflict_cluster_members_claim ON claim_conflict_cluster_members(claim_id);

-- Extend timeline snapshots
ALTER TABLE concept_timeline_snapshots ADD COLUMN time_bucket TEXT;
ALTER TABLE concept_timeline_snapshots ADD COLUMN refine_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE concept_timeline_snapshots ADD COLUMN consensus_score REAL;
ALTER TABLE concept_timeline_snapshots ADD COLUMN controversy_score REAL;
ALTER TABLE concept_timeline_snapshots ADD COLUMN basis_layer TEXT NOT NULL DEFAULT 'reviewed';
```

### Domain models (models.py)

- New: `ClaimConflictClusterRecord(id, anchor_concept_id, topic_label, status, summary_json, created_at, updated_at)`
- New: `ClaimConflictClusterMemberRecord(id, cluster_id, claim_id, role, stance, confidence, created_at)`
- Extend `ConceptTimelineSnapshotRecord`: add `time_bucket`, `refine_count`, `consensus_score`, `controversy_score`, `basis_layer`

### ID prefixes (ids.py)

Register: `concept_timeline_snapshot` → `cts`, `claim_conflict_cluster` → `cc`, `claim_conflict_cluster_member` → `ccm`

> **Bug fix**: `concept_timeline_snapshot` prefix is currently missing — `create_snapshot` will crash without it.

### New repository: `conflict_cluster_repository.py`

Methods: `create_cluster`, `add_member`, `get_cluster`, `list_clusters_for_concept`, `list_members_for_cluster`, `update_cluster_status`

---

## Step 2: Consensus/Controversy Scoring

Formulas (from design doc):
```
consensus_score = support_count / max(1, support_count + contradiction_count)
controversy_score = min(support_count, contradiction_count) / max(1, support_count + contradiction_count)
```

- Extend `build_concept_timeline` in operations/service.py to compute and store these scores
- Count `refine_count` from edges with `relation_type == "refines"`
- Store `basis_layer = "reviewed"`
- Update `evolution_repository.create_snapshot` to persist new columns

---

## Step 3: Time-Bucketed Trend Analysis

New method: `build_concept_timeline_bucketed(concept_id, bucket_size="yearly")`

Algorithm:
1. Fetch all claims for concept
2. Look up paper year for each claim
3. Group claims by year
4. For each bucket: count supports/contradicts/refines edges, compute scores
5. Create one snapshot row per bucket with `time_bucket = "2023"` etc.
6. Record evolution event

> Quarterly bucketing deferred — papers only have `year`, no month.

---

## Step 4: Conflict Clustering

New method: `cluster_claim_conflicts(concept_id=None)`

Algorithm:
1. For each concept, fetch claims and find all `contradicts` edges among them
2. Build graph, find connected components → each = one cluster
3. Create `ClaimConflictCluster` per component
4. Create members with stance assignment (majority = "mainstream", minority = "dissenting")
5. Record evolution events

---

## Step 5: Discovery Engine

New method: `compute_review_priorities(scope_type="concept", scope_id=None)`

Priority score:
```
priority = (candidate.score * 0.3
          + concept_controversy_score * 0.25
          + hypothesis_relevance * 0.25
          + recency_bonus * 0.2)
```

New method: `compute_open_questions(scope_type="concept", scope_id=None)`

Identifies: evidence-sparse controversies, recent trend shifts, conflicting hypothesis evidence.

---

## Step 6: Project-Scoped Evolution

New methods:
- `project_evolution_summary(project_id)` — aggregates timelines, clusters, candidates, hypothesis evolution
- `project_evolution_timeline(project_id, bucket_size="yearly")` — composite timeline across project concepts

---

## CLI Commands

```
rks evolve cluster-claim-conflicts [--concept-id <ID>]
rks evolve build-concept-timelines [--concept-id <ID>] [--bucket-size yearly]
rks query concept-consensus <concept_id>
rks query concept-controversies [--min-score <FLOAT>]
rks query review-priorities [--concept <ID>] [--project <ID>]
rks query open-questions [--concept <ID>] [--project <ID>]
rks query project-evolution <project_id>
```

## HTTP Endpoints

```
POST /api/evolution/cluster-conflicts
GET  /api/evolution/conflict-clusters/<concept_id>
POST /api/evolution/build-timeline/<concept_id>?bucket_size=yearly
GET  /api/evolution/concept-consensus/<concept_id>
GET  /api/evolution/concept-controversies
GET  /api/query/review-priorities
GET  /api/query/open-questions
GET  /api/evolution/project/<project_id>
```

## Test Plan

- Scoring formula tests (edge cases: all-support, all-contradict, equal split, zero)
- Time-bucketed timeline tests (grouping, per-bucket counts and scores)
- Conflict clustering tests (connected components, stance assignment, no-contradictions case)
- Discovery engine tests (priority ranking, open-question detection)
- Project-scoped evolution tests (scope filtering, aggregation)
- Migration test update for `0007`
