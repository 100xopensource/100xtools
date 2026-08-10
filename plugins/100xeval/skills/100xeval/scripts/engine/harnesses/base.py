"""The Harness protocol + a name registry.

A harness knows how to run a Case on one runtime and return a RunResult. It also
declares which grader types it can support — `tool_used` needs a harness that
exposes tool calls, which not every surface does. The
executor stays harness-agnostic; graders consume RunResult, never harness internals.
"""

from __future__ import annotations

from typing import Protocol

from ..models import Case, RunResult


class Abort(Exception):
    """Preflight failure — the case cannot run here (e.g. MCP unauthenticated).

    Carries actionable guidance so the runner can tell the user what to fix,
    rather than producing a misleading dataless run.
    """


class Harness(Protocol):
    name: str

    def supports(self, grader_type: str) -> bool:
        """Whether a grader of this type can be evaluated on this harness."""
        ...

    def preflight(self, case: Case) -> None:
        """Raise Abort if the case can't run here (e.g. needs auth)."""
        ...

    def run(self, case: Case, model: str | None, workspace: str | None = None) -> RunResult:
        """Invoke the plugin once and return the observable outcome.

        `workspace` (if given) is a persistent dir the harness may stage into, so the run
        is inspectable under evals/runs/<run_id>/; None → use an ephemeral temp dir.
        """
        ...


_REGISTRY: dict[str, Harness] = {}


def register_harness(harness: Harness) -> None:
    _REGISTRY[harness.name] = harness


def get_harness(name: str) -> Harness:
    if name not in _REGISTRY:
        raise KeyError(f"unknown harness {name!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def registered() -> list[str]:
    return sorted(_REGISTRY)
