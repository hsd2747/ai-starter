from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import checks as checks_module
from . import docs, gitutil, secrets, wiki
from .checks import Check
from .paths import RUNS_DIR, HarnessError, read_text_or_none, relative_to_root
from .schema import RUN_ID
from .schema import validate_artifact

SUMMARY_LIMIT = 1200
_CONFLICT = re.compile(r"^(<{7}|>{7}) ")


def timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")


def summarize(output: str, exit_code: int) -> str:
    """Keeps both ends of long output: the first failures and the trailing summary are what a reviewer needs."""
    if not output:
        return "Completed without output." if exit_code == 0 else "Failed without output."
    if len(output) <= SUMMARY_LIMIT:
        return output
    half = SUMMARY_LIMIT // 2
    omitted = len(output) - SUMMARY_LIMIT
    return f"{output[:half]}\n... ({omitted} chars omitted, see logPath) ...\n{output[-half:]}"


def _internal(check_id: str, failures: list[str], passed: str, started: float, warnings: list[str] | None = None) -> dict:
    lines = failures or [passed]
    if warnings:
        lines = lines + [f"warning: {w}" for w in warnings]
    return {
        "id": check_id,
        "command": ["internal", check_id],
        "cwd": ".",
        "status": "fail" if failures else "pass",
        "exitCode": 1 if failures else 0,
        "durationMs": int((time.monotonic() - started) * 1000),
        "summary": summarize("\n".join(lines), 1 if failures else 0),
    }


def whitespace_failures(root: Path, base: str, untracked: list[str], staged: list[str]) -> list[str]:
    output = gitutil.git(root, "diff", "--check", base, "--", check=False)
    failures = [line for line in output.decode("utf-8", errors="replace").splitlines() if line.strip()]
    if staged:
        output = gitutil.git(root, "--literal-pathspecs", "diff", "--cached", "--check", base, "--", *staged, check=False)
        failures += [f"staged: {line}" for line in output.decode("utf-8", errors="replace").splitlines() if line.strip()]
    # git diff --check never sees untracked files, which are most of a new feature.
    for path in untracked:
        text = read_text_or_none(root / path)
        if text is None:
            continue
        lines = text.split("\n")
        for number, line in enumerate(lines, start=1):
            if line.rstrip("\r") != line.rstrip("\r").rstrip(" \t"):
                failures.append(f"{path}:{number}: trailing whitespace.")
            if _CONFLICT.match(line):
                failures.append(f"{path}:{number}: leftover conflict marker.")
        if len(lines) > 2 and lines[-1] == "" and lines[-2].strip() == "":
            failures.append(f"{path}: new blank line at EOF.")
    return failures


def harness_config_failures(root: Path) -> list[str]:
    from .doctor import static_errors

    return static_errors(root)


