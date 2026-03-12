from __future__ import annotations

import os
import json
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


@dataclass(frozen=True)
class AppConfig:
    root: Path
    data_dir: Path
    llm_base_url: str
    llm_model: str
    llm_api_key_env: list[str]


DEFAULT_CONFIG = {
    "data_dir": "data",
    "llm": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "api_key_env": ["RKS_LLM_API_KEY", "OPENAI_API_KEY"],
    },
}


def resolve_root() -> Path:
    configured = os.environ.get("RKS_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.cwd().resolve()


def config_path(root: Path | None = None) -> Path:
    return (root or resolve_root()) / "rks.json"


def load_app_config() -> AppConfig:
    root = resolve_root()
    payload = dict(DEFAULT_CONFIG)
    file_path = config_path(root)
    if file_path.exists():
        loaded = json.loads(file_path.read_text(encoding="utf-8"))
        payload["data_dir"] = loaded.get("data_dir", payload["data_dir"])
        payload["llm"] = {
            **payload["llm"],
            **loaded.get("llm", {}),
        }

    data_dir = Path(os.environ.get("RKS_DATA_DIR", payload["data_dir"]))
    if not data_dir.is_absolute():
        data_dir = (root / data_dir).resolve()

    return AppConfig(
        root=root,
        data_dir=data_dir,
        llm_base_url=os.environ.get("RKS_LLM_BASE_URL", payload["llm"]["base_url"]),
        llm_model=os.environ.get("RKS_LLM_MODEL", payload["llm"]["model"]),
        llm_api_key_env=list(payload["llm"].get("api_key_env", ["RKS_LLM_API_KEY", "OPENAI_API_KEY"])),
    )


def load_paths() -> AppPaths:
    app_config = load_app_config()
    return AppPaths(
        root=app_config.root,
        data_dir=app_config.data_dir,
        papers_dir=app_config.data_dir / "papers",
        artifacts_dir=app_config.data_dir / "artifacts",
        db_path=app_config.data_dir / "rks.sqlite3",
    )


def load_llm_config() -> LlmConfig:
    app_config = load_app_config()
    api_key = None
    for env_name in app_config.llm_api_key_env:
        api_key = os.environ.get(env_name)
        if api_key:
            break
    if not api_key:
        raise ValueError(
            "Set one of the configured API key env vars to use llm-api mode: "
            + ", ".join(app_config.llm_api_key_env)
        )

    return LlmConfig(
        base_url=app_config.llm_base_url,
        api_key=api_key,
        model=app_config.llm_model,
    )


def write_default_config(destination: Path) -> Path:
    destination.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    return destination
