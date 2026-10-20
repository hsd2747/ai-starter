"""Three-way merges of one harness file. `merge_file` runs the merge that the file's Policy names."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .paths import StarterError
from .policy import Policy

# Lines between a pair of these markers belong to the target, in any harness file. upgrade merges only the text around them.
_BLOCK_MARKER = re.compile(r"[ \t]*(?:<!--|#)[ \t]*((?:project|workspace):[a-z0-9-]+):(start|end)[ \t]*(?:-->)?[ \t]*\Z")
# (harness file, schemaVersion N) -> function that returns the content at N + 1. A template change that raises a schemaVersion
# adds its steps here; without them upgrade skips the file instead of mixing two versions of its shape.
MIGRATIONS: dict[tuple[str, int], Callable[[dict], dict]] = {}


@dataclass
class Merge:
    data: bytes | None = None
    """Content to write, or None to leave the file as it is."""
    conflicts: int = 0
    """Conflict marker regions left in `data`."""
    kept: list[str] = field(default_factory=list)
    """JSON keys that both sides changed, where the target's value stayed."""
    skip: str | None = None
    """Why the file is left for a manual merge; nothing is written then."""


def merge_file(policy: Policy, rel: str, ours: bytes, base: bytes, theirs: bytes, label: str) -> Merge:
    """Merges the target's `ours` with the starter's change from `base` to `theirs`. `label` names `ours` in conflict markers."""
    if policy is Policy.SEED:
        return Merge(skip="the target writes this file after install; compare it with the starter's copy by hand")
    if policy is Policy.APPEND_LINES:
        return _append_lines(ours, base, theirs)
    if policy is Policy.JSON:
        merged = _merge_json(rel, ours, base, theirs)
        if merged is not None:
            return merged
    merged = _merge_with_blocks(ours, base, theirs, label)
    if merged is not None:
        return merged
    data, conflicts = merge_text(ours, base, theirs, label)
    return Merge(data=data, conflicts=conflicts)


def merge_text(ours: bytes, base: bytes, theirs: bytes, label: str) -> tuple[bytes, int]:
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            (Path(tmp) / name).write_bytes(data)
            paths.append(str(Path(tmp) / name))
        process = subprocess.run(["git", "merge-file", "-p", "-L", label, "-L", "starter (installed)", "-L", "starter (current)", *paths],
                                 cwd=tmp, capture_output=True)
    # merge-file exits with the number of conflicts, capped at 127; anything above is an error.
    if process.returncode > 127:
        raise StarterError(f"git merge-file failed: {process.stderr.decode(errors='replace').strip()}")
    return process.stdout, process.returncode


def pattern_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def with_lines(existing: str, missing: list[str]) -> str:
    separator = "" if existing.endswith("\n") or not existing else "\n"
    return existing + separator + "\n# ai-starter harness\n" + "\n".join(missing) + "\n"


def _append_lines(ours: bytes, base: bytes, theirs: bytes) -> Merge:
    present = {line.strip() for line in ours.decode().splitlines()}
    installed = {line.strip() for line in base.decode().splitlines()}
    missing = [line for line in pattern_lines(theirs.decode()) if line.strip() not in installed | present]
    return Merge(data=with_lines(ours.decode(), missing).encode() if missing else None)


def _split_blocks(text: str) -> tuple[str, dict[str, str]] | None:
    """The text with every marked block emptied, and the block bodies by name. None when the markers do not pair up."""
    skeleton: list[str] = []
    blocks: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines(keepends=True):
        match = _BLOCK_MARKER.match(line.rstrip("\r\n"))
        if match is None:
            (blocks[current] if current else skeleton).append(line)
            continue
        name, edge = match.groups()
        if edge == "start":
            if current is not None or name in blocks:
                return None
            current, blocks[name] = name, []
        elif name != current:
            return None
        else:
            current = None
        skeleton.append(line)
    if current is not None:
        return None
    return "".join(skeleton), {name: "".join(body) for name, body in blocks.items()}