def run_internal(root: Path, config: dict, subject: dict, scope: str) -> tuple[list[dict], list[str]]:
    files = subject["files"]
    existing = [f for f in files if (root / f).is_file()]
    untracked = set(gitutil.untracked_files(root))
    staged = [f for f in gitutil.staged_differences(root) if not checks_module.is_ignored(f, config)]
    results = []
    warnings: list[str] = []

    started = time.monotonic()
    results.append(_internal("git-diff-check",
                             whitespace_failures(root, subject["base"], [f for f in existing if f in untracked and not checks_module.is_ignored(f, config)],
                                                 staged),
                             "No whitespace errors or conflict markers.", started))

    started = time.monotonic()
    candidates = sorted(set(gitutil.tracked_files(root)) | untracked)
    secret_failures = secrets.secret_file_failures([f for f in candidates if not checks_module.is_ignored(f, config)])
    suppressed: list[str] = []
    secret_failures += secrets.content_failures(root, [f for f in existing if not checks_module.is_ignored(f, config)], suppressed)
    for path in staged:
        text = gitutil.staged_text(root, path)
        if text is not None:
            secret_failures += secrets.text_failures(f"{path} (staged)", text, suppressed)
    if suppressed:
        warnings.append(f"{len(suppressed)} secret-scan hit(s) suppressed by '{secrets.ALLOW_MARKER}'; a reviewer must confirm each: "
                        + "; ".join(suppressed))
    scanned = f"{len(existing)} file(s)" + (f" and the staged copies of {len(staged)}" if staged else "")
    results.append(_internal("secret-scan", secret_failures, f"{scanned} scanned; no secrets found.", started, warnings))

    started = time.monotonic()
    results.append(_internal("harness-config", harness_config_failures(root), "Harness configuration is valid.", started))

    json_files = [f for f in existing if checks_module.is_strict_json(f, config)]
    if json_files:
        started = time.monotonic()
        failures = []
        for path in json_files:
            try:
                json.loads((root / path).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                failures.append(f"{path}: {error}")
        results.append(_internal("json-syntax", failures, f"{len(json_files)} JSON file(s) parsed.", started))

    markdown = [f for f in existing if f.endswith(".md") and not checks_module.is_ignored(f, config)]
    if markdown:
        started = time.monotonic()
        results.append(_internal("doc-links", docs.link_failures(root, markdown), f"{len(markdown)} Markdown file(s) linked.", started))

    wiki_dir = checks_module.wiki_root(root)
    if scope == "all" or any(f == wiki_dir or f.startswith(wiki_dir + "/") for f in files):
        started = time.monotonic()
        errors, wiki_warnings = wiki.lint(root, wiki_dir)
        results.append(_internal("wiki-lint", errors, "Wiki structure is valid.", started, wiki_warnings))
    return results, warnings


def _executable(root: Path, check: Check) -> str | None:
    program = check.command[0]
    if "/" in program:
        candidate = (root / check.cwd / program) if not os.path.isabs(program) else Path(program)
        return str(candidate) if candidate.exists() else None
    return shutil.which(program)


def run_external(root: Path, check: Check, log_dir: Path) -> dict:
    started = time.monotonic()
    base = {"id": check.id, "command": check.command, "cwd": check.cwd}
    executable = _executable(root, check)
    if executable is None:
        return {**base, "status": "fail" if check.required else "skipped", "durationMs": 0,
                "summary": f"Executable not found: {check.command[0]}", "_required": check.required}
    try:
        process = subprocess.run([executable, *check.command[1:]], cwd=root / check.cwd, capture_output=True,
                                 text=True, errors="replace", timeout=check.timeout, env={**os.environ, **check.env})
        output = (process.stdout + process.stderr).strip()
        exit_code = process.returncode
    except subprocess.TimeoutExpired as error:
        output = f"Timed out after {check.timeout}s.\n{error.stdout or ''}{error.stderr or ''}".strip()
        exit_code = 124
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{check.id}.log"
    log.write_text(output + "\n", encoding="utf-8")
    return {**base, "status": "pass" if exit_code == 0 else "fail", "exitCode": exit_code,
            "durationMs": int((time.monotonic() - started) * 1000), "summary": summarize(output, exit_code),
            "logPath": relative_to_root(root, log), "_required": check.required}


def toolchain(root: Path, config: dict) -> dict:
    versions = {"python": platform.python_version()}
    entries = [{"name": "git", "command": ["git", "--version"]}, *config.get("toolchain", [])]
    for entry in entries:
        executable = shutil.which(entry["command"][0])
        if executable is None:
            versions[entry["name"]] = "unavailable"
            continue
        process = subprocess.run([executable, *entry["command"][1:]], cwd=root, capture_output=True, text=True, errors="replace")
        lines = (process.stdout or process.stderr).strip().splitlines()
        versions[entry["name"]] = lines[0] if process.returncode == 0 and lines else "unavailable"
    return versions


def run_dir(root: Path, run_id: str) -> Path:
    if not RUN_ID.match(run_id):
        raise HarnessError(f"Invalid run id {run_id!r}: up to 80 chars, start alphanumeric, then [A-Za-z0-9._-].")
    return root / RUNS_DIR / run_id


def verify(root: Path, scope: str, run_id: str, forced_ids: list[str], dry_run: bool) -> tuple[dict, int]:
    config = checks_module.load_config(root)
    base_branch = config["git"]["baseBranch"]
    subject = gitutil.subject(root, scope, base_branch)
    all_files = gitutil.all_files(root)
    forced = frozenset(forced_ids)
    planned = checks_module.select(root, config, subject["files"], all_files, scope, forced)
    harness = checks_module.harness_test_check(subject["files"])
    if harness:
        planned.insert(0, harness)
    dropped = sorted(set(forced) - {check.spec_id for check in planned})

    if dry_run:
        return {"ok": True, "dryRun": True, "runId": run_id, "subject": subject,
                "checks": [{"id": c.id, "command": c.command, "cwd": c.cwd, "stage": c.stage, "required": c.required}
                           for c in planned], "forcedWithoutFiles": dropped}, 0

    now = datetime.now(timezone.utc)
    stamp = timestamp(now)
    directory = run_dir(root, run_id)
    log_dir = directory / "logs" / stamp
    results, warnings = run_internal(root, config, subject, scope)
    for check_id in dropped:
        results.append({"id": check_id, "command": ["forced", check_id], "cwd": ".", "status": "skipped",
                        "durationMs": 0, "summary": "--check requested this check but no existing file matched it."})
    mutated = False
    for check in planned:
        results.append(run_external(root, check, log_dir))
        mutated = mutated or check.mutates

    after = gitutil.subject(root, scope, base_branch)
    if after["worktreeDigest"] != subject["worktreeDigest"]:
        reason = ("A generator rewrote tracked files: the committed generated code was stale. Keep the output and run verify again."
                  if mutated else "Files changed while verification ran. Run verify again on a quiet worktree.")
        results.append({"id": "verification-subject-stable", "command": ["internal", "subject-stable"], "cwd": ".",
                        "status": "fail", "exitCode": 1, "durationMs": 0, "summary": reason})

    failed = any(r["status"] == "fail" and r.get("_required", True) for r in results)
    for result in results:
        result.pop("_required", None)
    receipt = {
        "schemaVersion": 1,
        "runId": run_id,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "subject": subject,
        "toolchain": toolchain(root, config),
        "overall": "fail" if failed else ("pass" if results else "skipped"),
        "checks": results,
    }
    errors = validate_artifact(root, "verification", receipt)
    if errors:
        raise HarnessError("Refusing to write an invalid receipt: " + "; ".join(errors))
    path = directory / f"verification-{stamp}.json"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = {
        "ok": not failed,
        "overall": receipt["overall"],
        "receipt": relative_to_root(root, path),
        "checks": [{"id": r["id"], "status": r["status"], **({"summary": r["summary"]} if r["status"] != "pass" else {})}
                   for r in results],
    }
    if warnings:
        report["warnings"] = warnings
    return report, 1 if failed else 0
