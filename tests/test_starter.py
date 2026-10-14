from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tool"))

import starter  # noqa: E402


def run(*argv: str) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = starter.main(list(argv))
    return code, json.loads(out.getvalue())


def snapshot(root: Path) -> dict[str, str]:
    return {f: starter.file_hash(root / f) for f in starter.tree_files(root)} if root.exists() else {}


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return path


class StarterTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ai-starter-"))
        self.ws = self.base / "product"
        self.registry = self.base / "home" / "workspaces.json"
        self._saved_registry = os.environ.get(starter.REGISTRY_ENV)
        os.environ[starter.REGISTRY_ENV] = str(self.registry)
        self.template_before = snapshot(starter.TEMPLATE)
        self.workspace_template_before = snapshot(starter.WORKSPACE_TEMPLATE)

    def tearDown(self):
        if self._saved_registry is None:
            os.environ.pop(starter.REGISTRY_ENV, None)
        else:
            os.environ[starter.REGISTRY_ENV] = self._saved_registry
        self.assertEqual(snapshot(starter.TEMPLATE), self.template_before, "the starter template must never change")
        self.assertEqual(snapshot(starter.WORKSPACE_TEMPLATE), self.workspace_template_before)
        shutil.rmtree(self.base, ignore_errors=True)

    def manifest(self) -> dict:
        return json.loads((self.ws / "workspace.json").read_text(encoding="utf-8"))

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

        self.assertEqual(self.manifest()["repos"], [{"name": "be", "path": "be", "role": "Backend API", "kind": "managed", "remote": ""}])
        agents = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("| be | `be/` | Backend API | managed | - |", agents)

        env = {**os.environ, "AI_HARNESS_SELF_TEST": "1"}
        doctor = subprocess.run([sys.executable, "tool/ai.py", "doctor"], cwd=repo, capture_output=True, text=True, env=env)
        self.assertEqual(doctor.returncode, 0, doctor.stdout)
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
        before["web/notes.txt"] = starter.file_hash(self.ws / "web/notes.txt")
        self.assertEqual(run("new", "--workspace", str(self.ws), "--name", "web")[0], 1)
        self.assertEqual(snapshot(self.ws), before)

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
        self.assertEqual(run("workspace", "add", "--path", str(starter.STARTER / "nested"))[0], 1)

    def test_unreadable_workspace_list_does_not_block_creation(self):
        self.registry.parent.mkdir(parents=True)
        self.registry.write_text("not json", encoding="utf-8")
        code, report = run("new", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        self.assertTrue(any("workspace list" in w for w in report["warnings"]))
        self.assertEqual(self.registry.read_text(encoding="utf-8"), "not json")
        self.assertEqual(run("workspace", "list")[0], 1)

    def test_workspace_inside_the_starter_is_rejected(self):
        code, report = run("new", "--workspace", str(starter.STARTER / "scratch-ws"), "--name", "be")
        self.assertEqual(code, 1)
        self.assertFalse((starter.STARTER / "scratch-ws").exists())

    def test_folder_with_foreign_workspace_files_is_not_initialized(self):
        self.ws.mkdir()
        (self.ws / "AGENTS.md").write_text("# Mine\n", encoding="utf-8")
        code, report = run("new", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 1)
        self.assertFalse((self.ws / "be").exists())


class StarterSkillsTest(unittest.TestCase):
    def test_skills_have_matching_frontmatter_and_reference_existing_skills(self):
        skills = sorted((starter.STARTER / ".claude/skills").glob("starter-*/SKILL.md"))
        names = {path.parent.name for path in skills}
        self.assertTrue(names)
        for path in skills:
            text = path.read_text(encoding="utf-8")
            header = text.split("---", 2)[1]
            self.assertIn(f"\nname: {path.parent.name}\n", header, path)
            self.assertRegex(header, r"\ndescription: \S", path)
            for referenced in set(re.findall(r"`(starter-[a-z-]+)`", text)):
                self.assertIn(referenced, names, f"{path} names a missing skill")
        for path in (starter.STARTER / ".claude/skills").glob("starter-*/**/*.md"):
            for target in re.findall(r"\]\(([^)#:]+\.md)\)", path.read_text(encoding="utf-8")):
                self.assertTrue((path.parent / target).is_file(), f"{path} links a missing {target}")


if __name__ == "__main__":
    unittest.main()
