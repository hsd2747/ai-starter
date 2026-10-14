#!/usr/bin/env python3
"""ai-starter generator. Writes only into the workspace it is given and the saved workspace list; never into this starter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
TEMPLATE = STARTER / "template"
WORKSPACE_TEMPLATE = STARTER / "workspace-template"

WORKSPACE_FILE = "workspace.json"
HARNESS_RECORD = ".ai/harness.json"
GUARD_DIR = ".ai/guard"
REPOS_START = "<!-- workspace:repos:start -->"
REPOS_END = "<!-- workspace:repos:end -->"

SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_PATHS = {".ai/runs"}
# Existing repositories usually have these already; harness lines are appended instead of reported as a conflict.
MERGED_ON_ADOPT = {".gitignore", ".gitattributes"}

# The starter skills read this list to find the user's workspaces. It is the one file written outside a workspace.
REGISTRY_ENV = "AI_STARTER_REGISTRY"

REPO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")

USAGE = """\
python3 tool/starter.py <command>

  new   --workspace PATH --name NAME [--role TEXT] [--remote URL]
        Create PATH/NAME from template/, register it, and initialize the workspace on first use.
  adopt --workspace PATH --path REL [--name NAME] [--role TEXT] [--remote URL] [--install]
        Register an existing repository inside the workspace. Without --install no file in it is touched;
        with --install the harness is copied in, and any existing harness file stops the command before it writes.
        A repository registered earlier without --install can be adopted again with --install.
  sync  --workspace PATH
        Rewrite the repository table in the workspace AGENTS.md from workspace.json, after editing roles or remotes there.
  workspace list | add --path PATH | remove --path PATH
        The saved workspace list (~/.claude/ai-starter/workspaces.json, or $AI_STARTER_REGISTRY), most recent first.
        new, adopt, and sync record their workspace there. remove only forgets the entry; it never touches the folder.

