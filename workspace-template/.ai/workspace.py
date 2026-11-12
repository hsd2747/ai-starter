#!/usr/bin/env python3
"""Workspace commands that need only this workspace repository, not the ai-starter that created it.

    python3 .ai/workspace.py clone [--team TEAM] [--name NAME ...]
    python3 .ai/workspace.py update [--name NAME ...]
    python3 .ai/workspace.py local --team TEAM
    python3 .ai/workspace.py check [--access]
    python3 .ai/workspace.py skills sync

`clone` clones every repository that workspace.json lists and that is not here yet, from its `remote`, into its `path`,
and connects the pre-commit verify hook in the ones that have the ai-starter harness, because a clone does not carry
that git setting. A repository that is already here is never touched and an entry without a remote is skipped. A clone
that fails, for example on a repository the user has no access to, is reported under `failed` and the others go on.
A path that holds something other than a git repository stops the command before it clones anything. Run it again
after a pull that lists new repositories. With --team it also runs `local`.

`update` fast-forwards the workspace repository, clones repositories it lists since, and fast-forwards every repository here,
each on the branch it is on. It skips a repository with uncommitted changes to tracked files, a detached HEAD, or a branch without
an upstream, and reports one that cannot fast-forward. It never stashes, resets, merges, or switches branches. With --name it
updates only the named repositories, not the workspace repository.

`local` keeps the user's personal settings in CLAUDE.local.md at the workspace root: ignored by git, loaded by Claude Code
in every session there, and read by other agents as AGENTS.md says. It is made from .ai/CLAUDE.local.example.md the
first time; later only its `Team:` line is changed.

`check` reports what a new member still has to do: personal files that git tracks, no team recorded, missing tools,
listed repositories not cloned yet, and skills without a valid SKILL.md or a Claude Code link; `--access` also asks each
remote whether the user can read it. `skills sync` links every skill in .agents/skills into .claude/skills, where Claude Code
looks for them; it never deletes or overwrites.

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
# The only copy of each skill; .claude/skills holds links to it, as in repositories with the harness.
SKILLS_DIR = ".agents/skills"
CLAUDE_SKILLS_DIR = ".claude/skills"
SKILL_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
# Python that repositories with the harness need for `verify` and the commit hook; this file itself runs on 3.9.
HARNESS_PYTHON = (3, 10)
# Every session at the root loads AGENTS.md whole; past this, `check` warns. Claude Code's guidance for one instruction file.
AGENTS_LINE_LIMIT = 200


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


def _fast_forward(repo: Path) -> dict:
    """Fast-forwards the current branch from its upstream, or says why it did not. Never changes anything else."""
    def rev(*args: str) -> str:
        return _git(repo, "rev-parse", *args).strip()
    try:
        branch = rev("--abbrev-ref", "HEAD")
        if branch == "HEAD":
            return {"status": "skipped", "reason": "detached HEAD"}
        try:
            upstream = rev("--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        except WorkspaceError:
            return {"status": "skipped", "branch": branch, "reason": "the branch has no upstream"}
        if _git(repo, "status", "--porcelain", "--untracked-files=no").strip():
            return {"status": "skipped", "branch": branch, "reason": "uncommitted changes to tracked files"}
        before = rev("HEAD")
        _git(repo, "pull", "--ff-only", "--quiet")
        after = rev("HEAD")
    except WorkspaceError as error:
        return {"status": "failed", "error": f"{error}. A branch that has diverged from its upstream needs a merge or rebase by hand."}
    if before == after:
        return {"status": "up-to-date", "branch": branch, "upstream": upstream}
    return {"status": "updated", "branch": branch, "upstream": upstream, "from": before[:12], "to": after[:12]}


def update(workspace: Path, names: list[str]) -> dict:
    """Pulls the workspace repository first, so that repositories it newly lists are cloned in the same run."""
    report: dict = {"ok": True, "workspace": str(workspace)}
    if not names:
        report["root"] = _fast_forward(workspace)
    cloned = clone(workspace, names)
    repos = {r["name"]: r for r in load_repos(workspace)}
    fresh = {c["name"] for c in cloned["cloned"]}
    report["repos"] = {name: _fast_forward(workspace / repos[name]["path"]) for name in cloned["present"] if name not in fresh}
    report.update({key: cloned[key] for key in ("cloned", "skipped", "failed")})
    report["warnings"] = cloned["warnings"]
    stuck = [name for name, result in report["repos"].items() if result["status"] != "up-to-date" and result["status"] != "updated"]
    if report.get("root", {}).get("status") in ("skipped", "failed"):
        stuck.insert(0, "(workspace)")
    if stuck:
        report["warnings"].append(f"Not updated: {stuck}; see each entry's reason.")
    return report


def skill_names(workspace: Path) -> list[str]:
    base = workspace / SKILLS_DIR
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")) if base.is_dir() else []


def _link_ok(workspace: Path, name: str) -> bool:
    link = workspace / CLAUDE_SKILLS_DIR / name
    return link.exists() and link.resolve() == (workspace / SKILLS_DIR / name).resolve()


def sync_skills(workspace: Path) -> dict:
    """Creates missing .claude/skills/<name> links to .agents/skills/<name>. Never deletes or overwrites anything."""
    adapters = workspace / CLAUDE_SKILLS_DIR
    adapters.mkdir(parents=True, exist_ok=True)
    names = skill_names(workspace)
    created, conflicts = [], []
    for name in names:
        link = adapters / name
        if _link_ok(workspace, name):
            continue
        if os.path.lexists(link):
            conflicts.append(f"{CLAUDE_SKILLS_DIR}/{name}: exists but does not point at {SKILLS_DIR}/{name}")
            continue
        link.symlink_to(Path("..") / ".." / SKILLS_DIR / name, target_is_directory=True)
        created.append(f"{CLAUDE_SKILLS_DIR}/{name}")
    stale = [f"{CLAUDE_SKILLS_DIR}/{e.name}" for e in sorted(adapters.iterdir()) if e.is_symlink() and e.name not in names]
    return {"ok": not conflicts, "created": created, "conflicts": conflicts, "stale": stale}


def _frontmatter(text: str) -> dict[str, str] | None:
    """The top-level `key: value` lines of a SKILL.md frontmatter, enough to check its name and description."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fields = {}
    for line in text[4:end].splitlines():
        match = re.match(r"([A-Za-z][\w-]*):[ \t]*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip().strip("\"'")
    return fields


