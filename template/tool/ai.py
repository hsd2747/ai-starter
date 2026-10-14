#!/usr/bin/env python3
"""Entry point for the repository harness CLI. Run `python3 tool/ai.py help`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_harness.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
