from __future__ import annotations

from importlib import resources
import sqlite3
from pathlib import Path
from typing import Any

from rks.storage.schema import SCHEMA_SQL
from rks.utils import ensure_dir, utc_now


def connect_db(db_path: Path) -> sqlite3.Connection:
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def connect_db_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> None:
    apply_migrations(conn, migrations_dir=migrations_dir)
    conn.executescript(SCHEMA_SQL)
    _ensure_indexes(conn)
    conn.commit()


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> dict:
    _preflight_legacy_schema_compatibility(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    available = list_migration_files(migrations_dir)

    executed = []
    for migration_path in available:
        if migration_path.name in applied:
            continue
        if _migration_already_satisfied(conn, migration_path.name):
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                (migration_path.name, utc_now()),
            )
            continue
        conn.executescript(migration_path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
            (migration_path.name, utc_now()),
        )
        executed.append(migration_path.name)
    conn.commit()
    return {
        "applied_migrations": sorted(
            row["version"] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC").fetchall()
        ),
        "executed": executed,
    }


def list_migration_files(migrations_dir: Path | None = None) -> list[Any]:
    if migrations_dir is not None:
        if not migrations_dir.exists():
            return []
        return sorted(path for path in migrations_dir.glob("*.sql") if path.is_file())

    repo_directory = Path(__file__).resolve().parents[3] / "migrations"
    if repo_directory.exists():
        return sorted(path for path in repo_directory.glob("*.sql") if path.is_file())

    return _packaged_migration_files()


def current_schema_version(conn: sqlite3.Connection) -> str | None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    row = conn.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
    return row["version"] if row is not None else None


def audit_referential_integrity(conn: sqlite3.Connection) -> dict:
    """Return orphan-reference counts for the FK-less SQLite graph schema."""
    checks = {
        "papers_text_artifact_id": _orphan_count(
            conn,
            "papers",
            "text_artifact_id IS NOT NULL AND text_artifact_id NOT IN (SELECT id FROM artifacts)",
        ),
        "artifacts_paper_id": _orphan_count(
            conn,
            "artifacts",
            "paper_id IS NOT NULL AND paper_id NOT IN (SELECT id FROM papers)",
        ),
        "claims_paper_id": _orphan_count(
            conn,
            "claims",
            "paper_id NOT IN (SELECT id FROM papers)",
        ),
        "claims_subject_concept_id": _orphan_count(
            conn,
            "claims",
            "subject_concept_id IS NOT NULL AND subject_concept_id NOT IN (SELECT id FROM concepts)",
        ),
        "claims_object_concept_id": _orphan_count(
            conn,
            "claims",
            "object_concept_id IS NOT NULL AND object_concept_id NOT IN (SELECT id FROM concepts)",
        ),
        "methods_paper_id": _orphan_count(
            conn,
            "methods",
            "paper_id NOT IN (SELECT id FROM papers)",
        ),
        "datasets_paper_id": _orphan_count(
            conn,
            "datasets",
            "paper_id NOT IN (SELECT id FROM papers)",
        ),
        "paper_tags_paper_id": _orphan_count(
            conn,
            "paper_tags",
            "paper_id NOT IN (SELECT id FROM papers)",
        ),
        "tasks_paper_id": _orphan_count(
            conn,
            "tasks",
            "paper_id NOT IN (SELECT id FROM papers)",
        ),
        "edges_evidence_paper_id": _orphan_count(
            conn,
            "edges",
            "evidence_paper_id IS NOT NULL AND evidence_paper_id NOT IN (SELECT id FROM papers)",
        ),
        "project_links_project_id": _orphan_count(
            conn,
            "project_links",
            "project_id NOT IN (SELECT id FROM research_projects)",
        ),
        "hypotheses_project_id": _orphan_count(
            conn,
            "hypotheses",
            "project_id NOT IN (SELECT id FROM research_projects)",
        ),
        "hypothesis_evidence_links_hypothesis_id": _orphan_count(
            conn,
            "hypothesis_evidence_links",
            "hypothesis_id NOT IN (SELECT id FROM hypotheses)",
        ),
        "claim_relation_candidates_source_claim_id": _orphan_count(
            conn,
            "claim_relation_candidates",
            "source_claim_id NOT IN (SELECT id FROM claims)",
        ),
        "claim_relation_candidates_target_claim_id": _orphan_count(
            conn,
            "claim_relation_candidates",
            "target_claim_id NOT IN (SELECT id FROM claims)",
        ),
        "concept_timeline_snapshots_concept_id": _orphan_count(
            conn,
            "concept_timeline_snapshots",
            "concept_id NOT IN (SELECT id FROM concepts)",
        ),
        "claim_conflict_clusters_anchor_concept_id": _orphan_count(
            conn,
            "claim_conflict_clusters",
            "anchor_concept_id NOT IN (SELECT id FROM concepts)",
        ),
        "claim_conflict_cluster_members_cluster_id": _orphan_count(
            conn,
            "claim_conflict_cluster_members",
            "cluster_id NOT IN (SELECT id FROM claim_conflict_clusters)",
        ),
        "claim_conflict_cluster_members_claim_id": _orphan_count(
            conn,
            "claim_conflict_cluster_members",
            "claim_id NOT IN (SELECT id FROM claims)",
        ),
    }
    total = sum(checks.values())
    return {
        "ok": total == 0,
        "total_orphan_count": total,
        "orphan_counts": checks,
    }