def skill_problems(workspace: Path) -> list[str]:
    problems = []
    for name in skill_names(workspace):
        where = f"{SKILLS_DIR}/{name}"
        if not SKILL_NAME.match(name):
            problems.append(f"{where}: use lowercase letters, digits, and '-' in a skill folder name.")
        path = workspace / where / "SKILL.md"
        if not path.is_file():
            problems.append(f"{where}: SKILL.md is missing.")
            continue
        meta = _frontmatter(path.read_text(encoding="utf-8"))
        if meta is None:
            problems.append(f"{where}/SKILL.md: starts without a --- frontmatter block.")
            continue
        if meta.get("name") != name:
            problems.append(f"{where}/SKILL.md: frontmatter name must be {name!r}, the folder name.")
        if not meta.get("description"):
            problems.append(f"{where}/SKILL.md: frontmatter needs a description, which decides when the skill is used.")
        if not _link_ok(workspace, name):
            problems.append(f"{CLAUDE_SKILLS_DIR}/{name}: link is missing, so Claude Code cannot see the skill; run `python3 .ai/workspace.py skills sync`.")
    return problems


def _git_version() -> str | None:
    try:
        return subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip() or None
    except FileNotFoundError:
        return None


def check(workspace: Path, access: bool = False) -> dict:
    """Problems block work in this workspace; warnings name what is still to do or matters only to some teams."""
    manifest = load_manifest(workspace)
    problems, warnings = [], []
    git_version = _git_version()
    if git_version is None:
        problems.append("git is not installed or not on PATH. On macOS, run `xcode-select --install`.")
    else:
        tracked = _git(workspace, "ls-files", "--", *PERSONAL_FILES).split()
        if tracked:
            problems.append(f"Personal files are tracked by git: {tracked}. Untrack them with `git rm --cached <file>`, commit, "
                            "and keep each person's copy local.")
    python = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info[:2] < HARNESS_PYTHON:
        warnings.append(f"Python {python}: repositories with the harness need {'.'.join(map(str, HARNESS_PYTHON))}+ for `verify` and the commit hook. "
                        "Install a newer Python (for example `brew install python`) if you commit in them.")
    team = _local_team(workspace)
    if not team:
        problems.append(f"No team is recorded in {LOCAL_FILE}; run `python3 .ai/workspace.py local --team <team>`.")
    elif manifest.get("teams") and team not in manifest["teams"]:
        problems.append(f"{LOCAL_FILE} names team {team!r}, which workspace.json does not list: {manifest['teams']}.")
    problems += skill_problems(workspace)
    agents = workspace / "AGENTS.md"
    if agents.is_file():
        lines = len(agents.read_text(encoding="utf-8").splitlines())
        if lines > AGENTS_LINE_LIMIT:
            warnings.append(f"AGENTS.md has {lines} lines, over {AGENTS_LINE_LIMIT}: every session here loads it whole. Move procedures that only "
                            "some tasks need into workspace skills or .ai/<topic>.md files.")

    missing = [r["name"] for r in manifest["repos"] if not (workspace / r["path"] / ".git").exists()]
    if missing:
        warnings.append(f"Not cloned yet: {missing}. Run `python3 .ai/workspace.py clone`; one you cannot access needs a grant on its remote.")
    report = {"ok": not problems, "workspace": str(workspace), "team": team or None, "teams": manifest.get("teams", []),
              "tools": {"git": git_version, "python": python}, "missing": missing, "skills": skill_names(workspace),
              "problems": problems, "warnings": warnings}
    if access and git_version is not None:
        report["access"] = {}
        for repo in manifest["repos"]:
            if not repo.get("remote") or has_credentials(repo["remote"]):
                continue
            try:
                _git(workspace, "ls-remote", "--heads", repo["remote"])
                report["access"][repo["name"]] = "ok"
            except WorkspaceError as error:
                report["access"][repo["name"]] = str(error)
                warnings.append(f"No read access to {repo['name']} ({repo['remote']}); ask for it on the remote.")
    return report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 .ai/workspace.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    clone_parser = sub.add_parser("clone", help="clone the listed repositories that are not here yet")
    clone_parser.add_argument("--name", action="append", default=[], help="only this repository; repeat for more")
    clone_parser.add_argument("--team", default="", help="also record the team in CLAUDE.local.md")
    update_parser = sub.add_parser("update", help="pull the workspace, clone new repositories, fast-forward the others")
    update_parser.add_argument("--name", action="append", default=[], help="only this repository; repeat for more")
    local_parser = sub.add_parser("local", help="create or update CLAUDE.local.md with the user's team")
    local_parser.add_argument("--team", required=True)
    check_parser = sub.add_parser("check", help="report what is still to do: team, tools, repositories, skills")
    check_parser.add_argument("--access", action="store_true", help="also check read access to every remote")
    sub.add_parser("skills").add_subparsers(dest="action", required=True).add_parser("sync", help="link .agents/skills into .claude/skills")
    args = parser.parse_args(argv)
    try:
        if args.command == "clone":
            report = clone(WORKSPACE, args.name, args.team)
        elif args.command == "update":
            report = update(WORKSPACE, args.name)
        elif args.command == "local":
            report = {"ok": True, **set_local_team(WORKSPACE, args.team)}
        elif args.command == "check":
            report = check(WORKSPACE, args.access)
        else:
            report = sync_skills(WORKSPACE)
    except WorkspaceError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
