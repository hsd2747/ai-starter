"""A workspace root: its files, workspace.json, and the generated repository table in its AGENTS.md.

Registering, unregistering, and the table are the workspace's own code in workspace-template/.ai/workspace.py, so that a
teammate can run them without this starter. This module adds the full schema check and writes through Staging.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from . import paths
from .files import Staging, tree_files, write_atomic
from .gitutil import init_repo
from .manifests import load_manifest, manifest_bytes
from .paths import GUARD_DIR, WORKSPACE_FILE, StarterError



@contextlib.contextmanager
def _tool_errors():
    """The workspace tool's errors as StarterError, which the CLI reports."""
    tool = paths.workspace_tool()
    try:
        yield tool
    except tool.WorkspaceError as error:
        raise StarterError(str(error)) from None


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
    return paths.workspace_tool().repo_kind(workspace, repo)


def check_new_entry(manifest: dict | None, name: str, path: str) -> None:
    with _tool_errors() as tool:
        tool.check_new_entry(manifest, name, path)


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


def _agents_with_table(workspace: Path, repos: list[dict]) -> tuple[bytes | None, str | None]:
    """The workspace AGENTS.md with its generated table rewritten, or a warning when the markers are gone."""
    text, warning = paths.workspace_tool().agents_with_table(workspace, repos)
    return (None if text is None else text.encode("utf-8")), warning


def sync_agents(workspace: Path, repos: list[dict]) -> str | None:
    """Rewrites the generated table in the workspace AGENTS.md. Returns a warning when the markers are gone."""
    data, warning = _agents_with_table(workspace, repos)
    if data is not None:
        write_atomic(workspace / "AGENTS.md", data)
    return warning


def entry_at(manifest: dict | None, path: str) -> dict | None:
    return paths.workspace_tool().entry_at(manifest, path)


def register(workspace: Path, entry: dict) -> list[str]:
    """Adds the entry, or replaces the one at the same path when a registered repository gets the harness."""
    return _save_repos(workspace, paths.workspace_tool().with_repo(load_workspace(workspace), entry))


def unregister(workspace: Path, name: str) -> tuple[dict, list[str]]:
    """Removes the named entry from workspace.json and the table. The repository folder is never touched."""
    with _tool_errors() as tool:
        manifest, entry = tool.without_repo(load_workspace(workspace), name)
    return entry, _save_repos(workspace, manifest)


def _save_repos(workspace: Path, manifest: dict) -> list[str]:
    """Writes workspace.json and the table together; missing table markers only cost a warning."""
    agents, warning = _agents_with_table(workspace, manifest["repos"])
    with Staging() as stage:
        stage.write(workspace / WORKSPACE_FILE, manifest_bytes(workspace / WORKSPACE_FILE, "workspace", manifest))
        if agents is not None:
            stage.write(workspace / "AGENTS.md", agents)
    return [warning] if warning else []
