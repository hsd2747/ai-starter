"""Running git, and the starter commit that generated repositories record."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import paths
from .paths import StarterError


def git(cwd: Path, *args: str, check: bool = True, prompt: bool = True) -> str:
    """`prompt=False` makes git fail instead of asking for credentials, for commands that reach a remote."""
    env = None if prompt else {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        process = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env)
    except FileNotFoundError:
        raise StarterError("git is not installed or not on PATH.") from None
    if check and process.returncode != 0:
        raise StarterError(f"git {' '.join(args)} failed in {cwd}: {process.stderr.strip()}")
    return process.stdout.strip()


def git_ok(cwd: Path, *args: str) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True).returncode == 0


def init_repo(path: Path, branch: str) -> None:
    if not (path / ".git").exists():
        git(path, "-c", f"init.defaultBranch={branch}", "init", "-q")


def starter_version() -> dict:
    commit = git(paths.STARTER, "rev-parse", "--verify", "--quiet", "HEAD", check=False) or None
    changes = git(paths.STARTER, "status", "--porcelain", "--", "template", "workspace-template", check=False)
    return {"commit": commit, "dirty": bool(changes)}


def version_warnings(version: dict) -> list[str]:
    if version["commit"] is None:
        return ["The starter has no commit, so the version record cannot name one. Commit the starter before creating repositories you keep."]
    if version["dirty"]:
        return ["template/ or workspace-template/ has uncommitted changes; the version record names a commit that does not contain them."]
    return []


def known_commit(commit: str | None) -> bool:
    """Whether this starter's history has the commit, which `upgrade` needs as the base of its 3-way merge."""
    return commit is not None and git_ok(paths.STARTER, "cat-file", "-e", f"{commit}^{{commit}}")


def _split_credentials(url: str) -> tuple[str, bool]:
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
    return _split_credentials(url)[1]


def check_remote(url: str) -> str:
    """A remote URL given on the command line. workspace.json is shared with the team, so a URL that carries a secret is refused."""
    if has_credentials(url):
        raise StarterError("--remote contains credentials (a token or password in the URL). Give the URL without them; "
                           "workspace.json is committed and shared.")
    return url


def origin_url(repo: Path) -> tuple[str, list[str]]:
    """The repository's origin remote with any credentials removed, for workspace.json; empty when it has none."""
    url = git(repo, "remote", "get-url", "origin", check=False)
    clean, stripped = _split_credentials(url)
    warnings = [f"The origin URL of {repo} contains credentials; workspace.json records it without them. "
                "Consider moving them to a credential helper."] if stripped else []
    return clean, warnings
