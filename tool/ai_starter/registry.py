"""The saved workspace list that the starter skills read to find the user's workspaces."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from .manifests import load_manifest, write_manifest
from .paths import WORKSPACE_FILE, StarterError
from .workspace import load_workspace, repo_kind

# The starter skills read this list to find the user's workspaces. It is the one file written outside a workspace.
REGISTRY_ENV = "AI_STARTER_REGISTRY"


def registry_path() -> Path:
    raw = os.environ.get(REGISTRY_ENV)
    return Path(raw).expanduser() if raw else Path.home() / ".claude" / "ai-starter" / "workspaces.json"


def load_registry() -> dict:
    path = registry_path()
    if not path.is_file():
        return {"schemaVersion": 1, "workspaces": []}
    return load_manifest(path, "registry")


def remember_workspace(workspace: Path) -> list[str]:
    """Moves the workspace to the top of the saved list. A failure is only a warning: the workspace itself is complete."""
    try:
        data = load_registry()
        entries = [w for w in data["workspaces"] if w["path"] != str(workspace)]
        data["workspaces"] = [{"path": str(workspace), "lastUsed": date.today().isoformat()}, *entries]
        write_manifest(registry_path(), "registry", data)
    except (StarterError, OSError) as error:
        return [f"The workspace was not saved to the workspace list: {error}"]
    return []


def describe_workspace(entry: dict) -> dict:
    path = Path(entry["path"])
    info = {"path": str(path), "lastUsed": entry["lastUsed"], "exists": path.is_dir(), "initialized": False, "repos": []}
    if (path / WORKSPACE_FILE).is_file():
        try:
            manifest = load_workspace(path)
            info["initialized"] = True
            info["repos"] = [{"name": r["name"], "path": r["path"], "kind": repo_kind(path, r), "role": r.get("role", "")} for r in manifest["repos"]]
        except StarterError as error:
            info["error"] = str(error)
    return info
