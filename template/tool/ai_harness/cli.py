from __future__ import annotations

import argparse
import json
import sys

from . import doctor, guard, wiki
from .checks import wiki_root
from .paths import HarnessError, ToolMissing, locate_root

USAGE = """\
python3 tool/ai.py <command>

  doctor                          Check toolchain, harness files, skills, and adapters
  verify [--all] [--id ID]        Run checks selected from the changed files; write a receipt to .ai/runs/ID/
         [--check CHECK_ID ...]   Also run these checks from .ai/config.json even if no changed file selects them
         [--dry-run]              Show the selection without running it
  wiki lint                       Lint wiki frontmatter, slugs, links, index, and log
  adapters sync                   Create missing .claude/skills links (never deletes)
  hook pre-tool-use               Claude Code PreToolUse guard (reads the hook JSON on stdin)

Output is JSON. Exit codes: 0 ok, 1 validation or check failure, 2 guard block, 3 missing tool or doctor failure.
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool/ai.py", add_help=False)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor")
    verify = sub.add_parser("verify")
    verify.add_argument("--all", action="store_true")
    verify.add_argument("--id", default="adhoc")
    verify.add_argument("--check", action="append", default=[])
    verify.add_argument("--dry-run", action="store_true")
    sub.add_parser("wiki").add_subparsers(dest="action").add_parser("lint")
    sub.add_parser("adapters").add_subparsers(dest="action").add_parser("sync")
    return parser


def _print(value: dict) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def dispatch(args: argparse.Namespace) -> tuple[dict, int]:
    root = locate_root()
    if args.command == "doctor":
        return doctor.doctor(root)
    if args.command == "verify":
        from .verify import verify

        return verify(root, "all" if args.all else "changed", args.id, args.check, args.dry_run)
    if args.command == "wiki" and args.action == "lint":
        errors, warnings = wiki.lint(root, wiki_root(root))
        return {"ok": not errors, "errors": errors, "warnings": warnings}, 0 if not errors else 1
    if args.command == "adapters" and args.action == "sync":
        report = doctor.sync_adapters(root)
        return report, 0 if report["ok"] else 1
    raise HarnessError("Incomplete command. Run `python3 tool/ai.py help`.")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("help", "--help", "-h"):
        print(USAGE)
        return 0
    if argv[:2] == ["hook", "pre-tool-use"]:
        return guard.main(sys.stdin.read())
    try:
        args = _parser().parse_args(argv)
    except SystemExit:
        _print({"ok": False, "error": f"Invalid arguments: {' '.join(argv)}", "kind": "usage", "usage": USAGE})
        return 1
    try:
        report, code = dispatch(args)
    except HarnessError as error:
        _print({"ok": False, "error": str(error), "kind": "validation"})
        return 1
    except ToolMissing as error:
        _print({"ok": False, "error": str(error), "kind": "process"})
        return 3
    _print(report)
    return code