def _fill_blocks(skeleton: str, bodies: dict[str, str]) -> str:
    lines = []
    for line in skeleton.splitlines(keepends=True):
        lines.append(line)
        match = _BLOCK_MARKER.match(line.rstrip("\r\n"))
        if match and match.group(2) == "start":
            lines.append(bodies.get(match.group(1), ""))
    return "".join(lines)


def _merge_with_blocks(ours: bytes, base: bytes, theirs: bytes, label: str) -> Merge | None:
    """Merges the text outside marked blocks; a block keeps the target's body unless the target never changed it.

    None when no version has blocks or a version's markers do not pair up, so the caller merges plain text.
    A block that only the target has is its own and stays where it is.
    """
    try:
        parts = [_split_blocks(content.decode("utf-8")) for content in (ours, base, theirs)]
    except UnicodeDecodeError:
        return None
    if any(part is None for part in parts) or not any(blocks for _, blocks in parts):
        return None
    (ours_text, ours_blocks), (base_text, base_blocks), (theirs_text, theirs_blocks) = parts
    changed = {name: body for name, body in ours_blocks.items() if body != base_blocks.get(name)}
    dropped = sorted(name for name in changed if name in base_blocks and name not in theirs_blocks)
    if dropped:
        return Merge(skip=f"the starter no longer has the block {', '.join(dropped)}, which holds this target's content; move it by hand")
    merged, conflicts = merge_text(ours_text.encode(), base_text.encode(), theirs_text.encode(), label)
    return Merge(data=_fill_blocks(merged.decode("utf-8"), {**theirs_blocks, **changed}).encode(), conflicts=conflicts)


_MISSING = object()


def _merge_value(base, ours, theirs, key: str, kept: list[str]):
    """Three-way merge of parsed JSON. Objects merge per key and lists of scalars per item; any other clash keeps `ours`."""
    if ours == theirs or base == theirs:
        return ours
    if base == ours:
        return theirs
    if isinstance(ours, dict) and isinstance(theirs, dict) and (base is _MISSING or isinstance(base, dict)):
        base = {} if base is _MISSING else base
        merged = {}
        for name in [*ours, *(name for name in theirs if name not in ours)]:
            value = _merge_value(base.get(name, _MISSING), ours.get(name, _MISSING), theirs.get(name, _MISSING),
                                 f"{key}.{name}" if key else name, kept)
            if value is not _MISSING:
                merged[name] = value
        return merged
    if _scalar_list(ours) and _scalar_list(theirs) and (base is _MISSING or isinstance(base, list)):
        base = [] if base is _MISSING else base
        return [item for item in ours if item in theirs or item not in base] + [item for item in theirs if item not in base and item not in ours]
    kept.append(key or "(whole file)")
    return ours


def _scalar_list(value) -> bool:
    return isinstance(value, list) and not any(isinstance(item, (dict, list)) for item in value)


def _migrate(rel: str, value, target: int):
    """`value` raised to schemaVersion `target` through MIGRATIONS, or None when a step is missing."""
    version = value.get("schemaVersion") if isinstance(value, dict) else None
    if not isinstance(version, int):
        return value
    for step_from in range(version, target):
        step = MIGRATIONS.get((rel, step_from))
        if step is None:
            return None
        value = step(value)
    return value


def _merge_json(rel: str, ours: bytes, base: bytes, theirs: bytes) -> Merge | None:
    """Merges JSON by key instead of by line. None when a version does not parse, so the caller merges plain text."""
    try:
        original, base_value, theirs_value = (json.loads(content) for content in (ours, base, theirs))
    except ValueError:
        return None
    ours_value = original
    target = theirs_value.get("schemaVersion") if isinstance(theirs_value, dict) else None
    if isinstance(target, int):
        ours_value, base_value = _migrate(rel, ours_value, target), _migrate(rel, base_value, target)
        if ours_value is None or base_value is None:
            return Merge(skip=f"the starter raised schemaVersion to {target} without a migration in MIGRATIONS "
                              "(tool/ai_starter/merge.py); merge by hand")
    kept: list[str] = []
    merged = _merge_value(base_value, ours_value, theirs_value, "", kept)
    data = (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode() if merged != original else None
    return Merge(data=data, kept=kept)
