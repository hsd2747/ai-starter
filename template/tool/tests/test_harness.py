from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_harness import checks, docs, guard, hooks, secrets, wiki  # noqa: E402
from ai_harness.globs import matches  # noqa: E402
from ai_harness.paths import HarnessError, read_json  # noqa: E402
from ai_harness.schema import validate, validate_artifact  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "tool" / "ai.py"
HARNESS_PATHS = ["AGENTS.md", "CLAUDE.md", "REVIEW.md", ".ai", ".agents", ".githooks", "tool", "wiki", ".gitignore"]


def fixture_config() -> dict:
    """The repository's config without its project checks, whose tools a throwaway copy does not have."""
    config = read_json(REPO / ".ai/config.json")
    config.update(toolchain=[], checks=[])
    config.pop("members", None)
    return config


class TempRepo:
    """A throwaway git repository holding a copy of the harness."""

    def __init__(self, commit: bool = True):
        self.root = Path(tempfile.mkdtemp(prefix="ai-harness-"))
        for name in HARNESS_PATHS:
            source = REPO / name
            if source.is_dir():
                shutil.copytree(source, self.root / name, ignore=shutil.ignore_patterns("runs", "__pycache__"))
            else:
                shutil.copy2(source, self.root / name)
        (self.root / ".claude").mkdir()
        self.write(".ai/config.json", json.dumps(fixture_config(), indent=2) + "\n")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "test")
        self.cli("adapters", "sync")
        if commit:
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "init")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout

    def write(self, path: str, content: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def cli(self, *args: str, stdin: str | None = None) -> tuple[int, dict]:
        process = subprocess.run([sys.executable, str(self.root / "tool" / "ai.py"), *args], cwd=self.root,
                                 capture_output=True, text=True, input=stdin,
                                 env={**os.environ, checks.SELF_TEST_ENV: "1"}, timeout=120)
        try:
            return process.returncode, json.loads(process.stdout)
        except json.JSONDecodeError:
            return process.returncode, {"raw": process.stdout, "stderr": process.stderr}

    def set_checks(self, fragment: dict) -> None:
        config = fixture_config()
        config.update(fragment)
        self.write(".ai/config.json", json.dumps(config, indent=2) + "\n")

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class SchemaTest(unittest.TestCase):
    def test_shipped_config_is_valid(self):
        self.assertEqual(validate_artifact(REPO, "config", read_json(REPO / ".ai/config.json")), [])

    def test_config_rejects_unknown_check_fields_and_bad_patterns(self):
        config = read_json(REPO / ".ai/config.json")
        config["checks"] = [{"id": "lint", "description": "x", "command": ["x"], "shell": "rm -rf /",
                             "when": {"contentPattern": "("}}]
        config["git"]["branchPattern"] = "feature/x"
        errors = "\n".join(validate_artifact(REPO, "config", config))
        self.assertIn("unexpected property 'shell'", errors)
        self.assertIn("invalid regex", errors)
        self.assertIn("does not match", errors)

    def test_formats(self):
        schema = {"type": "object", "properties": {"p": {"type": "string", "format": "relative-path"},
                                                   "c": {"type": "string", "format": "check-id"}}}
        self.assertEqual(validate(schema, {"p": "src/a.ts", "c": "lint-web"}), [])
        self.assertEqual(len(validate(schema, {"p": "../etc", "c": "Lint_Web"})), 2)
        self.assertTrue(validate(schema, {"p": "/abs"}))

    def test_bool_is_not_integer_and_unknown_keywords_fail(self):
        self.assertTrue(validate({"type": "integer"}, True))
        self.assertTrue(validate({"type": "string", "oneOf": []}, "x"))


class GlobTest(unittest.TestCase):
    def test_star_does_not_cross_directories(self):
        self.assertTrue(matches("a.md", ["*.md"]))
        self.assertFalse(matches("docs/a.md", ["*.md"]))
        self.assertTrue(matches("docs/a.md", ["**/*.md"]))
        self.assertTrue(matches("a.md", ["**/*.md"]))
        self.assertTrue(matches("src/x/y.ts", ["src/**"]))
        self.assertFalse(matches("srcx/y.ts", ["src/**"]))


class DocLinkTest(unittest.TestCase):
    def test_code_is_not_scanned_and_resolution_stays_in_root(self):
        source = "[a](b.md) `[x](missing.md)`\n```\n[y](missing.md)\n```\n[w](https://x.y) [z](#anchor)"
        self.assertEqual(docs.link_targets(source), ["b.md"])
        self.assertEqual(docs.resolve_link("docs", "../a.md"), "a.md")
        self.assertIsNone(docs.resolve_link("", "../a.md"))
        self.assertEqual(docs.resolve_link("docs/x", "/README.md"), "README.md")

    def test_every_shipped_markdown_link_resolves(self):
        files = [p.relative_to(REPO).as_posix() for p in REPO.rglob("*.md")
                 if ".git" not in p.parts and "runs" not in p.parts and ".claude" not in p.parts
                 and not checks.DEPENDENCY_SEGMENTS.intersection(p.parts)]
        self.assertEqual(docs.link_failures(REPO, files), [])


class SecretTest(unittest.TestCase):
    def test_env_file_detection(self):
        self.assertTrue(secrets.is_env_file(".env"))
        self.assertTrue(secrets.is_env_file("apps/web/.env.local"))
        self.assertFalse(secrets.is_env_file(".env.example"))
        self.assertFalse(secrets.is_env_file("src/env.ts"))

    def test_content_findings_never_echo_the_value(self):
        repo = Path(tempfile.mkdtemp())
        try:
            key = "AKIA" + "Z" * 16
            (repo / "a.txt").write_text(f"x = '{key}'\nsafe = '{key}'  # secret-scan: allow\n")
            findings = secrets.content_failures(repo, ["a.txt"])
            self.assertEqual(findings, ["a.txt:1: looks like aws-access-key-id"])
            self.assertNotIn(key, "".join(findings))
        finally:
            shutil.rmtree(repo)

    def test_connection_strings_flag_real_passwords_only(self):
        repo = Path(tempfile.mkdtemp())
        try:
            (repo / "a.txt").write_text("postgres://app:" + "s3cr3t-Value9" + "@db.internal:5432/app\n"
                                        "postgres://postgres:postgres@localhost/dev\n"
                                        "mongodb+srv://${DB_USER}:${DB_PASS}@cluster/app\n")
            self.assertEqual(secrets.content_failures(repo, ["a.txt"]), ["a.txt:1: looks like connection-string-password"])
        finally:
            shutil.rmtree(repo)

    def test_signing_keys_and_credentials_are_secret_files(self):
        for path in ["android/app/release.jks", "android/key.properties", "ios/AuthKey_ABC.p8", "client_secret_123.json"]:
            self.assertIsNotNone(secrets.secret_file_kind(path), path)
        for path in ["src/key.ts", "docs/keystore.md", "id_rsa.pub"]:
            self.assertIsNone(secrets.secret_file_kind(path), path)


class GuardTest(unittest.TestCase):
    def blocked(self, command: str) -> bool:
        return guard.evaluate({"tool_name": "Bash", "tool_input": {"command": command}}) is not None

    def test_blocks_irreversible_git(self):
        for command in ["git push --force", "git push -f origin main", "git push origin +main", "git reset --hard HEAD~1",
                        "git clean -fd", "git checkout -- src/a.ts", "git checkout .", "git restore src/a.ts",
                        "git branch -D feature/x", "git stash drop", "git push origin --delete feature/x",
                        "git push origin :feature/x", "git push -d origin v1.0", "git push --prune origin", "git push --mirror"]:
            self.assertTrue(self.blocked(command), command)

    def test_allows_safe_git(self):
        for command in ["git status", "git push -u origin feature/x", "git restore --staged a.ts", "git checkout -b feature/x",
                        "git push origin main && rm -rf build", "git diff --check HEAD --", "git push origin HEAD:refs/heads/feature/x",
                        "git branch -d feature/x"]:
            self.assertFalse(self.blocked(command), command)

    def test_secret_reads(self):
        for command in ["cat .env", "head -n 3 apps/.env.local", "grep TOKEN .env", "env", "printenv", "cut -d= -f2 .env"]:
            self.assertTrue(self.blocked(command), command)
        for command in ["cat .env.example", "grep -q TOKEN .env", "cut -d= -f1 .env", "env FOO=1 make", "printenv HOME"]:
            self.assertFalse(self.blocked(command), command)
        self.assertIsNotNone(guard.evaluate({"tool_name": "Read", "tool_input": {"file_path": "/x/.env"}}))
        self.assertIsNone(guard.evaluate({"tool_name": "Read", "tool_input": {"file_path": "/x/.env.example"}}))

    def test_broad_rm(self):
        self.assertTrue(self.blocked("rm -rf /"))
        self.assertTrue(self.blocked("rm -fr ."))
        self.assertTrue(self.blocked("rm -r ~"))
        self.assertFalse(self.blocked("rm -rf build"))
        self.assertFalse(self.blocked("rm a.txt"))

    def test_wrappers_global_options_and_nested_shells_do_not_bypass(self):
        for command in ["git -C . reset --hard", "git -c core.pager=cat push --force", "git checkout -f main",
                        "git switch --discard-changes main", "git branch -d -f old", "sudo rm -rf /", "rm -rf ./*",
                        "find . -delete", "bash -c 'git reset --hard'", "echo $(git reset --hard)",
                        "sh <<EOF\ngit reset --hard\nEOF"]:
            self.assertTrue(self.blocked(command), command)

    def test_text_inside_quotes_and_written_heredocs_is_data(self):
        for command in ["git commit -m 'docs: never run git reset --hard'", "git commit -m 'a; git reset --hard'",
                        "cat > notes.md <<'EOF'\nDo not run git reset --hard or cat .env\nEOF", "find . -name '*.pyc' -delete"]:
            self.assertFalse(self.blocked(command), command)

    def test_indirect_secret_reads(self):
        for command in ["cat .env*", "base64 .env", "cp .env /tmp/x", "printenv OPENAI_API_KEY", "echo $DB_PASSWORD",
                        "export -p", "python3 -c \"print(open('.env').read())\"",
                        "python3 - <<'EOF'\nprint(open('.env').read())\nEOF"]:
            self.assertTrue(self.blocked(command), command)
        for command in ["cp .env.example .env", "echo $PWD", "cat *.md", "source .env && npm run dev",
                        "node -e \"console.log(process.env.NODE_ENV)\""]:
            self.assertFalse(self.blocked(command), command)
        for command in ["git show HEAD:.env", "git show :.env", "git cat-file -p HEAD~2:apps/.env.local", "git log -p -- .env",
                        "git log --all --patch -- '.env*'", "git diff HEAD~1 -- .env", "git show abc123 -- .env", "git blame .env",
                        "git grep TOKEN HEAD -- .env", "tee /tmp/x < .env", "while read l; do echo $l; done < .env", "cat<.env"]:
            self.assertTrue(self.blocked(command), command)
        for command in ["git log --all --full-history -- '.env*'", "git log --oneline -- .env", "git diff --stat HEAD~1 -- .env",
                        "git show --name-only abc123 -- .env", "git show HEAD:.env.example", "git grep -l TOKEN -- .env",
                        "cut -d= -f1 < .env", "grep -q TOKEN < .env", "git log -p -- src/app.ts"]:
            self.assertFalse(self.blocked(command), command)
        grep = {"tool_name": "Grep", "tool_input": {"pattern": ".", "path": ".env", "output_mode": "content"}}
        self.assertIsNotNone(guard.evaluate(grep))
        grep["tool_input"]["output_mode"] = "files_with_matches"
        self.assertIsNone(guard.evaluate(grep))

    def test_hook_bypasses(self):
        for command in ["git commit --no-verify -m x", "git commit -nm x", "git commit -a -n", "git -c core.hooksPath=/dev/null commit -m x",
                        "git config core.hooksPath x", "git config --unset core.hooksPath", "git config set core.hooksPath x",
                        "bash -c 'git commit -n'"]:
            self.assertTrue(self.blocked(command), command)
        for command in ["git commit -m 'skip -n'", "git commit -m -n", "git commit -am fix", "git commit --amend --no-edit",
                        "git config --get core.hooksPath", "git config get core.hooksPath", "git commit -m 'never use --no-verify'"]:
            self.assertFalse(self.blocked(command), command)

    def test_unparseable_payload_is_allowed(self):
        self.assertEqual(guard.main("not json"), 0)
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(guard.main(json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}})), 2)
        self.assertIn("reset-hard", stderr.getvalue())


