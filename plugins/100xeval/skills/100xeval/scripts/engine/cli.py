"""CLI — `init` and `eval`.

`eval` runs static + behavioral by default; `--static-only` / `--skip-static` select a
layer. Exit codes: 0 all-pass, 1 a case below threshold, 2 engine error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import loader, reporter
from .orchestrator import run_case

DEFAULT_ROOT = "evals"
# `run.py` beside the engine package — used to print copy-pasteable next steps.
RUN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py")


def _run_py() -> str:
    """The shortest path to run.py that actually works from here.

    A relative path is only friendlier when it is shorter. Installed outside the user's
    tree it becomes `../../../Users/...`, which is worse than the absolute path and reads
    like a bug.
    """
    rel = os.path.relpath(RUN_PY)
    return rel if not rel.startswith("..") else RUN_PY


def _new_run_id() -> str:
    """Sortable timestamp + short random suffix, unique per invocation."""
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

CASE_STUB = """\
name: {name}
description: <what this case proves>
plugins: ["../../plugins/<plugin>"]
tags: [{tag}]
runs: 3
execution:
  prompt: "<the user question, verbatim>"
  model: claude-sonnet-5
  harness: claude_code                 # runtime that executes the turn
  entrypoint: none                     # surface emulated; `none` = the harness's own prompt
  max_turns: 15
  allowed_tools: [Read, Glob, Grep, Skill]
  append_system_prompt: null
graders:
  # Assert the SHAPE of the query, not a figure — a hard-coded number is a scheduled
  # false failure. Replace <your-mcp-tool> with a tool your plugin actually calls, e.g.
  # mcp__<Server>__<tool>; delete this grader if your plugin declares no MCP.
  - {{type: tool_used, name: queried-right-data, tool: <your-mcp-tool>, min: 1}}
  - {{type: llm, name: presentation, focus: last_message, criteria: "<what a good answer looks like>"}}
