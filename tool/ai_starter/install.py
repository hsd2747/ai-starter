"""Copying the harness into a new or adopted repository."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from . import paths
from .files import Staging, file_hash, read_json
from .manifests import manifest_bytes
from .merge import pattern_lines, with_lines
from .paths import HARNESS_RECORD
from .policy import Policy, policy_for


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
