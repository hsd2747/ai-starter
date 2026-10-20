from __future__ import annotations

import json
import unittest

from support import WorkspaceCase, git_repo, run, snapshot


class AdoptTest(WorkspaceCase):
    def test_adopt_without_install_touches_nothing_in_the_repository(self):
        repo = git_repo(self.ws / "legacy")
        (repo / "AGENTS.md").write_text("# Their rules\n", encoding="utf-8")
        before = snapshot(repo)
        code, report = run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--role", "Admin web")
        self.assertEqual(code, 0, report)
        self.assertEqual(snapshot(repo), before)
        self.assertEqual(self.manifest()["repos"][0]["kind"], "registered")

    def test_adopt_install_stops_on_any_existing_harness_file(self):
        repo = git_repo(self.ws / "legacy")
        (repo / "CLAUDE.md").write_text("their file\n", encoding="utf-8")
        before = snapshot(repo)
        code, report = run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--install")
        self.assertEqual(code, 1)
        self.assertIn("CLAUDE.md", report["error"])
        self.assertEqual(snapshot(repo), before)
        self.assertFalse((self.ws / "workspace.json").exists())

    def test_adopt_install_appends_to_an_existing_gitignore(self):
        repo = git_repo(self.ws / "legacy")
        (repo / ".gitignore").write_text("node_modules/\n.env\n", encoding="utf-8")
        code, report = run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--install")
        self.assertEqual(code, 0, report)
        lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:2], ["node_modules/", ".env"])
        self.assertEqual(lines.count(".env"), 1)
        self.assertIn(".ai/runs/", lines)
        self.assertEqual(json.loads((repo / ".ai/harness.json").read_text(encoding="utf-8"))["mode"], "adopt")

    def test_registered_repository_can_later_get_the_harness(self):
        repo = git_repo(self.ws / "legacy")
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--role", "Admin web")[0], 0)
        code, report = run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--install")
        self.assertEqual(code, 0, report)
        self.assertTrue((repo / ".ai/harness.json").is_file())
        self.assertEqual(self.manifest()["repos"], [{"name": "legacy", "path": "legacy", "role": "Admin web", "kind": "managed", "remote": ""}])
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--install")[0], 1)


if __name__ == "__main__":
    unittest.main()
