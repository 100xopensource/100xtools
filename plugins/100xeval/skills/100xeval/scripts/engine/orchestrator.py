"""Orchestrator — coordinates the pipeline: for each case it drives `runs` repetitions of
ONE harness + ONE model, calls the Executor-harness for each run, scores via graders, and
persists each stage as structured files under the run directory. (Diagram: the
"Orchestrator" box; the "Executor-harness" box is `harnesses/`.)

Harness-agnostic: dispatches to a registered adapter and only ever touches
RunResult. Scoring: per grader `passRate = passed/runs`; case score = weighted
mean of passRates. When `run_dir` is given, components hand off via files: each
run writes `result.json` + `transcript.jsonl`, each case writes `scorecard.json`.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor

from . import graders as graders_mod
from .harnesses.base import Abort, get_harness
from .harnesses.claude_code import add_tokens
from .models import Case, Scorecard


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in name)


def case_dirname(case: Case) -> str:
    return _safe(case.name)


def plugin_names(case: Case) -> list[str]:
    """`Case.plugins` resolved to plugin names, for grouping a report by plugin.

    The paths in a case file are relative to that case file, so the same plugin is spelled
    differently from cases at different depths (`../../plugins/x` vs `../plugins/x`).
    Resolving then taking the basename is what `graders.py` and `harnesses/claude_code.py`
    already do to find the plugin on disk; here it also makes the name stable enough to
    group on.
    """
    names = []
    for rel in case.plugins:
        name = os.path.basename(os.path.normpath(os.path.join(case.path, rel)))
        if name and name not in names:
            names.append(name)
    return names


def run_case(case: Case, threshold: float = 1.0, concurrency: int = 4,
             context_builder=None, judge_model=None, judge_votes=3, run_dir=None,
             judge_system_prompt=None, run_slots=None) -> Scorecard:
    """Execute a case's `runs` repetitions on its harness + model, and score them.

    `run_slots` is an optional semaphore shared across ALL cases in a suite. Cases may
    execute concurrently (cli.py), and each plugin run is a `claude -p` subprocess hitting
    the API and the plugin's MCP — so the cap that matters is the total number in flight,
    not the per-case one. Held only around `harness.run`: a case that has finished running
    and is grading releases its slot so another case can start.
    """
    card = Scorecard(name=case.name, harness=case.harness, model=case.model,
                     plugins=plugin_names(case))
    case_dir = os.path.join(run_dir, case_dirname(case)) if run_dir else None
    base_ctx = {"judge_model": judge_model, "judge_votes": judge_votes,
                "judge_system_prompt": judge_system_prompt}

    try:
        harness = get_harness(case.harness)
    except KeyError as exc:
        return _errored_card(card, str(exc))
    try:
        harness.preflight(case)
    except Abort as exc:
        return _errored_card(card, f"preflight aborted: {exc}")

    slot = run_slots if run_slots is not None else contextlib.nullcontext()

    def one_run(i):
        run_subdir = os.path.join(case_dir, f"run-{i + 1}") if case_dir else None
        workspace = os.path.join(run_subdir, "workspace") if run_subdir else None
        with slot:
            result = harness.run(case, case.model, workspace)
        if run_subdir:
            _persist_run(run_subdir, result)
        return result

    workers = max(1, min(concurrency, case.runs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one_run, range(case.runs)))

    # Grade every run with every grader; a harness that can't expose tool calls
    # tells the tool_used grader via context so it reports "unsupported", not fail.
    per_grader: dict[str, list] = {g.name: [] for g in case.graders}
    order = {g.name: (g.type, g.weight) for g in case.graders}
    for result in results:
        ctx = {"case": case, "harness": case.harness, "model": case.model}
        ctx.update(base_ctx)
        if not harness.supports("tool_used"):
            ctx["tool_calls_unavailable"] = True
        if context_builder:
            ctx.update(context_builder(case, result))
        for grader in case.graders:
            outcome = graders_mod.grade(grader, result, ctx)
            per_grader[grader.name].append(outcome)

    weighted_sum = 0.0
    weight_total = 0.0
    judge_cost = 0.0
    judge_tokens: list[dict] = []
    for name, outcomes in per_grader.items():
        judge_cost += sum(o.cost_usd for o in outcomes)
        judge_tokens.extend(o.tokens for o in outcomes if o.tokens)
        gtype, weight = order[name]
        passed = sum(1 for o in outcomes if o.passed)
        pass_rate = passed / case.runs if case.runs else 0.0
        card.graders.append({
            "name": name, "type": gtype, "weight": weight, "passRate": pass_rate,
            "runs": [{"passed": o.passed, "detail": o.detail} for o in outcomes],
        })
        weighted_sum += weight * pass_rate
        weight_total += weight

    # Per-run execution metadata — everything needed to debug a failing run.
    card.executions = [
        {
            "run": i + 1,
            "session_id": r.session_id,
            "transcript_path": r.transcript_path,
            "cost_usd": r.cost_usd,
            "tokens": r.tokens,
            "duration_ms": r.duration_ms,
            "error": r.error,
            "tool_calls": [{"name": c.name, "input": c.input_str} for c in r.tool_calls],
            "final_text": r.final_text,
        }
        for i, r in enumerate(results)
    ]
    card.score = weighted_sum / weight_total if weight_total else 0.0
    card.passed = card.score >= threshold
    card.cost_usd = sum(r.cost_usd for r in results)      # the plugin runs
    card.judge_cost_usd = judge_cost                       # what grading them cost
    card.tokens = add_tokens(*[r.tokens for r in results])
    card.judge_tokens = add_tokens(*judge_tokens)
    # AVERAGE, not sum: runs execute concurrently, so a total describes no real elapsed
    # time. "a run takes ~170s" is the useful number; per-run figures stay in executions.
    card.duration_ms = round(sum(r.duration_ms for r in results) / len(results)) if results else 0
    _persist_scorecard(case_dir, card)
    return card


def _persist_scorecard(case_dir: str | None, card: Scorecard) -> None:
    if not case_dir:
        return
    os.makedirs(case_dir, exist_ok=True)
    with open(os.path.join(case_dir, "scorecard.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "name": card.name,
            "harness": card.harness,
            "model": card.model,
            "score": card.score,
            "passed": card.passed,
            "error": card.error,
            "cost_usd": card.cost_usd,
            "judge_cost_usd": card.judge_cost_usd,
            "total_cost_usd": card.cost_usd + card.judge_cost_usd,
            "tokens": card.tokens,
            "judge_tokens": card.judge_tokens,
            "total_tokens": add_tokens(card.tokens, card.judge_tokens),
            "duration_ms": card.duration_ms,
            "graders": card.graders,
            "executions": card.executions,
        }, fh, indent=2)


def _persist_run(run_subdir: str, result) -> None:
    """Write result.json + copy the session transcript into the run's folder."""
    os.makedirs(run_subdir, exist_ok=True)
    with open(os.path.join(run_subdir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "session_id": result.session_id,
            "transcript_path": result.transcript_path,
            "cost_usd": result.cost_usd,
            "tokens": result.tokens,
            "duration_ms": result.duration_ms,
            "error": result.error,
            "command": result.command,
            "returncode": result.returncode,
            "stderr": result.stderr,
            "debug_log": result.debug_log,
            "tool_calls": [{"name": c.name, "input": c.input_str} for c in result.tool_calls],
            "final_text": result.final_text,
        }, fh, indent=2)
    if result.transcript_path and os.path.isfile(result.transcript_path):
        try:
            shutil.copy(result.transcript_path, os.path.join(run_subdir, "transcript.jsonl"))
        except OSError:
            pass


def _errored_card(card: Scorecard, message: str) -> Scorecard:
    card.error = message
    card.score = 0.0
    card.passed = False
    return card