"""


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="100xeval", description="Behavioral + static eval for plugins.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold a new evals/<name>/case.yaml")
    p_init.add_argument("name")
    p_init.add_argument("--plugin", default="<plugin>")
    p_init.add_argument("--tag", default="")
    p_init.add_argument("--prompt", default=None)
    p_init.add_argument("--root", default=DEFAULT_ROOT)
    p_init.add_argument("--force", action="store_true")

    p_eval = sub.add_parser("eval", help="run static and/or behavioral evals")
    p_eval.add_argument("--root", default=DEFAULT_ROOT)
    p_eval.add_argument("--tag", action="append", default=[], help="repeatable; all must be present")
    p_eval.add_argument("--case", default=None, help="fnmatch glob on case name")
    p_eval.add_argument("--target", default=None, help="plugin path for --static-only")
    p_eval.add_argument("--runs", type=int, default=None, help="override runs per case")
    p_eval.add_argument("--judge-model", default="claude-haiku-4-5-20251001")
    p_eval.add_argument("--judge-votes", type=int, default=3)
    p_eval.add_argument("--judge-system-prompt", default=None, metavar="PATH_OR_TEXT",
                        help="override the judge's grader system prompt (a file path, or literal text)")
    p_eval.add_argument("--static-only", action="store_true")
    p_eval.add_argument("--skip-static", action="store_true")
    p_eval.add_argument("--threshold", type=float, default=1.0)
    p_eval.add_argument("--concurrency", type=int, default=4,
                        help="max plugin runs in flight across the WHOLE suite; cases run "
                             "in parallel under this budget (1 = fully sequential)")
    p_eval.add_argument("--case-concurrency", dest="case_concurrency", type=int, default=None,
                        help="max cases in flight (default: --concurrency). Grading doesn't "
                             "hold a run slot, so a higher value can overlap judging with runs.")
    p_eval.add_argument("--timeout", type=int, default=None,
                        help="override each case's per-run timeout, in seconds")
    p_eval.add_argument("--report", default=None, help="write markdown here")
    p_eval.add_argument("--json", dest="json_path", default=None, help="write JSON here")
    p_eval.add_argument("--html", dest="html_path", default=None, help="write HTML here")
    p_eval.add_argument("--verbose", action="store_true")
    p_eval.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="list what would run and the rough spend, without running it")

    args = ap.parse_args(argv)
    if args.command == "init":
        return _cmd_init(args)
    return _cmd_eval(args)


def _cmd_init(args) -> int:
    case_dir = os.path.join(args.root, args.name)
    path = os.path.join(case_dir, "case.yaml")
    if os.path.exists(path) and not args.force:
        print(f"refusing to overwrite {path} (use --force)", file=sys.stderr)
        return 2
    os.makedirs(case_dir, exist_ok=True)
    text = CASE_STUB.format(name=args.name, tag=args.tag or args.name)
    if args.plugin and args.plugin != "<plugin>":
        # `plugins:` is relative to the CASE dir, but --plugin is given repo-relative
        # (`plugins/foo`). Resolve it rather than leaving the literal placeholder — the
        # flag was accepted and silently ignored, so every scaffolded case needed a
        # hand-edit before it could load.
        rel = os.path.relpath(args.plugin, case_dir).replace(os.sep, "/")
        text = text.replace('["../../plugins/<plugin>"]', f'["{rel}"]')
    if args.prompt:
        text = text.replace('"<the user question, verbatim>"', f'"{args.prompt}"')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    # A scaffold that does not say what to do next is a dead end: the stub still has
    # placeholders in it, and running it as-is spends money to fail.
    print(f"wrote {path}\n")
    print("Next:")
    print(f"  1. edit {path} — replace <your-mcp-tool> and the grader criteria")
    print(f"  2. dry run:  python3 {_run_py()} eval --case {args.name} --dry-run")
    print(f"  3. for real: python3 {_run_py()} eval --case {args.name} --runs 1")
    print("\n     A behavioral run costs real money (~$1-2 per run, more with llm graders).")
    return 0


def _cmd_eval(args) -> int:
    if args.static_only and args.skip_static:
        print("--static-only and --skip-static are mutually exclusive", file=sys.stderr)
        return 2

    # Static layer (optional; import guarded so behavioral works even if unavailable).
    static_report = None
    if not args.skip_static:
        try:
            static_report = _run_static(args)
        except _StaticUsageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.static_only:
            _emit_static(static_report, args)
            return 0 if (static_report or {}).get("ok", True) else 1
        # Default `eval` = static AND behavioral. The static result used to be computed
        # here and then dropped: never printed, never written, never used — so the run
        # claimed two layers and showed one. It is reported SEPARATELY, so it
        # prints here and lands in the run dir; the exit code stays behavioral-only.
        if static_report is not None:
            print(static_render(static_report))
            print()

    cases, errors = loader.load_all(args.root, tags=args.tag or None, case_glob=args.case)
    for path, msg in errors:
        print(f"⚠️  skipped {path}: {msg}", file=sys.stderr)
    # A case that will not parse is broken, and the run used to warn and still exit 0 — so a
    # case that rotted (renamed plugin, bad YAML) silently stopped testing anything and CI
    # stayed green. The valid cases still run: one bad case must not block a suite of fifty.
    # But the exit code tells the truth, at every return path below.
    load_failed = bool(errors)
    # Deliberately-skipped cases are announced every run: a silent skip becomes a
    # permanent one nobody remembers to revisit.
    all_cases, _ = loader.load_all(args.root, tags=args.tag or None, case_glob=args.case,
                                   include_skipped=True)
    for c in all_cases:
        if c.skip:
            print(f"⏭  skipping {c.name}: {c.skip}")
    if not cases:
        print("no matching cases — nothing to run (not an error).")
        return 2 if load_failed else 0

    if args.dry_run:
        # Behavioral runs spend real money, and the first one a user tries is usually a
        # freshly scaffolded case that still has placeholders in it. Let them look first.
        total_runs = sum(args.runs or c.runs for c in cases)
        judges = sum(1 for c in cases for g in c.graders if g.type == "llm")
        print(f"\ndry run — {len(cases)} case(s), {total_runs} plugin run(s), "
              f"{judges} llm grader(s)\n")
        for c in cases:
            n = args.runs or c.runs
            print(f"  {c.name}  ×{n}  [{c.label()}]  {len(c.graders)} grader(s)")
            for g in c.graders:
                print(f"      - {g.type}: {g.name}")
        print(f"\n  Rough spend: ${total_runs * 1.0:.0f}-${total_runs * 2.0 + judges * 1.0:.0f}. "
              f"Judges are extra model calls on top of each run.")
        print("  Nothing was executed. Drop --dry-run to run it.")
        return 2 if load_failed else 0

    # One self-contained run directory: workspace + artifacts + reports.
    run_id = _new_run_id()
    run_dir = os.path.join(args.root, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "cases.json"), "w", encoding="utf-8") as fh:
        json.dump([c.as_dict() for c in cases], fh, indent=2)
    print(f"run {run_id} → {run_dir}")

    judge_system_prompt = _load_judge_system_prompt(args.judge_system_prompt)

    for case in cases:
        if args.runs:
            case.runs = args.runs
        if args.timeout:
            case.timeout_s = args.timeout

    # Cases run CONCURRENTLY, all drawing from one shared pool of `--concurrency` run
    # slots. The bounded resource is the number of `claude -p` subprocesses in flight
    # (API + the plugin's MCP), not how they are spread over cases — so overlapping cases
    # cuts wall clock without raising peak load. `--concurrency 1` is still fully serial.
    run_slots = threading.BoundedSemaphore(max(1, args.concurrency))
    case_workers = max(1, min(len(cases), args.case_concurrency or args.concurrency))
    print_lock = threading.Lock()

    def run_one(case):
        if args.verbose:
            with print_lock:
                print(f"▶ {case.name} ({case.label()} × {case.runs} run(s))…", flush=True)
        card = run_case(
            case, threshold=args.threshold, concurrency=args.concurrency,
            judge_model=args.judge_model, judge_votes=args.judge_votes, run_dir=run_dir,
            judge_system_prompt=judge_system_prompt, run_slots=run_slots,
        )
        if args.verbose:
            with print_lock:
                mark = "✅" if card.passed else "❌"
                print(f"{mark} {case.name} — score {card.score:.2f}", flush=True)
        return card

    cards = []
    engine_error = False
    # Submit in case order and collect in the same order, so the report is deterministic
    # no matter which case happens to finish first.
    with ThreadPoolExecutor(max_workers=case_workers) as pool:
        futures = [(case, pool.submit(run_one, case)) for case in cases]
        for case, future in futures:
            try:
                cards.append(future.result())
            except Exception as exc:  # engine-level failure
                engine_error = True
                print(f"engine error on {case.name}: {exc}", file=sys.stderr)

    report = reporter.build_report(cards)
    md = reporter.to_markdown(report)
    print(md)
    # Reports always land in the run dir; explicit flags write additional copies.
    if static_report is not None:
        _write(os.path.join(run_dir, "static.md"), static_render(static_report))
        _write(os.path.join(run_dir, "static.json"), json.dumps(static_report, indent=2))
    _write(os.path.join(run_dir, "report.md"), md)
    _write(os.path.join(run_dir, "report.json"), reporter.to_json(report))
    _write(os.path.join(run_dir, "report.html"), reporter.to_html(report))
    if args.report:
        _write(args.report, md)
    if args.json_path:
        _write(args.json_path, reporter.to_json(report))
    if args.html_path:
        _write(args.html_path, reporter.to_html(report))
    print(f"\n📁 run artifacts: {run_dir}")

    if engine_error or load_failed:
        return 2
    return 0 if report["casesPassed"] == report["casesTotal"] else 1


def _load_judge_system_prompt(value):
    """`--judge-system-prompt` is a file path when one exists, else literal text.

    None keeps the built-in grader persona (judge.system_prompt_for).
    """
    if not value:
        return None
    if os.path.isfile(value):
        with open(value, encoding="utf-8") as fh:
            return fh.read()
    return value


class _StaticUsageError(Exception):
    """Wraps static.TargetError so _cmd_eval can exit 2 rather than reporting a score."""


def _run_static(args):
    try:
        from . import static as static_mod
    except Exception as exc:  # static layer not built yet
        if args.verbose:
            print(f"(static layer unavailable: {exc})", file=sys.stderr)
        return None
    targets = [args.target] if args.target else None
    try:
        return static_mod.run(args.root, targets=targets)
    except static_mod.TargetError as exc:
        raise _StaticUsageError(str(exc)) from exc


def _emit_static(report, args):
    """Print the static scorecard and honour --report / --json / --html.

    `--static-only` used to write ONLY --json: `--report` was accepted and silently
    ignored, so CI's `--static-only --report static.md` produced no file and the next
    step died on `cat: static.md: No such file or directory`.
    """
    if report is None:
        print("static layer not available.")
        return
    rendered = static_render(report)
    print(rendered)
    if args.report:
        _write(args.report, rendered)
    if args.json_path:
        _write(args.json_path, json.dumps(report, indent=2))
    if args.html_path:
        _write(args.html_path, static_html(report))


def static_html(report) -> str:
    """Minimal self-contained HTML for the static scorecard (no external assets)."""
    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rows = []
    for plugin in report.get("plugins", []):
        subs = " · ".join(f"{k} {v:.2f}" for k, v in (plugin.get("sub_scores") or {}).items())
        rows.append(f"<tr><td><code>{esc(plugin['path'])}</code></td>"
                    f"<td>{plugin['design_score']:.2f}</td><td>{esc(subs)}</td></tr>")
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>100xeval — static design quality</title>"
            "<style>body{font:15px/1.5 -apple-system,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}"
            "table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:.4rem .6rem;"
            "border-bottom:1px solid #ddd}code{font:12px ui-monospace,Menlo,monospace}</style></head><body>"
            "<h1>100xeval — static design quality</h1><table><thead><tr><th>Plugin</th>"
            "<th>design_score</th><th>sub-scores</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></body></html>")


def static_render(report) -> str:
    """Scores AND the findings behind them.

    Printing the score alone left the only actionable half of the result reachable through
    an undocumented `python3 -c` incantation — a sub-score of 0.75 named a category and
    nothing you could fix.
    """
    lines = ["# 100xeval — static design quality", ""]
    for plugin in report.get("plugins", []):
        lines.append(f"## {plugin['path']} — design_score {plugin['design_score']:.2f}")
        if plugin.get("error"):
            lines += [f"- error: {plugin['error']}", ""]
            continue
        for name, score in plugin["sub_scores"].items():
            lines.append(f"- {name}: {score:.2f}")
        findings = plugin.get("findings") or []
        if findings:
            lines += ["", f"### findings ({len(findings)})"]
            lines += [f"- {f}" for f in findings]
        elif plugin["design_score"] >= 1.0:
            lines.append("\nNo findings. Nothing to fix.")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
