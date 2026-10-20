from __future__ import annotations

import json
import unittest
from unittest import mock

from support import merge, policy

Policy = policy.Policy

MAP = "<!-- project:map:start -->\n{}<!-- project:map:end -->\n"
RULES = "<!-- project:rules:start -->\n{}<!-- project:rules:end -->\n"


def doc(*parts: str) -> bytes:
    return "".join(parts).encode()


def as_json(value) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode()


def text(ours: bytes, base: bytes, theirs: bytes) -> merge.Merge:
    return merge.merge_file(Policy.TEXT, "AGENTS.md", ours, base, theirs, "be")


def config(ours, base, theirs) -> merge.Merge:
    return merge.merge_file(Policy.JSON, ".ai/config.json", as_json(ours), as_json(base), as_json(theirs), "be")


class PolicyTest(unittest.TestCase):
    def test_policy_follows_the_path_and_how_the_target_got_its_harness(self):
        cases = [
            ("wiki/log.md", "new", Policy.SEED), ("wiki/index.md", "adopt", Policy.SEED),
            (".gitignore", "adopt", Policy.APPEND_LINES), (".gitignore", "new", Policy.TEXT), (".gitignore", "workspace", Policy.TEXT),
            (".ai/config.json", "new", Policy.JSON), (".claude/settings.json", "workspace", Policy.JSON),
            ("AGENTS.md", "adopt", Policy.TEXT),
        ]
        for rel, mode, expected in cases:
            self.assertIs(policy.policy_for(rel, mode), expected, (rel, mode))

    def test_seed_is_never_merged_into(self):
        result = merge.merge_file(Policy.SEED, "wiki/log.md", b"mine\n", b"base\n", b"theirs\n", "be")
        self.assertIsNone(result.data)
        self.assertIn("writes this file after install", result.skip)


class TextMergeTest(unittest.TestCase):
    def test_edits_on_distant_lines_both_survive(self):
        result = text(b"A\nb\nc\nd\ne\n", b"a\nb\nc\nd\ne\n", b"a\nb\nc\nd\nE\n")
        self.assertEqual((result.data, result.conflicts), (b"A\nb\nc\nd\nE\n", 0))

    def test_the_same_line_changed_on_both_sides_leaves_markers(self):
        result = text(b"mine\n", b"base\n", b"theirs\n")
        self.assertEqual(result.conflicts, 1)
        self.assertIn(b"<<<<<<< be\nmine\n=======\ntheirs\n>>>>>>> starter (current)", result.data)


class BlockMergeTest(unittest.TestCase):
    base = doc("# Title\n", MAP.format("placeholder\n"), "tail\n")

    def test_the_target_body_survives_starter_edits_inside_and_next_to_the_block(self):
        result = text(doc("# Title\n", MAP.format("- src/: code\n"), "tail\n"), self.base,
                      doc("# Title\n", MAP.format("new placeholder\n"), "new tail\n"))
        self.assertEqual(result.conflicts, 0)
        self.assertEqual(result.data, doc("# Title\n", MAP.format("- src/: code\n"), "new tail\n"))

    def test_an_untouched_block_takes_the_new_placeholder(self):
        result = text(doc("# Mine\n", MAP.format("placeholder\n"), "tail\n"), self.base,
                      doc("# Title\n", MAP.format("new placeholder\n"), "tail\n"))
        self.assertEqual(result.data, doc("# Mine\n", MAP.format("new placeholder\n"), "tail\n"))

    def test_a_block_the_starter_adds_arrives_with_its_body(self):
        result = text(doc("# Title\n", MAP.format("- src/\n"), "tail\n"), self.base,
                      doc("# Title\n", MAP.format("placeholder\n"), "tail\n", RULES.format("None yet.\n")))
        self.assertEqual(result.data, doc("# Title\n", MAP.format("- src/\n"), "tail\n", RULES.format("None yet.\n")))

    def test_a_filled_block_the_starter_dropped_is_skipped(self):
        result = text(doc("# Title\n", MAP.format("- src/\n"), "tail\n"), self.base, doc("# Title\n", "tail\n"))
        self.assertIsNone(result.data)
        self.assertIn("project:map", result.skip)

    def test_a_block_only_the_target_has_stays_where_it_is(self):
        own = "<!-- project:extra:start -->\nmine\n<!-- project:extra:end -->\n"
        result = text(doc("# Title\n", MAP.format("placeholder\n"), "tail\n", own), self.base,
                      doc("# New title\n", MAP.format("placeholder\n"), "tail\n"))
        self.assertEqual((result.data, result.conflicts), (doc("# New title\n", MAP.format("placeholder\n"), "tail\n", own), 0))

    def test_unpaired_markers_fall_back_to_a_line_merge(self):
        ours = doc("# Title\n", "<!-- project:map:start -->\n- src/\n", "tail\n")
        theirs = doc("# Title\n", MAP.format("placeholder\n"), "new tail\n")
        self.assertEqual(text(ours, self.base, theirs).data, merge.merge_text(ours, self.base, theirs, "be")[0])

    def test_crlf_files_keep_their_line_endings(self):
        def crlf(value: bytes) -> bytes:
            return value.replace(b"\n", b"\r\n")

        result = text(crlf(doc("# Title\n", MAP.format("- src/\n"), "tail\n")), crlf(self.base),
                      crlf(doc("# Title\n", MAP.format("placeholder\n"), "new tail\n")))
        self.assertEqual(result.data, crlf(doc("# Title\n", MAP.format("- src/\n"), "new tail\n")))


