from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    data_dir: Path
    papers_dir: Path
    artifacts_dir: Path
    db_path: Path


def resolve_root() -> Path:
    configured = os.environ.get("RKS_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.cwd().resolve()


def load_paths() -> AppPaths:
    root = resolve_root()
    data_dir = root / "data"
    return AppPaths(
        root=root,
        data_dir=data_dir,
        papers_dir=data_dir / "papers",
        artifacts_dir=data_dir / "artifacts",
        db_path=data_dir / "rks.sqlite3",
    )
