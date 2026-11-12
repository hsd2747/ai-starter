#!/usr/bin/env python3
"""Entry point for the repository harness CLI. Run `python3 tool/ai.py help`."""

import json
import sys
from pathlib import Path

REQUIRED_PYTHON = (3, 10)


def python_problem():
    """Why this Python cannot run the CLI, with how to install a newer one, or None. Checked before any import that may not parse."""
    if sys.version_info[:2] >= REQUIRED_PYTHON:
        return None
    found = sys.version.split()[0]
    return (f"Python {found} found; this repository's harness needs Python 3.10 or later. Install it (on macOS `brew install python`, "
            "or the installer from python.org), open a new terminal, check `python3 --version`, and run the command again. "
            "Until then commits stop at the pre-commit hook.")


if __name__ == "__main__":
    # The guard hook still runs: a hook that exits with an error lets every tool call through unchecked.
    if python_problem() and sys.argv[1:] != ["hook", "pre-tool-use"]:
        print(json.dumps({"ok": False, "error": python_problem()}, indent=2))
        sys.exit(3)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ai_harness.cli import main

    sys.exit(main(sys.argv[1:]))
