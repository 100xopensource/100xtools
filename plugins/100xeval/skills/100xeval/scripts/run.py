#!/usr/bin/env python3
"""100xeval entrypoint. Usage: python3 evals/100xeval/run.py <init|eval> [...]."""

import os
import sys

# Before the engine import, not after: engine.models uses `str | None` annotations, which
# are evaluated at import time, so an old interpreter dies with `TypeError: unsupported
# operand type(s) for |` and no hint about what to do. 3.11 is the floor CI tests.
if sys.version_info < (3, 11):
    v = ".".join(str(n) for n in sys.version_info[:3])
    sys.exit(
        f"100xeval needs Python 3.11 or newer. This is Python {v} ({sys.executable}).\n"
        "\n"
        "  macOS:   brew install python@3.12\n"
        "  Ubuntu:  sudo apt install python3.12\n"
        "  Windows: https://www.python.org/downloads/\n"
        "\n"
        "Then run it with the newer one, e.g. `python3.12` instead of `python3`.\n"
        "Nothing else needs installing — 100xeval uses only the standard library."
    )

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
