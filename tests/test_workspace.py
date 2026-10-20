from __future__ import annotations

import json
import unittest

from support import WorkspaceCase, paths, run


class WorkspaceTest(WorkspaceCase):
    def test_sync_rewrites_the_table_from_the_manifest(self):
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be", "--role", "Backend API")[0], 0)
        manifest = self.manifest()
        manifest["repos"][0]["role"] = "Payments API"
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        code, report = run("sync", "--workspace", str(self.ws))
        self.assertEqual(code, 0, report)
        agents = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("| be | `be/` | Payments API | managed | - |", agents)
        self.assertNotIn("Backend API", agents)

        manifest["repos"][0]["kind"] = "other"
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(run("sync", "--workspace", str(self.ws))[0], 1)
        self.assertIn("Payments API", (self.ws / "AGENTS.md").read_text(encoding="utf-8"))

    def test_workspace_list_records_use_and_forgets_without_touching_folders(self):
        self.assertEqual(run("workspace", "list")[1]["workspaces"], [])
        planned = self.base / "planned"
        code, report = run("workspace", "add", "--path", str(planned))
        self.assertEqual(code, 0, report)
        self.assertFalse(report["workspace"]["exists"])
        self.assertFalse(planned.exists())

        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be", "--role", "Backend API")[0], 0)
        listed = run("workspace", "list")[1]["workspaces"]
        self.assertEqual([w["path"] for w in listed], [str(self.ws.resolve()), str(planned.resolve())])
        self.assertTrue(listed[0]["initialized"])
        self.assertEqual(listed[0]["repos"], [{"name": "be", "path": "be", "kind": "managed", "role": "Backend API"}])

        code, report = run("workspace", "remove", "--path", str(self.ws))
        self.assertEqual(code, 0, report)
        self.assertTrue((self.ws / "workspace.json").is_file())
        self.assertEqual([w["path"] for w in run("workspace", "list")[1]["workspaces"]], [str(planned.resolve())])
        self.assertEqual(run("workspace", "add", "--path", str(paths.STARTER / "nested"))[0], 1)

    def test_unreadable_workspace_list_does_not_block_creation(self):
        self.registry.parent.mkdir(parents=True)
        self.registry.write_text("not json", encoding="utf-8")
        code, report = run("new", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        self.assertTrue(any("workspace list" in w for w in report["warnings"]))
        self.assertEqual(self.registry.read_text(encoding="utf-8"), "not json")
        self.assertEqual(run("workspace", "list")[0], 1)

    def test_invalid_workspace_list_is_reported(self):
        self.registry.parent.mkdir(parents=True)
        self.registry.write_text(json.dumps({"schemaVersion": 1, "workspaces": [{"path": str(self.ws)}]}), encoding="utf-8")
        code, report = run("workspace", "list")
        self.assertEqual(code, 1, report)
        self.assertIn("registry.schema.json", report["error"])
        self.assertIn("'lastUsed'", report["error"])


if __name__ == "__main__":
    unittest.main()
