"""Copying the harness into a repository: a new one, or an existing one inside a workspace or not."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import paths
from .files import Staging, file_hash, read_json, tree_files
from .manifests import manifest_bytes
from .merge import pattern_lines, with_lines
from .paths import HARNESS_RECORD
from .policy import Policy, policy_for


# Instruction files and folders of other agent tools. The harness neither reads nor replaces them, so they are reported
# before an install for a merge plan instead of being left to compete with the harness rules.
OTHER_INSTRUCTIONS = ["AGENT.md", "CLAUDE.local.md", "GEMINI.md", ".cursorrules", ".windsurfrules", ".clinerules", ".roorules",
                      ".github/copilot-instructions.md", ".claude/settings.local.json",
                      ".cursor/rules", ".windsurf/rules", ".roo/rules", ".kiro/steering", ".github/instructions"]
# Folders the harness installs into; anything else a repository keeps there is its own agent setup.
HARNESS_DIRS = (".claude", ".agents", ".gemini")
# A file moved out of the harness's way before an install, for example AGENTS.pre-harness.md, waits there to be merged.
SET_ASIDE = ".pre-harness"


def install_conflicts(repo: Path, files: list[str]) -> list[str]:
    """Harness files that already exist in an existing repository, in any capitalization; installing over any of them is refused."""
    conflicts = [f for f in files if policy_for(f, "adopt") is not Policy.APPEND_LINES and _exists_any_case(repo, f)]
    if _exists_any_case(repo, HARNESS_RECORD):
        conflicts.append(HARNESS_RECORD)
    return conflicts


def existing_instructions(repo: Path, files: list[str]) -> list[str]:
    """Agent instructions in the repository that the harness did not ship: other tools' rule files, files set aside for a merge,
    and the repository's own entries under the folders the harness installs into. A folder is listed once, with a trailing slash."""
    found = {rel + "/" if (repo / rel).is_dir() else rel for rel in OTHER_INSTRUCTIONS if os.path.lexists(repo / rel)}
    found.update(entry.name for entry in repo.iterdir() if SET_ASIDE in entry.name)
    shipped = set(files)
    for folder in HARNESS_DIRS:
        if (repo / folder).is_dir() and not (repo / folder).is_symlink():
            for rel in tree_files(repo / folder):
                path = f"{folder}/{rel}"
                if path not in shipped:
                    parts = path.split("/")
                    found.add("/".join(parts[:3]) + ("/" if len(parts) > 3 else ""))
    return sorted(found)


def _exists_any_case(root: Path, rel: str) -> bool:
    """Whether `rel` exists under `root` in any capitalization, so that agents.md conflicts with AGENTS.md on every file system."""
    current = root
    for part in rel.split("/"):
        if os.path.lexists(current / part):
            current = current / part
            continue
        if not current.is_dir():
            return False
        match = next((name for name in os.listdir(current) if name.lower() == part.lower()), None)
        if match is None:
            return False
        current = current / match
    return True


def install(repo: Path, files: list[str], mode: str, version: dict) -> list[str]:
    """Copies `files` from the template into `repo`. An existing file is allowed only where the policy appends lines to it."""
    record = {
        "schemaVersion": 1,
        "starter": version,
        "mode": mode,
        "installedAt": date.today().isoformat(),
        "files": {relative: file_hash(paths.TEMPLATE / relative) for relative in files},
    }
    merged = []
    with Staging() as stage:
        for relative in files:
            if policy_for(relative, mode) is Policy.APPEND_LINES and os.path.lexists(repo / relative):
                text = _with_missing_lines(paths.TEMPLATE / relative, repo / relative)
                if text is not None:
                    stage.write(repo / relative, text.encode("utf-8"))
                    merged.append(relative)
                continue
            stage.copy(paths.TEMPLATE / relative, repo / relative)
        stage.write(repo / HARNESS_RECORD, manifest_bytes(repo / HARNESS_RECORD, "harness", record))
    return merged


def _with_missing_lines(source: Path, dest: Path) -> str | None:
    """`dest` with the pattern lines of `source` it lacks appended, or None when it lacks none."""
    existing = dest.read_text(encoding="utf-8")
    present = {line.strip() for line in existing.splitlines()}
    missing = [line for line in pattern_lines(source.read_text(encoding="utf-8")) if line.strip() not in present]
    return with_lines(existing, missing) if missing else None


def base_branch() -> str:
    return read_json(paths.TEMPLATE / ".ai/config.json")["git"]["baseBranch"]


def connect_hooks(repo: Path) -> tuple[dict, list[str]]:
    """Runs the installed harness's `hooks install` in `repo`, after its files are in place and it is a git repository.

    It changes only the repository's local git config, never a file, so it is not staged; when it cannot connect the hook,
    the files stay installed and the reason becomes a warning.
    """
    process = subprocess.run([sys.executable, "tool/ai.py", "hooks", "install"], cwd=repo, capture_output=True, text=True,
                             env={**os.environ, "AI_HARNESS_ROOT": str(repo)})
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError:
        report = {"ok": False, "problem": f"hooks install did not report: {process.stderr.strip() or process.stdout.strip()}"}
    if report.get("ok"):
        return report, []
    problem = report.get("problem") or report.get("error") or "unknown"
    return report, [f"The pre-commit verify hook is not connected: {problem}"]
