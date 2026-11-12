"""Where the starter lives, the names of the files it keeps state in, and path checks.

Other modules read STARTER, TEMPLATE, WORKSPACE_TEMPLATE, and SCHEMAS as `paths.<NAME>` at call time rather than
importing them by name, so that tests can point them at a throwaway copy of the starter.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

STARTER = Path(__file__).resolve().parents[2]
TEMPLATE = STARTER / "template"
WORKSPACE_TEMPLATE = STARTER / "workspace-template"
SCHEMAS = STARTER / "tool" / "schemas"

WORKSPACE_FILE = "workspace.json"
HARNESS_RECORD = ".ai/harness.json"
GUARD_DIR = ".ai/guard"


class StarterError(Exception):
    pass


WORKSPACE_TOOL = ".ai/workspace.py"


def workspace_tool() -> ModuleType:
    """The workspace's own command module, workspace-template/.ai/workspace.py, which a workspace runs without this starter.

    The starter runs the same code for `workspace clone` and for registering, unregistering, and the repository table,
    so the two never drift. Loaded from WORKSPACE_TEMPLATE at call time.
    """
    source = WORKSPACE_TEMPLATE / WORKSPACE_TOOL
    name = f"ai_starter_workspace_tool_{abs(hash(str(source)))}"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def resolve_workspace(raw: str) -> Path:
    workspace = Path(raw).expanduser().resolve()
    if workspace == STARTER or STARTER in workspace.parents:
        raise StarterError(f"The workspace must be outside the starter ({STARTER}).")
    if workspace.exists() and not workspace.is_dir():
        raise StarterError(f"{workspace} exists and is not a directory.")
    return workspace


def resolve_repo(raw: str) -> Path:
    """An existing git repository outside the starter, inside a workspace or not."""
    repo = Path(raw).expanduser().resolve()
    if repo == STARTER or STARTER in repo.parents:
        raise StarterError(f"The repository must be outside the starter ({STARTER}).")
    if not (repo / ".git").exists():
        raise StarterError(f"{repo} is not a git repository.")
    return repo


def clean_relative(raw: str) -> str | None:
    parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".")]
    if raw.startswith("/") or not parts or ".." in parts:
        return None
    return "/".join(parts)


def relative_path(raw: str) -> str:
    clean = clean_relative(raw)
    if clean is None:
        raise StarterError(f"--path must be a folder inside the workspace, relative to it: {raw!r}")
    return clean
