"""Reproducing a shared workspace: clone its root repository, then every listed repository from its remote."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from .gitutil import git, has_credentials, known_commit
from .install import connect_hooks
from .manifests import load_manifest
from .paths import HARNESS_RECORD, WORKSPACE_FILE, StarterError, clean_relative, resolve_workspace
from .registry import remember_workspace
from .workspace import load_workspace


def _clone(url: str, parent: Path) -> Path:
    """Clones into a temporary folder inside `parent`; the caller moves it into place. git removes a failed clone itself."""
    temp = parent / f".clone.{uuid.uuid4().hex[:12]}.starter-tmp"
    git(parent, "clone", "-q", url, temp.name, prompt=False)
    return temp


def _clone_root(url: str, workspace: Path) -> None:
    """Clones the workspace repository into an empty or missing folder, and keeps it only if it holds a valid workspace.json.

    The clone is made inside the workspace folder and its entries are then moved up, so nothing is written outside it.
    """
    if has_credentials(url):
        raise StarterError("--url contains credentials (a token or password in the URL). Give the URL without them.")
    if workspace.exists() and any(workspace.iterdir()):
        raise StarterError(f"{workspace} is not empty. Omit --url to clone the repositories of a workspace that is already there.")
    created = not workspace.exists()
    workspace.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        temp = _clone(url, workspace)
        if load_workspace(temp) is None:
            raise StarterError(f"{url} has no {WORKSPACE_FILE} in its default branch, so it is not a workspace repository.")
        for entry in sorted(temp.iterdir()):
            entry.rename(workspace / entry.name)
        temp.rmdir()
    except BaseException:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
        if created:
            shutil.rmtree(workspace, ignore_errors=True)
        raise


def _plan(workspace: Path, repos: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Sorts the entries into present, to clone, and skipped. A folder in the way stops the command before it clones anything."""
    present, to_clone, skipped, blocked = [], [], [], []
    for repo in repos:
        if clean_relative(repo["path"]) != repo["path"]:
            raise StarterError(f"{WORKSPACE_FILE} gives {repo['name']!r} the path {repo['path']!r}; use a folder inside the workspace, relative to it.")
        target = workspace / repo["path"]
        remote = repo.get("remote", "")
        if (target / ".git").exists():
            present.append(repo)
        elif target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
            blocked.append(repo["path"])
        elif not remote:
            skipped.append({"name": repo["name"], "reason": "no remote in workspace.json"})
        elif has_credentials(remote):
            skipped.append({"name": repo["name"], "reason": "the remote in workspace.json contains credentials; remove them and push the workspace"})
        else:
            to_clone.append(repo)
    if blocked:
        raise StarterError(f"These paths already hold something that is not a git repository; nothing was cloned. Move them first: {blocked}")
    return present, to_clone, skipped


def clone_workspace(raw_path: str, url: str, names: list[str]) -> dict:
    workspace = resolve_workspace(raw_path)
    if url:
        _clone_root(url, workspace)
    manifest = load_workspace(workspace)
    if manifest is None:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE}. Pass --url with the workspace repository to clone it first.")
    repos = manifest["repos"]
    unknown = sorted(set(names) - {r["name"] for r in repos})
    if unknown:
        raise StarterError(f"The workspace lists no repository named {unknown}; listed: {[r['name'] for r in repos]}.")
    if names:
        repos = [r for r in repos if r["name"] in names]
    present, to_clone, skipped = _plan(workspace, repos)

    warnings = []
    if not known_commit(manifest["starter"]["commit"]):
        warnings.append("The workspace was made from a starter commit this starter does not have; pull the starter before running upgrade.")
    cloned = []
    for repo in to_clone:
        target = workspace / repo["path"]
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = _clone(repo["remote"], target.parent)
            if target.exists():
                target.rmdir()
            temp.rename(target)
        except (StarterError, OSError) as error:
            raise StarterError(f"Cloning {repo['name']!r} failed: {error}. Already cloned: {[c['name'] for c in cloned] or 'none'}. "
                               "Fix the cause and run the command again without --url; finished repositories are kept and skipped.") from None
        entry = {"name": repo["name"], "path": repo["path"], "harness": (target / HARNESS_RECORD).is_file()}
        if entry["harness"]:
            # core.hooksPath is local git config, so a clone does not have it: connect the pre-commit verify hook again.
            entry["hooks"], hook_warnings = connect_hooks(target)
            warnings += hook_warnings
            record = load_manifest(target / HARNESS_RECORD, "harness")
            if not known_commit(record["starter"]["commit"]):
                warnings.append(f"{repo['name']} was made from a starter commit this starter does not have; pull the starter before upgrading it.")
        cloned.append(entry)

    warnings += remember_workspace(workspace)
    return {"ok": True, "workspace": str(workspace), "workspaceCloned": bool(url), "cloned": cloned,
            "present": [r["name"] for r in present], "skipped": skipped, "warnings": warnings,
            "next": "Each repository's own setup (dependencies, .env from .env.example) is still to do; see its README or AGENTS.md."}
