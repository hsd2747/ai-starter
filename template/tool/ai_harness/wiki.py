"""Structural lint for the project wiki. The format contract lives in wiki/README.md."""

from __future__ import annotations

import re
from pathlib import Path

from .docs import strip_code
from .schema import FORMATS

FACT_KINDS = {"current", "rule", "hub"}
ADOPTIONS = {"enforced", "on-touch", "target"}
LOG_OPS = {"setup", "add", "update", "learn", "correct", "lint", "refresh", "migrate"}
SPECIAL_FILES = {"README.md", "index.md", "log.md"}
LEAF_LINE_LIMIT = 80

FACT_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
NOTE_SLUG = re.compile(r"[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)*\Z")
WIKILINK = re.compile(r"\[\[([^\]|#\n]+)(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]")
LOG_HEADING = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] ([a-z-]+) \| \S.*$")
_KEY = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")
_INLINE_COMMENT = re.compile(r"\s+#.*$")


def _scalar(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] not in ("'", '"'):
        raw = _INLINE_COMMENT.sub("", raw)
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    return raw


def parse_frontmatter(text: str) -> tuple[dict | None, str]:
    """(fields, error). Supports scalars, inline [a, b] lists, and block `- item` lists."""
    if not text.startswith("---\n"):
        return None, "missing frontmatter"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "unterminated frontmatter"
    fields: dict = {}
    current: str | None = None
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current is not None and line[0] in " -":
            if not isinstance(fields[current], list):
                return None, f"mixed scalar and list for {current!r}"
            fields[current].append(_scalar(stripped[2:]))
            continue
        match = _KEY.match(line)
        if not match:
            return None, f"unparseable frontmatter line: {line!r}"
        key, raw = match.group(1), match.group(2).strip()
        if raw.startswith("#"):
            raw = ""
        elif raw.startswith("["):
            raw = _INLINE_COMMENT.sub("", raw).strip()
        current = key
        if raw == "":
            fields[key] = []
        elif raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            fields[key] = [_scalar(item) for item in inner.split(",")] if inner else []
        else:
            fields[key] = _scalar(raw)
            current = None
    return fields, ""


def lint(root: Path, wiki_root: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    base = root / wiki_root
    for name in sorted(SPECIAL_FILES):
        if not (base / name).is_file():
            errors.append(f"{wiki_root}/{name}: required file is missing")
    if errors:
        return errors, warnings

    pages: dict[str, str] = {}
    bodies: dict[str, str] = {}
    layers: dict[str, str] = {}
    for file in sorted(base.rglob("*.md")):
        relative = file.relative_to(base).as_posix()
        if relative in SPECIAL_FILES:
            continue
        shown = f"{wiki_root}/{relative}"
        parts = relative.split("/")
        layer = parts[0]
        slug = file.stem
        if layer not in ("facts", "notes"):
            errors.append(f"{shown}: pages live under facts/<category>/ or notes/")
            continue
        if layer == "facts" and len(parts) != 3:
            errors.append(f"{shown}: facts pages live exactly one category folder deep (facts/<category>/<slug>.md)")
        slug_rule = FACT_SLUG if layer == "facts" else NOTE_SLUG
        if not slug_rule.match(slug):
            errors.append(f"{shown}: slug {slug!r} is not a valid {layer} slug")
        if slug in pages:
            errors.append(f"{shown}: slug {slug!r} duplicates {pages[slug]}; slugs are unique across the wiki")
            continue
        pages[slug] = shown
        layers[slug] = layer
        text = file.read_text(encoding="utf-8")
        bodies[slug] = text
        errors += [f"{shown}: {message}" for message in _frontmatter_errors(text, layer)]
        meta, _ = parse_frontmatter(text)
        kind = (meta or {}).get("kind")
        if layer == "facts" and kind != "hub" and text.count("\n") > LEAF_LINE_LIMIT:
            warnings.append(f"{shown}: over {LEAF_LINE_LIMIT} lines; split it into separate leaves")

    index = (base / "index.md").read_text(encoding="utf-8")
    log = (base / "log.md").read_text(encoding="utf-8")
    linked_from_pages: set[str] = set()
    for source_name, text in [("index.md", index), ("log.md", log), *((pages[s], t) for s, t in bodies.items())]:
        shown = source_name if "/" in source_name else f"{wiki_root}/{source_name}"
        for target in WIKILINK.findall(strip_code(text)):
            target = target.strip()
            if target not in pages:
                errors.append(f"{shown}: dangling wikilink [[{target}]]")
            elif source_name not in ("index.md", "log.md") and pages.get(target) != source_name:
                linked_from_pages.add(target)

    in_index = set(WIKILINK.findall(strip_code(index)))
    for slug, shown in pages.items():
        if slug not in in_index:
            errors.append(f"{shown}: page is not listed in {wiki_root}/index.md")
        if layers[slug] == "facts" and slug not in linked_from_pages:
            warnings.append(f"{shown}: no other page links here; link it from its hub or a related leaf")

    log_errors, log_warnings = _log_problems(log, f"{wiki_root}/log.md")
    return errors + log_errors, warnings + log_warnings


def _frontmatter_errors(text: str, layer: str) -> list[str]:
    meta, problem = parse_frontmatter(text)
    if meta is None:
        return [problem]
    errors = []
    if meta.get("layer") != layer:
        errors.append(f"frontmatter layer must be {layer!r}")
    for key in ("tags", "sources"):
        if not isinstance(meta.get(key), list):
            errors.append(f"frontmatter {key!r} must be a list")
    if layer == "facts" and not meta.get("sources"):
        errors.append("facts pages need at least one source")
    for key in ("created", "updated"):
        if not FORMATS["date"](str(meta.get(key, ""))):
            errors.append(f"frontmatter {key!r} must be an absolute YYYY-MM-DD date")
    if layer == "facts":
        kind = meta.get("kind")
        if kind not in FACT_KINDS:
            errors.append(f"frontmatter kind must be one of {sorted(FACT_KINDS)}")
        if kind == "current" and not FORMATS["date"](str(meta.get("verified", ""))):
            errors.append("current pages need verified: YYYY-MM-DD")
        if kind == "rule" and meta.get("adoption") not in ADOPTIONS:
            errors.append(f"rule pages need adoption: one of {sorted(ADOPTIONS)}")
    return errors


def _log_problems(log: str, shown: str) -> tuple[list[str], list[str]]:
    """Heading errors, and order warnings: branches merged out of date order leave older entries below newer ones."""
    errors: list[str] = []
    warnings: list[str] = []
    previous = ""
    for line in strip_code(log).splitlines():
        if not line.startswith("## "):
            continue
        match = LOG_HEADING.match(line)
        if not match:
            errors.append(f"{shown}: entry heading must be '## [YYYY-MM-DD] <op> | <title>': {line!r}")
            continue
        day, op = match.groups()
        if op not in LOG_OPS:
            errors.append(f"{shown}: unknown operation {op!r}; use one of {sorted(LOG_OPS)}")
        if not FORMATS["date"](day):
            errors.append(f"{shown}: invalid date {day}")
        elif day < previous:
            warnings.append(f"{shown}: entry {day} is older than the one above it; expected after a merge, otherwise append new entries at the bottom")
        else:
            previous = day
    return errors, warnings
