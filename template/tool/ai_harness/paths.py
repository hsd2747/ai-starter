from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

RUNS_DIR = ".ai/runs"
CONFIG_FILE = ".ai/config.json"
SCHEMAS_DIR = ".ai/schemas"
SKILLS_DIR = ".agents/skills"
CLAUDE_SKILLS_DIR = ".claude/skills"
CLAUDE_AGENTS_DIR = ".claude/agents"


class HarnessError(Exception):
    """Usage or validation failure. Reported as JSON with exit code 1."""


class ToolMissing(Exception):
    """A required executable is unavailable. Reported with exit code 3."""


def locate_root(start: Path | None = None) -> Path:
    override = os.environ.get("AI_HARNESS_ROOT")
    if override:
        return Path(override).resolve()
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise HarnessError("Repository root not found: run inside a repository that has .git and AGENTS.md.")


def normalize_relative(path: str) -> str:
    """Clean repository-relative form of `path`, or HarnessError when it could leave the root."""
    if not path or path.startswith("/") or "\\" in path or path.startswith("-"):
        raise HarnessError(f"Not a repository-relative path: {path!r}")
    parts: list[str] = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise HarnessError(f"Path must not contain '..': {path!r}")
        parts.append(segment)
    return "/".join(parts) or "."


def within_root(root: Path, relative: str) -> Path:
    clean = normalize_relative(relative)
    target = root if clean == "." else root / clean
    resolved = target.resolve()
    if resolved != root and root not in resolved.parents:
        raise HarnessError(f"Path resolves outside the repository: {relative!r}")
    return target


def relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def is_relative_path(value: str) -> bool:
    try:
        normalize_relative(value)
    except HarnessError:
        return False
    return True


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HarnessError(f"File not found: {path}") from None
    except json.JSONDecodeError as error:
        raise HarnessError(f"Invalid JSON in {path}: {error}") from None


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_text_or_none(path: Path, limit: int = 2_000_000) -> str | None:
    """Text content of a regular file, or None for binaries, oversized files, and non-files."""
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")
