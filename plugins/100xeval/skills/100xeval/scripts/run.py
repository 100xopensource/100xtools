#!/usr/bin/env python3
"""100xeval entrypoint. Usage: python3 evals/100xeval/run.py <init|eval> [...]."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
