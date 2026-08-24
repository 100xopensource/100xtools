"""Codex harness — SEAM ONLY, not implemented.

A second RUNTIME (not a surface): running the same case on a non-Claude engine to check
how a plugin's skills travel. Unlike `claude_code`, the driving mechanism and whether
tool calls are observable at all are both still open.

It registers so a case can name it and get an actionable abort, rather than the generic
"unknown harness" error. It declares `tool_used` unsupported, so if it ever runs before
tool observability is proven the grader reports "unsupported" instead of a false fail.

Note this is the ONLY reason to add a harness: a genuinely different runtime. A different
*surface* (Cowork, claude.ai chat) is the `entrypoint` axis on top of an existing runtime —
see `engine/entrypoints/README.md`.
"""

from __future__ import annotations

from ..models import Case, RunResult
from .base import Abort, register_harness


class CodexHarness:
    name = "codex"

    def supports(self, grader_type: str) -> bool:
        # Conservative until tool-call observability on this runtime is proven.
        return grader_type in ("regex", "llm")

    def preflight(self, case: Case) -> None:
        raise Abort(
            "codex harness not yet implemented (no driving mechanism decided, and tool-call "
            "observability unproven). Use harness `claude_code` for now."
        )

    def run(self, case: Case, model: str | None, workspace: str | None = None) -> RunResult:  # pragma: no cover
        return RunResult(error="codex harness not implemented")


register_harness(CodexHarness())
