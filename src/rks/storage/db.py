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
