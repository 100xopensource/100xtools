"""Behavioral graders — each scores one RunResult → GraderOutcome.

Free graders (no model): `tool_used`, `regex`. Paid graders (`llm` format/agentic)
and the `static` grader are registered by their own modules (Phase 3/4) via
`register_grader`; this module owns the dispatch table and the two free graders so
the orchestrator never imports grader internals.
"""

from __future__ import annotations

import fnmatch
import os
import re
from typing import Callable

from .models import Grader, GraderOutcome, RunResult

# A grader fn takes (grader, run_result, context) → (passed, detail).
GraderFn = Callable[[Grader, RunResult, dict], "tuple[bool, str]"]

_GRADERS: dict[str, GraderFn] = {}


def register_grader(gtype: str, fn: GraderFn) -> None:
    _GRADERS[gtype] = fn


def grade(grader: Grader, result: RunResult, context: dict | None = None) -> GraderOutcome:
    context = context or {}
    fn = _GRADERS.get(grader.type)
    if fn is None:
        return GraderOutcome(grader.name, grader.type, grader.weight, False,
                             f"unknown grader type {grader.type!r}")
    try:
        out = fn(grader, result, context)
    except Exception as exc:  # a grader bug must not crash the suite
        return GraderOutcome(grader.name, grader.type, grader.weight, False, f"grader error: {exc}")
    # Graders return (passed, detail); llm adds (cost) and (tokens) since grading spends.
    passed, detail = out[0], out[1]
    cost = out[2] if len(out) > 2 else 0.0
    tokens = out[3] if len(out) > 3 else {}
    return GraderOutcome(grader.name, grader.type, grader.weight, passed, detail, cost, tokens)


def _grade_tool_used(grader: Grader, result: RunResult, context: dict):
    """Right-data check: count tool calls matching `tool` (+ optional `input_match`).

    Stale-proof accuracy — asserts the query SHAPE, never a hard-coded number.
    """
    from .harnesses.claude_code import canonical_tool_name

    p = grader.params
    tool = p.get("tool")
    if not tool:
        return False, "tool_used grader missing required `tool`"
    if context.get("tool_calls_unavailable"):
        # The harness cannot expose tool calls: don't false-fail.
        return False, "tool_used unsupported on this harness (tool calls not observable)"
    tool = canonical_tool_name(tool)  # match across account vs plugin-scoped naming
    substring = p.get("input_match")
    minimum = int(p.get("min", 1))
    maximum = p.get("max")

    # Globs are what make absence assertions possible: you cannot enumerate the tools of a
    # server you do not have. Under exact matching `mcp__x__*` matched nothing, so
    # `min: 0, max: 0` passed however often the server was actually called.
    is_glob = any(ch in tool for ch in "*?[")

    def _hit(call) -> bool:
        canon = canonical_tool_name(call.name)
        named = fnmatch.fnmatchcase(canon, tool) if is_glob else canon == tool
        return named and (substring is None or str(substring) in call.input_str)

    matches = [c for c in result.tool_calls if _hit(c)]
    n = len(matches)
    ok = n >= minimum and (maximum is None or n <= int(maximum))
    where = f"{tool}" + (f" matching {substring!r}" if substring else "")
    bound = f">= {minimum}" + (f" and <= {maximum}" if maximum is not None else "")
    return ok, f"called {where} {n}x (needed {bound})"


def _grade_regex(grader: Grader, result: RunResult, context: dict):
    """Phrase present/absent in the output."""
    p = grader.params
    pattern = p.get("pattern")
    if not pattern:
        return False, "regex grader missing required `pattern`"
    target = p.get("target", "last_message")
    mode = p.get("match", "contains")
    flags = 0
    for flag in str(p.get("flags", "")).split("|"):
        flag = flag.strip().upper()
        if flag and hasattr(re, flag):
            flags |= getattr(re, flag)
    if target == "trace":
        haystack = "\n".join(f"{c.name} {c.input_str}" for c in result.tool_calls)
    else:
        haystack = result.final_text
    found = re.search(pattern, haystack, flags) is not None
    if mode == "not_contains":
        return (not found), f"pattern {pattern!r} {'found' if found else 'absent'} in {target} (wanted absent)"
    return found, f"pattern {pattern!r} {'found' if found else 'missing'} in {target}"


def _grade_llm(grader: Grader, result: RunResult, context: dict):
    """AI-judge grader. Empty `allowed_tools` → format mode (presentation);
    non-empty → agentic mode (verifies figures live). Judge config comes from context.
    """
    from . import judge as judge_mod

    p = grader.params
    criteria = p.get("criteria")
    if not criteria:
        return False, "llm grader missing required `criteria`"
    focus = p.get("focus", "last_message")
    allowed = p.get("allowed_tools") or []
    agentic = bool(allowed)

    if focus == "trace":
        content = "\n".join(f"{c.name} {c.input_str}" for c in result.tool_calls)
    else:
        content = result.final_text

    # An agentic judge verifies figures against the data, so it needs the SAME MCP the
    # case ran against — resolved from the case, exactly as the harness resolves it.
    mcp_config = None
    if agentic and context.get("case") is not None:
        from .harnesses.claude_code import resolve_strict_mcp_config
        try:
            mcp_config = resolve_strict_mcp_config(context["case"])
        except Exception:
            mcp_config = None    # fall through; the judge reports what it could not reach

    return judge_mod.judge(
        criteria, content,
        agentic=agentic,
        model=context.get("judge_model"),
        votes=int(context.get("judge_votes", 3)),
        allowed_tools=allowed,
        runner=context.get("judge_runner"),  # tests inject a stub; None → live claude
        mcp_config=mcp_config,
        system_prompt=context.get("judge_system_prompt"),
    )


def _grade_static(grader: Grader, result: RunResult, context: dict):
    """Design-quality gate for the case's plugin — deterministic, free, no run needed.

    The design doc always described `static` as combinable per case, but the type was
    never registered, so `type: static` scored "unknown grader type". Reuses the same
    static layer as `--static-only`, so a case and the standalone report can't disagree.
    """
    case = context.get("case")
    if case is None or not case.plugins:
        return False, "static grader needs a case with `plugins`"

    from . import static as static_mod

    plugin_dir = os.path.normpath(os.path.join(case.path, case.plugins[0]))
    try:
        analysis = static_mod.analyze(plugin_dir)
    except Exception as exc:
        return False, f"static analysis failed for {plugin_dir}: {exc}"

    score = float(analysis.get("design_score", 0.0))
    minimum = float(grader.params.get("min_score", 0.8))
    detail = f"design_score {score:.2f} (needed >= {minimum:.2f})"
    if score < minimum:
        # Name the weakest sub-scores so the failure is actionable, not just a number.
        subs = analysis.get("sub_scores") or {}
        worst = sorted(subs.items(), key=lambda kv: kv[1])[:3]
        if worst:
            detail += " — weakest: " + ", ".join(f"{k} {v:.2f}" for k, v in worst)
    return score >= minimum, detail


register_grader("tool_used", _grade_tool_used)
register_grader("regex", _grade_regex)
register_grader("llm", _grade_llm)
register_grader("static", _grade_static)
