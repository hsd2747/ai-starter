from __future__ import annotations

import unittest

from support import WorkspaceCase, git_repo, run, snapshot


class UnregisterTest(WorkspaceCase):
    def test_unregister_removes_only_the_entry_and_its_row(self):
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be", "--role", "Backend API")[0], 0)
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "web", "--role", "Web frontend")[0], 0)
        before = snapshot(self.ws / "be")
        code, report = run("unregister", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["removed"]["name"], "be")
        self.assertEqual(snapshot(self.ws / "be"), before)
        self.assertEqual([r["name"] for r in self.manifest()["repos"]], ["web"])
        agents = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("| be |", agents)
        self.assertIn("| web | `web/` | Web frontend | managed | - |", agents)
        self.assertEqual(run("upgrade", "--workspace", str(self.ws), "--name", "be", "--dry-run")[0], 1)

    def test_unregistered_folder_can_be_registered_again(self):
        git_repo(self.ws / "legacy")
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--role", "Admin web")[0], 0)
        self.assertEqual(run("unregister", "--workspace", str(self.ws), "--name", "legacy")[0], 0)
        self.assertEqual(self.manifest()["repos"], [])
        self.assertIn("No repositories yet.", (self.ws / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "legacy")[0], 0)

    def test_unknown_name_or_missing_workspace_changes_nothing(self):
        self.assertEqual(run("unregister", "--workspace", str(self.ws), "--name", "be")[0], 1)
        self.assertFalse(self.ws.exists())
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be")[0], 0)
        before = snapshot(self.ws)
        code, report = run("unregister", "--workspace", str(self.ws), "--name", "web")
        self.assertEqual(code, 1)
        self.assertIn("'be'", report["error"])
        self.assertEqual(snapshot(self.ws), before)


if __name__ == "__main__":
    unittest.main()
