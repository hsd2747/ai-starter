"""Running git, and the starter commit that generated repositories record."""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import paths
from .paths import StarterError


def git(cwd: Path, *args: str, check: bool = True) -> str:
    try:
        process = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        raise StarterError("git is not installed or not on PATH.") from None
    if check and process.returncode != 0:
        raise StarterError(f"git {' '.join(args)} failed in {cwd}: {process.stderr.strip()}")
    return process.stdout.strip()


def git_ok(cwd: Path, *args: str) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True).returncode == 0


def init_repo(path: Path, branch: str) -> None:
    if not (path / ".git").exists():
        git(path, "-c", f"init.defaultBranch={branch}", "init", "-q")


def starter_version() -> dict:
    commit = git(paths.STARTER, "rev-parse", "--verify", "--quiet", "HEAD", check=False) or None
    changes = git(paths.STARTER, "status", "--porcelain", "--", "template", "workspace-template", check=False)
    return {"commit": commit, "dirty": bool(changes)}


def version_warnings(version: dict) -> list[str]:
    if version["commit"] is None:
        return ["The starter has no commit, so the version record cannot name one. Commit the starter before creating repositories you keep."]
    if version["dirty"]:
        return ["template/ or workspace-template/ has uncommitted changes; the version record names a commit that does not contain them."]
    return []
