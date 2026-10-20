"""The git pre-commit hook that runs verify before every commit.

core.hooksPath lives in the local git config, so every clone connects it again with `hooks install`.
A repository whose hooks already belong to another tool (husky, lefthook, pre-commit, hand-written ones) keeps them:
install leaves its config alone and says where to add verify instead, because switching core.hooksPath would silently disable them.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import gitutil

HOOKS_DIR = ".githooks"
PRE_COMMIT = f"{HOOKS_DIR}/pre-commit"
VERIFY_CALL = "tool/ai.py verify"


def _configured_path(root: Path) -> str | None:
    value = gitutil.git(root, "config", "--get", "core.hooksPath", check=False).decode("utf-8", errors="replace").strip()
    return value or None


def _default_hooks_dir(root: Path) -> Path:
    # --git-path resolves worktrees and submodules, whose hooks are not in ./.git/hooks.
    path = gitutil.git(root, "rev-parse", "--git-path", "hooks").decode("utf-8", errors="replace").strip()
    return root / path


def _active_hooks(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(entry.name for entry in directory.iterdir() if entry.is_file() and not entry.name.endswith(".sample"))


def _runs_verify(hook: Path) -> bool:
    try:
        return VERIFY_CALL in hook.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def state(root: Path) -> dict:
    """Which pre-commit hook git runs here and whether it runs verify. `problem` is None when commits are verified."""
    configured = _configured_path(root)
    directory = root / configured if configured else _default_hooks_dir(root)
    hook = directory / "pre-commit"
    report = {"hooksPath": configured, "preCommit": os.path.relpath(hook, root), "runsVerify": False, "problem": None}
    if _runs_verify(hook) and os.access(hook, os.X_OK):
        report["runsVerify"] = True
    elif configured == HOOKS_DIR:
        report["problem"] = (f"{PRE_COMMIT} is missing, not executable, or no longer runs verify, so commits are not verified. "
                             f"Restore it from the starter and run `chmod +x {PRE_COMMIT}`.")
    elif _foreign(root, configured):
        report["problem"] = (f"Commits are not verified: git runs the hooks in {os.path.relpath(directory, root)}, which belong to another tool. "
                             f"Add `python3 {VERIFY_CALL} --id pre-commit` to its pre-commit hook.")
    else:
        report["problem"] = "Commits are not verified: run `python3 tool/ai.py hooks install`."
    return report


def _foreign(root: Path, configured: str | None) -> bool:
    """Whether hooks of another tool are in effect, which pointing core.hooksPath at .githooks would disable."""
    if configured is not None:
        return configured != HOOKS_DIR
    return bool(_active_hooks(_default_hooks_dir(root)))


def install(root: Path) -> tuple[dict, int]:
    """Points core.hooksPath at .githooks unless another tool's hooks would be disabled by it."""
    before = state(root)
    if before["runsVerify"]:
        return {"ok": True, "installed": False, **before}, 0
    if before["hooksPath"] is not None or _foreign(root, None):
        return {"ok": False, "installed": False, **before}, 1
    if not os.access(root / PRE_COMMIT, os.X_OK):
        return {"ok": False, "installed": False, **before,
                "problem": f"{PRE_COMMIT} is missing or not executable. Restore it from the starter and run `chmod +x {PRE_COMMIT}`."}, 1
    gitutil.git(root, "config", "--local", "core.hooksPath", HOOKS_DIR)
    return {"ok": True, "installed": True, **state(root)}, 0
