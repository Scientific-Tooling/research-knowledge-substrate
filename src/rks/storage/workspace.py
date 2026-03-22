"""Workspace export/import — portable archive of the full RKS data directory.

Archive layout (tar.gz):
  manifest.json          — version, timestamps, original data_dir
  graph_snapshot.json    — all DB tables with file paths rewritten to relative
  files/<rel_path>       — actual files, mirroring their position under data_dir
"""
from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from pathlib import Path

from rks.storage.snapshot import TABLES
from rks.utils import utc_now

WORKSPACE_VERSION = "workspace.v1"

# Columns in each table that hold file-system paths.
PATH_COLUMNS: dict[str, list[str]] = {
    "papers": ["pdf_path"],
    "artifacts": ["path"],
}


def _to_relative(abs_path: str | None, data_dir: Path) -> str | None:
    """Return a path string relative to data_dir, or None if not applicable."""
    if not abs_path:
        return abs_path
    try:
        return str(Path(abs_path).relative_to(data_dir))
    except ValueError:
        # Path is outside data_dir — keep as-is; the file won't be bundled.
        return abs_path


def _to_absolute(rel_or_abs: str | None, data_dir: Path) -> str | None:
    """Rewrite a relative path back to absolute under data_dir."""
    if not rel_or_abs:
        return rel_or_abs
    p = Path(rel_or_abs)
    if p.is_absolute():
        return rel_or_abs
    return str(data_dir / p)


def export_workspace(conn, data_dir: Path, archive_path: Path) -> dict:
    """Bundle all DB tables and referenced files into a portable tar.gz archive."""
    if not str(archive_path).endswith(".tar.gz"):
        archive_path = Path(str(archive_path) + ".tar.gz")

    tables_data: dict[str, list[dict]] = {}
    for table in TABLES:
        tables_data[table] = [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]

    # Collect files to bundle and rewrite paths to relative.
    files_to_add: list[tuple[Path, str]] = []  # (abs_path, archive_member_path)
    for table, columns in PATH_COLUMNS.items():
        for row in tables_data.get(table, []):
            for col in columns:
                abs_val = row.get(col)
                if not abs_val:
                    continue
                abs_path = Path(abs_val)
                try:
                    rel = abs_path.relative_to(data_dir)
                except ValueError:
                    continue  # outside data_dir, skip bundling
                if abs_path.exists():
                    files_to_add.append((abs_path, str(Path("files") / rel)))
                row[col] = str(rel)  # rewrite to relative

    snapshot = {
        "version": WORKSPACE_VERSION,
        "exported_at": utc_now(),
        "original_data_dir": str(data_dir),
        "tables": tables_data,
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snapshot_file = tmp_path / "graph_snapshot.json"
        manifest_file = tmp_path / "manifest.json"

        snapshot_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        manifest_file.write_text(
            json.dumps(
                {
                    "version": WORKSPACE_VERSION,
                    "exported_at": snapshot["exported_at"],
                    "original_data_dir": str(data_dir),
                    "file_count": len(files_to_add),
                    "table_counts": {t: len(rows) for t, rows in tables_data.items()},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(manifest_file, arcname="manifest.json")
            tar.add(snapshot_file, arcname="graph_snapshot.json")
            for abs_path, member in files_to_add:
                tar.add(abs_path, arcname=member)

    return {
        "archive": str(archive_path),
        "file_count": len(files_to_add),
        "table_counts": {t: len(rows) for t, rows in tables_data.items()},
    }


def import_workspace(conn, data_dir: Path, archive_path: Path) -> dict:
    """Extract a workspace archive and load it into the current data directory."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        with tarfile.open(archive_path, "r:gz") as tar:
            # Safety: reject members with absolute paths or path traversal.
            for member in tar.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError(f"Unsafe archive member: {member.name}")
            tar.extractall(tmp_path)  # noqa: S202 — members validated above

        snapshot_file = tmp_path / "graph_snapshot.json"
        if not snapshot_file.exists():
            raise FileNotFoundError("Archive is missing graph_snapshot.json")

        payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
        if payload.get("version") != WORKSPACE_VERSION:
            raise ValueError(f"Unsupported workspace version: {payload.get('version')!r}")

        tables_data: dict[str, list[dict]] = payload.get("tables", {})

        # Rewrite relative paths back to absolute under the new data_dir.
        for table, columns in PATH_COLUMNS.items():
            for row in tables_data.get(table, []):
                for col in columns:
                    row[col] = _to_absolute(row.get(col), data_dir)

        # Copy bundled files into data_dir.
        files_dir = tmp_path / "files"
        copied_files = 0
        if files_dir.exists():
            for src in files_dir.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(files_dir)
                    dest = data_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    copied_files += 1

        # Import all tables.
        table_counts: dict[str, int] = {}
        for table in TABLES:
            rows = tables_data.get(table, [])
            if not rows:
                table_counts[table] = 0
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join("?" for _ in columns)
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                [tuple(row[col] for col in columns) for row in rows],
            )
            table_counts[table] = len(rows)
        conn.commit()

    return {
        "archive": str(archive_path),
        "copied_files": copied_files,
        "table_counts": table_counts,
    }
