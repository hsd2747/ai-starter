from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from support import WorkspaceCase, cli, files, paths, run, snapshot


class NewTest(WorkspaceCase):
    def test_new_creates_workspace_and_a_working_repository(self):
        code, report = run("new", "--workspace", str(self.ws), "--name", "be", "--role", "Backend API")
        self.assertEqual(code, 0, report)
        repo = self.ws / "be"

        record = json.loads((repo / ".ai/harness.json").read_text(encoding="utf-8"))
        self.assertEqual(record["mode"], "new")
        self.assertEqual(record["files"], {f: h for f, h in self.template_before.items()})
        installed = {f for f in snapshot(repo) if not f.startswith(".git/")} - {".ai/harness.json"}
        self.assertEqual(installed, self.template_before.keys())
        self.assertTrue((repo / ".git").is_dir())
        self.assertTrue((self.ws / ".git").is_dir())
        self.assertTrue((repo / ".claude/skills/repo-change/SKILL.md").is_file())

        self.assertEqual(self.manifest()["repos"], [{"name": "be", "path": "be", "role": "Backend API", "remote": ""}])
        agents = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("| be | `be/` | Backend API | managed | - |", agents)

        env = {**os.environ, "AI_HARNESS_SELF_TEST": "1"}
        doctor = subprocess.run([sys.executable, "tool/ai.py", "doctor"], cwd=repo, capture_output=True, text=True, env=env)
        self.assertEqual(doctor.returncode, 0, doctor.stdout)
        self.assertNotIn("Commits are not verified", doctor.stdout)
        self.assertTrue(report["hooks"]["installed"], report)
        self.assertEqual(subprocess.run(["git", "config", "core.hooksPath"], cwd=repo, capture_output=True, text=True).stdout.strip(), ".githooks")
        dry = subprocess.run([sys.executable, "tool/ai.py", "verify", "--dry-run"], cwd=repo, capture_output=True, text=True, env=env)
        self.assertEqual(dry.returncode, 0, dry.stdout)

    def test_workspace_repository_tracks_only_its_own_files(self):
        run("new", "--workspace", str(self.ws), "--name", "be")
        run("new", "--workspace", str(self.ws), "--name", "web")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.ws,
                                capture_output=True, text=True, check=True).stdout
        tracked = {line[3:] for line in status.splitlines()}
        self.assertFalse({p for p in tracked if p.startswith(("be/", "web/"))})
        self.assertIn("workspace.json", tracked)
        self.assertIn(".ai/guard/ai.py", tracked)

    def test_workspace_guard_blocks_env_reads(self):
        run("new", "--workspace", str(self.ws), "--name", "be")
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat be/.env"}})
        process = subprocess.run([sys.executable, str(self.ws / ".ai/guard/ai.py"), "hook", "pre-tool-use"],
                                 input=payload, capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)

    def test_duplicate_name_and_non_empty_target_are_rejected_without_writes(self):
        run("new", "--workspace", str(self.ws), "--name", "be")
        before = snapshot(self.ws)
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be")[0], 1)
        (self.ws / "web").mkdir()
        (self.ws / "web" / "notes.txt").write_text("x", encoding="utf-8")
        before["web/notes.txt"] = files.file_hash(self.ws / "web/notes.txt")
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "web")[0], 1)
        self.assertEqual(snapshot(self.ws), before)

    def test_workspace_inside_the_starter_is_rejected(self):
        code, report = run("new", "--workspace", str(paths.STARTER / "scratch-ws"), "--name", "be")
        self.assertEqual(code, 1)
        self.assertFalse((paths.STARTER / "scratch-ws").exists())

    def test_folder_with_foreign_workspace_files_is_not_initialized(self):
        self.ws.mkdir()
        (self.ws / "AGENTS.md").write_text("# Mine\n", encoding="utf-8")
        code, report = run("new", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 1)
        self.assertFalse((self.ws / "be").exists())

    def test_failed_new_leaves_nothing_behind(self):
        real_git = cli.git

        def git_without_remotes(cwd: Path, *args: str, check: bool = True) -> str:
            if args[:2] == ("remote", "add"):
                raise paths.StarterError("remote rejected")
            return real_git(cwd, *args, check=check)

        with mock.patch.object(cli, "git", git_without_remotes):
            code, report = run("new", "--workspace", str(self.ws), "--name", "be", "--remote", "git@example.com:team/be.git")
        self.assertEqual(code, 1, report)
        self.assertEqual(list(self.ws.iterdir()), [])
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be")[0], 0)


if __name__ == "__main__":
    unittest.main()