def _packaged_migration_files() -> list[Any]:
    directory = resources.files("rks.migrations")
    return sorted(
        (path for path in directory.iterdir() if path.name.endswith(".sql") and path.is_file()),
        key=lambda path: path.name,
    )


def _ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name)")
    _ensure_column(conn, "datasets", "paper_id", "TEXT")
    _ensure_column(conn, "papers", "reading_status", "TEXT NOT NULL DEFAULT 'unread'")
    _ensure_column(conn, "concepts", "canonical_abbrev", "TEXT")
    _ensure_alias_index(conn)


def _ensure_alias_index(conn: sqlite3.Connection) -> None:
    """Backfill concept_alias_index from existing concepts rows.

    Safe to call repeatedly: uses INSERT OR IGNORE so already-indexed entries
    are skipped.  Only runs when the table exists (created by migration 0011).
    """
    if not _table_exists(conn, "concept_alias_index"):
        return
    import json as _json
    rows = conn.execute("SELECT id, name, aliases_json, canonical_abbrev FROM concepts").fetchall()
    for row in rows:
        keys: set[str] = set()
        name = row["name"] or ""
        if name:
            keys.add(name)
            keys.add(name.lower())
        abbrev = row["canonical_abbrev"]
        if abbrev:
            keys.add(abbrev)
            keys.add(abbrev.lower())
        for alias in _json.loads(row["aliases_json"] or "[]"):
            if alias:
                keys.add(alias)
        concept_id = row["id"]
        conn.executemany(
            "INSERT OR IGNORE INTO concept_alias_index(alias_key, concept_id) VALUES(?, ?)",
            [(k, concept_id) for k in keys if k],
        )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _table_exists(conn, table):
        return
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _orphan_count(conn: sqlite3.Connection, table: str, predicate: str) -> int:
    if not _table_exists(conn, table):
        return 0
    try:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["count"] if row is not None else 0)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in columns


def _migration_already_satisfied(conn: sqlite3.Connection, migration_name: str) -> bool:
    # Allow recovery when a schema change was applied out-of-band but the
    # migration history table was not updated.
    if migration_name == "0008_paper_reading_status.sql":
        return _column_exists(conn, "papers", "reading_status")
    return False


def _preflight_legacy_schema_compatibility(conn: sqlite3.Connection) -> None:
    """Backfill legacy columns required by migration-time index creation."""
    _ensure_column(conn, "claims", "paper_id", "TEXT")
    _ensure_column(conn, "methods", "paper_id", "TEXT")
    _ensure_column(conn, "datasets", "paper_id", "TEXT")
    _ensure_column(conn, "tasks", "paper_id", "TEXT")
