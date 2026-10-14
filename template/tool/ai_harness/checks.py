"""Selection of project checks declared in .ai/config.json.

Onboarding writes every language-specific command into that one file. Nothing
else in the harness names a formatter, linter, test runner, or generator, and
`verify --check` only accepts ids declared there, so no caller can inject an
arbitrary command as verification evidence.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .globs import matches
from .paths import CONFIG_FILE, HarnessError, read_json, read_text_or_none
from .schema import validate_artifact

STAGES = ("early", "generate", "late")

# Package-manager install trees: nobody in this repository can fix their contents.
DEPENDENCY_SEGMENTS = {"node_modules", "vendor", "Pods", ".symlinks", ".venv", "venv", "__pycache__", ".git"}

# Editor and tool configs that are JSON with comments by convention.
DEFAULT_JSONC = ["**/.vscode/**", "**/.obsidian/**", "**/tsconfig*.json", "**/jsconfig*.json", "**/.devcontainer/**"]

HARNESS_TEST_TRIGGERS = ["tool/**", ".ai/schemas/**"]

# The self-test runs verify inside throwaway repositories whose files are all new,
# so without this marker every nested verify would start the self-test again.
SELF_TEST_ENV = "AI_HARNESS_SELF_TEST"

BUILTIN_IDS = {"git-diff-check", "secret-scan", "harness-config", "json-syntax", "doc-links", "wiki-lint",
               "harness-test", "verification-subject-stable"}


@dataclass
class Check:
    id: str
    command: list[str]
    cwd: str = "."
    stage: str = "late"
    required: bool = True
    mutates: bool = False
    timeout: int | None = None
    env: dict[str, str] = field(default_factory=dict)
    spec_id: str = ""
    files: list[str] = field(default_factory=list)


def load_config(root: Path) -> dict:
    config = read_json(root / CONFIG_FILE)
    errors = validate_artifact(root, "config", config) + config_rule_errors(config)
    if errors:
        raise HarnessError(f"{CONFIG_FILE} is invalid: " + "; ".join(errors))
    return config


def wiki_root(root: Path) -> str:
    try:
        return load_config(root)["wiki"]["root"]
    except HarnessError:
        return "wiki"


def config_rule_errors(config: dict) -> list[str]:
    errors = []
    ids = [spec.get("id") for spec in config.get("checks", [])]
    for check_id in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate check id {check_id!r}")
    for spec in config.get("checks", []):
        if spec.get("id") in BUILTIN_IDS:
            errors.append(f"check id {spec['id']!r} is reserved for a built-in check")
        if spec.get("per") == "member" and not config.get("members"):
            errors.append(f"check {spec.get('id')!r} runs per member but no 'members' are declared")
    return errors


def is_ignored(path: str, config: dict) -> bool:
    return any(segment in DEPENDENCY_SEGMENTS for segment in path.split("/")) or matches(path, config.get("ignore", []))


def is_strict_json(path: str, config: dict) -> bool:
    return path.endswith(".json") and not is_ignored(path, config) and not matches(path, DEFAULT_JSONC + config.get("jsonc", []))


def discover_members(all_files: list[str], config: dict) -> list[str]:
    members = config.get("members")
    if not members:
        return []
    found = set()
    for path in all_files:
        directory, _, name = path.rpartition("/")
        if name != members["marker"] or is_ignored(path, config):
            continue
        directory = directory or "."
        if matches(directory, members["globs"]):
            found.add(directory)
    return sorted(found)


def _member_slug(member: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", member.lower()).strip("-") or "root"


def _in(member: str, path: str) -> bool:
    return member == "." or path == member or path.startswith(member + "/")


def _relative(member: str, path: str) -> str:
    return path if member == "." else path[len(member) + 1 :]


def _content_hit(root: Path, path: str, pattern: re.Pattern[str]) -> bool:
    # A deleted source cannot be inspected; treat it as a hit so its outputs regenerate.
    if not os.path.lexists(root / path):
        return True
    text = read_text_or_none(root / path)
    return bool(text and pattern.search(text))


def _expand(command: list[str], files: list[str]) -> list[str]:
    expanded = []
    for token in command:
        if token == "{files}":
            expanded.extend(files)
        else:
            expanded.append(token)
    return expanded


def _build(root: Path, spec: dict, files: list[str], scope: str, cwd: str, check_id: str) -> Check | None:
    command = spec["command"]
    if scope == "all" and spec.get("allCommand"):
        command = spec["allCommand"]
        existing: list[str] = []
    else:
        existing = [f for f in files if os.path.lexists(root / (f if cwd == "." else f"{cwd}/{f}"))]
        if "{files}" in command and not existing:
            return None
    return Check(
        id=check_id,
        command=_expand(command, existing),
        cwd=cwd,
        stage=spec.get("stage", "late"),
        required=spec.get("required", True),
        mutates=spec.get("mutates", False),
        timeout=spec.get("timeoutSec"),
        spec_id=spec["id"],
        files=existing,
    )


def select(root: Path, config: dict, subject_files: list[str], all_files: list[str], scope: str,
           forced: frozenset[str] = frozenset()) -> list[Check]:
    """Checks the subject needs, ordered by stage. Ids in `forced` run even when no changed file matches them."""
    members = discover_members(all_files, config)
    selected: list[Check] = []
    for spec in config.get("checks", []):
        when = spec.get("when", {})
        candidates = [f for f in subject_files if not is_ignored(f, config) and matches(f, when.get("paths", ["**"]))]
        if when.get("contentPattern"):
            pattern = re.compile(when["contentPattern"], re.M)
            candidates = [f for f in candidates if _content_hit(root, f, pattern)]
        is_forced = spec["id"] in forced
        if not candidates and not is_forced:
            continue
        if spec.get("per") != "member":
            built = _build(root, spec, [_relative(spec.get("cwd", "."), f) for f in candidates if _in(spec.get("cwd", "."), f)],
                           scope, spec.get("cwd", "."), spec["id"])
            if built:
                selected.append(built)
            continue

        every_member = spec.get("memberSelect") == "all" or scope == "all" or (is_forced and not candidates)
        chosen = members if every_member else [m for m in members if any(_in(m, f) for f in candidates)]
        for member in chosen:
            if spec.get("memberHas") and not any(_in(member, f) and matches(_relative(member, f), [spec["memberHas"]]) for f in all_files):
                continue
            member_files = [_relative(member, f) for f in candidates if _in(member, f)]
            built = _build(root, spec, member_files, scope, member, f"{spec['id']}-{_member_slug(member)}")
            if built:
                selected.append(built)

    unknown = sorted(set(forced) - {spec["id"] for spec in config.get("checks", [])})
    if unknown:
        raise HarnessError(f"--check names id(s) not declared in {CONFIG_FILE}: {unknown}")
    return sorted(selected, key=lambda check: STAGES.index(check.stage))


def harness_test_check(subject_files: list[str]) -> Check | None:
    if os.environ.get(SELF_TEST_ENV) or not any(matches(f, HARNESS_TEST_TRIGGERS) for f in subject_files):
        return None
    return Check(
        id="harness-test",
        command=[sys.executable, "-m", "unittest", "discover", "-s", "tool/tests", "-t", "tool", "-q"],
        stage="early",
        env={SELF_TEST_ENV: "1"},
    )
