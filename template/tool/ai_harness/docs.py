from __future__ import annotations

import re
from pathlib import Path

from .paths import read_text_or_none

_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.M | re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def strip_code(source: str) -> str:
    """Markdown with fenced and inline code removed, so examples are not read as links."""
    return _INLINE_CODE.sub("", _FENCE.sub("", source))


def link_targets(source: str) -> list[str]:
    """Relative link targets that must exist. External schemes and bare anchors are skipped."""
    targets = []
    for match in _LINK.finditer(strip_code(source)):
        raw = match.group(1)
        if raw.startswith("#") or raw.startswith("mailto:") or "://" in raw:
            continue
        target = raw.split("#", 1)[0]
        if target:
            targets.append(target)
    return targets


def resolve_link(directory: str, target: str) -> str | None:
    """Repository-relative path of `target` inside `directory`, or None when it climbs above the root."""
    rooted = target.startswith("/")
    segments = [] if rooted or not directory else directory.split("/")
    for segment in (target[1:] if rooted else target).split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not segments:
                return None
            segments.pop()
            continue
        segments.append(segment)
    return "/".join(segments) if segments else None


def link_failures(root: Path, markdown_files: list[str]) -> list[str]:
    """One message per unresolvable link. AGENTS.md delegates rules by link, so a dead link is a rule nobody reads."""
    failures = []
    for path in markdown_files:
        source = read_text_or_none(root / path)
        if source is None:
            continue
        directory = path.rsplit("/", 1)[0] if "/" in path else ""
        for target in link_targets(source):
            resolved = resolve_link(directory, target)
            if resolved is None:
                failures.append(f"{path}: link escapes the repository: {target}")
            elif not (root / resolved).exists():
                failures.append(f"{path}: missing link target: {target}")
    return failures
