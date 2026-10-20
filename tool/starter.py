#!/usr/bin/env python3
"""ai-starter generator. Writes only into the workspace it is given and the saved workspace list; never into this starter.

The code lives in tool/ai_starter/; run `python3 tool/starter.py help` for the commands.
"""

import sys

from ai_starter.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
