from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from rks import __version__
from rks.utils import ensure_dir

SKILL_BUNDLE_VERSION = f"{__version__}.skillbundle.1"


@dataclass(frozen=True)
class BundledSkill:
    name: str
    description: str
    content: str


def list_bundled_skills() -> list[BundledSkill]:
    bundle_dir = resources.files("rks.agent_skills").joinpath("bundle")
    skills = []
    for skill_dir in sorted(bundle_dir.iterdir(), key=lambda path: path.name):
        if not skill_dir.is_dir():
            continue
        skill_path = skill_dir.joinpath("SKILL.md")
        if not skill_path.is_file():
            continue
        content = skill_path.read_text(encoding="utf-8")
        metadata = _parse_front_matter(content)
        skills.append(
            BundledSkill(
                name=metadata.get("name", skill_dir.name),
                description=metadata.get("description", ""),
                content=content,
            )
        )
    return skills


def export_bundled_skills(destination: Path) -> dict:
    destination = destination.resolve()
    ensure_dir(destination)
    skills_dir = ensure_dir(destination / "skills")
    skills = list_bundled_skills()

    exported_skill_paths = []
    index_entries = []
    for skill in skills:
        skill_root = ensure_dir(skills_dir / skill.name)
        relative_path = Path("skills") / skill.name / "SKILL.md"
        (skill_root / "SKILL.md").write_text(skill.content, encoding="utf-8")
        exported_skill_paths.append(str(relative_path))
        index_entries.append(
            {
                "name": skill.name,
                "description": skill.description,
                "path": str(relative_path).replace("\\", "/"),
            }
        )

    (destination / "skills-index.json").write_text(json.dumps(index_entries, indent=2), encoding="utf-8")
    (destination / "bundle-metadata.json").write_text(
        json.dumps(
            {
                "bundle_version": SKILL_BUNDLE_VERSION,
                "skill_count": len(index_entries),
                "skills_index": "skills-index.json",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (destination / "AGENTS.md").write_text(_agents_md(index_entries), encoding="utf-8")
    (destination / "CLAUDE.md").write_text(_claude_md(index_entries), encoding="utf-8")
    (destination / "README.md").write_text(_bundle_readme(index_entries), encoding="utf-8")

    return {
        "destination": str(destination),
        "bundle_version": SKILL_BUNDLE_VERSION,
        "skill_count": len(index_entries),
        "skills": index_entries,
        "exported_files": [
            "AGENTS.md",
            "CLAUDE.md",
            "README.md",
            "bundle-metadata.json",
            "skills-index.json",
            *[entry["path"] for entry in index_entries],
        ],
    }


def _parse_front_matter(content: str) -> dict[str, str]:
    lines = content.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}

    metadata: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _bundle_readme(entries: list[dict]) -> str:
    lines = [
        "# RKS Agent Skill Bundle",
        "",
        "This directory was exported by `rks skills export`.",
        f"Bundle version: `{SKILL_BUNDLE_VERSION}`.",
        "",
        "Contents:",
        "",
        "- `skills/`: raw skill markdown files",
        "- `skills-index.json`: machine-readable index",
        "- `bundle-metadata.json`: bundle version and export metadata",
        "- `AGENTS.md`: project instructions file for Codex-style agent tools",
        "- `CLAUDE.md`: project instructions file for Claude Code-style agent tools",
        "",
        "Available skills:",
        "",
    ]
    for entry in entries:
        lines.append(f"- `{entry['name']}`: {entry['description']}")
    lines.extend(
        [
            "",
            "For other agent runtimes, ingest `skills-index.json` and the markdown files under `skills/`.",
            "",
        ]
    )
    return "\n".join(lines)


def _agents_md(entries: list[dict]) -> str:
    lines = [
        "# RKS Agent Skills",
        "",
        "This workspace includes exported RKS skills under `./skills`.",
        "",
        "Use these rules:",
        "",
        "- When a task clearly matches one of the named skills below, read the corresponding `SKILL.md` first.",
        "- Use the smallest number of skills that fully covers the task.",
        "- Prefer the repository's CLI and HTTP interfaces over ad hoc behavior.",
        "- Do not load every skill unless the task genuinely spans multiple workflows.",
        "",
        "Available skills:",
        "",
    ]
    for entry in entries:
        lines.append(f"- `{entry['name']}`: {entry['description']}")
    lines.extend(
        [
            "",
            "Skill files:",
            "",
        ]
    )
    for entry in entries:
        lines.append(f"- `./{entry['path']}`")
    lines.append("")
    return "\n".join(lines)


def _claude_md(entries: list[dict]) -> str:
    lines = [
        "# RKS Claude Code Instructions",
        "",
        "This workspace includes exported RKS skill markdown files under `./skills`.",
        "",
        "Suggested usage:",
        "",
        "- Match the user task to one or more skills in this bundle.",
        "- Read only the needed `SKILL.md` files before acting.",
        "- Treat the skill text as repository-specific operating instructions.",
        "- Prefer `rks` CLI commands first, then use HTTP when the skill explicitly asks for a cross-check.",
        "",
        "Available skills:",
        "",
    ]
    for entry in entries:
        lines.append(f"- `{entry['name']}`: {entry['description']}")
    lines.append("")
    return "\n".join(lines)
