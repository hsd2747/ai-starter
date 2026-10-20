"""High-confidence secret detection. Findings name the file, line, and rule, never the value."""

from __future__ import annotations

import re
from pathlib import Path

from .paths import read_text_or_none

ALLOW_MARKER = "secret-scan: allow"

PATTERNS = {
    "aws-access-key-id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "aws-secret-access-key": re.compile(r"(?i)aws_?secret_?access_?key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "github-token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}"),
    "slack-token": re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    "slack-webhook": re.compile(r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]{20,}"),
    "anthropic-api-key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "openai-api-key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}"),
    "google-api-key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "stripe-live-key": re.compile(r"\b[rs]k_live_[0-9A-Za-z]{24,}"),
    "toss-payments-secret-key": re.compile(r"\b(?:live|test)_g?sk_[0-9A-Za-z]{16,}"),
    "npm-token": re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    "connection-string-password": re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|rediss?|amqps?|mssql|sqlserver)://[^\s:/@'\"]*:(?P<password>[^\s@'\"/]+)@"),
}

# Local-only and documentation credentials that are not secrets: variables, templates, and well-known defaults.
_PLACEHOLDER = re.compile(r"(?i)(?:\$\{?\w+\}?|<[^>]*>|\{\{[^}]*\}\}|%\(\w+\)s|\*+|x+|\.{3}|"
                          r"password|passwd|pass|pw|secret|changeme|example|test|postgres|root|admin|user|guest)\Z")

_ENV_FILE = re.compile(r"(?:^|/)\.env(?:\.[^/]+)?\Z")
SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".dist")
SECRET_FILE_SUFFIXES = (".jks", ".keystore", ".p8", ".p12", ".pfx")
SECRET_FILE_NAMES = {"key.properties", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}


def is_env_file(path: str) -> bool:
    """True for files that conventionally hold real secrets (.env, .env.local, ...), false for templates."""
    clean = path.strip().strip("'\"")
    return bool(_ENV_FILE.search(clean)) and not clean.endswith(SAFE_ENV_SUFFIXES)


def secret_file_kind(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if is_env_file(path):
        return "env file"
    if name.endswith(SECRET_FILE_SUFFIXES) or name in SECRET_FILE_NAMES:
        return "signing key or credential"
    if name.startswith("client_secret") and name.endswith(".json"):
        return "OAuth client secret"
    return None


def secret_file_failures(paths: list[str]) -> list[str]:
    """Secret files that git tracks or would add: tracked paths plus untracked paths that .gitignore does not cover."""
    failures = []
    for path in paths:
        kind = secret_file_kind(path)
        if kind:
            failures.append(f"{path}: {kind} is tracked or not ignored; add it to .gitignore, remove it from the index "
                            "(git rm --cached) if tracked, and rotate every value it ever held if it was pushed")
    return failures


def _finding(name: str, match: re.Match[str]) -> bool:
    return name != "connection-string-password" or not _PLACEHOLDER.match(match.group("password"))


def content_failures(root: Path, files: list[str], suppressed: list[str] | None = None) -> list[str]:
    failures = []
    for path in files:
        text = read_text_or_none(root / path)
        if text is not None:
            failures += text_failures(path, text, suppressed)
    return failures


def text_failures(label: str, text: str, suppressed: list[str] | None = None) -> list[str]:
    """Pattern hits per line, named `label:line`. Hits on lines carrying ALLOW_MARKER go to `suppressed` so a report can still show them."""
    failures = []
    for number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS.items():
            if any(_finding(name, match) for match in pattern.finditer(line)):
                entry = f"{label}:{number}: looks like {name}"
                if ALLOW_MARKER in line:
                    if suppressed is not None:
                        suppressed.append(entry)
                else:
                    failures.append(entry)
    return failures
