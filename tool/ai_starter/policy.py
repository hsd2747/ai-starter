"""How the starter treats each harness file that a target may have changed. Add special handling for a file here.

Content decides the rest at merge time: a text file with `project:` or `workspace:` markers keeps the target's blocks,
and links or binaries changed on both sides are always left for a manual merge.
"""

from __future__ import annotations

from enum import Enum


class Policy(Enum):
    SEED = "seed"
    """Installed once, then written by the target: replaced only while untouched, never merged into."""
    APPEND_LINES = "append-lines"
    """A pattern list the target already had: starter lines it lacks are appended; starter removals never apply."""
    JSON = "json"
    """Merged by key; where both sides changed a key, the target's value stays."""
    TEXT = "text"
    """Merged by line, around any marked blocks."""


SEEDS = {"wiki/index.md", "wiki/log.md"}
# Existing repositories usually have these already, so adopting one appends harness lines instead of reporting a conflict.
APPEND_ON_ADOPT = {".gitignore", ".gitattributes"}


def policy_for(rel: str, mode: str) -> Policy:
    """`mode` is how the target got its harness: "new", "adopt", or "workspace" for a workspace root."""
    if rel in SEEDS:
        return Policy.SEED
    if mode == "adopt" and rel in APPEND_ON_ADOPT:
        return Policy.APPEND_LINES
    if rel.endswith(".json"):
        return Policy.JSON
    return Policy.TEXT
