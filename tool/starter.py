#!/usr/bin/env python3
"""ai-starter generator. Writes only into the workspace it is given and the saved workspace list; never into this starter.

The code lives in tool/ai_starter/; run `python3 tool/starter.py help` for the commands.
"""

import json
import sys

REQUIRED_PYTHON = (3, 10)

if __name__ == "__main__":
    # Checked before importing the generator, so that an older Python gets this report instead of a traceback or a half-run command.
    if sys.version_info[:2] < REQUIRED_PYTHON:
        print(json.dumps({"ok": False, "error": f"Python {sys.version.split()[0]} found; ai-starter needs Python 3.10 or later. Install it "
                          "(on macOS `brew install python`, or the installer from python.org), open a new terminal, check `python3 --version`, "
                          "and run the command again."}, indent=2))
        sys.exit(1)
    from ai_starter.cli import main

    sys.exit(main(sys.argv[1:]))
