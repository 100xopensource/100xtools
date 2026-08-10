"""Harness adapters — the pluggable RUNTIME seam.

A harness is named for the runtime it drives (`claude_code` = the Claude Code CLI), never
for a surface. The surface a case emulates is the orthogonal `entrypoint` axis (that
surface's real system prompt, see `engine/entrypoints/README.md`). Keeping the two apart is what
lets one runtime emulate several surfaces, and it keeps this registry reserved for what it
is for: genuinely different runtimes.

Each adapter registers under its name; the orchestrator dispatches by `Case.harness`.
Importing the built-in adapter modules registers them.
"""

from .base import Abort, Harness, get_harness, register_harness, registered  # noqa: F401
from . import claude_code  # noqa: F401  (registers "claude_code")
from . import codex  # noqa: F401  (registers "codex" — seam only, preflight aborts)
