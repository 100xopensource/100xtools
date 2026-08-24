"""Reporter — Scorecards → markdown scorecard + stable JSON.

The JSON carries `schemaVersion` so the corpus / dashboards can depend
on it. A case is one harness + one model, so each case reports a single flat grader table
labelled with the `harness`/`model` it executed on.
"""

from __future__ import annotations

import json

# 2.0: the per-case `cells` map (the old harness × model matrix) was flattened away —
# `harness`, `model`, `graders`, `executions` now sit directly on each case.
# 2.1: ADDITIVE — each case gained a `plugins` list of plugin names, so a report can be
# grouped by plugin rather than only by case. Nothing was removed or renamed, so a 2.0
# reader keeps working; require 2.1 only if you need the grouping.
SCHEMA_VERSION = "2.1"


def build_report(cards: list, started_at: str | None = None) -> dict:
    """Assemble the stable JSON report from per-case Scorecards."""
    cases = []
    for card in cards:
        cases.append({
            "name": card.name,
            "plugins": list(card.plugins),   # names; lets a reader group by plugin
            "score": round(card.score, 4),
            "passed": card.passed,
            "error": card.error,
            "harness": card.harness,
            "model": card.model,
            "runCostUsd": round(card.cost_usd, 6),
            "judgeCostUsd": round(card.judge_cost_usd, 6),
            "costUsd": round(card.cost_usd + card.judge_cost_usd, 6),   # TOTAL eval cost
            "runTokens": card.tokens,
            "judgeTokens": card.judge_tokens,
            "tokens": _add_tokens(card.tokens, card.judge_tokens),      # TOTAL eval tokens
            "durationMs": card.duration_ms,   # mean per run
            "graders": [
                {
                    "name": g["name"], "type": g["type"], "weight": g["weight"],
                    "passRate": round(g["passRate"], 4),
                    "runs": g["runs"],
                }
                for g in card.graders
            ],
            "executions": card.executions,
        })
    passed = sum(1 for c in cases if c["passed"])
    overall = round(sum(c["score"] for c in cases) / len(cases), 4) if cases else 0.0
    return {
        "schemaVersion": SCHEMA_VERSION,
        "startedAt": started_at,
        "runCostUsd": round(sum(c["runCostUsd"] for c in cases), 6),
        "judgeCostUsd": round(sum(c["judgeCostUsd"] for c in cases), 6),
        "costUsd": round(sum(c["costUsd"] for c in cases), 6),          # TOTAL eval cost
        "tokens": _add_tokens(*[c["tokens"] for c in cases]),
        "overallScore": overall,
        "casesTotal": len(cases),
        "casesPassed": passed,
        "cases": cases,
    }


def to_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=False)


_TOKEN_FIELDS = ("input_tokens", "output_tokens",
                 "cache_read_input_tokens", "cache_creation_input_tokens")


def _add_tokens(*ds) -> dict:
    out = dict.fromkeys(_TOKEN_FIELDS, 0)
    for d in ds:
        for k in _TOKEN_FIELDS:
            out[k] += int((d or {}).get(k) or 0)
    return out


def _fmt_tokens(t: dict) -> str:
    """`12.3k in / 4.1k out / 88.0k cached` — cache split out because it dominates."""
    if not t:
        return "—"
    def k(n):
        n = int(n or 0)
        return f"{n/1000:.1f}k" if n >= 1000 else str(n)
    cached = int(t.get("cache_read_input_tokens") or 0) + int(t.get("cache_creation_input_tokens") or 0)
    return f"{k(t.get('input_tokens'))} in / {k(t.get('output_tokens'))} out / {k(cached)} cached"


def _label(case: dict) -> str:
    """The case's execution identity, e.g. `claude_code/claude-sonnet-5`."""
    return f"{case.get('harness') or '—'}/{case.get('model') or 'default'}"


