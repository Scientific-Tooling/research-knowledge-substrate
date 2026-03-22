from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    pass


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


ALL_AUTO_EXTRACT_MODES = ("none", "llm-api", "llm-api-combined", "agent")


@dataclass(frozen=True)
class AppConfig:
    root: Path
    data_dir: Path
    global_config_path: Path
    reference_pdf_acquisition: str
    auto_extract_mode: str
    llm_base_url: str
    llm_model: str
    llm_api_key_env: list[str]


DEFAULT_CONFIG = {
    "data_dir": "data",
    "reference_pdf_acquisition": "auto",
    "auto_extract_mode": "none",
    "llm": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "api_key_env": ["RKS_LLM_API_KEY", "OPENAI_API_KEY"],
    },
}


def global_config_path() -> Path:
    """Return the path to the global user-level RKS config file."""
    return Path.home() / ".rks" / "config.json"


def load_global_config() -> dict:
    """Load the global config, returning an empty dict if not present."""
    path = global_config_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def write_global_config(data: dict) -> Path:
    """Write data to the global config file, creating parent dirs as needed."""
    path = global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_app_config() -> AppConfig:
    gcfg_path = global_config_path()
    payload = dict(DEFAULT_CONFIG)
    payload["llm"] = dict(DEFAULT_CONFIG["llm"])

    # Resolution order:
    # 1. RKS_DATA_DIR env var — direct absolute path override (used by tests)
    # 2. Global config (~/.rks/config.json) data_dir
    # 3. ConfigError — ask user to run `rks init <path>`
    if "RKS_DATA_DIR" in os.environ:
        data_dir = Path(os.environ["RKS_DATA_DIR"]).expanduser().resolve()
    else:
        global_cfg = load_global_config()
        if "data_dir" in global_cfg:
            data_dir = Path(global_cfg["data_dir"]).expanduser().resolve()
            payload["reference_pdf_acquisition"] = global_cfg.get(
                "reference_pdf_acquisition", payload["reference_pdf_acquisition"]
            )
            payload["auto_extract_mode"] = global_cfg.get(
                "auto_extract_mode", payload["auto_extract_mode"]
            )
            payload["llm"] = {**payload["llm"], **global_cfg.get("llm", {})}
        else:
            raise ConfigError(
                "No data directory configured. Run `rks init <path>` to set one."
            )

    return AppConfig(
        root=data_dir,
        data_dir=data_dir,
        global_config_path=gcfg_path,
        reference_pdf_acquisition=os.environ.get(
            "RKS_REFERENCE_PDF_ACQUISITION",
            payload["reference_pdf_acquisition"],
        ),
        auto_extract_mode=os.environ.get(
            "RKS_AUTO_EXTRACT_MODE",
            payload["auto_extract_mode"],
        ),
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