Output is JSON. Exit codes: 0 ok, 1 usage error or conflict.
"""


class StarterError(Exception):
    pass


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    try:
        process = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        raise StarterError("git is not installed or not on PATH.") from None
    if check and process.returncode != 0:
        raise StarterError(f"git {' '.join(args)} failed in {cwd}: {process.stderr.strip()}")
    return process.stdout.strip()


def _skipped(relative: str) -> bool:
    parts = relative.split("/")
    return any(part in SKIP_NAMES for part in parts) or relative.endswith(".pyc") or any(
        relative == p or relative.startswith(p + "/") for p in SKIP_PATHS)


def tree_files(source: Path) -> list[str]:
    """Files and symlinks under `source` as sorted relative paths. Symlinked directories stay links."""
    found = []
    for directory, dirnames, filenames in os.walk(source):
        base = Path(directory)
        for name in list(dirnames):
            if (base / name).is_symlink():
                dirnames.remove(name)
                filenames.append(name)
        for name in filenames:
            relative = (base / name).relative_to(source).as_posix()
            if not _skipped(relative):
                found.append(relative)
        dirnames[:] = [d for d in dirnames if not _skipped((base / d).relative_to(source).as_posix())]
    return sorted(found)


def _copy(source_root: Path, relative: str, dest_root: Path) -> None:
    source, dest = source_root / relative, dest_root / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        os.symlink(os.readlink(source), dest)
    else:
        shutil.copy2(source, dest)


def file_hash(path: Path) -> str:
    data = b"link:" + os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def starter_version() -> dict:
    commit = _git(STARTER, "rev-parse", "--verify", "--quiet", "HEAD", check=False) or None
    changes = _git(STARTER, "status", "--porcelain", "--", "template", "workspace-template", check=False)
    return {"commit": commit, "dirty": bool(changes)}


def _version_warnings(version: dict) -> list[str]:
    if version["commit"] is None:
        return ["The starter has no commit, so the version record cannot name one. Commit the starter before creating repositories you keep."]
    if version["dirty"]:
        return ["template/ or workspace-template/ has uncommitted changes; the version record names a commit that does not contain them."]
    return []


def _init_repo(path: Path, branch: str) -> None:
    if not (path / ".git").exists():
        _git(path, "-c", f"init.defaultBranch={branch}", "init", "-q")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StarterError(f"Cannot read {path}: {error}") from None


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _resolve_workspace(raw: str) -> Path:
    workspace = Path(raw).expanduser().resolve()
    if workspace == STARTER or STARTER in workspace.parents:
        raise StarterError(f"The workspace must be outside the starter ({STARTER}).")
    if workspace.exists() and not workspace.is_dir():
        raise StarterError(f"{workspace} exists and is not a directory.")
    return workspace


def _relative_path(raw: str) -> str:
    parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".")]
    if raw.startswith("/") or not parts or ".." in parts:
        raise StarterError(f"--path must be a folder inside the workspace, relative to it: {raw!r}")
    return "/".join(parts)


def _load_workspace(workspace: Path) -> dict | None:
    path = workspace / WORKSPACE_FILE
    return _read_json(path) if path.is_file() else None


def _check_new_entry(manifest: dict | None, name: str, path: str) -> None:
    if not REPO_NAME.match(name):
        raise StarterError(f"Invalid repository name {name!r}: letters, digits, '.', '_', '-', up to 64 characters.")
    for repo in (manifest or {}).get("repos", []):
        if repo["name"] == name or repo["path"] == path:
            raise StarterError(f"The workspace already registers {repo['name']!r} at {repo['path']!r}.")


def _check_workspace_free(workspace: Path) -> None:
    """A folder without workspace.json is initialized only if none of the workspace files exist yet."""
    if (workspace / WORKSPACE_FILE).is_file():
        return
    taken = [f for f in tree_files(WORKSPACE_TEMPLATE) if os.path.lexists(workspace / f)]
    if os.path.lexists(workspace / GUARD_DIR):
        taken.append(GUARD_DIR)
    if taken:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE} but already contains {taken}; merge them by hand first.")


def ensure_workspace(workspace: Path, version: dict) -> list[str]:
    if (workspace / WORKSPACE_FILE).is_file():
        return []
    workspace.mkdir(parents=True, exist_ok=True)
    created = []
    for relative in tree_files(WORKSPACE_TEMPLATE):
        _copy(WORKSPACE_TEMPLATE, relative, workspace)
        created.append(relative)
    # The workspace hook needs the guard without a full harness; the repositories below carry their own copy.
    guard_files = ["ai.py", *(f"ai_harness/{f}" for f in tree_files(TEMPLATE / "tool" / "ai_harness"))]
    for relative in guard_files:
        _copy(TEMPLATE / "tool", relative, workspace / GUARD_DIR)
    created.append(GUARD_DIR + "/")
    _write_json(workspace / WORKSPACE_FILE, {"schemaVersion": 1, "starter": version, "repos": []})
    created.append(WORKSPACE_FILE)
    _init_repo(workspace, "main")
    return created


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip() or "-"


def render_repos(repos: list[dict]) -> str:
    if not repos:
        return "No repositories yet."
    rows = ["| Repository | Path | Role | Harness | Remote |", "| --- | --- | --- | --- | --- |"]
    for repo in repos:
        rows.append(f"| {_cell(repo['name'])} | `{repo['path']}/` | {_cell(repo.get('role', ''))} | {repo['kind']} | {_cell(repo.get('remote', ''))} |")
    return "\n".join(rows)


def sync_agents(workspace: Path, repos: list[dict]) -> str | None:
    """Rewrites the generated table in the workspace AGENTS.md. Returns a warning when the markers are gone."""
    path = workspace / "AGENTS.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    start, end = text.find(REPOS_START), text.find(REPOS_END)
    if start == -1 or end < start:
        return f"{path}: repository markers are missing; the table was not updated. Restore {REPOS_START} and {REPOS_END}."
    body = f"{REPOS_START}\n{render_repos(repos)}\n"
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")
    return None


def _registered_only(manifest: dict | None, path: str) -> dict | None:
    return next((r for r in (manifest or {}).get("repos", []) if r["path"] == path and r["kind"] == "registered"), None)


def register(workspace: Path, entry: dict) -> list[str]:
    """Adds the entry, or replaces the one at the same path when a registered repository gets the harness."""
    manifest = _read_json(workspace / WORKSPACE_FILE)
    repos = manifest["repos"]
    index = next((i for i, r in enumerate(repos) if r["path"] == entry["path"]), None)
    if index is None:
        repos.append(entry)
    else:
        repos[index] = entry
    _write_json(workspace / WORKSPACE_FILE, manifest)
    warning = sync_agents(workspace, manifest["repos"])
    return [warning] if warning else []


def install(repo: Path, files: list[str], mode: str, version: dict) -> list[str]:
    merged = []
    for relative in files:
        if relative in MERGED_ON_ADOPT and os.path.lexists(repo / relative):
            if _append_missing_lines(TEMPLATE / relative, repo / relative):
                merged.append(relative)
            continue
        _copy(TEMPLATE, relative, repo)
    _write_json(repo / HARNESS_RECORD, {
        "schemaVersion": 1,
        "starter": version,
        "mode": mode,
        "installedAt": date.today().isoformat(),
        "files": {relative: file_hash(TEMPLATE / relative) for relative in files},
    })
    return merged


def _append_missing_lines(source: Path, dest: Path) -> bool:
    existing = dest.read_text(encoding="utf-8")
    present = {line.strip() for line in existing.splitlines()}
    missing = [line for line in source.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#") and line.strip() not in present]
    if not missing:
        return False
    separator = "" if existing.endswith("\n") or not existing else "\n"
    dest.write_text(existing + separator + "\n# ai-starter harness\n" + "\n".join(missing) + "\n", encoding="utf-8")
    return True


def registry_path() -> Path:
    raw = os.environ.get(REGISTRY_ENV)
    return Path(raw).expanduser() if raw else Path.home() / ".claude" / "ai-starter" / "workspaces.json"


def _load_registry() -> dict:
    path = registry_path()
    if not path.is_file():
        return {"schemaVersion": 1, "workspaces": []}
    data = _read_json(path)
    if not isinstance(data.get("workspaces"), list):
        raise StarterError(f"{path} has unexpected content; fix or delete it.")
    return data


def remember_workspace(workspace: Path) -> list[str]:
    """Moves the workspace to the top of the saved list. A failure is only a warning: the workspace itself is complete."""
    try:
        data = _load_registry()
        entries = [w for w in data["workspaces"] if w.get("path") != str(workspace)]
        data["workspaces"] = [{"path": str(workspace), "lastUsed": date.today().isoformat()}, *entries]
        _write_json(registry_path(), data)
    except (StarterError, OSError) as error:
        return [f"The workspace was not saved to the workspace list: {error}"]
    return []


def _describe_workspace(entry: dict) -> dict:
    path = Path(entry.get("path", ""))
    info = {"path": str(path), "lastUsed": entry.get("lastUsed", ""), "exists": path.is_dir(), "initialized": False, "repos": []}
    if (path / WORKSPACE_FILE).is_file():
        try:
            manifest = _read_json(path / WORKSPACE_FILE)
            info["initialized"] = True
            info["repos"] = [{k: r.get(k, "") for k in ("name", "path", "kind", "role")} for r in manifest.get("repos", [])]
        except StarterError as error:
            info["error"] = str(error)
    return info


def _base_branch() -> str:
    return _read_json(TEMPLATE / ".ai/config.json")["git"]["baseBranch"]


def cmd_new(args: argparse.Namespace) -> dict:
    workspace = _resolve_workspace(args.workspace)
    manifest = _load_workspace(workspace)
    _check_new_entry(manifest, args.name, args.name)
    target = workspace / args.name
    if target.exists() and any(target.iterdir()):
        raise StarterError(f"{target} already exists and is not empty. Use `adopt` for an existing repository.")
    _check_workspace_free(workspace)

    version = starter_version()
    created = ensure_workspace(workspace, version)
    target.mkdir(parents=True, exist_ok=True)
    files = tree_files(TEMPLATE)
    install(target, files, "new", version)
    _init_repo(target, _base_branch())
    if args.remote:
        _git(target, "remote", "add", "origin", args.remote)
    warnings = _version_warnings(version)
    warnings += register(workspace, {"name": args.name, "path": args.name, "role": args.role, "kind": "managed", "remote": args.remote})
    warnings += remember_workspace(workspace)
    return {
        "ok": True,
        "workspace": str(workspace),
        "workspaceCreated": created,
        "repository": str(target),
        "filesInstalled": len(files),
        "warnings": warnings,
        "next": f"Open an agent session in {target} and ask it to onboard the project. Nothing was committed.",
    }


def cmd_adopt(args: argparse.Namespace) -> dict:
    workspace = _resolve_workspace(args.workspace)
    relative = _relative_path(args.path)
    repo = workspace / relative
    manifest = _load_workspace(workspace)
    previous = _registered_only(manifest, relative) if args.install else None
    if previous:
        if args.name and args.name != previous["name"]:
            raise StarterError(f"{relative!r} is registered as {previous['name']!r}; omit --name or use that name.")
        name = previous["name"]
    else:
        name = args.name or relative.rsplit("/", 1)[-1]
        _check_new_entry(manifest, name, relative)
    if not (repo / ".git").exists():
        raise StarterError(f"{repo} is not a git repository.")
    files = tree_files(TEMPLATE)
    if args.install:
        conflicts = [f for f in files if f not in MERGED_ON_ADOPT and os.path.lexists(repo / f)]
        if os.path.lexists(repo / HARNESS_RECORD):
            conflicts.append(HARNESS_RECORD)
        if conflicts:
            raise StarterError(f"{repo} already has harness files; nothing was written. Merge or move these first: {conflicts}")
    _check_workspace_free(workspace)

    version = starter_version()
    created = ensure_workspace(workspace, version)
    merged = install(repo, files, "adopt", version) if args.install else []
    kind = "managed" if args.install else "registered"
    warnings = _version_warnings(version) if args.install else []
    role = args.role or (previous or {}).get("role", "")
    remote = args.remote or (previous or {}).get("remote", "")
    warnings += register(workspace, {"name": name, "path": relative, "role": role, "kind": kind, "remote": remote})
    warnings += remember_workspace(workspace)
    report = {"ok": True, "workspace": str(workspace), "workspaceCreated": created, "repository": str(repo), "kind": kind, "warnings": warnings}
    if args.install:
        report["filesInstalled"] = len(files)
        report["merged"] = merged
        report["next"] = (f"Open an agent session in {repo} and ask it to onboard the existing codebase. "
                          "Review the added files with git status; nothing was committed.")
    return report


def cmd_sync(args: argparse.Namespace) -> dict:
    workspace = _resolve_workspace(args.workspace)
    manifest = _load_workspace(workspace)
    if manifest is None:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE}.")
    for repo in manifest.get("repos", []):
        missing = [k for k in ("name", "path", "kind") if not isinstance(repo.get(k), str) or not repo[k]]
        if missing or repo["kind"] not in ("managed", "registered"):
            raise StarterError(f"{WORKSPACE_FILE}: invalid entry {repo!r}; it needs name, path, and kind managed or registered.")
    warning = sync_agents(workspace, manifest["repos"])
    if warning:
        raise StarterError(warning)
    return {"ok": True, "workspace": str(workspace), "repos": [r["name"] for r in manifest["repos"]], "warnings": remember_workspace(workspace)}


def cmd_workspace(args: argparse.Namespace) -> dict:
    if args.action == "list":
        return {"ok": True, "registry": str(registry_path()), "workspaces": [_describe_workspace(w) for w in _load_registry()["workspaces"]]}
    if not args.path:
        raise StarterError(f"workspace {args.action} needs --path.")
    if args.action == "add":
        workspace = _resolve_workspace(args.path)
        warnings = remember_workspace(workspace)
        if warnings:
            raise StarterError(warnings[0])
        return {"ok": True, "registry": str(registry_path()), "workspace": _describe_workspace(_load_registry()["workspaces"][0])}
    target = str(Path(args.path).expanduser().resolve())
    data = _load_registry()
    remaining = [w for w in data["workspaces"] if w.get("path") != target]
    if len(remaining) == len(data["workspaces"]):
        raise StarterError(f"{target} is not in the workspace list.")
    data["workspaces"] = remaining
    _write_json(registry_path(), data)
    return {"ok": True, "registry": str(registry_path()), "removed": target, "note": "Only the list entry was removed; the folder is untouched."}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool/starter.py", add_help=False)
    sub = parser.add_subparsers(dest="command")
    new = sub.add_parser("new", add_help=False)
    new.add_argument("--workspace", required=True)
    new.add_argument("--name", required=True)
    new.add_argument("--role", default="")
    new.add_argument("--remote", default="")
    adopt = sub.add_parser("adopt", add_help=False)
    adopt.add_argument("--workspace", required=True)
    adopt.add_argument("--path", required=True)
    adopt.add_argument("--name", default="")
    adopt.add_argument("--role", default="")
    adopt.add_argument("--remote", default="")
    adopt.add_argument("--install", action="store_true")
    sync = sub.add_parser("sync", add_help=False)
    sync.add_argument("--workspace", required=True)
    workspace = sub.add_parser("workspace", add_help=False)
    workspace.add_argument("action", choices=["list", "add", "remove"])
    workspace.add_argument("--path", default="")
    return parser


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("help", "--help", "-h"):
        print(USAGE)
        return 0
    try:
        args = _parser().parse_args(argv)
    except SystemExit:
        print(json.dumps({"ok": False, "error": f"Invalid arguments: {' '.join(argv)}", "usage": USAGE}, indent=2))
        return 1
    try:
        report = {"new": cmd_new, "adopt": cmd_adopt, "sync": cmd_sync, "workspace": cmd_workspace}[args.command](args)
    except StarterError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
