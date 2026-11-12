#!/usr/bin/env python3
"""Workspace commands that need only this workspace repository, not the ai-starter that created it.

    python3 .ai/workspace.py clone [--name NAME ...]

`clone` clones every repository that workspace.json lists and that is not here yet, from its `remote`, into its `path`,
and connects the pre-commit verify hook in the ones that have the ai-starter harness, because a clone does not carry
that git setting. A repository that is already here is never touched, an entry without a remote is skipped, and a path
that holds something other than a git repository stops the command before it clones anything. Run it again after a
pull that lists new repositories. The workspace is the folder above this file. Output is JSON; exit code 1 on an error.

Python 3.10+, standard library only. ai-starter's `workspace clone` runs this same code, so change it only here.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

WORKSPACE = Path(__file__).resolve().parents[1]
WORKSPACE_FILE = "workspace.json"
HARNESS_RECORD = ".ai/harness.json"


class WorkspaceError(Exception):
    pass


def split_credentials(url: str) -> tuple[str, bool]:
    """The URL without secrets in its user part, and whether it had any.

    Over http(s) the whole user part is a credential (a token or user:password); for ssh-style URLs only a password is, so
    `ssh://git@host/...` and `git@host:org/repo.git` stay as they are.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url, False
    if not parts.scheme or "@" not in parts.netloc:
        return url, False
    userinfo, host = parts.netloc.rsplit("@", 1)
    if parts.scheme.lower() in ("http", "https"):
        return urlunsplit(parts._replace(netloc=host)), True
    if ":" in userinfo:
        return urlunsplit(parts._replace(netloc=userinfo.split(":", 1)[0] + "@" + host)), True
    return url, False


def has_credentials(url: str) -> bool:
    return split_credentials(url)[1]


def _clean_relative(raw: str) -> str | None:
    parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".")]
    if raw.startswith("/") or not parts or ".." in parts:
        return None
    return "/".join(parts)


def load_repos(workspace: Path) -> list[dict]:
    """The repository entries of workspace.json, checked for what cloning needs. ai-starter checks the full schema itself."""
    path = workspace / WORKSPACE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkspaceError(f"Cannot read {path}: {error}") from None
    repos = data.get("repos") if isinstance(data, dict) else None
    if not isinstance(repos, list):
        raise WorkspaceError(f"{path} has no repos list.")
    for repo in repos:
        if not (isinstance(repo, dict) and isinstance(repo.get("name"), str) and isinstance(repo.get("path"), str)
                and isinstance(repo.get("remote", ""), str)):
            raise WorkspaceError(f"{path} has an invalid repository entry: {repo!r}")
        if _clean_relative(repo["path"]) != repo["path"]:
            raise WorkspaceError(f"{path} gives {repo['name']!r} the path {repo['path']!r}; use a folder inside the workspace, relative to it.")
    return repos


def _git(cwd: Path, *args: str) -> None:
    """Runs git without a terminal prompt, so that missing credentials fail instead of waiting for input."""
    try:
        process = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                 env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except FileNotFoundError:
        raise WorkspaceError("git is not installed or not on PATH.") from None
    if process.returncode != 0:
        raise WorkspaceError(f"git {' '.join(args)} failed: {process.stderr.strip()}")


def clone_into(url: str, parent: Path) -> Path:
    """Clones into a new temporary folder inside `parent` and returns it; the caller moves it into place. git removes a failed clone."""
    temp = parent / f".clone.{uuid.uuid4().hex[:12]}.starter-tmp"
    _git(parent, "clone", "-q", url, temp.name)
    return temp


def _plan(workspace: Path, repos: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    present, to_clone, skipped, blocked = [], [], [], []
    for repo in repos:
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
        raise WorkspaceError(f"These paths already hold something that is not a git repository; nothing was cloned. Move them first: {blocked}")
    return present, to_clone, skipped


def connect_hooks(repo: Path) -> tuple[dict, list[str]]:
    """Runs the repository's own `tool/ai.py hooks install`; only its local git config changes. A failure is a warning."""
    process = subprocess.run([sys.executable, "tool/ai.py", "hooks", "install"], cwd=repo, capture_output=True, text=True,
                             env={**os.environ, "AI_HARNESS_ROOT": str(repo)})
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError:
        report = {"ok": False, "problem": f"hooks install did not report: {process.stderr.strip() or process.stdout.strip()}"}
    if report.get("ok"):
        return report, []
    problem = report.get("problem") or report.get("error") or "unknown"
    return report, [f"{repo.name}: the pre-commit verify hook is not connected: {problem}"]


def clone(workspace: Path, names: list[str]) -> dict:
    repos = load_repos(workspace)
    unknown = sorted(set(names) - {r["name"] for r in repos})
    if unknown:
        raise WorkspaceError(f"The workspace lists no repository named {unknown}; listed: {[r['name'] for r in repos]}.")
    if names:
        repos = [r for r in repos if r["name"] in names]
    present, to_clone, skipped = _plan(workspace, repos)

    cloned, warnings = [], []
    for repo in to_clone:
        target = workspace / repo["path"]
        temp = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = clone_into(repo["remote"], target.parent)
            if target.exists():
                target.rmdir()
            temp.rename(target)
        except (WorkspaceError, OSError) as error:
            if temp is not None and temp.exists():
                shutil.rmtree(temp, ignore_errors=True)
            raise WorkspaceError(f"Cloning {repo['name']!r} failed: {error}. Already cloned: {[c['name'] for c in cloned] or 'none'}. "
                                 "Fix the cause and run the command again; finished repositories are kept and skipped.") from None
        entry = {"name": repo["name"], "path": repo["path"], "harness": (target / HARNESS_RECORD).is_file()}
        if entry["harness"]:
            entry["hooks"], hook_warnings = connect_hooks(target)
            warnings += hook_warnings
        cloned.append(entry)
    return {"ok": True, "workspace": str(workspace), "cloned": cloned, "present": [r["name"] for r in present],
            "skipped": skipped, "warnings": warnings,
            "next": "Each repository's own setup (dependencies, local config from its examples) is still to do; see its README or AGENTS.md."}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 .ai/workspace.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    clone_parser = sub.add_parser("clone", help="clone the listed repositories that are not here yet")
    clone_parser.add_argument("--name", action="append", default=[], help="only this repository; repeat for more")
    args = parser.parse_args(argv)
    try:
        report = clone(WORKSPACE, args.name)
    except WorkspaceError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
