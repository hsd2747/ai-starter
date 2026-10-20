from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import hooks
from .checks import config_rule_errors
from .paths import CLAUDE_AGENTS_DIR, CLAUDE_SKILLS_DIR, CONFIG_FILE, SKILLS_DIR, HarnessError, read_json
from .schema import SCHEMA_FILES, SKILL_NAME, validate_artifact
from .wiki import parse_frontmatter

REQUIRED_FILES = [
    "AGENTS.md", "CLAUDE.md", "REVIEW.md", CONFIG_FILE,
    *[f".ai/schemas/{name}" for name in SCHEMA_FILES.values()],
    "tool/ai.py", hooks.PRE_COMMIT,
]
SKILL_BODY_LIMIT = 500
_SKILL_REFERENCE = re.compile(r"\.agents/skills/([a-z0-9-]+)/SKILL\.md")


def skill_names(root: Path) -> list[str]:
    base = root / SKILLS_DIR
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def _adapter_target(root: Path, name: str) -> Path:
    return (root / SKILLS_DIR / name).resolve()


def static_errors(root: Path, warnings: list[str] | None = None) -> list[str]:
    """Problems an agent could introduce by editing harness files. Cheap enough to run on every verify."""
    warnings = warnings if warnings is not None else []
    errors = [f"{path}: required harness file is missing" for path in REQUIRED_FILES if not (root / path).is_file()]

    if (root / CONFIG_FILE).is_file():
        try:
            config = read_json(root / CONFIG_FILE)
        except HarnessError as error:
            errors.append(str(error))
        else:
            errors += [f"{CONFIG_FILE}: {e}" for e in validate_artifact(root, "config", config) + config_rule_errors(config)]
            if not config.get("onboarded"):
                warnings.append("Project is not onboarded yet; run the repo-onboard skill before feature work.")

    claude = root / "CLAUDE.md"
    if claude.is_file() and "@AGENTS.md" not in claude.read_text(encoding="utf-8"):
        errors.append("CLAUDE.md must import @AGENTS.md so Claude Code reads the same policy")

    names = skill_names(root)
    for name in names:
        skill = root / SKILLS_DIR / name / "SKILL.md"
        if not skill.is_file():
            errors.append(f"{SKILLS_DIR}/{name}: SKILL.md is missing")
            continue
        text = skill.read_text(encoding="utf-8")
        meta, problem = parse_frontmatter(text)
        if meta is None:
            errors.append(f"{SKILLS_DIR}/{name}/SKILL.md: {problem}")
            continue
        if meta.get("name") != name or not SKILL_NAME.match(name) or len(name) > 64:
            errors.append(f"{SKILLS_DIR}/{name}/SKILL.md: name must equal the directory name and be lowercase-hyphenated")
        description = meta.get("description")
        if not isinstance(description, str) or not description.strip() or len(description) > 1024:
            errors.append(f"{SKILLS_DIR}/{name}/SKILL.md: description must be 1-1024 characters")
        if text.count("\n") > SKILL_BODY_LIMIT:
            warnings.append(f"{SKILLS_DIR}/{name}/SKILL.md: over {SKILL_BODY_LIMIT} lines; move detail into references/")

    adapters = root / CLAUDE_SKILLS_DIR
    for name in names:
        link = adapters / name
        if not link.exists() or link.resolve() != _adapter_target(root, name):
            errors.append(f"{CLAUDE_SKILLS_DIR}/{name}: missing or not pointing at {SKILLS_DIR}/{name}; run `python3 tool/ai.py adapters sync`")
    if adapters.is_dir():
        for entry in sorted(adapters.iterdir()):
            if entry.name not in names:
                errors.append(f"{CLAUDE_SKILLS_DIR}/{entry.name}: adapter has no skill in {SKILLS_DIR}; remove it")

    agents = root / CLAUDE_AGENTS_DIR
    if agents.is_dir():
        for wrapper in sorted(agents.glob("*.md")):
            for referenced in _SKILL_REFERENCE.findall(wrapper.read_text(encoding="utf-8")):
                if referenced not in names:
                    errors.append(f"{CLAUDE_AGENTS_DIR}/{wrapper.name}: references missing skill {referenced!r}")
    return errors


def doctor(root: Path) -> tuple[dict, int]:
    warnings: list[str] = []
    errors = []
    if sys.version_info < (3, 10):
        errors.append(f"Python 3.10+ is required; found {sys.version.split()[0]}")
    if shutil.which("git") is None:
        errors.append("git is not on PATH")
    errors += static_errors(root, warnings)
    if shutil.which("git") is not None:
        problem = hooks.state(root)["problem"]
        if problem:
            warnings.append(problem)

    tools = {}
    if (root / CONFIG_FILE).is_file():
        try:
            entries = read_json(root / CONFIG_FILE).get("toolchain", [])
        except HarnessError:
            entries = []
        for entry in entries:
            executable = shutil.which(entry["command"][0])
            version = None
            if executable:
                process = subprocess.run([executable, *entry["command"][1:]], cwd=root, capture_output=True, text=True, errors="replace")
                lines = (process.stdout or process.stderr).strip().splitlines()
                version = lines[0] if process.returncode == 0 and lines else None
            tools[entry["name"]] = version or "unavailable"
            if version is None and entry.get("required", True):
                errors.append(f"toolchain {entry['name']!r} is unavailable: {' '.join(entry['command'])}")
    report = {"ok": not errors, "errors": errors, "warnings": warnings, "toolchain": tools}
    return report, 0 if not errors else 3


def sync_adapters(root: Path) -> dict:
    """Create missing .claude/skills/<name> symlinks. Never deletes or overwrites."""
    adapters = root / CLAUDE_SKILLS_DIR
    adapters.mkdir(parents=True, exist_ok=True)
    created, conflicts = [], []
    for name in skill_names(root):
        link = adapters / name
        if link.exists() and link.resolve() == _adapter_target(root, name):
            continue
        if os.path.lexists(link):
            conflicts.append(f"{CLAUDE_SKILLS_DIR}/{name}: exists but does not point at {SKILLS_DIR}/{name}")
            continue
        link.symlink_to(Path("..") / ".." / SKILLS_DIR / name, target_is_directory=True)
        created.append(f"{CLAUDE_SKILLS_DIR}/{name}")
    stale = [f"{CLAUDE_SKILLS_DIR}/{e.name}" for e in sorted(adapters.iterdir()) if e.name not in skill_names(root)]
    return {"ok": not conflicts, "created": created, "conflicts": conflicts, "stale": stale}
