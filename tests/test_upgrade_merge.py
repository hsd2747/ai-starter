from __future__ import annotations

import json
import re
import unittest

from support import UpgradeCase, commit_all, git_repo, merge, run


class UpgradeMergeTest(UpgradeCase):
    def test_marked_blocks_keep_the_target_text_while_the_text_around_them_merges(self):
        repo = self.create()
        self.edit(repo / "AGENTS.md", "Not onboarded yet. Onboarding replaces the text between these markers with the top-level layout, "
                  "one line per area, and links\nto the architecture pages in the wiki.", "- `src/`: application code.")
        commit_all(repo)
        template = self.fake / "template/AGENTS.md"
        self.edit(template, "Not onboarded yet. Onboarding replaces the text", "Not onboarded. Onboarding replaces the text")
        self.edit(template, "<!-- project:map:end -->\n", "<!-- project:map:end -->\n\nStarter note right after the map.\n")
        self.edit(template, "Not onboarded yet. Onboarding states", "Not onboarded. Onboarding states")
        commit_all(self.fake)

        code, report = run("upgrade", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["targets"][0]["merged"], ["AGENTS.md"])
        self.assertEqual(report["targets"][0]["conflicts"], [])
        agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- project:map:start -->\n- `src/`: application code.\n<!-- project:map:end -->\n\nStarter note right after the map.\n", agents)
        self.assertIn("Not onboarded. Onboarding states", agents)
        self.assertNotIn("Not onboarded. Onboarding replaces", agents)

    def test_a_filled_block_the_starter_dropped_skips_the_file(self):
        repo = self.create()
        self.edit(repo / "AGENTS.md", "None yet. Judgement rules", "- Never call the payment sandbox from tests.\nNone yet. Judgement rules")
        commit_all(repo)
        template = self.fake / "template/AGENTS.md"
        text = template.read_text(encoding="utf-8")
        template.write_text(re.sub(r"## Project rules\n\n<!-- project:rules:start -->\n.*?<!-- project:rules:end -->\n\n", "", text, flags=re.S),
                            encoding="utf-8")
        commit_all(self.fake)

        before = (repo / "AGENTS.md").read_bytes()
        code, report = run("upgrade", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        skipped = report["targets"][0]["skipped"]
        self.assertEqual([s["path"] for s in skipped], ["AGENTS.md"])
        self.assertIn("project:rules", skipped[0]["reason"])
        self.assertEqual((repo / "AGENTS.md").read_bytes(), before)

    def test_json_merges_by_key_and_keeps_the_target_value_on_a_clash(self):
        repo = self.create()
        config = json.loads((repo / ".ai/config.json").read_text(encoding="utf-8"))
        config["project"]["name"] = "be"
        config["git"]["baseBranch"] = "develop"
        config["toolchain"] = [{"name": "node", "command": ["node", "--version"]}]
        (repo / ".ai/config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        settings = json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))
        settings["permissions"]["allow"].append("Bash(npm test:*)")
        (repo / ".claude/settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        commit_all(repo)
        template = self.fake / "template"
        config = json.loads((template / ".ai/config.json").read_text(encoding="utf-8"))
        config["git"]["baseBranch"] = "trunk"
        config["wiki"]["pageLimit"] = 500
        (template / ".ai/config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        settings = json.loads((template / ".claude/settings.json").read_text(encoding="utf-8"))
        settings["permissions"]["allow"].append("Bash(git blame:*)")
        (template / ".claude/settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        commit_all(self.fake)

        code, report = run("upgrade", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        be = report["targets"][0]
        self.assertEqual(be["merged"], [".ai/config.json", ".claude/settings.json"])
        self.assertEqual(be["conflicts"], [])
        self.assertEqual(be["kept"], [{"path": ".ai/config.json", "keys": ["git.baseBranch"]}])
        config = json.loads((repo / ".ai/config.json").read_text(encoding="utf-8"))
        self.assertEqual((config["project"]["name"], config["git"]["baseBranch"], config["wiki"]["pageLimit"]), ("be", "develop", 500))
        self.assertEqual(config["toolchain"], [{"name": "node", "command": ["node", "--version"]}])
        allow = json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
        self.assertEqual(allow[-2:], ["Bash(npm test:*)", "Bash(git blame:*)"])

    def test_raised_schema_version_needs_a_migration(self):
        repo = self.create()
        self.edit(repo / ".ai/config.json", '"name": ""', '"name": "be"')
        commit_all(repo)
        template = self.fake / "template/.ai/config.json"
        self.edit(template, '"schemaVersion": 1', '"schemaVersion": 2')
        self.edit(template, '"summary": ""', '"description": ""')
        commit_all(self.fake)

        code, report = run("upgrade", "--workspace", str(self.ws), "--name", "be", "--dry-run")
        self.assertEqual(code, 0, report)
        skipped = report["targets"][0]["skipped"]
        self.assertEqual([s["path"] for s in skipped], [".ai/config.json"])
        self.assertIn("MIGRATIONS", skipped[0]["reason"])

        def rename_summary(value: dict) -> dict:
            project = {"name": value["project"]["name"], "description": value["project"]["summary"]}
            return {**value, "schemaVersion": 2, "project": project}

        merge.MIGRATIONS[(".ai/config.json", 1)] = rename_summary
        self.addCleanup(merge.MIGRATIONS.pop, (".ai/config.json", 1))
        code, report = run("upgrade", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["targets"][0]["kept"], [])
        config = json.loads((repo / ".ai/config.json").read_text(encoding="utf-8"))
        self.assertEqual((config["schemaVersion"], config["project"]), (2, {"name": "be", "description": ""}))

    def test_seed_files_are_replaced_only_while_untouched(self):
        repo = self.create()
        with (repo / "wiki/log.md").open("a", encoding="utf-8") as handle:
            handle.write("\n## [2026-01-01] setup | Architecture\nSource: onboarding\nCreated: [[architecture]]\n")
        commit_all(repo)
        template = self.fake / "template/wiki"
        self.edit(template / "log.md", "Append-only history of wiki writes.", "Append-only history of every wiki write.")
        self.edit(template / "index.md", "Catalog of every page.", "Catalog of every wiki page.")
        commit_all(self.fake)

        before = (repo / "wiki/log.md").read_bytes()
        code, report = run("upgrade", "--workspace", str(self.ws), "--name", "be")
        self.assertEqual(code, 0, report)
        be = report["targets"][0]
        self.assertEqual(be["updated"], ["wiki/index.md"])
        self.assertEqual([s["path"] for s in be["skipped"]], ["wiki/log.md"])
        self.assertEqual((repo / "wiki/log.md").read_bytes(), before)

    def test_adopted_gitignore_gets_only_lines_new_in_the_starter(self):
        repo = git_repo(self.ws / "legacy")
        (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        self.assertEqual(run("adopt", "--workspace", str(self.ws), "--path", "legacy", "--install")[0], 0)
        self.edit(repo / ".gitignore", ".DS_Store\n", "")
        commit_all(repo)
        commit_all(self.ws)
        with (self.fake / "template/.gitignore").open("a", encoding="utf-8") as handle:
            handle.write("coverage/\n")
        commit_all(self.fake)
        code, report = run("upgrade", "--workspace", str(self.ws))
        self.assertEqual(code, 0, report)
        lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "node_modules/")
        self.assertEqual(lines.count("coverage/"), 1)
        self.assertNotIn(".DS_Store", lines)


if __name__ == "__main__":
    unittest.main()
