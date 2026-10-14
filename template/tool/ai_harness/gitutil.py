from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from .paths import RUNS_DIR, HarnessError, ToolMissing

# Diffing against the empty tree lets a repository without any commit be verified.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
NO_HEAD = "no-head"


def git(root: Path, *args: str, check: bool = True) -> bytes:
    try:
        process = subprocess.run(["git", *args], cwd=root, capture_output=True)
    except FileNotFoundError:
        raise ToolMissing("git is not installed or not on PATH.") from None
    if check and process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise HarnessError(f"git {' '.join(args)} failed: {message}")
    return process.stdout


def _paths(output: bytes) -> list[str]:
    return [item.decode("utf-8", errors="surrogateescape") for item in output.split(b"\0") if item]


def head(root: Path) -> str | None:
    process = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=root, capture_output=True)
    return process.stdout.decode().strip() if process.returncode == 0 else None


def diff_base(root: Path) -> str:
    return head(root) or EMPTY_TREE


def untracked_files(root: Path) -> list[str]:
    return _paths(git(root, "ls-files", "--others", "--exclude-standard", "-z"))


def tracked_files(root: Path) -> list[str]:
    return _paths(git(root, "ls-files", "--cached", "-z"))


def comparison_base(root: Path, base_branch: str) -> tuple[str, str]:
    """(commit, ref) that `verify` diffs against: the merge base with the base branch.

    Diffing against HEAD would drop every committed change, so a branch that
    commits before verifying would pass with nothing checked. The remote branch
    comes first because a stale local copy widens the diff instead of hiding work.
    """
    current = head(root)
    if current is None:
        return EMPTY_TREE, "none"
    for ref in (f"refs/remotes/origin/{base_branch}", f"refs/heads/{base_branch}"):
        process = subprocess.run(["git", "merge-base", "HEAD", ref], cwd=root, capture_output=True, text=True)
        if process.returncode == 0 and process.stdout.strip():
            return process.stdout.strip(), ref.removeprefix("refs/remotes/").removeprefix("refs/heads/")
    return current, "HEAD"


def changed_files(root: Path, base: str) -> list[str]:
    """Paths that differ from `base`: committed, staged, unstaged, deleted, and untracked.

    Renames are split into a deletion and an addition so both sides stay visible
    to unit coverage and codegen selection.
    """
    files: set[str] = set()
    common = ("--name-only", "-z", "--no-renames", "--diff-filter=ACMD", base, "--")
    files.update(_paths(git(root, "diff", *common)))
    files.update(_paths(git(root, "diff", "--cached", *common)))
    files.update(untracked_files(root))
    return sorted(path for path in files if not path.startswith(RUNS_DIR + "/"))


def all_files(root: Path) -> list[str]:
    files = set(tracked_files(root)) | set(untracked_files(root))
    return sorted(path for path in files if os.path.lexists(root / path))


def worktree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    digest.update((head(root) or NO_HEAD).encode())
    digest.update(b"\0")
    digest.update(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"))
    digest.update(git(root, "diff", "--binary", "--no-ext-diff", diff_base(root), "--"))
    for path in untracked_files(root):
        full = root / path
        digest.update(path.encode("utf-8", errors="surrogateescape") + b"\0")
        if full.is_symlink():
            digest.update(b"link:" + os.readlink(full).encode())
        elif full.is_file():
            digest.update(hashlib.sha256(full.read_bytes()).digest())
    return digest.hexdigest()


def subject(root: Path, scope: str, base_branch: str) -> dict:
    base, base_ref = comparison_base(root, base_branch)
    files = changed_files(root, base) if scope == "changed" else all_files(root)
    return {
        "scope": scope,
        "base": base,
        "baseRef": base_ref,
        "head": head(root) or NO_HEAD,
        "worktreeDigest": worktree_digest(root),
        "files": files,
    }
