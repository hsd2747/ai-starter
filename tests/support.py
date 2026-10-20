"""Helpers shared by the generator tests.

Test modules import the generator from here (`from support import cli, ...`), so tool/ is on sys.path before any of them loads it.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tool"))

from ai_starter import cli, files, merge, paths, policy  # noqa: E402
from ai_starter.registry import REGISTRY_ENV  # noqa: E402

__all__ = ["cli", "files", "merge", "paths", "policy", "run", "snapshot", "work_tree", "leftovers", "git_repo", "git", "commit_all",
           "WorkspaceCase", "UpgradeCase"]


def run(*argv: str) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, json.loads(out.getvalue())


def snapshot(root: Path) -> dict[str, str]:
    return {f: files.file_hash(root / f) for f in files.tree_files(root)} if root.exists() else {}


def work_tree(root: Path) -> dict[str, str]:
    return {f: h for f, h in snapshot(root).items() if not (f.startswith(".git/") or "/.git/" in f)}


def leftovers(root: Path) -> list[str]:
    return [str(p) for p in root.rglob("*.starter-tmp")]


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return path


def git(cwd: Path, *args: str) -> str:
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]
    return subprocess.run(["git", *identity, *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def commit_all(cwd: Path) -> None:
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", "change")


class WorkspaceCase(unittest.TestCase):
    """A temporary workspace and saved list; fails if a test changed the starter's templates."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ai-starter-"))
        self.ws = self.base / "product"
        self.registry = self.base / "home" / "workspaces.json"
        self._saved_registry = os.environ.get(REGISTRY_ENV)
        os.environ[REGISTRY_ENV] = str(self.registry)
        self.template_before = snapshot(paths.TEMPLATE)
        self.workspace_template_before = snapshot(paths.WORKSPACE_TEMPLATE)

    def tearDown(self):
        if self._saved_registry is None:
            os.environ.pop(REGISTRY_ENV, None)
        else:
            os.environ[REGISTRY_ENV] = self._saved_registry
        self.assertEqual(snapshot(paths.TEMPLATE), self.template_before, "the starter template must never change")
        self.assertEqual(snapshot(paths.WORKSPACE_TEMPLATE), self.workspace_template_before)
        shutil.rmtree(self.base, ignore_errors=True)

    def manifest(self) -> dict:
        return json.loads((self.ws / "workspace.json").read_text(encoding="utf-8"))


class UpgradeCase(unittest.TestCase):
    """Runs against a throwaway copy of the starter so that the template can change between two commits."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ai-starter-upgrade-"))
        self.fake = self.base / "starter"
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
        for folder in ("template", "workspace-template"):
            shutil.copytree(paths.STARTER / folder, self.fake / folder, symlinks=True, ignore=ignore)
        git(self.fake, "init", "-q")
        commit_all(self.fake)
        self.saved = (paths.STARTER, paths.TEMPLATE, paths.WORKSPACE_TEMPLATE, os.environ.get(REGISTRY_ENV))
        paths.STARTER, paths.TEMPLATE, paths.WORKSPACE_TEMPLATE = self.fake, self.fake / "template", self.fake / "workspace-template"
        os.environ[REGISTRY_ENV] = str(self.base / "workspaces.json")
        self.ws = self.base / "product"

    def tearDown(self):
        paths.STARTER, paths.TEMPLATE, paths.WORKSPACE_TEMPLATE, registry = self.saved
        if registry is None:
            os.environ.pop(REGISTRY_ENV, None)
        else:
            os.environ[REGISTRY_ENV] = registry
        shutil.rmtree(self.base, ignore_errors=True)

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def create(self) -> Path:
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be")[0], 0)
        commit_all(self.ws / "be")
        commit_all(self.ws)
        return self.ws / "be"

    def change_starter_for_both_targets(self) -> None:
        self.edit(self.fake / "template/tool/ai_harness/guard.py", "MAX_DEPTH = 4", "MAX_DEPTH = 5")
        self.edit(self.fake / "template/AGENTS.md", "## Goals", "## Goals\n\nNew starter line.")
        commit_all(self.fake)
