from __future__ import annotations

import json
import subprocess
import unittest

from support import UpgradeCase, WorkspaceCase, commit_all, git, git_repo, run, snapshot, work_tree


class HarnessTest(WorkspaceCase):
    def test_install_outside_any_workspace_writes_only_inside_the_repository(self):
        repo = git_repo(self.base / "solo")
        (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        self.assertEqual(run("harness", "status", "--repo", str(repo))[1]["installed"], False)

        code, report = run("harness", "install", "--repo", str(repo))
        self.assertEqual(code, 0, report)
        self.assertEqual(report["merged"], [".gitignore"])
        self.assertEqual(json.loads((repo / ".ai/harness.json").read_text(encoding="utf-8"))["mode"], "adopt")
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["solo"])
        status = run("harness", "status", "--repo", str(repo))[1]
        self.assertTrue(status["installed"])
        self.assertEqual(status["mode"], "adopt")

        before = snapshot(repo)
        code, report = run("harness", "install", "--repo", str(repo))
        self.assertEqual(code, 1)
        self.assertIn(".ai/harness.json", report["error"])
        self.assertEqual(snapshot(repo), before)

    def test_other_agent_instructions_are_reported_before_and_after_the_install(self):
        repo = git_repo(self.base / "solo")
        for rel in ("AGENT.md", "agents.md", ".cursorrules", ".cursor/rules/style.mdc", ".github/copilot-instructions.md",
                    ".claude/settings.local.json", ".claude/commands/deploy.md", ".claude/skills/mine/SKILL.md"):
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text("their rules\n", encoding="utf-8")
        expected = [".claude/commands/deploy.md", ".claude/settings.local.json", ".claude/skills/mine/", ".cursor/rules/", ".cursorrules",
                    ".github/copilot-instructions.md", "AGENT.md"]
        status = run("harness", "status", "--repo", str(repo))[1]
        self.assertEqual(status["conflicts"], ["AGENTS.md"])
        self.assertEqual(status["existingInstructions"], expected)
        before = snapshot(repo)
        self.assertEqual(run("harness", "install", "--repo", str(repo))[0], 1)
        self.assertEqual(snapshot(repo), before)

        (repo / "agents.md").rename(repo / "AGENTS.pre-harness.md")
        code, report = run("harness", "install", "--repo", str(repo))
        self.assertEqual(code, 0, report)
        self.assertEqual(report["existingInstructions"], sorted([*expected, "AGENTS.pre-harness.md"]))
        self.assertEqual(run("harness", "status", "--repo", str(repo))[1]["existingInstructions"], report["existingInstructions"])
        self.assertEqual((repo / ".cursorrules").read_text(encoding="utf-8"), "their rules\n")

    def test_install_connects_the_hook_unless_other_hooks_are_in_effect(self):
        repo = git_repo(self.base / "solo")
        code, report = run("harness", "install", "--repo", str(repo))
        self.assertEqual(code, 0, report)
        self.assertTrue(report["hooks"]["installed"], report)
        self.assertEqual(git(repo, "config", "core.hooksPath").strip(), ".githooks")

        other = git_repo(self.base / "other")
        (other / ".git/hooks/pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        code, report = run("harness", "install", "--repo", str(other))
        self.assertEqual(code, 0, report)
        self.assertFalse(report["hooks"]["ok"])
        self.assertTrue(any("not connected" in w for w in report["warnings"]), report["warnings"])
        self.assertTrue((other / ".ai/harness.json").is_file())
        self.assertEqual(subprocess.run(["git", "config", "core.hooksPath"], cwd=other).returncode, 1)

    def test_repository_must_be_a_git_repository_outside_the_starter(self):
        (self.base / "plain").mkdir()
        self.assertEqual(run("harness", "install", "--repo", str(self.base / "plain"))[0], 1)
        self.assertEqual(list((self.base / "plain").iterdir()), [])
        self.assertEqual(run("harness", "status", "--repo", str(self.base / "missing"))[0], 1)
        self.assertEqual(run("harness", "install", "--repo", str(self.base), "--dry-run")[0], 1)

    def test_workspace_table_reads_the_harness_from_the_repository(self):
        repo = git_repo(self.ws / "legacy")
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--role", "Admin web")[0], 0)
        self.assertEqual(run("harness", "install", "--repo", str(repo))[0], 0)
        self.assertIn("| registered |", (self.ws / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(run("sync", "--workspace", str(self.ws))[0], 0)
        self.assertIn("| legacy | `legacy/` | Admin web | managed | - |", (self.ws / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(run("workspace", "list")[1]["workspaces"][0]["repos"][0]["kind"], "managed")

    def test_kind_stored_by_older_versions_is_accepted_and_ignored(self):
        git_repo(self.ws / "legacy")
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "legacy")[0], 0)
        manifest = self.manifest()
        manifest["repos"][0]["kind"] = "managed"
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        code, report = run("sync", "--workspace", str(self.ws))
        self.assertEqual(code, 0, report)
        self.assertIn("| registered |", (self.ws / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(run("upgrade", "--workspace", str(self.ws), "--name", "legacy", "--dry-run")[0], 1)


class HarnessUpgradeTest(UpgradeCase):
    def test_upgrade_reaches_a_repository_no_workspace_lists(self):
        repo = git_repo(self.base / "solo")
        self.assertEqual(run("harness", "install", "--repo", str(repo))[0], 0)
        commit_all(repo)
        self.change_starter_for_both_targets()
        self.assertFalse(run("harness", "status", "--repo", str(repo))[1]["upToDate"])

        before = work_tree(repo)
        code, report = run("harness", "upgrade", "--repo", str(repo), "--dry-run")
        self.assertEqual(code, 0, report)
        self.assertEqual(work_tree(repo), before)
        code, report = run("harness", "upgrade", "--repo", str(repo))
        self.assertEqual(code, 0, report)
        self.assertEqual([t["target"] for t in report["targets"]], ["solo"])
        self.assertIn("MAX_DEPTH = 5", (repo / "tool/ai_harness/guard.py").read_text(encoding="utf-8"))
        self.assertTrue(run("harness", "status", "--repo", str(repo))[1]["upToDate"])
        self.assertFalse((self.base / "workspaces.json").exists())

    def test_unregistered_repository_keeps_its_upgrades(self):
        repo = self.create()
        self.assertEqual(run("unregister", "--workspace", str(self.ws), "--name", "be")[0], 0)
        commit_all(self.ws)
        self.change_starter_for_both_targets()
        code, report = run("upgrade", "--workspace", str(self.ws))
        self.assertEqual(code, 0, report)
        self.assertEqual([t["target"] for t in report["targets"]], ["workspace"])
        code, report = run("harness", "upgrade", "--repo", str(repo))
        self.assertEqual(code, 0, report)
        self.assertIn("MAX_DEPTH = 5", (repo / "tool/ai_harness/guard.py").read_text(encoding="utf-8"))

        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "be")[1]["kind"], "managed")


if __name__ == "__main__":
    unittest.main()
