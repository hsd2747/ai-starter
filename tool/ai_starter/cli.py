"""Command-line interface: argument parsing, the JSON report, and the commands other than upgrade."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import traceback
import uuid
from pathlib import Path

from . import paths, upgrade
from .files import tree_files
from .gitutil import git, init_repo, starter_version, version_warnings
from .install import MERGED_ON_ADOPT, base_branch, install
from .manifests import write_manifest
from .paths import HARNESS_RECORD, WORKSPACE_FILE, StarterError, relative_path, resolve_workspace
from .registry import describe_workspace, load_registry, registry_path, remember_workspace
from .workspace import check_new_entry, check_workspace_free, ensure_workspace, load_workspace, register, registered_only, sync_agents

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
  upgrade --workspace PATH [--name NAME ...] [--dry-run]
        Bring starter changes into managed repositories (all of them and the workspace root, or only the named ones)
        with a 3-way merge per harness file against the starter commit each one recorded. Every file it would write must
        be committed and unmodified; otherwise nothing is written. Conflicts are left as markers and listed.
  workspace list | add --path PATH | remove --path PATH
        The saved workspace list (~/.claude/ai-starter/workspaces.json, or $AI_STARTER_REGISTRY), most recent first.
        new, adopt, and sync record their workspace there. remove only forgets the entry; it never touches the folder.

Output is JSON. Exit codes: 0 ok, 1 usage error, conflict, invalid manifest, or filesystem error,
2 unexpected error (a starter bug; the report carries the traceback).
Every write goes to a temporary file first and is moved into place only when all of a command's files are ready.
"""


def cmd_new(args: argparse.Namespace) -> dict:
    workspace = resolve_workspace(args.workspace)
    manifest = load_workspace(workspace)
    check_new_entry(manifest, args.name, args.name)
    target = workspace / args.name
    if target.exists() and any(target.iterdir()):
        raise StarterError(f"{target} already exists and is not empty. Use `adopt` for an existing repository.")
    check_workspace_free(workspace)

    version = starter_version()
    files = tree_files(paths.TEMPLATE)
    # Built under a temporary name and renamed whole, so a failure never leaves a half-made repository to block the next run.
    workspace.mkdir(parents=True, exist_ok=True)
    building = workspace / f".{args.name}.{uuid.uuid4().hex[:12]}.starter-tmp"
    building.mkdir()
    try:
        install(building, files, "new", version)
        init_repo(building, base_branch())
        if args.remote:
            git(building, "remote", "add", "origin", args.remote)
        created = ensure_workspace(workspace, version)
        if target.exists():
            target.rmdir()
        building.rename(target)
    except BaseException:
        shutil.rmtree(building, ignore_errors=True)
        raise
    warnings = version_warnings(version)
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
    workspace = resolve_workspace(args.workspace)
    relative = relative_path(args.path)
    repo = workspace / relative
    manifest = load_workspace(workspace)
    previous = registered_only(manifest, relative) if args.install else None
    if previous:
        if args.name and args.name != previous["name"]:
            raise StarterError(f"{relative!r} is registered as {previous['name']!r}; omit --name or use that name.")
        name = previous["name"]
    else:
        name = args.name or relative.rsplit("/", 1)[-1]
        check_new_entry(manifest, name, relative)
    if not (repo / ".git").exists():
        raise StarterError(f"{repo} is not a git repository.")
    files = tree_files(paths.TEMPLATE)
    if args.install:
        conflicts = [f for f in files if f not in MERGED_ON_ADOPT and os.path.lexists(repo / f)]
        if os.path.lexists(repo / HARNESS_RECORD):
            conflicts.append(HARNESS_RECORD)
        if conflicts:
            raise StarterError(f"{repo} already has harness files; nothing was written. Merge or move these first: {conflicts}")
    check_workspace_free(workspace)

    version = starter_version()
    created = ensure_workspace(workspace, version)
    merged = install(repo, files, "adopt", version) if args.install else []
    kind = "managed" if args.install else "registered"
    warnings = version_warnings(version) if args.install else []
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
    workspace = resolve_workspace(args.workspace)
    manifest = load_workspace(workspace)
    if manifest is None:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE}.")
    warning = sync_agents(workspace, manifest["repos"])
    if warning:
        raise StarterError(warning)
    return {"ok": True, "workspace": str(workspace), "repos": [r["name"] for r in manifest["repos"]], "warnings": remember_workspace(workspace)}


def cmd_upgrade(args: argparse.Namespace) -> dict:
    return upgrade.run(args.workspace, args.name, args.dry_run)


def cmd_workspace(args: argparse.Namespace) -> dict:
    if args.action == "list":
        return {"ok": True, "registry": str(registry_path()), "workspaces": [describe_workspace(w) for w in load_registry()["workspaces"]]}
    if not args.path:
        raise StarterError(f"workspace {args.action} needs --path.")
    if args.action == "add":
        workspace = resolve_workspace(args.path)
        warnings = remember_workspace(workspace)
        if warnings:
            raise StarterError(warnings[0])
        return {"ok": True, "registry": str(registry_path()), "workspace": describe_workspace(load_registry()["workspaces"][0])}
    target = str(Path(args.path).expanduser().resolve())
    data = load_registry()
    remaining = [w for w in data["workspaces"] if w["path"] != target]
    if len(remaining) == len(data["workspaces"]):
        raise StarterError(f"{target} is not in the workspace list.")
    data["workspaces"] = remaining
    write_manifest(registry_path(), "registry", data)
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
    upgrade = sub.add_parser("upgrade", add_help=False)
    upgrade.add_argument("--workspace", required=True)
    upgrade.add_argument("--name", action="append", default=[])
    upgrade.add_argument("--dry-run", action="store_true")
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
        report = {"new": cmd_new, "adopt": cmd_adopt, "sync": cmd_sync, "upgrade": cmd_upgrade, "workspace": cmd_workspace}[args.command](args)
    except StarterError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2, ensure_ascii=False))
        return 1
    except OSError as error:
        print(json.dumps({"ok": False, "kind": "filesystem", "error": str(error)}, indent=2, ensure_ascii=False))
        return 1
    except Exception as error:
        # The skills read this output as JSON; a bug must reach them as a report, not as a bare traceback.
        print(json.dumps({"ok": False, "kind": "internal", "error": f"Unexpected {type(error).__name__}: {error}. This is a starter bug.",
                          "traceback": traceback.format_exc().splitlines()}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0
