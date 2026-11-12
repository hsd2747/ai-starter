from __future__ import annotations

import json
import os
import shutil
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

    def test_workspace_skills_are_shared_and_linked_for_claude_code(self):
        url = self.share()
        tracked = git(self.ws, "ls-files").split()
        for path in ("README.md", ".agents/skills/workspace-onboard/SKILL.md", ".claude/skills/workspace-onboard"):
            self.assertIn(path, tracked)
        mate = self.base / "mate"
        self.assertEqual(run("workspace", "clone", "--path", str(mate), "--url", str(url), "--team", "dev")[0], 0)
        self.assertTrue((mate / ".claude/skills/workspace-onboard/SKILL.md").is_file())

        code, report = self.tool(mate, "check", "--access")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["skills"], ["workspace-onboard", "workspace-repos", "workspace-rules"])
        self.assertEqual(report["access"], {"be": "ok"})
        self.assertEqual(report["missing"], ["legacy"])

        skill = mate / ".agents/skills/plan-review"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: plan-review\ndescription: Review a plan. Use for 기획 리뷰.\n---\n\n# Plan review\n", encoding="utf-8")
        code, report = self.tool(mate, "check")
        self.assertEqual(code, 1)
        self.assertIn("skills sync", report["problems"][0])
        code, report = self.tool(mate, "skills", "sync")
        self.assertEqual((code, report["created"]), (0, [".claude/skills/plan-review"]), report)
        self.assertTrue((mate / ".claude/skills/plan-review/SKILL.md").is_file())
        self.assertEqual(self.tool(mate, "check")[0], 0)
        self.assertEqual(self.tool(mate, "skills", "sync")[1]["created"], [])

        (skill / "SKILL.md").write_text("---\nname: other\n---\n", encoding="utf-8")
        problems = self.tool(mate, "check")[1]["problems"]
        self.assertTrue(any("must be 'plan-review'" in p for p in problems), problems)
        self.assertTrue(any("needs a description" in p for p in problems), problems)

    def test_update_pulls_the_workspace_clones_new_repositories_and_only_fast_forwards(self):
        url = self.share()
        git(self.ws, "remote", "add", "origin", str(url))
        mate = self.base / "mate"
        self.assertEqual(run("workspace", "clone", "--path", str(mate), "--url", str(url), "--team", "dev")[0], 0)

        (self.ws / "be" / "upstream.txt").write_text("one\n", encoding="utf-8")
        commit_all(self.ws / "be")
        git(self.ws / "be", "push", "-q", "origin", "HEAD")
        web = git_repo(self.ws / "web")
        (web / "index.html").write_text("web\n", encoding="utf-8")
        commit_all(web)
        manifest = self.manifest()
        manifest["repos"].append({"name": "web", "path": "web", "remote": str(self.bare(web, "web"))})
        (self.ws / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        commit_all(self.ws)
        git(self.ws, "push", "-q", "origin", "HEAD")

        code, report = self.tool(mate, "update")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["root"]["status"], "updated")
        self.assertEqual([c["name"] for c in report["cloned"]], ["web"])
        self.assertEqual(report["repos"]["be"]["status"], "updated")
        self.assertTrue((mate / "be" / "upstream.txt").is_file())
        self.assertEqual(self.tool(mate, "update")[1]["repos"]["be"]["status"], "up-to-date")

        (self.ws / "be" / "upstream.txt").write_text("two\n", encoding="utf-8")
        commit_all(self.ws / "be")
        git(self.ws / "be", "push", "-q", "origin", "HEAD")
        (mate / "be" / "upstream.txt").write_text("local edit\n", encoding="utf-8")
        code, report = self.tool(mate, "update", "--name", "be")
        self.assertEqual(code, 0, report)
        self.assertNotIn("root", report)
        self.assertEqual(report["repos"]["be"]["reason"], "uncommitted changes to tracked files")
        self.assertEqual((mate / "be" / "upstream.txt").read_text(encoding="utf-8"), "local edit\n")

        commit_all(mate / "be")
        head = git(mate / "be", "rev-parse", "HEAD")
        report = self.tool(mate, "update", "--name", "be")[1]
        self.assertEqual(report["repos"]["be"]["status"], "failed")
        self.assertIn("diverged", report["repos"]["be"]["error"])
        self.assertEqual(git(mate / "be", "rev-parse", "HEAD"), head)
        self.assertTrue(any("Not updated" in w for w in report["warnings"]), report["warnings"])

    def test_check_warns_when_agents_md_grows_past_the_limit(self):
        url = self.share()
        mate = self.base / "mate"
        self.assertEqual(run("workspace", "clone", "--path", str(mate), "--url", str(url), "--team", "dev")[0], 0)
        self.assertFalse(any("AGENTS.md has" in w for w in self.tool(mate, "check")[1]["warnings"]))
        with open(mate / "AGENTS.md", "a", encoding="utf-8") as handle:
            handle.write("- filler rule\n" * 200)
        code, report = self.tool(mate, "check")
        self.assertEqual(code, 0, "a long AGENTS.md is a warning, not a problem")
        self.assertTrue(any("AGENTS.md has" in w for w in report["warnings"]), report["warnings"])

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

    def test_check_warns_about_teams_without_a_rules_file(self):
        url = self.share()
        mate = self.base / "mate"
        self.assertEqual(run("workspace", "clone", "--path", str(mate), "--url", str(url), "--team", "dev")[0], 0)
        self.assertFalse(any(".ai/teams" in w for w in self.tool(mate, "check")[1]["warnings"]), "no teams listed, nothing to warn about")

        manifest = json.loads((mate / "workspace.json").read_text(encoding="utf-8"))
        manifest["teams"] = ["dev", "pm"]
        (mate / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
        teams = mate / ".ai" / "teams"
        teams.mkdir()
        (teams / "dev.md").write_text("# dev\n", encoding="utf-8")
        (teams / "qa.md").write_text("# qa\n", encoding="utf-8")
        code, report = self.tool(mate, "check")
        self.assertEqual(code, 0, "a missing team file is a warning, not a problem")
        self.assertTrue(any("No rules file" in w and "'pm'" in w and "'dev'" not in w for w in report["warnings"]), report["warnings"])
        self.assertTrue(any("does not list" in w and "'qa'" in w for w in report["warnings"]), report["warnings"])

        (teams / "pm.md").write_text("# pm\n", encoding="utf-8")
        (teams / "qa.md").unlink()
        self.assertFalse(any(".ai/teams" in w or "No rules file" in w for w in self.tool(mate, "check")[1]["warnings"]))

    def test_a_remote_that_looks_like_a_git_option_is_never_run(self):
        url = self.share()
        mate = self.base / "mate"
        git(self.base, "clone", "-q", str(url), str(mate))
        marker = self.base / "ran"
        manifest = json.loads((mate / "workspace.json").read_text(encoding="utf-8"))
        manifest["repos"].append({"name": "evil", "path": "evil", "remote": f"--upload-pack=touch {marker}"})
        (mate / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")

        code, report = self.tool(mate, "clone", "--name", "evil")
        self.assertEqual(code, 0, report)
        self.assertEqual([f["name"] for f in report["failed"]], ["evil"])
        code, report = self.tool(mate, "check", "--access")
        self.assertNotEqual(report["access"]["evil"], "ok")
        self.assertFalse(marker.exists(), "the remote was passed to git as an option")
        self.assertFalse((mate / "evil").exists())
        self.assertEqual(leftovers(mate), [])

    def test_a_refused_team_or_name_with_url_leaves_the_folder_as_it_was(self):
        url = self.share()
        missing = self.base / "mate" / "product"
        for args, message in ((["--name", "web"], "no repository named"), (["--team", "Dev"], "Invalid team")):
            code, report = run("workspace", "clone", "--path", str(missing), "--url", str(url), *args)
            self.assertEqual(code, 1, report)
            self.assertIn(message, report["error"])
            self.assertFalse(missing.exists(), args)

        empty = self.base / "empty"
        empty.mkdir()
        self.assertEqual(run("workspace", "clone", "--path", str(empty), "--url", str(url), "--name", "web")[0], 1)
        self.assertEqual(list(empty.iterdir()), [])
        code, report = run("workspace", "clone", "--path", str(empty), "--url", str(url), "--name", "be")
        self.assertEqual(code, 0, "the corrected command runs in the same folder")
        self.assertEqual([c["name"] for c in report["cloned"]], ["be"])

    def test_a_harness_record_this_starter_cannot_read_is_only_a_warning(self):
        url = self.share()
        be = self.ws / "be"
        record = json.loads((be / ".ai/harness.json").read_text(encoding="utf-8"))
        record["fromANewerStarter"] = True
        (be / ".ai/harness.json").write_text(json.dumps(record), encoding="utf-8")
        commit_all(be)
        git(be, "push", "-q", str(self.base / "remotes" / "be.git"), "HEAD")

        mate = self.base / "mate"
        code, report = run("workspace", "clone", "--path", str(mate), "--url", str(url))
        self.assertEqual(code, 0, report)
        self.assertEqual([c["name"] for c in report["cloned"]], ["be"])
        self.assertTrue(any("cannot read" in w and w.startswith("be:") for w in report["warnings"]), report["warnings"])
        self.assertIn(str(mate.resolve()), [w["path"] for w in run("workspace", "list")[1]["workspaces"]])

    def test_check_reports_a_folder_git_cannot_read_and_still_checks_the_rest(self):
        url = self.share()
        mate = self.base / "mate"
        self.assertEqual(run("workspace", "clone", "--path", str(mate), "--url", str(url), "--team", "dev")[0], 0)
        shutil.rmtree(mate / ".git")
        process = subprocess.run([sys.executable, "-I", str(mate / ".ai/workspace.py"), "check"], capture_output=True, text=True,
                                 env={**os.environ, "GIT_CEILING_DIRECTORIES": str(self.base)})
        report = json.loads(process.stdout)
        self.assertEqual(process.returncode, 1, report)
        self.assertTrue(any("git cannot read" in p for p in report["problems"]), report)
        self.assertEqual((report["team"], report["missing"]), ("dev", ["legacy"]), "the rest of the check still ran")


if __name__ == "__main__":
    unittest.main()
