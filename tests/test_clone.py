from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from support import WorkspaceCase, commit_all, git, git_repo, leftovers, run, snapshot


class CloneTest(WorkspaceCase):
    """A workspace pushed to bare remotes, then reproduced in a teammate's folder."""

    def bare(self, source: Path, name: str) -> Path:
        target = self.base / "remotes" / f"{name}.git"
        target.parent.mkdir(exist_ok=True)
        git(self.base, "clone", "-q", "--bare", str(source), str(target))
        return target

    def share(self) -> Path:
        be_remote = self.base / "remotes" / "be.git"
        code, report = run("new", "--workspace", str(self.ws), "--name", "be", "--role", "Backend API", "--remote", str(be_remote))
        self.assertEqual(code, 0, report)
        commit_all(self.ws / "be")
        self.bare(self.ws / "be", "be")
        legacy = git_repo(self.ws / "legacy")
        (legacy / "README.md").write_text("legacy\n", encoding="utf-8")
        commit_all(legacy)
        code, report = run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--role", "Admin web")
        self.assertEqual(code, 0, report)
        self.assertTrue(any("No remote" in w and "legacy" in w for w in report["warnings"]), report["warnings"])
        commit_all(self.ws)
        return self.bare(self.ws, "product")

    def test_clone_reproduces_the_workspace_and_skips_what_it_cannot_get(self):
        url = self.share()
        mate = self.base / "mate" / "product"
        code, report = run("workspace", "clone", "--path", str(mate), "--url", str(url))
        self.assertEqual(code, 0, report)
        self.assertTrue(report["workspaceCloned"])
        self.assertEqual([c["name"] for c in report["cloned"]], ["be"])
        self.assertTrue(report["cloned"][0]["harness"])
        self.assertEqual(report["skipped"], [{"name": "legacy", "reason": "no remote in workspace.json"}])
        self.assertEqual(json.loads((mate / "workspace.json").read_text(encoding="utf-8"))["repos"][0]["name"], "be")
        self.assertTrue((mate / ".git").is_dir())
        self.assertTrue((mate / "be/.ai/harness.json").is_file())
        hooks = subprocess.run(["git", "config", "core.hooksPath"], cwd=mate / "be", capture_output=True, text=True).stdout.strip()
        self.assertEqual(hooks, ".githooks")
        self.assertEqual(leftovers(mate), [])
        self.assertIn(str(mate.resolve()), [w["path"] for w in run("workspace", "list")[1]["workspaces"]])
        self.assertFalse(any("starter commit" in w for w in report["warnings"]), report["warnings"])

        before = snapshot(mate)
        code, report = run("workspace", "clone", "--path", str(mate))
        self.assertEqual(code, 0, report)
        self.assertEqual((report["cloned"], report["present"]), ([], ["be"]))
        self.assertEqual(snapshot(mate), before)

    def test_clone_fills_in_only_the_named_missing_repository(self):
        url = self.share()
        mate = self.base / "mate"
        git(self.base, "clone", "-q", str(url), str(mate))
        code, report = run("workspace", "clone", "--path", str(mate), "--name", "be")
        self.assertEqual(code, 0, report)
        self.assertFalse(report["workspaceCloned"])
        self.assertEqual(([c["name"] for c in report["cloned"]], report["skipped"]), (["be"], []))
        self.assertEqual(run("workspace", "clone", "--path", str(mate), "--name", "web")[0], 1)

    def test_a_plain_clone_of_the_workspace_can_clone_its_repositories_without_the_starter(self):
        url = self.share()
        mate = self.base / "mate"
        git(self.base, "clone", "-q", str(url), str(mate))
        self.assertTrue((mate / ".ai/workspace.py").is_file())
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        process = subprocess.run([sys.executable, "-I", str(mate / ".ai/workspace.py"), "clone"], cwd=elsewhere,
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual([c["name"] for c in report["cloned"]], ["be"])
        self.assertEqual(report["skipped"], [{"name": "legacy", "reason": "no remote in workspace.json"}])
        hooks = subprocess.run(["git", "config", "core.hooksPath"], cwd=mate / "be", capture_output=True, text=True).stdout.strip()
        self.assertEqual(hooks, ".githooks")
        self.assertEqual(leftovers(mate), [])
        self.assertEqual(run("workspace", "list")[1]["workspaces"][0]["path"], str(self.ws.resolve()), "the tool never writes the starter's list")

        again = subprocess.run([sys.executable, str(mate / ".ai/workspace.py"), "clone", "--name", "web"], capture_output=True, text=True)
        self.assertEqual(again.returncode, 1)
        self.assertIn("web", json.loads(again.stdout)["error"])

    def test_a_folder_in_the_way_stops_before_any_clone(self):
        url = self.share()
        mate = self.base / "mate"
        git(self.base, "clone", "-q", str(url), str(mate))
        (mate / "be").mkdir()
        (mate / "be" / "notes.txt").write_text("mine\n", encoding="utf-8")
        before = snapshot(mate)
        code, report = run("workspace", "clone", "--path", str(mate))
        self.assertEqual(code, 1, report)
        self.assertIn("'be'", report["error"])
        self.assertEqual(snapshot(mate), before)

    def test_root_clone_needs_an_empty_folder_and_a_workspace_repository(self):
        url = self.share()
        busy = self.base / "busy"
        busy.mkdir()
        (busy / "file.txt").write_text("x\n", encoding="utf-8")
        code, report = run("workspace", "clone", "--path", str(busy), "--url", str(url))
        self.assertEqual(code, 1, report)
        self.assertEqual(sorted(p.name for p in busy.iterdir()), ["file.txt"])

        target = self.base / "not-a-workspace"
        code, report = run("workspace", "clone", "--path", str(target), "--url", str(self.base / "remotes" / "be.git"))
        self.assertEqual(code, 1, report)
        self.assertIn("not a workspace", report["error"])
        self.assertFalse(target.exists())

        code, report = run("workspace", "clone", "--path", str(target), "--url", str(self.base / "remotes" / "missing.git"))
        self.assertEqual(code, 1, report)
        self.assertFalse(target.exists())
        self.assertEqual(run("workspace", "list", "--url", str(url))[0], 1)

    def test_remotes_never_carry_credentials_into_the_workspace(self):
        code, report = run("new", "--workspace", str(self.ws), "--name", "be", "--remote", "https://user:secret@example.com/team/be.git")
        self.assertEqual(code, 1, report)
        self.assertNotIn("secret", json.dumps(report))
        self.assertFalse(self.ws.exists())

        legacy = git_repo(self.ws / "legacy")
        git(legacy, "remote", "add", "origin", "https://x-token@example.com/team/legacy.git")
        code, report = run("adopt", "--workspace", str(self.ws), "--path", "legacy")
        self.assertEqual(code, 0, report)
        self.assertEqual(self.manifest()["repos"][0]["remote"], "https://example.com/team/legacy.git")
        self.assertTrue(any("credentials" in w for w in report["warnings"]), report["warnings"])
        self.assertNotIn("x-token", (self.ws / "AGENTS.md").read_text(encoding="utf-8"))

        ssh = git_repo(self.ws / "admin")
        git(ssh, "remote", "add", "origin", "git@example.com:team/admin.git")
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "admin")[0], 0)
        self.assertEqual(self.manifest()["repos"][1]["remote"], "git@example.com:team/admin.git")

    def tool(self, workspace: Path, *args: str) -> tuple[int, dict]:
        process = subprocess.run([sys.executable, "-I", str(workspace / ".ai/workspace.py"), *args], capture_output=True, text=True)
        return process.returncode, json.loads(process.stdout)

    def test_a_repository_out_of_reach_does_not_stop_the_others(self):
        self.share()
        manifest = self.manifest()
        manifest["repos"].insert(0, {"name": "secret-repo", "path": "secret-repo", "remote": str(self.base / "remotes" / "no-access.git")})
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        commit_all(self.ws)
        mate = self.base / "mate"
        git(self.base, "clone", "-q", str(self.bare(self.ws, "product2")), str(mate))
        code, report = self.tool(mate, "clone")
        self.assertEqual(code, 0, report)
        self.assertEqual([c["name"] for c in report["cloned"]], ["be"])
        self.assertEqual([f["name"] for f in report["failed"]], ["secret-repo"])
        self.assertFalse((mate / "secret-repo").exists())
        self.assertEqual(leftovers(mate), [])
        self.assertTrue(any("could not be cloned" in w for w in report["warnings"]), report["warnings"])

    def test_local_settings_stay_personal_and_keep_what_the_user_wrote(self):
        url = self.share()
        manifest = self.manifest()
        manifest["teams"] = ["dev", "pm", "pd"]
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(run("sync", "--workspace", str(self.ws))[0], 0, "teams must pass the workspace schema")
        commit_all(self.ws)
        url = self.bare(self.ws, "product-teams")

        mate = self.base / "mate"
        code, report = run("workspace", "clone", "--path", str(mate), "--url", str(url), "--team", "pm")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["local"]["team"], "pm")
        local = mate / "CLAUDE.local.md"
        self.assertIn("Team: pm", local.read_text(encoding="utf-8"))
        self.assertIn("CLAUDE.local.md", git(mate, "check-ignore", "CLAUDE.local.md"))
        self.assertEqual(self.tool(mate, "check")[1]["problems"], [])

        local.write_text(local.read_text(encoding="utf-8") + "- Answer in Korean.\n", encoding="utf-8")
        code, report = self.tool(mate, "local", "--team", "pd")
        self.assertEqual((code, report["created"]), (0, False), report)
        text = local.read_text(encoding="utf-8")
        self.assertIn("Team: pd", text)
        self.assertNotIn("Team: pm", text)
        self.assertIn("- Answer in Korean.", text)

        before = text
        code, report = self.tool(mate, "local", "--team", "sales")
        self.assertEqual(code, 1)
        self.assertIn("Unknown team", report["error"])
        self.assertEqual(local.read_text(encoding="utf-8"), before)

        git(mate, "add", "-f", "CLAUDE.local.md")
        code, report = self.tool(mate, "check")
        self.assertEqual(code, 1)
        self.assertIn("tracked by git", report["problems"][0])

    def test_check_asks_for_a_team_until_one_is_recorded(self):
        url = self.share()
        mate = self.base / "mate"
        code, report = run("workspace", "clone", "--path", str(mate), "--url", str(url))
        self.assertEqual(code, 0, report)
        self.assertTrue(any("No team" in w for w in report["warnings"]), report["warnings"])
        code, report = self.tool(mate, "check")
        self.assertEqual(code, 1)
        self.assertIn("No team", report["problems"][0])
        self.assertEqual(self.tool(mate, "local", "--team", "anything")[0], 0, "without a teams list any valid name is accepted")
        self.assertEqual(self.tool(mate, "check")[0], 0)


if __name__ == "__main__":
    unittest.main()