class JsonMergeTest(unittest.TestCase):
    def test_keys_the_starter_adds_arrive_next_to_the_target_values(self):
        result = config({"a": 2}, {"a": 1}, {"a": 1, "b": 3})
        self.assertEqual((json.loads(result.data), result.kept), ({"a": 2, "b": 3}, []))

    def test_a_key_both_sides_changed_keeps_the_target_value_and_is_reported_by_path(self):
        result = config({"git": {"base": "develop"}}, {"git": {"base": "main"}}, {"git": {"base": "trunk"}})
        self.assertIsNone(result.data)
        self.assertEqual(result.kept, ["git.base"])

    def test_a_key_the_target_deleted_stays_deleted_even_when_the_starter_changed_it(self):
        result = config({"a": 1}, {"a": 1, "b": 1}, {"a": 1, "b": 2})
        self.assertIsNone(result.data)
        self.assertEqual(result.kept, ["b"])

    def test_a_key_the_starter_deleted_goes_when_the_target_left_it_alone(self):
        result = config({"a": 2, "b": 1}, {"a": 1, "b": 1}, {"a": 1})
        self.assertEqual(json.loads(result.data), {"a": 2})

    def test_lists_of_plain_values_merge_by_item(self):
        result = config({"allow": ["x", "y", "mine"]}, {"allow": ["x", "y"]}, {"allow": ["x", "new"]})
        self.assertEqual(json.loads(result.data), {"allow": ["x", "mine", "new"]})

    def test_lists_of_objects_changed_on_both_sides_keep_the_target_list(self):
        result = config({"checks": [{"id": "a"}, {"id": "b"}]}, {"checks": [{"id": "a"}]}, {"checks": [{"id": "c"}]})
        self.assertIsNone(result.data)
        self.assertEqual(result.kept, ["checks"])

    def test_a_type_changed_on_both_sides_keeps_the_target_value(self):
        result = config({"a": "mine"}, {"a": "base"}, {"a": {"nested": True}})
        self.assertEqual(result.kept, ["a"])

    def test_json_that_does_not_parse_falls_back_to_a_line_merge(self):
        ours, base, theirs = b'{\n  "a": 2,\n}\n', b'{\n  "a": 1\n}\n', b'{\n  "a": 1\n}\n'
        result = merge.merge_file(Policy.JSON, "x.json", ours, base, theirs, "be")
        self.assertEqual(result.data, merge.merge_text(ours, base, theirs, "be")[0])

    def test_a_raised_schema_version_needs_every_migration_step(self):
        ours, base, theirs = {"schemaVersion": 1, "summary": "mine"}, {"schemaVersion": 1, "summary": ""}, {"schemaVersion": 2, "description": ""}
        self.assertIn("MIGRATIONS", config(ours, base, theirs).skip)

        def rename(value: dict) -> dict:
            return {"schemaVersion": 2, "description": value["summary"]}

        with mock.patch.dict(merge.MIGRATIONS, {(".ai/config.json", 1): rename}):
            result = config(ours, base, theirs)
        self.assertEqual(json.loads(result.data), {"schemaVersion": 2, "description": "mine"})


class AppendLinesTest(unittest.TestCase):
    def merged(self, ours: bytes, base: bytes, theirs: bytes) -> merge.Merge:
        return merge.merge_file(Policy.APPEND_LINES, ".gitignore", ours, base, theirs, "legacy")

    def test_only_lines_new_in_the_starter_are_appended(self):
        result = self.merged(b"node_modules/\na\n", b"a\nb\n", b"a\nb\nc\n")
        self.assertEqual(result.data, b"node_modules/\na\n\n# ai-starter harness\nc\n")

    def test_lines_the_target_already_has_write_nothing(self):
        self.assertIsNone(self.merged(b"a\nc\n", b"a\n", b"a\nc\n").data)


if __name__ == "__main__":
    unittest.main()