def to_html(report: dict) -> str:
    """Self-contained, theme-aware HTML scorecard (no external assets)."""
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    rows = []
    for c in report["cases"]:
        mark = "✅" if c["passed"] else "❌"
        cls = "pass" if c["passed"] else "fail"
        rows.append(
            f'<tr class="{cls}"><td><a href="#{esc(c["name"])}">{esc(c["name"])}</a></td>'
            f'<td><code>{esc(_label(c))}</code></td>'
            f'<td class="num">{c["score"]:.2f}</td><td>{mark}</td>'
            f'<td class="num">${c.get("runCostUsd", 0):.4f}</td>'
            f'<td class="num">${c.get("judgeCostUsd", 0):.4f}</td>'
            f'<td class="num"><b>${c["costUsd"]:.4f}</b></td>'
            f'<td class="num">{c["durationMs"]} ms</td></tr>'
        )
    summary_rows = "\n".join(rows)

    sections = []
    for c in report["cases"]:
        body = []
        if c.get("error"):
            body.append(f'<p class="err">⚠️ {esc(c["error"])}</p>')
        # Per-grader summary rows. Detail does NOT go in a table cell: with `runs` × judge
        # votes it reached thousands of characters and made the table unreadable. It goes
        # below, one block per grader, one line per run.
        grows, dblocks = [], []
        for g in c.get("graders", []):
            pct = g["passRate"]
            bar = int(round(pct * 100))
            gcls = "pass" if pct >= 1.0 else ("part" if pct > 0 else "fail")
            grows.append(
                f'<tr class="{gcls}"><td>{esc(g["name"])}</td><td>{esc(g["type"])}</td>'
                f'<td class="num">{g["weight"]}</td>'
                f'<td><div class="bar"><span style="width:{bar}%"></span></div>{bar}%</td></tr>'
            )
            runs = [r for r in g["runs"] if r.get("detail")]
            if not runs:
                continue
            items = "".join(
                f'<li class="{"pass" if r["passed"] else "fail"}">'
                f'<span class="mark">{"✅" if r["passed"] else "❌"}</span>'
                f'<span class="rn">run {i}</span>'
                f'<span class="dtext">{esc(r["detail"])}</span></li>'
                for i, r in enumerate(runs, 1)
            )
            dblocks.append(f'<div class="gdetail"><h5>{esc(g["name"])}</h5><ul>{items}</ul></div>')
        # Execution/debug panel — session id, transcript path, tool calls, answer.
        debug = []
        for ex in c.get("executions", []):
            tcs = "".join(
                f"<li><code>{esc(t['name'])}</code> <span class='muted'>{esc(t['input'][:200])}</span></li>"
                for t in ex.get("tool_calls", [])
            ) or "<li class='muted'>none observed</li>"
            err = f'<p class="err">ERROR: {esc(ex["error"])}</p>' if ex.get("error") else ""
            debug.append(
                f'<div class="run"><b>run {ex["run"]}</b> '
                f'<span class="muted">${ex.get("cost_usd",0):.4f} · {esc(_fmt_tokens(ex.get("tokens")))} '
                f'· {ex.get("duration_ms",0)} ms</span>{err}'
                f'<dl><dt>session</dt><dd><code>{esc(ex.get("session_id") or "—")}</code></dd>'
                f'<dt>transcript</dt><dd><code>{esc(ex.get("transcript_path") or "—")}</code></dd></dl>'
                f'<div class="muted">tool calls</div><ul class="tc">{tcs}</ul>'
                f'<details><summary>answer ({len(ex.get("final_text",""))} chars)</summary>'
                f'<pre>{esc(ex.get("final_text",""))}</pre></details></div>'
            )
        if grows:
            body.append(
                f'<h4>{esc(_label(c))} — score {c["score"]:.2f} '
                f'<span class="muted">(${c.get("costUsd",0):.4f} total = runs ${c.get("runCostUsd",0):.4f} '
                f'+ judges ${c.get("judgeCostUsd",0):.4f} · {esc(_fmt_tokens(c.get("tokens")))} '
                f'· {c.get("durationMs",0)} ms/run avg)</span></h4>'
                '<table class="graders"><thead><tr><th>grader</th><th>type</th><th>wt</th>'
                '<th>passRate</th></tr></thead><tbody>'
                + "\n".join(grows) + "</tbody></table>"
                + "".join(dblocks)
            )
        if debug:
            body.append('<details class="debug"><summary>🔍 execution / debug</summary>'
                        + "".join(debug) + "</details>")
        badge = "✅ passed" if c["passed"] else "❌ failed"
        sections.append(
            f'<section id="{esc(c["name"])}"><h3>{esc(c["name"])} '
            f'<span class="badge {"pass" if c["passed"] else "fail"}">{badge}</span></h3>'
            + "".join(body) + "</section>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>100xeval report</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --muted:#6b7280; --line:#e5e7eb; --pass:#16a34a; --fail:#dc2626; --part:#d97706; --accent:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --fg:#e5e7eb; --muted:#9ca3af; --line:#272b33; --pass:#22c55e; --fail:#ef4444; --part:#f59e0b; --accent:#60a5fa; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2rem 1.25rem; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; max-width:1000px; margin-inline:auto; }}
h1 {{ font-size:1.4rem; margin:0 0 .25rem; }} h3 {{ margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }} h4 {{ margin:.75rem 0 .35rem; }}
.overall {{ font-size:1.1rem; margin:.5rem 0 1.5rem; }} .muted {{ color:var(--muted); font-weight:400; font-size:.85em; }}
table {{ border-collapse:collapse; width:100%; margin:.25rem 0; overflow-x:auto; display:block; }}
th,td {{ text-align:left; padding:.4rem .6rem; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; font-size:.8rem; text-transform:uppercase; letter-spacing:.03em; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.detail {{ color:var(--muted); font-size:.85rem; }}
a {{ color:var(--accent); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
.badge {{ font-size:.75rem; padding:.1rem .5rem; border-radius:999px; font-weight:600; }}
.badge.pass {{ color:var(--pass); border:1px solid var(--pass); }} .badge.fail {{ color:var(--fail); border:1px solid var(--fail); }}
tr.pass td:first-child {{ box-shadow:inset 3px 0 var(--pass); }} tr.fail td:first-child {{ box-shadow:inset 3px 0 var(--fail); }} tr.part td:first-child {{ box-shadow:inset 3px 0 var(--part); }}
.bar {{ display:inline-block; width:80px; height:8px; background:var(--line); border-radius:4px; margin-right:.5rem; overflow:hidden; vertical-align:middle; }}
.bar span {{ display:block; height:100%; background:var(--pass); }}
tr.fail .bar span {{ background:var(--fail); }} tr.part .bar span {{ background:var(--part); }}
.err {{ color:var(--fail); font-weight:600; }}
.gdetail {{ margin:.6rem 0 1rem; }}
.gdetail h5 {{ margin:.4rem 0 .3rem; font-size:.82rem; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:.03em; }}
.gdetail ul {{ list-style:none; margin:0; padding:0; }}
.gdetail li {{ display:grid; grid-template-columns:1.4rem 3.4rem 1fr; gap:.4rem; align-items:start;
               padding:.4rem .5rem; border-left:2px solid var(--line); margin-bottom:.3rem; font-size:.86rem; }}
.gdetail li.pass {{ border-left-color:var(--pass); }} .gdetail li.fail {{ border-left-color:var(--fail); }}
.gdetail .rn {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
.gdetail .dtext {{ color:var(--fg); overflow-wrap:anywhere; }}
.debug {{ margin:.75rem 0; }} .debug > summary {{ cursor:pointer; color:var(--accent); font-size:.9rem; }}
.run {{ border-left:2px solid var(--line); padding:.5rem .75rem; margin:.5rem 0; }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:.15rem .75rem; margin:.4rem 0; }}
dt {{ color:var(--muted); font-size:.8rem; }} dd {{ margin:0; }}
code {{ font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--line); padding:.05rem .3rem; border-radius:3px; word-break:break-all; }}
ul.tc {{ margin:.2rem 0 .5rem; padding-left:1.2rem; }} ul.tc li {{ font-size:.85rem; }}
pre {{ background:var(--line); padding:.6rem; border-radius:6px; overflow-x:auto; white-space:pre-wrap; font:12px/1.5 ui-monospace,Menlo,monospace; max-height:400px; }}
details summary {{ cursor:pointer; }}
</style></head><body>
<h1>100xeval report</h1>
<div class="overall"><b>Overall {report['overallScore']:.2f}</b> · {report['casesPassed']}/{report['casesTotal']} cases passed · <b>${report['costUsd']:.4f} total</b>
<span class="muted">runs ${report.get('runCostUsd', 0):.4f} + judges ${report.get('judgeCostUsd', 0):.4f} · schema v{esc(report['schemaVersion'])}</span></div>
<table class="summary"><thead><tr><th>Case</th><th>Harness / model</th><th class="num">Score</th><th>Passed</th><th class="num">Run $</th><th class="num">Judge $</th><th class="num">Total $</th><th class="num">Avg run</th></tr></thead>
<tbody>
{summary_rows}
</tbody></table>
{''.join(sections)}
</body></html>"""


def to_markdown(report: dict) -> str:
    out: list[str] = []
    out.append("# 100xeval report")
    out.append("")
    out.append(f"**Overall {report['overallScore']:.2f}** · "
               f"{report['casesPassed']}/{report['casesTotal']} cases passed · "
               f"**${report['costUsd']:.4f} total** "
               f"(runs ${report.get('runCostUsd', 0):.4f} + judges ${report.get('judgeCostUsd', 0):.4f}) · "
               f"{_fmt_tokens(report.get('tokens'))}")
    out.append("")
    out.append("| Case | Harness / model | Score | Passed | Run $ | Judge $ | Total $ | Avg run |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for c in report["cases"]:
        mark = "✅" if c["passed"] else "❌"
        out.append(f"| {c['name']} | `{_label(c)}` | {c['score']:.2f} | {mark} | "
                   f"${c.get('runCostUsd', 0):.4f} | ${c.get('judgeCostUsd', 0):.4f} | "
                   f"${c['costUsd']:.4f} | {c['durationMs']} ms |")
    out.append("")

    for c in report["cases"]:
        label = _label(c)
        out.append(f"## {c['name']}")
        if c["error"]:
            out.append(f"> ⚠️ {c['error']}")
        out.append("")
        out.append(f"`{label}` · score **{c['score']:.2f}** · "
                   f"${c['costUsd']:.4f} total "
                   f"(runs ${c.get('runCostUsd', 0):.4f} + judges ${c.get('judgeCostUsd', 0):.4f}) · "
                   f"{c['durationMs']} ms/run avg")
        out.append("")
        out.append("| Tokens | Input | Output | Cache read | Cache write |")
        out.append("| --- | --- | --- | --- | --- |")
        for lbl, key in (("runs", "runTokens"), ("judges", "judgeTokens"), ("**total**", "tokens")):
            tk = c.get(key) or {}
            out.append(f"| {lbl} | {tk.get('input_tokens', 0):,} | {tk.get('output_tokens', 0):,} | "
                       f"{tk.get('cache_read_input_tokens', 0):,} | {tk.get('cache_creation_input_tokens', 0):,} |")
        out.append("")
        # Per-grader results for this case's runs.
        if c.get("graders"):
            out.append("| Grader | Type | Weight | passRate |")
            out.append("| --- | --- | --- | --- |")
            for g in c["graders"]:
                out.append(f"| {g['name']} | {g['type']} | {g['weight']} | {g['passRate']:.0%} |")
            out.append("")
        # Per-grader detail, ONE LINE PER RUN. Joining every run's detail into a single
        # line produced thousands of characters with no way to tell the runs apart.
        for g in c.get("graders", []):
            runs = [r for r in g["runs"] if r.get("detail")]
            if not runs or all(r["passed"] for r in runs):
                continue          # a fully passing grader needs no explanation
            out.append(f"- **{g['name']}** ({g['type']}) — {g['passRate']:.0%}")
            for i, r in enumerate(runs, 1):
                mark = "✅" if r["passed"] else "❌"
                out.append(f"    - {mark} run {i}: {r['detail']}")
        # Execution/debug metadata — session id + transcript path per run.
        for ex in c.get("executions", []):
            bits = [f"run {ex['run']}", f"session `{ex.get('session_id') or '—'}`"]
            if ex.get("transcript_path"):
                bits.append(f"transcript `{ex['transcript_path']}`")
            bits.append(f"${ex.get('cost_usd', 0):.4f}")
            bits.append(_fmt_tokens(ex.get("tokens")))
            bits.append(f"{ex.get('duration_ms', 0)} ms")
            if ex.get("error"):
                bits.append(f"**ERROR:** {ex['error']}")
            out.append("- 🔍 " + " · ".join(bits))
        out.append("")
    return "\n".join(out)
