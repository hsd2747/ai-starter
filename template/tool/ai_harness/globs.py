from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable


@lru_cache(maxsize=None)
def compile_glob(pattern: str) -> re.Pattern[str]:
    """Glob over repository-relative paths.

    `*` and `?` never cross `/`; `**/` matches zero or more directories. Unlike
    fnmatch, `*.md` therefore matches only top-level files and `**/*.md` matches
    every depth, which keeps check patterns in .ai/config.json explicit.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        char = pattern[i]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                out.append(re.escape(char))
            else:
                body = pattern[i + 1 : end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = end + 1
                continue
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, patterns: Iterable[str]) -> bool:
    return any(compile_glob(pattern).match(path) for pattern in patterns)
