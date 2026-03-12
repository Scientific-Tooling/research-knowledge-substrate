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


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str


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


def load_llm_config() -> LlmConfig:
    api_key = os.environ.get("RKS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Set RKS_LLM_API_KEY or OPENAI_API_KEY to use llm-api mode.")

    return LlmConfig(
        base_url=os.environ.get("RKS_LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=api_key,
        model=os.environ.get("RKS_LLM_MODEL", "gpt-4.1-mini"),
    )
