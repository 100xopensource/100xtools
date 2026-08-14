#!/usr/bin/env python3
"""Entrypoint for the 100xcontinuity engine.

Kept to a launcher so the engine stays importable as a package from the tests and
from any other tool that wants it. Put the engine's own directory on the path
first, so running this from a clone works without installing anything.

    python3 run.py save --name summary.md --file ./summary.md
    python3 run.py list
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from engine.cli import main  # noqa: E402 - the path insert above must run first


if __name__ == "__main__":
    raise SystemExit(main())