class WikiLintTest(unittest.TestCase):
    def setUp(self):
        # An onboarded repository's own pages must not leak into the fixtures below.
        self.root = Path(tempfile.mkdtemp())
        (self.root / "wiki").mkdir()
        shutil.copy(REPO / "wiki" / "README.md", self.root / "wiki" / "README.md")
        (self.root / "wiki/index.md").write_text("# Wiki index\n\n## Facts\n\n## Notes\n")
        (self.root / "wiki/log.md").write_text("# Wiki log\n")

    def tearDown(self):
        shutil.rmtree(self.root)

    def page(self, path: str, meta: str, body: str = "") -> None:
        target = self.root / "wiki" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"---\n{meta}\n---\n# Title\n{body}\n")

    def test_shipped_wiki_is_clean(self):
        self.assertEqual(wiki.lint(REPO, "wiki")[0], [])

    def test_valid_pages(self):
        common = "layer: facts\ntags: [architecture]\nsources:\n  - manual:2026-10-13\ncreated: 2026-10-13\nupdated: 2026-10-13"
        self.page("facts/architecture/architecture.md", f"kind: hub  # entry\n{common}", "[[dependency-rule]]")
        self.page("facts/architecture/dependency-rule.md", f"kind: rule\nadoption: enforced\n{common}", "## Related\n[[architecture]]")
        (self.root / "wiki/index.md").write_text("# Index\n## Facts\n- [[architecture]]\n- [[dependency-rule]]\n")
        errors, warnings = wiki.lint(self.root, "wiki")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_structural_errors(self):
        common = "layer: facts\ntags: []\nsources: [manual:2026-10-13]\ncreated: 2026-10-13\nupdated: 2026-10-13"
        self.page("facts/api/a-rule.md", f"kind: rule\n{common}", "[[ghost]]")
        self.page("notes/a-rule.md", "layer: notes\ntags: []\nsources: []\ncreated: 2026-10-13\nupdated: 2026-10-13")
        self.page("facts/api/Bad_Slug.md", f"kind: current\n{common}")
        with (self.root / "wiki/log.md").open("a") as log:
            log.write("\n## [2026-10-13] add | A\n\n## [2026-10-01] add | B\n\n## [2026-10-14] wrote | C\n")
        errors, warnings = wiki.lint(self.root, "wiki")
        errors = "\n".join(errors)
        for expected in ["need adoption", "dangling wikilink [[ghost]]", "duplicates", "not a valid facts slug",
                         "verified", "not listed", "unknown operation"]:
            self.assertIn(expected, errors)
        self.assertNotIn("older than", errors)
        self.assertIn("older than", "\n".join(warnings))

    def test_union_merge_is_declared_for_wiki_catalogs(self):
        attributes = (REPO / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("wiki/log.md merge=union", attributes)
        self.assertIn("wiki/index.md merge=union", attributes)


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()

    def tearDown(self):
        self.repo.close()

    def checks_by_id(self, report: dict) -> dict:
        return {c["id"]: c for c in report["checks"]}

    def test_clean_change_passes_and_writes_a_valid_receipt(self):
        self.repo.write("notes.md", "See [agents](AGENTS.md).\n")
        code, report = self.repo.cli("verify", "--id", "t1")
        self.assertEqual(code, 0, report)
        receipt = read_json(self.repo.root / report["receipt"])
        self.assertEqual(validate_artifact(self.repo.root, "verification", receipt), [])
        self.assertEqual(receipt["subject"]["files"], ["notes.md"])
        self.assertIn("doc-links", self.checks_by_id(report))

    def test_untracked_whitespace_staged_whitespace_and_dead_links_fail(self):
        self.repo.write("new.md", "trailing   \n[x](nope.md)\n")
        self.repo.write("AGENTS.md", (self.repo.root / "AGENTS.md").read_text() + "tail \n")
        self.repo.git("add", "AGENTS.md")
        code, report = self.repo.cli("verify", "--id", "t2")
        self.assertEqual(code, 1)
        checks = self.checks_by_id(report)
        self.assertEqual(checks["git-diff-check"]["status"], "fail")
        self.assertIn("new.md:1", checks["git-diff-check"]["summary"])
        self.assertIn("AGENTS.md", checks["git-diff-check"]["summary"])
        self.assertEqual(checks["doc-links"]["status"], "fail")

    def test_tracked_env_file_fails_secret_scan(self):
        self.repo.write(".env", "TOKEN=x\n")
        self.repo.git("add", "-f", ".env")
        code, report = self.repo.cli("verify", "--id", "t3")
        self.assertEqual(code, 1)
        self.assertEqual(self.checks_by_id(report)["secret-scan"]["status"], "fail")

    def test_committed_changes_on_a_branch_stay_in_scope(self):
        self.repo.git("switch", "-q", "-c", "feature/x")
        self.repo.write("leak.txt", "key = '" + "AKIA" + "Q" * 16 + "'\n")
        self.repo.git("add", "leak.txt")
        self.repo.git("commit", "-q", "-m", "leak")
        code, report = self.repo.cli("verify", "--id", "t8")
        self.assertEqual(code, 1)
        self.assertEqual(self.checks_by_id(report)["secret-scan"]["status"], "fail")
        receipt = read_json(self.repo.root / report["receipt"])
        self.assertEqual(receipt["subject"]["files"], ["leak.txt"])
        self.assertEqual(receipt["subject"]["baseRef"], "main")

    def test_tracked_signing_key_fails_and_suppressed_hits_are_reported(self):
        self.repo.write("release.keystore", "binary-ish\n")
        self.repo.git("add", "-f", "release.keystore")
        code, report = self.repo.cli("verify", "--id", "t9")
        self.assertEqual(code, 1)
        self.assertIn("release.keystore", self.checks_by_id(report)["secret-scan"]["summary"])
        self.repo.git("rm", "-q", "--cached", "release.keystore")
        (self.repo.root / "release.keystore").unlink()
        self.repo.write("doc.txt", "example = '" + "AKIA" + "Q" * 16 + "'  # secret-scan: allow\n")
        code, report = self.repo.cli("verify", "--id", "t10")
        self.assertEqual(code, 0, report)
        self.assertIn("doc.txt:1", "".join(report["warnings"]))

    def test_configured_checks_select_by_path_content_and_member(self):
        self.repo.set_checks({
            "members": {"globs": ["packages/*"], "marker": "pkg.json"},
            "checks": [
                {"id": "fmt", "description": "format", "stage": "early", "when": {"paths": ["**/*.txt"]},
                 "command": [sys.executable, "-c", "import sys; sys.exit(0)", "{files}"]},
                {"id": "gen", "description": "generate", "stage": "generate", "mutates": True,
                 "when": {"paths": ["**/*.txt"], "contentPattern": "^@generate"},
                 "command": [sys.executable, "-c", "pass"]},
                {"id": "test", "description": "tests", "per": "member", "when": {"paths": ["packages/**"]},
                 "command": [sys.executable, "-c", "pass"]},
            ],
        })
        self.repo.write("packages/a/pkg.json", "{}\n")
        self.repo.write("packages/b/pkg.json", "{}\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "members")
        self.repo.write("packages/a/x.txt", "plain\n")
        code, report = self.repo.cli("verify", "--dry-run")
        planned = [c["id"] for c in report["checks"]]
        self.assertEqual(planned, ["fmt", "test-packages-a"])
        self.assertEqual(report["checks"][0]["command"][-1], "packages/a/x.txt")
        self.repo.write("packages/b/y.txt", "@generate\n")
        _, report = self.repo.cli("verify", "--dry-run")
        self.assertEqual([c["id"] for c in report["checks"]], ["fmt", "gen", "test-packages-a", "test-packages-b"])

    def test_missing_optional_tool_is_skipped_and_required_fails(self):
        self.repo.set_checks({"checks": [
            {"id": "opt", "description": "optional", "required": False, "command": ["definitely-missing-tool-x"]},
            {"id": "req", "description": "required", "command": ["definitely-missing-tool-y"]},
        ]})
        code, report = self.repo.cli("verify", "--id", "t4")
        checks = self.checks_by_id(report)
        self.assertEqual(checks["opt"]["status"], "skipped")
        self.assertEqual(checks["req"]["status"], "fail")
        self.assertEqual(code, 1)

    def test_generator_that_rewrites_files_fails_subject_stability(self):
        self.repo.set_checks({"checks": [
            {"id": "gen", "description": "generator", "stage": "generate", "mutates": True,
             "command": [sys.executable, "-c", "open('generated.txt','w').write('new\\n')"]},
        ]})
        code, report = self.repo.cli("verify", "--id", "t5")
        self.assertEqual(code, 1)
        self.assertIn("stale", self.checks_by_id(report)["verification-subject-stable"]["summary"])

    def test_broken_adapter_fails_harness_config(self):
        (self.repo.root / ".claude/skills/repo-review").unlink()
        self.repo.write("x.md", "x\n")
        code, report = self.repo.cli("verify", "--id", "t6")
        self.assertEqual(code, 1)
        self.assertIn("adapters sync", self.checks_by_id(report)["harness-config"]["summary"])

    def test_forced_check_runs_without_matching_files_and_unknown_ids_fail(self):
        self.repo.set_checks({"checks": [
            {"id": "lint", "description": "lint", "when": {"paths": ["**/*.py"]}, "command": [sys.executable, "-c", "pass"]},
        ]})
        self.repo.git("commit", "-qam", "checks")
        self.repo.write("notes.md", "x\n")
        _, report = self.repo.cli("verify", "--dry-run")
        self.assertEqual(report["checks"], [])
        _, report = self.repo.cli("verify", "--dry-run", "--check", "lint")
        self.assertEqual([c["id"] for c in report["checks"]], ["lint"])
        code, report = self.repo.cli("verify", "--check", "ghost")
        self.assertEqual(code, 1)
        self.assertIn("ghost", report["error"])

    def test_receipts_are_never_overwritten(self):
        self.repo.cli("verify", "--id", "R3")
        self.repo.cli("verify", "--id", "R3")
        self.assertEqual(len(list((self.repo.root / ".ai/runs/R3").glob("verification-*.json"))), 2)

    def test_staged_copy_is_checked_when_the_working_tree_differs(self):
        self.repo.write("config.txt", "key = '" + "AKIA" + "Q" * 16 + "'\n<<<<<<< ours\n")
        self.repo.git("add", "config.txt")
        self.repo.write("config.txt", "key = ''\n")
        code, report = self.repo.cli("verify", "--id", "t11")
        self.assertEqual(code, 1)
        checks = self.checks_by_id(report)
        self.assertIn("config.txt (staged):1", checks["secret-scan"]["summary"])
        self.assertIn("staged: config.txt:2", checks["git-diff-check"]["summary"])

        self.repo.write("config.txt", "key = ''\n")
        self.repo.git("add", "config.txt")
        self.repo.write("config.txt", "key = ''\nmore\n")
        code, report = self.repo.cli("verify", "--id", "t12")
        self.assertEqual(code, 0, report)

    def test_repository_without_commits(self):
        fresh = TempRepo(commit=False)
        try:
            code, report = fresh.cli("verify", "--id", "t7")
            self.assertEqual(code, 0, report)
        finally:
            fresh.close()


class HookTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()

    def tearDown(self):
        self.repo.close()

    def commit(self, add_all: bool = True) -> subprocess.CompletedProcess:
        if add_all:
            self.repo.git("add", "-A")
        return subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=self.repo.root, capture_output=True, text=True,
                              env={**os.environ, checks.SELF_TEST_ENV: "1"})

    def test_installed_hook_verifies_every_commit(self):
        self.assertIn("hooks install", " ".join(self.repo.cli("doctor")[1]["warnings"]))
        code, report = self.repo.cli("hooks", "install")
        self.assertEqual(code, 0, report)
        self.assertTrue(report["installed"] and report["runsVerify"])
        self.assertEqual(self.repo.git("config", "core.hooksPath").strip(), hooks.HOOKS_DIR)
        self.assertNotIn("Commits are not verified", " ".join(self.repo.cli("doctor")[1]["warnings"]))
        self.assertEqual(self.repo.cli("hooks", "install")[1]["installed"], False)

        self.repo.write("notes.md", "trailing   \n")
        self.assertNotEqual(self.commit().returncode, 0)
        self.assertEqual(self.repo.git("rev-list", "--count", "HEAD").strip(), "1")
        self.repo.write("notes.md", "clean\n")
        self.assertEqual(self.commit().returncode, 0)
        self.assertTrue(list((self.repo.root / ".ai/runs/pre-commit").glob("verification-*.json")))

    def test_hook_checks_the_staged_copy_and_allows_staging_in_part(self):
        self.repo.cli("hooks", "install")
        self.repo.write("config.txt", "key = '" + "AKIA" + "Q" * 16 + "'\n")
        self.repo.git("add", "config.txt")
        self.repo.write("config.txt", "key = ''\n")
        self.assertNotEqual(self.commit(add_all=False).returncode, 0)
        self.assertEqual(self.repo.git("rev-list", "--count", "HEAD").strip(), "1")

        self.repo.git("add", "config.txt")
        self.repo.write("config.txt", "key = ''\nnot staged\n")
        self.assertEqual(self.commit(add_all=False).returncode, 0)
        self.assertEqual(self.repo.git("show", "HEAD:config.txt"), "key = ''\n")

    def test_other_tools_hooks_stay_in_effect(self):
        hook = Path(self.repo.git("rev-parse", "--git-path", "hooks").strip())
        hook = (self.repo.root / hook / "pre-push")
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        hook.chmod(0o755)
        code, report = self.repo.cli("hooks", "install")
        self.assertEqual(code, 1)
        self.assertIn("another tool", report["problem"])
        self.assertEqual(subprocess.run(["git", "config", "core.hooksPath"], cwd=self.repo.root).returncode, 1)

        self.repo.git("config", "core.hooksPath", ".husky")
        self.assertEqual(self.repo.cli("hooks", "install")[0], 1)
        self.repo.write(".husky/pre-commit", "#!/bin/sh\npython3 tool/ai.py verify --id pre-commit\n")
        (self.repo.root / ".husky/pre-commit").chmod(0o755)
        code, report = self.repo.cli("hooks", "install")
        self.assertEqual(code, 0, report)
        self.assertTrue(report["runsVerify"])
        self.assertEqual(self.repo.git("config", "core.hooksPath").strip(), ".husky")

    def test_unexecutable_hook_is_reported(self):
        (self.repo.root / hooks.PRE_COMMIT).chmod(0o644)
        code, report = self.repo.cli("hooks", "install")
        self.assertEqual(code, 1)
        self.assertIn("chmod +x", report["problem"])


class ConfigRuleTest(unittest.TestCase):
    def test_reserved_and_duplicate_ids(self):
        config = {"schemaVersion": 1, "toolchain": [], "checks": [
            {"id": "wiki-lint", "description": "x", "command": ["x"]},
            {"id": "a", "description": "x", "command": ["x"]},
            {"id": "a", "description": "x", "command": ["x"], "per": "member"},
        ]}
        errors = "\n".join(checks.config_rule_errors(config))
        self.assertIn("reserved", errors)
        self.assertIn("duplicate", errors)
        self.assertIn("no 'members'", errors)

    def test_forcing_an_undeclared_check_raises(self):
        with self.assertRaises(HarnessError):
            checks.select(REPO, {"checks": []}, [], [], "changed", frozenset({"ghost"}))


if __name__ == "__main__":
    unittest.main()
