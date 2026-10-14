#!/usr/bin/env python3
"""Guard hook for sessions opened in the starter itself.

The harness CLI lives in template/tool/ and runs inside generated repositories.
This root is not a harness repository, so this entry point only serves the
PreToolUse hook that .claude/settings.json registers. It keeps the same path as
in generated repositories because Claude Code snapshots hook commands per session.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "template" / "tool"))

from ai_harness import guard  # noqa: E402

if __name__ == "__main__":
    if sys.argv[1:] != ["hook", "pre-tool-use"]:
        print("The starter root is not a harness repository. Use `python3 tool/starter.py help`, "
              "or run tool/ai.py inside a generated repository.", file=sys.stderr)
        sys.exit(1)
    sys.exit(guard.main(sys.stdin.read()))
