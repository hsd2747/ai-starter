"""The files the starter keeps state in, checked against tool/schemas/ on every read and write."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import paths
from .files import json_bytes, read_json, write_atomic
from .paths import StarterError, clean_relative

# Manifests are checked with the harness's own dependency-free validator, so both read the same JSON Schema subset.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "template" / "tool"))
from ai_harness.schema import validate  # noqa: E402


def manifest_errors(kind: str, value) -> list[str]:
    """Problems in a file the starter keeps state in: its schema in tool/schemas/, then the rules a schema cannot state."""
    errors = validate(json.loads((paths.SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8")), value)
    if errors:
        return errors
    if kind == "workspace":
        for field in ("name", "path"):
            values = [repo[field] for repo in value["repos"]]
            errors += [f"$.repos: {field} {v!r} appears more than once" for v in sorted(set(values)) if values.count(v) > 1]
        errors += [f"$.repos: {repo['path']!r} is not a clean folder path inside the workspace"
                   for repo in value["repos"] if clean_relative(repo["path"]) != repo["path"]]
    elif kind == "harness":
        errors += [f"$.files: {rel!r} is not a clean path inside the repository" for rel in value["files"] if clean_relative(rel) != rel]
    return errors


def load_manifest(path: Path, kind: str) -> dict:
    value = read_json(path)
    errors = manifest_errors(kind, value)
    if errors:
        raise StarterError(f"{path} does not match tool/schemas/{kind}.schema.json; fix it by hand: " + "; ".join(errors))
    return value


def manifest_bytes(path: Path, kind: str, value: dict) -> bytes:
    errors = manifest_errors(kind, value)
    if errors:
        raise StarterError(f"Refusing to write an invalid {path}: " + "; ".join(errors))
    return json_bytes(value)


def write_manifest(path: Path, kind: str, value: dict) -> None:
    write_atomic(path, manifest_bytes(path, kind, value))
