from __future__ import annotations

import re
import unittest

from support import paths


class StarterSkillsTest(unittest.TestCase):
    def test_skills_have_matching_frontmatter_and_reference_existing_skills(self):
        skills = sorted((paths.STARTER / ".claude/skills").glob("starter-*/SKILL.md"))
        names = {path.parent.name for path in skills}
        self.assertTrue(names)
        for path in skills:
            text = path.read_text(encoding="utf-8")
            header = text.split("---", 2)[1]
            self.assertIn(f"\nname: {path.parent.name}\n", header, path)
            self.assertRegex(header, r"\ndescription: \S", path)
            for referenced in set(re.findall(r"`(starter-[a-z-]+)`", text)):
                self.assertIn(referenced, names, f"{path} names a missing skill")
        for path in (paths.STARTER / ".claude/skills").glob("starter-*/**/*.md"):
            for target in re.findall(r"\]\(([^)#:]+\.md)\)", path.read_text(encoding="utf-8")):
                self.assertTrue((path.parent / target).is_file(), f"{path} links a missing {target}")


if __name__ == "__main__":
    unittest.main()
