#!/usr/bin/env python3
"""Entrypoint for the 100x-continuity engine.

Kept to a launcher so the engine stays importable as a package from the tests and
from any other tool that wants it. The engine's own directory goes on the path first,
so running this from a clone works with nothing installed.

    python3 run.py where
    python3 run.py publish --session "$SESSION" --artifact ./notes.md
    python3 run.py open --handle default/my-session-9f2c1ab4d0e5/20260820T140311Z-...
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from engine.cli import main  # noqa: E402 - the path insert above must run first


if __name__ == "__main__":
    raise SystemExit(main())
