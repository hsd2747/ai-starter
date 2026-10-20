"""Command-line interface: argument parsing, the JSON report, and the commands other than upgrade."""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
import uuid
from pathlib import Path

from . import paths, upgrade
from .files import tree_files
from .gitutil import git, init_repo, starter_version, version_warnings
from .install import base_branch, existing_instructions, install, install_conflicts
from .manifests import load_manifest, write_manifest
from .paths import HARNESS_RECORD, WORKSPACE_FILE, StarterError, relative_path, resolve_repo, resolve_workspace
from .registry import describe_workspace, load_registry, registry_path, remember_workspace
from .workspace import (check_new_entry, check_workspace_free, ensure_workspace, entry_at, load_workspace, register, repo_kind,
                        sync_agents, unregister)

USAGE = """\
python3 tool/starter.py <command>

Workspace: which repositories a workspace lists, their roles, and the workspace root's own files.

  adopt --workspace PATH --path REL [--name NAME] [--role TEXT] [--remote URL] [--install]
        Register an existing repository inside the workspace; no file in it is touched.
        --install also runs `harness install` on it first, so a registered repository can get the harness this way too.
  unregister --workspace PATH --name NAME
        Remove a repository from workspace.json and the workspace table. The folder and every file in it stay as they are,
        an installed harness included; `harness upgrade` still reaches it.
  sync  --workspace PATH
        Rewrite the repository table in the workspace AGENTS.md from workspace.json, after editing roles or remotes there.
        The Harness column is read from each repository's .ai/harness.json.
  workspace list | add --path PATH | remove --path PATH
        The saved workspace list (~/.claude/ai-starter/workspaces.json, or $AI_STARTER_REGISTRY), most recent first.
        new, adopt, unregister, sync, and upgrade record their workspace there. remove only forgets the entry; it never touches the folder.

Harness: the starter files inside one repository, whether or not a workspace lists it. Nothing outside --repo is written.

  harness install --repo PATH
        Copy the harness into an existing git repository. Any existing harness file stops the command before it writes;
        only .gitignore and .gitattributes are merged by appending missing lines.
  harness upgrade --repo PATH [--dry-run]
        Bring starter changes into the repository with a 3-way merge per harness file against the starter commit it recorded.
  harness status --repo PATH
        Whether the repository has the harness and the starter commit it recorded. Before an install, also the harness files that
        would conflict and existingInstructions: other agent tools' rule files, files named *.pre-harness.*, and the repository's own
        entries under .claude/, .agents/, and .gemini/. These are never changed; install and adopt --install report them too.

Both:

  new   --workspace PATH --name NAME [--role TEXT] [--remote URL]
        Create PATH/NAME with the harness, register it, and initialize the workspace on first use.
  upgrade --workspace PATH [--name NAME ...] [--dry-run]
        Upgrade the workspace root and every listed repository that has the harness, or only the named repositories.
        Every file it would write must be committed and unmodified; otherwise nothing is written. Conflicts are left as markers and listed.

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
    warnings += register(workspace, {"name": args.name, "path": args.name, "role": args.role, "remote": args.remote})
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
    previous = entry_at(manifest, relative) if args.install else None
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
        _refuse_conflicts(repo, files)
        instructions = existing_instructions(repo, files)
    check_workspace_free(workspace)

    version = starter_version()
    created = ensure_workspace(workspace, version)
    merged = install(repo, files, "adopt", version) if args.install else []
    kind = repo_kind(workspace, {"path": relative})
    warnings = version_warnings(version) if args.install else []
    role = args.role or (previous or {}).get("role", "")
    remote = args.remote or (previous or {}).get("remote", "")
    warnings += register(workspace, {"name": name, "path": relative, "role": role, "remote": remote})
    warnings += remember_workspace(workspace)
    report = {"ok": True, "workspace": str(workspace), "workspaceCreated": created, "repository": str(repo), "kind": kind, "warnings": warnings}
    if args.install:
        report["filesInstalled"] = len(files)
        report["merged"] = merged
        report["existingInstructions"] = instructions
        report["next"] = (f"Open an agent session in {repo} and ask it to onboard the existing codebase. "
                          "Review the added files with git status; nothing was committed.")
    return report


def cmd_unregister(args: argparse.Namespace) -> dict:
    workspace = resolve_workspace(args.workspace)
    if load_workspace(workspace) is None:
        raise StarterError(f"{workspace} has no {WORKSPACE_FILE}.")
    entry, warnings = unregister(workspace, args.name)
    warnings += remember_workspace(workspace)
    return {"ok": True, "workspace": str(workspace), "removed": entry, "repository": str(workspace / entry["path"]), "warnings": warnings,
            "note": "Only the workspace entry was removed; the repository folder is untouched. Nothing was committed."}


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


def _refuse_conflicts(repo: Path, files: list[str]) -> None:
    conflicts = install_conflicts(repo, files)
    if conflicts:
        raise StarterError(f"{repo} already has harness files; nothing was written. Merge or move these first: {conflicts}")


def cmd_harness(args: argparse.Namespace) -> dict:
    if args.dry_run and args.action != "upgrade":
        raise StarterError("--dry-run applies only to `harness upgrade`.")
    if args.action == "upgrade":
        return upgrade.run_repository(args.repo, args.dry_run)
    repo = resolve_repo(args.repo)
    record_path = repo / HARNESS_RECORD
    files = tree_files(paths.TEMPLATE)
    instructions = existing_instructions(repo, files)
    if args.action == "status":
        if not record_path.is_file():
            return {"ok": True, "repository": str(repo), "installed": False, "conflicts": install_conflicts(repo, files),
                    "existingInstructions": instructions}
        record = load_manifest(record_path, "harness")
        current = starter_version()
        return {"ok": True, "repository": str(repo), "installed": True, "mode": record["mode"], "installedAt": record["installedAt"],
                "upgradedAt": record.get("upgradedAt"), "starter": record["starter"], "currentStarter": current,
                "upToDate": record["starter"]["commit"] is not None and record["starter"]["commit"] == current["commit"],
                "existingInstructions": instructions}
    _refuse_conflicts(repo, files)
    version = starter_version()
    merged = install(repo, files, "adopt", version)
    return {"ok": True, "repository": str(repo), "filesInstalled": len(files), "merged": merged, "existingInstructions": instructions,
            "warnings": version_warnings(version),
            "next": (f"Open an agent session in {repo} and ask it to onboard the existing codebase. If a workspace lists this repository, "
                     "run `sync --workspace <path>` so that its table shows the harness. Review the added files with git status; nothing was committed.")}


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
    unregister = sub.add_parser("unregister", add_help=False)
    unregister.add_argument("--workspace", required=True)
    unregister.add_argument("--name", required=True)
    sync = sub.add_parser("sync", add_help=False)
    sync.add_argument("--workspace", required=True)
    upgrade = sub.add_parser("upgrade", add_help=False)
    upgrade.add_argument("--workspace", required=True)
    upgrade.add_argument("--name", action="append", default=[])
    upgrade.add_argument("--dry-run", action="store_true")
    harness = sub.add_parser("harness", add_help=False)
    harness.add_argument("action", choices=["install", "upgrade", "status"])
    harness.add_argument("--repo", required=True)
    harness.add_argument("--dry-run", action="store_true")
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
        report = {"new": cmd_new, "adopt": cmd_adopt, "unregister": cmd_unregister, "sync": cmd_sync, "upgrade": cmd_upgrade, "harness": cmd_harness,
                  "workspace": cmd_workspace}[args.command](args)
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
