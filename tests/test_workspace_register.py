from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from support import WorkspaceCase, commit_all, git, git_repo, leftovers, run, snapshot
from ai_starter.manifests import load_manifest


class WorkspaceRegisterTest(WorkspaceCase):
    """`register`, `unregister`, and `sync` of the workspace's own .ai/workspace.py, run without the starter."""

    def setUp(self):
        super().setUp()
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be", "--role", "Backend API", "--remote", "git@example.com:org/be.git")[0], 0)

    def tool(self, *args: str) -> tuple[int, dict]:
        process = subprocess.run([sys.executable, "-I", str(self.ws / ".ai/workspace.py"), *args], capture_output=True, text=True)
        return process.returncode, json.loads(process.stdout)

    def legacy(self, origin: str = "") -> Path:
        repo = git_repo(self.ws / "apps" / "legacy")
        (repo / "README.md").write_text("legacy\n", encoding="utf-8")
        commit_all(repo)
        if origin:
            git(repo, "remote", "add", "origin", origin)
        return repo

    def test_register_lists_the_repository_and_strips_credentials_from_its_origin(self):
        repo = self.legacy("https://user:secret@example.com/org/legacy.git")
        before = snapshot(repo)
        code, report = self.tool("register", "--path", "apps/legacy", "--role", "Admin | web")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["registered"], {"name": "legacy", "path": "apps/legacy", "role": "Admin | web",
                                                "remote": "https://example.com/org/legacy.git"})
        self.assertEqual(report["kind"], "registered")
        self.assertTrue(any("credentials" in w for w in report["warnings"]), report["warnings"])
        self.assertEqual(snapshot(repo), before, "the repository itself is never touched")
        manifest = load_manifest(self.ws / "workspace.json", "workspace")
        self.assertEqual([r["name"] for r in manifest["repos"]], ["be", "legacy"])
        agents = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("| legacy | `apps/legacy/` | Admin \\| web | registered | https://example.com/org/legacy.git |", agents)
        self.assertNotIn("secret", agents + (self.ws / "workspace.json").read_text(encoding="utf-8"))
        self.assertEqual(leftovers(self.ws), [])

    def test_the_starter_and_the_tool_write_the_same_files(self):
        self.legacy("git@example.com:org/legacy.git")
        start = snapshot(self.ws)
        self.assertEqual(self.tool("register", "--path", "apps/legacy", "--role", "Admin web")[0], 0)
        by_tool = {f: (self.ws / f).read_bytes() for f in ("workspace.json", "AGENTS.md")}
        self.assertEqual(self.tool("unregister", "--name", "legacy")[0], 0)
        self.assertEqual(snapshot(self.ws), start, "unregister undoes register exactly")
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "apps/legacy", "--role", "Admin web")[0], 0)
        self.assertEqual({f: (self.ws / f).read_bytes() for f in by_tool}, by_tool)

    def test_refusals_write_nothing(self):
        self.legacy()
        (self.ws / "notes").mkdir()
        before = snapshot(self.ws)
        cases = [
            (["register", "--path", "notes"], "not a git repository"),
            (["register", "--path", "../outside"], "inside the workspace"),
            (["register", "--path", "apps/legacy", "--name", "be"], "already registers"),
            (["register", "--path", "apps/legacy", "--name", "bad name"], "Invalid repository name"),
            (["register", "--path", "apps/legacy", "--remote", "https://token@example.com/org/legacy.git"], "credentials"),
            (["unregister", "--name", "web"], "'be'"),
        ]
        for args, message in cases:
            code, report = self.tool(*args)
            self.assertEqual(code, 1, args)
            self.assertIn(message, report["error"], args)
        self.assertEqual(snapshot(self.ws), before)

    def test_register_without_a_remote_warns_and_unregister_keeps_the_folder(self):
        repo = self.legacy()
        code, report = self.tool("register", "--path", "apps/legacy")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["registered"]["remote"], "")
        self.assertTrue(any("No remote" in w for w in report["warnings"]), report["warnings"])
        before = snapshot(repo)
        code, report = self.tool("unregister", "--name", "legacy")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["removed"]["path"], "apps/legacy")
        self.assertEqual(snapshot(repo), before)
        self.assertNotIn("| legacy |", (self.ws / "AGENTS.md").read_text(encoding="utf-8"))

    def test_sync_rewrites_the_table_after_a_hand_edit_and_needs_its_markers(self):
        manifest = self.manifest()
        manifest["repos"][0]["role"] = "Backend API v2"
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        code, report = self.tool("sync")
        self.assertEqual(code, 0, report)
        self.assertIn("| be | `be/` | Backend API v2 | managed |", (self.ws / "AGENTS.md").read_text(encoding="utf-8"))

        agents = self.ws / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8").replace("<!-- workspace:repos:start -->", ""), encoding="utf-8")
        before = snapshot(self.ws)
        code, report = self.tool("sync")
        self.assertEqual(code, 1)
        self.assertIn("markers are missing", report["error"])
        self.assertEqual(snapshot(self.ws), before)
        self.legacy()
        code, report = self.tool("register", "--path", "apps/legacy")
        self.assertEqual(code, 0, "missing markers cost a warning, not the entry")
        self.assertTrue(any("markers are missing" in w for w in report["warnings"]), report["warnings"])
        self.assertEqual(snapshot(self.ws)["AGENTS.md"], before["AGENTS.md"])

    def test_hand_edited_entries_are_checked_like_the_starter_checks_them(self):
        good = self.manifest()
        second = {"name": "web", "path": "web", "role": "Web", "remote": ""}
        cases = [
            ({"role": None}, "are strings"),
            ({"remote": 1}, "are strings"),
            ({"name": "be api"}, "invalid repository name"),
            ({"path": "be/"}, "write it as 'be'"),
            ({"path": "./be"}, "write it as 'be'"),
            ({"path": "../be"}, "inside the workspace"),
        ]
        for change, message in cases:
            manifest = json.loads(json.dumps(good))
            manifest["repos"][0].update(change)
            (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
            before = snapshot(self.ws)
            for args in (["sync"], ["check"], ["unregister", "--name", "be"]):
                code, report = self.tool(*args)
                self.assertEqual(code, 1, (change, args))
                self.assertIn(message, report["error"], (change, args))
            self.assertEqual(snapshot(self.ws), before, change)
            self.assertEqual(run("sync", "--workspace", str(self.ws))[0], 1, f"the starter refuses {change} as well")

        for field in ("name", "path"):
            manifest = json.loads(json.dumps(good))
            manifest["repos"].append({**second, field: manifest["repos"][0][field]})
            (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
            code, report = self.tool("sync")
            self.assertEqual(code, 1, field)
            self.assertIn("more than once", report["error"])

    def test_team_add_records_the_team_and_creates_its_rules_file_once(self):
        code, report = self.tool("team", "add", "pm")
        self.assertEqual(code, 0, report)
        self.assertTrue(report["rulesCreated"])
        self.assertEqual(load_manifest(self.ws / "workspace.json", "workspace")["teams"], ["pm"])
        self.assertIn("pm team", (self.ws / ".ai/teams/pm.md").read_text(encoding="utf-8"))

        (self.ws / ".ai/teams/pd.md").write_text("# pd\n\n- Our own rule.\n", encoding="utf-8")
        code, report = self.tool("team", "add", "pd")
        self.assertEqual(code, 0, report)
        self.assertFalse(report["rulesCreated"], "an existing rules file is kept")
        self.assertEqual((self.ws / ".ai/teams/pd.md").read_text(encoding="utf-8"), "# pd\n\n- Our own rule.\n")
        self.assertEqual(self.manifest()["teams"], ["pm", "pd"])
        self.assertFalse(any("teams" in w for w in self.tool("check")[1]["warnings"]))

        before = snapshot(self.ws)
        for name, message in (("pm", "already lists"), ("Bad", "Invalid team")):
            code, report = self.tool("team", "add", name)
            self.assertEqual(code, 1, name)
            self.assertIn(message, report["error"])
        self.assertEqual(snapshot(self.ws), before)
        self.assertEqual(leftovers(self.ws), [])


if __name__ == "__main__":
    unittest.main()
