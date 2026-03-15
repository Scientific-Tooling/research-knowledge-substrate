from __future__ import annotations

import json
from pathlib import Path

from rks.utils import utc_now


TABLES = [
    "counters",
    "research_projects",
    "project_links",
    "hypotheses",
    "hypothesis_evidence_links",
    "papers",
    "claims",
    "methods",
    "datasets",
    "concepts",
    "notes",
    "edges",
    "artifacts",
    "embeddings",
    "tasks",
    "claim_relation_candidates",
    "evolution_events",
    "concept_timeline_snapshots",
    "claim_conflict_clusters",
    "claim_conflict_cluster_members",
]


def export_graph_snapshot(conn, destination: Path) -> dict:
    payload = {
        "version": "graph_snapshot.v1",
        "exported_at": utc_now(),
        "tables": {
            table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
            for table in TABLES
        },
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"path": str(destination), "table_counts": {table: len(rows) for table, rows in payload["tables"].items()}}


def import_graph_snapshot(conn, snapshot_path: Path) -> dict:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    table_counts = {}
    for table in TABLES:
        rows = payload.get("tables", {}).get(table, [])
        if not rows:
            table_counts[table] = 0
            continue
        columns = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )
        table_counts[table] = len(rows)
    conn.commit()
    return {"path": str(snapshot_path), "table_counts": table_counts}
