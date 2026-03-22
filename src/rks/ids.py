from __future__ import annotations

import sqlite3


ID_PREFIXES = {
    "paper": "p",
    "claim": "c",
    "method": "m",
    "dataset": "d",
    "concept": "k",
    "note": "n",
    "project": "rp",
    "project_link": "pl",
    "hypothesis": "h",
    "task": "t",
    "edge": "e",
    "artifact": "a",
    "evolution_event": "ev",
    "concept_timeline_snapshot": "cts",
    "claim_conflict_cluster": "cc",
    "claim_conflict_cluster_member": "ccm",
}


def next_id(conn: sqlite3.Connection, kind: str) -> str:
    try:
        prefix = ID_PREFIXES[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown ID kind: {kind}") from exc

    row = conn.execute(
        "SELECT next_value FROM counters WHERE kind = ?",
        (kind,),
    ).fetchone()

    if row is None:
        next_value = 1
        conn.execute(
            "INSERT INTO counters(kind, next_value) VALUES(?, ?)",
            (kind, 2),
        )
    else:
        next_value = int(row[0])
        conn.execute(
            "UPDATE counters SET next_value = ? WHERE kind = ?",
            (next_value + 1, kind),
        )

    return f"{prefix}_{next_value:06d}"
