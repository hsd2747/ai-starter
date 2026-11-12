"""`workspace clone`: clone a shared workspace's root repository, then its repositories with the workspace's own tool.

Cloning the listed repositories is done by workspace-template/.ai/workspace.py, which every workspace carries so that a
teammate can run it without this starter. This module adds what only the starter has: cloning the root from --url,
the full schema check, warnings about starter commits it lacks, and the saved workspace list.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import paths
from .gitutil import has_credentials, known_commit
from .manifests import load_manifest
from .paths import HARNESS_RECORD, WORKSPACE_FILE, StarterError, resolve_workspace
from .registry import remember_workspace
from .workspace import load_workspace


def _clone_root(url: str, workspace: Path, names: list[str], team: str) -> None:
    """Clones the workspace repository into an empty or missing folder, and keeps it only if it holds a valid workspace.json
    that the requested names and team pass, so that a refused request leaves the folder as it was.

    The clone is made inside the workspace folder and its entries are then moved up, so nothing is written outside it.
    """
    if has_credentials(url):
        raise StarterError("--url contains credentials (a token or password in the URL). Give the URL without them.")
    if workspace.exists() and any(workspace.iterdir()):
        raise StarterError(f"{workspace} is not empty. Omit --url to clone the repositories of a workspace that is already there.")
    tool = paths.workspace_tool()
    created = not workspace.exists()
    workspace.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        try:
            temp = tool.clone_into(url, workspace)
        except tool.WorkspaceError as error:
            raise StarterError(str(error)) from None
        if load_workspace(temp) is None:
            raise StarterError(f"{url} has no {WORKSPACE_FILE} in its default branch, so it is not a workspace repository.")
        try:
            tool.plan_clone(temp, names, team)
        except tool.WorkspaceError as error:
            raise StarterError(f"{error} Nothing was kept in {workspace}.") from None
        for entry in sorted(temp.iterdir()):
            entry.rename(workspace / entry.name)
        temp.rmdir()
    except BaseException:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
        if created:
            shutil.rmtree(workspace, ignore_errors=True)
        raise


def clone_workspace(raw_path: str, url: str, names: list[str], team: str = "") -> dict:
    workspace = resolve_workspace(raw_path)
    if url:
        _clone_root(url, workspace, names, team)
    manifest = load_workspace(workspace)
    if manifest is None:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE}. Pass --url with the workspace repository to clone it first.")
    tool = paths.workspace_tool()
    try:
        report = tool.clone(workspace, names, team)
    except tool.WorkspaceError as error:
        raise StarterError(str(error)) from None

    warnings = []
    if not known_commit(manifest["starter"]["commit"]):
        warnings.append("The workspace was made from a starter commit this starter does not have; pull the starter before running upgrade.")
    for entry in report["cloned"]:
        if entry["harness"]:
            try:
                record = load_manifest(workspace / entry["path"] / HARNESS_RECORD, "harness")
            except StarterError as error:
                # The repository is cloned and usable; only this starter cannot read its record, so the report must survive.
                warnings.append(f"{entry['name']}: this starter cannot read its {HARNESS_RECORD}, often because a newer starter made it; "
                                f"pull the starter before upgrading it. {error}")
                continue
            if not known_commit(record["starter"]["commit"]):
                warnings.append(f"{entry['name']} was made from a starter commit this starter does not have; pull the starter before upgrading it.")
    report["warnings"] += warnings + remember_workspace(workspace)
    return {**report, "workspaceCloned": bool(url)}
