"""A workspace root: its files, workspace.json, and the generated repository table in its AGENTS.md."""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import paths
from .files import Staging, tree_files, write_atomic
from .gitutil import init_repo
from .manifests import load_manifest, manifest_bytes
from .paths import GUARD_DIR, HARNESS_RECORD, WORKSPACE_FILE, StarterError

REPOS_START = "<!-- workspace:repos:start -->"
REPOS_END = "<!-- workspace:repos:end -->"
REPO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def load_workspace(workspace: Path) -> dict | None:
    """workspace.json without the `kind` that older versions stored: whether a repository has the harness is read from the repository."""
    path = workspace / WORKSPACE_FILE
    if not path.is_file():
        return None
    manifest = load_manifest(path, "workspace")
    for repo in manifest["repos"]:
        repo.pop("kind", None)
    return manifest


def repo_kind(workspace: Path, repo: dict) -> str:
    return "managed" if (workspace / repo["path"] / HARNESS_RECORD).is_file() else "registered"


def check_new_entry(manifest: dict | None, name: str, path: str) -> None:
    if not REPO_NAME.match(name):
        raise StarterError(f"Invalid repository name {name!r}: letters, digits, '.', '_', '-', up to 64 characters.")
    for repo in (manifest or {}).get("repos", []):
        if repo["name"] == name or repo["path"] == path:
            raise StarterError(f"The workspace already registers {repo['name']!r} at {repo['path']!r}.")


def check_workspace_free(workspace: Path) -> None:
    """A folder without workspace.json is initialized only if none of the workspace files exist yet."""
    if (workspace / WORKSPACE_FILE).is_file():
        return
    taken = [f for f in tree_files(paths.WORKSPACE_TEMPLATE) if os.path.lexists(workspace / f)]
    if os.path.lexists(workspace / GUARD_DIR):
        taken.append(GUARD_DIR)
    if taken:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE} but already contains {taken}; merge them by hand first.")


def guard_files() -> list[str]:
    """Paths under template/tool/ that a workspace root copies to GUARD_DIR.

    The workspace hook needs the guard without a full harness; the repositories below carry their own copy.
    """
    return ["ai.py", *(f"ai_harness/{f}" for f in tree_files(paths.TEMPLATE / "tool" / "ai_harness"))]


def ensure_workspace(workspace: Path, version: dict) -> list[str]:
    if (workspace / WORKSPACE_FILE).is_file():
        return []
    workspace.mkdir(parents=True, exist_ok=True)
    # Initialized first: a .git without the files is completed by the next run, files without workspace.json block it.
    init_repo(workspace, "main")
    created = tree_files(paths.WORKSPACE_TEMPLATE)
    manifest = workspace / WORKSPACE_FILE
    with Staging() as stage:
        for relative in created:
            stage.copy(paths.WORKSPACE_TEMPLATE / relative, workspace / relative)
        for relative in guard_files():
            stage.copy(paths.TEMPLATE / "tool" / relative, workspace / GUARD_DIR / relative)
        stage.write(manifest, manifest_bytes(manifest, "workspace", {"schemaVersion": 1, "starter": version, "repos": []}))
    return [*created, GUARD_DIR + "/", WORKSPACE_FILE]


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip() or "-"


def render_repos(workspace: Path, repos: list[dict]) -> str:
    if not repos:
        return "No repositories yet."
    rows = ["| Repository | Path | Role | Harness | Remote |", "| --- | --- | --- | --- | --- |"]
    for repo in repos:
        rows.append(f"| {_cell(repo['name'])} | `{repo['path']}/` | {_cell(repo.get('role', ''))} | {repo_kind(workspace, repo)} | {_cell(repo.get('remote', ''))} |")
    return "\n".join(rows)


def _agents_with_table(workspace: Path, repos: list[dict]) -> tuple[bytes | None, str | None]:
    """The workspace AGENTS.md with its generated table rewritten, or a warning when the markers are gone."""
    path = workspace / "AGENTS.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    start, end = text.find(REPOS_START), text.find(REPOS_END)
    if start == -1 or end < start:
        return None, f"{path}: repository markers are missing; the table was not updated. Restore {REPOS_START} and {REPOS_END}."
    body = f"{REPOS_START}\n{render_repos(workspace, repos)}\n"
    return (text[:start] + body + text[end:]).encode("utf-8"), None


def sync_agents(workspace: Path, repos: list[dict]) -> str | None:
    """Rewrites the generated table in the workspace AGENTS.md. Returns a warning when the markers are gone."""
    data, warning = _agents_with_table(workspace, repos)
    if data is not None:
        write_atomic(workspace / "AGENTS.md", data)
    return warning


def entry_at(manifest: dict | None, path: str) -> dict | None:
    return next((r for r in (manifest or {}).get("repos", []) if r["path"] == path), None)


def register(workspace: Path, entry: dict) -> list[str]:
    """Adds the entry, or replaces the one at the same path when a registered repository gets the harness."""
    manifest = load_workspace(workspace)
    repos = manifest["repos"]
    index = next((i for i, r in enumerate(repos) if r["path"] == entry["path"]), None)
    if index is None:
        repos.append(entry)
    else:
        repos[index] = entry
    return _save_repos(workspace, manifest)


def unregister(workspace: Path, name: str) -> tuple[dict, list[str]]:
    """Removes the named entry from workspace.json and the table. The repository folder is never touched."""
    manifest = load_workspace(workspace)
    repos = manifest["repos"]
    entry = next((r for r in repos if r["name"] == name), None)
    if entry is None:
        known = [r["name"] for r in repos]
        raise StarterError(f"The workspace has no repository named {name!r}; registered: {known}.")
    repos.remove(entry)
    return entry, _save_repos(workspace, manifest)


def _save_repos(workspace: Path, manifest: dict) -> list[str]:
    """Writes workspace.json and the table together; missing table markers only cost a warning."""
    agents, warning = _agents_with_table(workspace, manifest["repos"])
    with Staging() as stage:
        stage.write(workspace / WORKSPACE_FILE, manifest_bytes(workspace / WORKSPACE_FILE, "workspace", manifest))
        if agents is not None:
            stage.write(workspace / "AGENTS.md", agents)
    return [warning] if warning else []
