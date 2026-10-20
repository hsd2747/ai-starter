from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from support import UpgradeCase, commit_all, files, git, leftovers, run, snapshot, work_tree


class UpgradeTest(UpgradeCase):
    def test_merges_project_and_starter_edits_and_records_the_new_base(self):
        repo = self.create()
        self.edit(repo / "AGENTS.md", "Not onboarded yet. Onboarding replaces the text between these markers", "Project map written by onboarding.")
        commit_all(repo)
        template = self.fake / "template"
        self.edit(template / "AGENTS.md", "- Use subagents and handoff notes", "- Starter goal added later.\n- Use subagents and handoff notes")
        self.edit(template / "tool/ai_harness/guard.py", "MAX_DEPTH = 4", "MAX_DEPTH = 5")
        (template / ".ai/NEW.md").write_text("new\n", encoding="utf-8")
        (template / "wiki/notes/.gitkeep").unlink()
        commit_all(self.fake)

        before = snapshot(repo), snapshot(self.ws / ".ai")
        code, report = run("upgrade", "--workspace", str(self.ws), "--dry-run")
        self.assertEqual(code, 0, report)
        self.assertEqual((snapshot(repo), snapshot(self.ws / ".ai")), before)

        code, report = run("upgrade", "--workspace", str(self.ws))
        self.assertEqual(code, 0, report)
        workspace, be = report["targets"]
        self.assertEqual(be["merged"], ["AGENTS.md"])
        self.assertEqual(be["updated"], ["tool/ai_harness/guard.py"])
        self.assertEqual(be["added"], [".ai/NEW.md"])
        self.assertEqual(be["removedUpstream"], ["wiki/notes/.gitkeep"])
        self.assertEqual(be["conflicts"], [])
        agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Project map written by onboarding.", agents)
        self.assertIn("- Starter goal added later.", agents)
        self.assertTrue((repo / "wiki/notes/.gitkeep").exists())
        self.assertIn("MAX_DEPTH = 5", (self.ws / ".ai/guard/ai_harness/guard.py").read_text(encoding="utf-8"))
        self.assertEqual(workspace["updated"], [".ai/guard/ai_harness/guard.py"])

        head = git(self.fake, "rev-parse", "HEAD").strip()
        record = json.loads((repo / ".ai/harness.json").read_text(encoding="utf-8"))
        self.assertEqual(record["starter"]["commit"], head)
        self.assertIn(".ai/NEW.md", record["files"])
        self.assertNotIn("wiki/notes/.gitkeep", record["files"])
        self.assertEqual(json.loads((self.ws / "workspace.json").read_text(encoding="utf-8"))["starter"]["commit"], head)

        commit_all(repo)
        commit_all(self.ws)
        code, report = run("upgrade", "--workspace", str(self.ws))
        self.assertEqual(code, 0, report)
        self.assertTrue(all(target["upToDate"] for target in report["targets"]))

    def test_same_line_changed_on_both_sides_leaves_markers(self):
        repo = self.create()
        line = "- Finish the requested change completely, within the intended scope."
        self.edit(repo / "AGENTS.md", line, "- Project wording.")
        commit_all(repo)
        self.edit(self.fake / "template/AGENTS.md", line, "- Starter wording.")
        commit_all(self.fake)
        code, report = run("upgrade", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        self.assertEqual([t["target"] for t in report["targets"]], ["be"])
        self.assertEqual(report["targets"][0]["conflicts"], ["AGENTS.md"])
        agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<<<<<<< be\n- Project wording.\n=======\n- Starter wording.\n>>>>>>> starter (current)", agents)

    def test_uncommitted_target_file_blocks_every_write(self):
        repo = self.create()
        self.edit(self.fake / "template/AGENTS.md", "## Goals", "## Goals\n\nNew starter line.")
        self.edit(self.fake / "template/tool/ai_harness/guard.py", "MAX_DEPTH = 4", "MAX_DEPTH = 5")
        commit_all(self.fake)
        self.edit(repo / "AGENTS.md", "## Goals", "## Goals (local draft)")
        before = snapshot(repo), snapshot(self.ws / ".ai")
        code, report = run("upgrade", "--workspace", str(self.ws))
        self.assertEqual(code, 1)
        self.assertIn("AGENTS.md", report["error"])
        self.assertEqual((snapshot(repo), snapshot(self.ws / ".ai")), before)

        code, report = run("upgrade", "--workspace", str(self.ws), "--dry-run")
        self.assertEqual(code, 0, report)
        self.assertTrue(report["targets"][1]["blockers"])

    def test_invalid_harness_record_blocks_its_repository(self):
        repo = self.create()
        record = json.loads((repo / ".ai/harness.json").read_text(encoding="utf-8"))
        record["files"]["../outside"] = record["files"]["AGENTS.md"]
        (repo / ".ai/harness.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        commit_all(repo)
        self.edit(self.fake / "template/tool/ai_harness/guard.py", "MAX_DEPTH = 4", "MAX_DEPTH = 5")
        commit_all(self.fake)

        code, report = run("upgrade", "--workspace", str(self.ws), "--dry-run")
        self.assertEqual(code, 0, report)
        blockers = report["targets"][1]["blockers"]
        self.assertEqual(len(blockers), 1)
        self.assertIn("harness.schema.json", blockers[0])
        self.assertIn("'../outside'", blockers[0])

        before = snapshot(repo), snapshot(self.ws / ".ai")
        self.assertEqual(run("upgrade", "--workspace", str(self.ws))[0], 1)
        self.assertEqual((snapshot(repo), snapshot(self.ws / ".ai")), before)

    def test_dirty_starter_is_refused(self):
        self.create()
        (self.fake / "template/AGENTS.md").write_text("changed\n", encoding="utf-8")
        code, report = run("upgrade", "--workspace", str(self.ws))
        self.assertEqual(code, 1)
        self.assertIn("Commit the starter", report["error"])

    def test_failure_while_preparing_leaves_every_target_untouched(self):
        self.create()
        self.change_starter_for_both_targets()
        real_write = files.Staging.write

        def full_disk_at_record(stage, dest: Path, data: bytes, mode_from: Path | None = None) -> None:
            if dest.name == "harness.json":
                raise OSError(28, "No space left on device")
            real_write(stage, dest, data, mode_from)

        before = work_tree(self.ws)
        with mock.patch.object(files.Staging, "write", full_disk_at_record):
            code, report = run("upgrade", "--workspace", str(self.ws))
        self.assertEqual(code, 1, report)
        self.assertEqual(report["kind"], "filesystem")
        self.assertEqual(work_tree(self.ws), before)
        self.assertEqual(leftovers(self.ws), [])

    def test_failure_while_moving_in_names_what_was_replaced(self):
        self.create()
        self.change_starter_for_both_targets()
        real_replace, moved = os.replace, []

        def failing_second_move(source, dest) -> None:
            moved.append(str(dest))
            if len(moved) == 2:
                raise OSError(5, "Input/output error")
            real_replace(source, dest)

        with mock.patch.object(os, "replace", failing_second_move):
            code, report = run("upgrade", "--workspace", str(self.ws))
        self.assertEqual(code, 1, report)
        self.assertIn(f"Replaced: ['{moved[0]}']", report["error"])
        self.assertIn(f"Not replaced: ['{moved[1]}'", report["error"])
        self.assertEqual(leftovers(self.ws), [])


if __name__ == "__main__":
    unittest.main()
