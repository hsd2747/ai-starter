#!/usr/bin/env python3
"""Workspace commands that need only this workspace repository, not the ai-starter that created it.

    python3 .ai/workspace.py clone [--team TEAM] [--name NAME ...]
    python3 .ai/workspace.py local --team TEAM
    python3 .ai/workspace.py check

`clone` clones every repository that workspace.json lists and that is not here yet, from its `remote`, into its `path`,
and connects the pre-commit verify hook in the ones that have the ai-starter harness, because a clone does not carry
that git setting. A repository that is already here is never touched and an entry without a remote is skipped. A clone
that fails, for example on a repository the user has no access to, is reported under `failed` and the others go on.
A path that holds something other than a git repository stops the command before it clones anything. Run it again
after a pull that lists new repositories. With --team it also runs `local`.

`local` keeps the user's personal settings in CLAUDE.local.md at the workspace root: ignored by git, loaded by Claude Code
in every session there, and read by other agents as AGENTS.md says. It is made from .ai/CLAUDE.local.example.md the
first time; later only its `Team:` line is changed. `check` reports personal files that git tracks and a missing team.

The workspace is the folder above this file. Output is JSON; exit code 1 on an error.
Python 3.10+, standard library only. ai-starter's `workspace clone` runs this same code, so change it only here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

WORKSPACE = Path(__file__).resolve().parents[1]
WORKSPACE_FILE = "workspace.json"
HARNESS_RECORD = ".ai/harness.json"
LOCAL_FILE = "CLAUDE.local.md"
LOCAL_EXAMPLE = ".ai/CLAUDE.local.example.md"
# Files that hold one person's settings. They are ignored by the workspace .gitignore and must never be committed.
PERSONAL_FILES = [LOCAL_FILE, ".claude/settings.local.json"]
TEAM_LINE = re.compile(r"^Team:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
TEAM_NAME = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")


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


def load_manifest(workspace: Path) -> dict:
    """workspace.json, checked for what these commands need. ai-starter checks the full schema itself."""
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
    teams = data.get("teams", [])
    if not (isinstance(teams, list) and all(isinstance(t, str) and TEAM_NAME.match(t) for t in teams)):
        raise WorkspaceError(f"{path} has an invalid teams list: {teams!r}")
    return data


def load_repos(workspace: Path) -> list[dict]:
    return load_manifest(workspace)["repos"]


def _git(cwd: Path, *args: str) -> str:
    """Runs git without a terminal prompt, so that missing credentials fail instead of waiting for input."""
    try:
        process = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                 env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except FileNotFoundError:
        raise WorkspaceError("git is not installed or not on PATH.") from None
    if process.returncode != 0:
        raise WorkspaceError(f"git {' '.join(args)} failed: {process.stderr.strip()}")
    return process.stdout


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


def _clone_one(workspace: Path, repo: dict) -> None:
    target = workspace / repo["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = clone_into(repo["remote"], target.parent)
    try:
        if target.exists():
            target.rmdir()
        temp.rename(target)
    except OSError:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def clone(workspace: Path, names: list[str], team: str = "") -> dict:
    """Clones what is missing. With `team`, the team is checked before any clone and recorded in CLAUDE.local.md after."""
    manifest = load_manifest(workspace)
    if team:
        _check_team(manifest, team)
    repos = manifest["repos"]
    unknown = sorted(set(names) - {r["name"] for r in repos})
    if unknown:
        raise WorkspaceError(f"The workspace lists no repository named {unknown}; listed: {[r['name'] for r in repos]}.")
    if names:
        repos = [r for r in repos if r["name"] in names]
    present, to_clone, skipped = _plan(workspace, repos)

    cloned, failed, warnings = [], [], []
    for repo in to_clone:
        try:
            _clone_one(workspace, repo)
        except (WorkspaceError, OSError) as error:
            # Access differs per person and team, so one repository out of reach must not stop the others.
            failed.append({"name": repo["name"], "remote": repo["remote"], "error": str(error)})
            continue
        target = workspace / repo["path"]
        entry = {"name": repo["name"], "path": repo["path"], "harness": (target / HARNESS_RECORD).is_file()}
        if entry["harness"]:
            entry["hooks"], hook_warnings = connect_hooks(target)
            warnings += hook_warnings
        cloned.append(entry)
    if failed:
        warnings.append(f"{len(failed)} repositories could not be cloned, often for lack of access. "
                        "Check access with `git ls-remote <remote>`, ask for it if needed, and run clone again.")
    report = {"ok": True, "workspace": str(workspace), "cloned": cloned, "present": [r["name"] for r in present],
              "skipped": skipped, "failed": failed, "warnings": warnings,
              "next": "Each repository's own setup (dependencies, local config from its examples) is still to do; see its README or AGENTS.md."}
    if team:
        report["local"] = set_local_team(workspace, team)
    elif not _local_team(workspace):
        report["warnings"].append(f"No team is recorded in {LOCAL_FILE}; run `python3 .ai/workspace.py local --team <team>`.")
    return report


def _check_team(manifest: dict, team: str) -> None:
    teams = manifest.get("teams", [])
    if not TEAM_NAME.match(team):
        raise WorkspaceError(f"Invalid team {team!r}: lowercase letters, digits, and '-'.")
    if teams and team not in teams:
        raise WorkspaceError(f"Unknown team {team!r}; workspace.json lists {teams}.")


def _local_team(workspace: Path) -> str:
    path = workspace / LOCAL_FILE
    if not path.is_file():
        return ""
    match = TEAM_LINE.search(path.read_text(encoding="utf-8"))
    value = match.group(1) if match else ""
    return value if TEAM_NAME.match(value) else ""


def _write(path: Path, text: str) -> None:
    """Writes through a temporary file, so that a failure leaves the old file as it was."""
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:12]}.starter-tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def set_local_team(workspace: Path, team: str) -> dict:
    """Creates CLAUDE.local.md from the example, or changes only its Team line. Nothing else in it is ever rewritten."""
    _check_team(load_manifest(workspace), team)
    path = workspace / LOCAL_FILE
    created = not path.is_file()
    if created:
        example = workspace / LOCAL_EXAMPLE
        text = example.read_text(encoding="utf-8") if example.is_file() else "# Personal settings for this workspace\n\nTeam: <team>\n"
    else:
        text = path.read_text(encoding="utf-8")
    if TEAM_LINE.search(text):
        text = TEAM_LINE.sub(lambda _: f"Team: {team}", text, count=1)
    else:
        text = f"Team: {team}\n\n" + text
    _write(path, text)
    return {"path": str(path), "created": created, "team": team}


def check(workspace: Path) -> dict:
    manifest = load_manifest(workspace)
    problems = []
    tracked = _git(workspace, "ls-files", "--", *PERSONAL_FILES).split()
    if tracked:
        problems.append(f"Personal files are tracked by git: {tracked}. Untrack them with `git rm --cached <file>`, commit, "
                        "and keep each person's copy local.")
    team = _local_team(workspace)
    if not team:
        problems.append(f"No team is recorded in {LOCAL_FILE}; run `python3 .ai/workspace.py local --team <team>`.")
    elif manifest.get("teams") and team not in manifest["teams"]:
        problems.append(f"{LOCAL_FILE} names team {team!r}, which workspace.json does not list: {manifest['teams']}.")
    return {"ok": not problems, "workspace": str(workspace), "team": team or None, "teams": manifest.get("teams", []), "problems": problems}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 .ai/workspace.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    clone_parser = sub.add_parser("clone", help="clone the listed repositories that are not here yet")
    clone_parser.add_argument("--name", action="append", default=[], help="only this repository; repeat for more")
    clone_parser.add_argument("--team", default="", help="also record the team in CLAUDE.local.md")
    local_parser = sub.add_parser("local", help="create or update CLAUDE.local.md with the user's team")
    local_parser.add_argument("--team", required=True)
    sub.add_parser("check", help="report tracked personal files and a missing team")
    args = parser.parse_args(argv)
    try:
        if args.command == "clone":
            report = clone(WORKSPACE, args.name, args.team)
        elif args.command == "local":
            report = {"ok": True, **set_local_team(WORKSPACE, args.team)}
        else:
            report = check(WORKSPACE)
    except WorkspaceError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
