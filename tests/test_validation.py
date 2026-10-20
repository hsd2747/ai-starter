from __future__ import annotations

import json
import unittest
from unittest import mock

from support import WorkspaceCase, cli, run, snapshot


class ValidationTest(WorkspaceCase):
    def test_invalid_workspace_manifest_stops_every_command_before_it_writes(self):
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be")[0], 0)
        manifest = self.manifest()
        del manifest["repos"][0]["path"]
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        before = snapshot(self.ws)
        for command, *rest in (("new", "--name", "web"), ("sync",), ("upgrade", "--dry-run")):
            code, report = run(command, "--workspace", str(self.ws), *rest)
            self.assertEqual(code, 1, report)
            self.assertIn("workspace.schema.json", report["error"])
            self.assertIn("'path'", report["error"])
        self.assertEqual(snapshot(self.ws), before)
        listed = run("workspace", "list")[1]["workspaces"][0]
        self.assertIn("workspace.schema.json", listed["error"])

    def test_duplicate_or_escaping_manifest_entries_are_rejected(self):
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "be")[0], 0)
        manifest = self.manifest()
        manifest["repos"].append({**manifest["repos"][0], "name": "be2"})
        manifest["repos"].append({**manifest["repos"][0], "name": "up", "path": "../elsewhere"})
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        code, report = run("sync", "--workspace", str(self.ws))
        self.assertEqual(code, 1, report)
        self.assertIn("path 'be' appears more than once", report["error"])
        self.assertIn("'../elsewhere' is not a clean folder path", report["error"])

    def test_unexpected_error_is_still_reported_as_json(self):
        with mock.patch.object(cli, "cmd_sync", side_effect=RuntimeError("boom")):
            code, report = run("sync", "--workspace", str(self.ws))
        self.assertEqual(code, 2)
        self.assertEqual(report["kind"], "internal")
        self.assertIn("RuntimeError: boom", report["error"])
        self.assertTrue(report["traceback"])


if __name__ == "__main__":
    unittest.main()
