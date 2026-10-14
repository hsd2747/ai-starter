"""Dependency-free validator for the JSON Schema subset used under .ai/schemas.

Supported keywords: type, const, enum, required, properties, additionalProperties,
items, minItems, maxItems, uniqueItems, minLength, maxLength, pattern, minimum,
format, $ref (local #/$defs only), and allOf with if/then/else. An unsupported
keyword is an error rather than a silent pass, so a schema edit cannot loosen
validation by accident.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .paths import SCHEMAS_DIR, HarnessError, is_relative_path, read_json

SCHEMA_FILES = {
    "config": "config.schema.json",
    "verification": "verification.schema.json",
}

_SUPPORTED = {
    "$schema", "$id", "$defs", "$ref", "title", "description", "type", "const", "enum",
    "required", "properties", "additionalProperties", "items", "minItems", "maxItems",
    "uniqueItems", "minLength", "maxLength", "pattern", "minimum", "format", "allOf",
    "if", "then", "else", "default",
}

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
CHECK_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def _is_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return "T" in value


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10


FORMATS = {
    "run-id": lambda v: bool(RUN_ID.match(v)),
    "check-id": lambda v: bool(CHECK_ID.match(v)),
    "skill-name": lambda v: bool(SKILL_NAME.match(v)) and len(v) <= 64,
    "relative-path": is_relative_path,
    "non-blank": lambda v: bool(v.strip()),
    "date-time": _is_datetime,
    "date": _is_date,
    "regex": lambda v: _compiles(v),
}


def _compiles(value: str) -> bool:
    try:
        re.compile(value)
    except re.error:
        return False
    return True


_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(schema: dict, value: Any, root_schema: dict | None = None, at: str = "$") -> list[str]:
    root_schema = root_schema if root_schema is not None else schema
    unknown = set(schema) - _SUPPORTED
    if unknown:
        return [f"{at}: schema uses unsupported keyword(s) {sorted(unknown)}"]
    errors: list[str] = []

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            return [f"{at}: unsupported $ref {ref}"]
        target = root_schema.get("$defs", {}).get(ref[len("#/$defs/") :])
        if target is None:
            return [f"{at}: unresolved $ref {ref}"]
        errors += validate(target, value, root_schema, at)

    for sub in schema.get("allOf", []):
        if "if" in sub:
            branch = sub.get("then") if not validate(sub["if"], value, root_schema, at) else sub.get("else")
            if branch:
                errors += validate(branch, value, root_schema, at)
        else:
            errors += validate(sub, value, root_schema, at)

    if "const" in schema and value != schema["const"]:
        errors.append(f"{at}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{at}: must be one of {schema['enum']}")

    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_TYPES[name](value) for name in types):
            return errors + [f"{at}: expected {expected}"]

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{at}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{at}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{at}: does not match {schema['pattern']}")
        fmt = schema.get("format")
        if fmt is not None:
            check = FORMATS.get(fmt)
            if check is None:
                errors.append(f"{at}: unknown format {fmt}")
            elif not check(value):
                errors.append(f"{at}: invalid {fmt}: {value!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{at}: below minimum {schema['minimum']}")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{at}: needs at least {schema['minItems']} item(s)")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{at}: allows at most {schema['maxItems']} item(s)")
        if schema.get("uniqueItems"):
            seen: list[Any] = []
            for item in value:
                if item in seen:
                    errors.append(f"{at}: duplicate item {item!r}")
                seen.append(item)
        if "items" in schema:
            for index, item in enumerate(value):
                errors += validate(schema["items"], item, root_schema, f"{at}[{index}]")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{at}: missing required property {key!r}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                errors += validate(properties[key], item, root_schema, f"{at}.{key}")
            elif extra is False:
                errors.append(f"{at}: unexpected property {key!r}")
            elif isinstance(extra, dict):
                errors += validate(extra, item, root_schema, f"{at}.{key}")

    return errors


def load_schema(root: Path, kind: str) -> dict:
    name = SCHEMA_FILES.get(kind)
    if name is None:
        raise HarnessError(f"Unknown artifact kind {kind!r}; expected one of {sorted(SCHEMA_FILES)}")
    return read_json(root / SCHEMAS_DIR / name)


def validate_artifact(root: Path, kind: str, value: Any) -> list[str]:
    return validate(load_schema(root, kind), value)
