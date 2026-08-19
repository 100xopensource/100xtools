"""Comment shaping — a report dict → one markdown body that fits in a PR comment.

Why this is not just `to_markdown` with a size limit. A PR comment is read in a narrow
column by someone who has not opened the Actions tab and may never open it, so the useful
shape is different from a full report: the verdict first, one row per plugin, and detail
folded away. And it has a hard ceiling — GitHub rejects a comment body over 65536
characters — which a real scorecard on a multi-plugin repo can exceed.

**Degradation is announced, never silent.** Every drop appends a line naming what went and
where the full version is. A report that ends mid-sentence with no note reads as complete,
which is the same defect as a gate that passes because it evaluated nothing: the number
looks fine and means nothing. So the ladder below drops whole named sections, and the
byte-slice backstop still leaves a note.

Pure by design — dict in, string out. No filesystem, no environment, no network, so the
whole module is testable on synthetic dicts. That is also why nothing here builds a link to
the workflow run: only the caller in CI knows the run's URL, and reading `GITHUB_*` to guess
one would make these functions depend on the environment they happen to run in.

Two entry points, one per layer, because the two reports have different shapes:
`static_comment` over `static.run()`'s dict, `cases_comment` over
`reporter.build_report()`'s.
"""

from __future__ import annotations

# GitHub's cap is 65536 characters. The headroom absorbs whatever the caller wraps the body
# in — an identity marker, a heading, a run link — none of which this module can see.
MAX_BYTES = 65000

# Beyond this many findings for one plugin, the rest are counted rather than listed. A
# plugin with 200 findings has one systemic problem, and printing all 200 buries the other
# plugins' results without adding a fact.
FINDINGS_PER_PLUGIN = 12

# Node budget for the mermaid diagram. Past roughly this many nodes a flowchart stops being
# readable in a comment column and becomes a wall, so failing cases are kept and passing
# ones collapse into a count.
MERMAID_NODES = 60


def static_comment(report: dict, *, max_bytes: int = MAX_BYTES) -> str:
    """Static design-quality scorecard, one row per plugin."""
    return _fit(lambda **kw: _render_static(report, **kw), max_bytes)


def cases_comment(report: dict, *, max_bytes: int = MAX_BYTES) -> str:
    """Behavioral scorecard, cases grouped under the plugin they exercise."""
    return _fit(lambda **kw: _render_cases(report, **kw), max_bytes)


# --------------------------------------------------------------------------- the drop ladder

# Tried in order, most complete first. Each entry is the keyword state passed to a renderer;
# the first rendering that fits is returned. `_render_*` records what each setting cost in
# the body itself, so the note a reader sees always matches the setting that produced it.
_LADDER = (
    {"findings_cap": None, "detail": True, "diagram": True},
    {"findings_cap": FINDINGS_PER_PLUGIN, "detail": True, "diagram": True},
    {"findings_cap": 3, "detail": True, "diagram": True},
    {"findings_cap": 3, "detail": False, "diagram": True},
    {"findings_cap": 0, "detail": False, "diagram": False},
)


def _fit(render, max_bytes: int) -> str:
    """Render at the most complete setting that fits; slice only if even the barest does not."""
    body = ""
    for settings in _LADDER:
        body = render(**settings)
        if len(body) <= max_bytes:
            return body
    # Backstop. Reaching here means the summary table alone is over the cap — dozens of
    # plugins, or plugin paths long enough to matter. Slice, but say so: a body that just
    # stops is indistinguishable from a complete one.
    note = "\n\n_Truncated: even the summary exceeded the comment size limit. Read the job summary for the full scorecard._\n"
    return body[: max(0, max_bytes - len(note))] + note


def _dropnote(dropped: list[str]) -> list[str]:
    """One line per thing withheld, or nothing at all when the body is complete."""
    if not dropped:
        return []
    return ["", "> **Trimmed to fit a PR comment:** " + "; ".join(dropped) +
            ". The job summary and the uploaded run artifact carry the full report."]


# --------------------------------------------------------------------------- static layer


def _render_static(report: dict, *, findings_cap, detail: bool, diagram: bool) -> str:
    # `diagram` is accepted and ignored: the per-plugin table already carries every number a
    # chart would, so a chart here would restate it. Keeping the parameter lets one ladder
    # drive both layers.
    del diagram
    plugins = list(report.get("plugins") or [])
    dropped: list[str] = []
    out = ["## 100xeval — static design quality", ""]

    if not plugins:
        out += ["**No plugins were analyzed.** Nothing was scored, so this check proves "
                "nothing — point the run at a plugin with `--target`.", ""]
        return "\n".join(out)

    broken = [p for p in plugins if p.get("error")]
    scored = [p for p in plugins if not p.get("error")]
    total_findings = sum(len(p.get("findings") or []) for p in scored)
    ver = report.get("scoringVersion")

    head = []
    if broken:
        head.append(f"⚠️ **{len(broken)} of {len(plugins)} plugins could not be analyzed**")
    if scored:
        lowest = min(p["design_score"] for p in scored)
        head.append(f"**{len(scored)} plugin(s) scored · lowest design_score {lowest:.2f} · "
                    f"{total_findings} finding(s)**")
    if ver is not None:
        head.append(f"scoring v{ver}")
    out += [" · ".join(head), ""]

    out += ["| Plugin | design_score | Weakest sub-score | Findings |",
            "| --- | --- | --- | --- |"]
    for p in plugins:
        if p.get("error"):
            out.append(f"| `{p['path']}` | — | — | ⚠️ {_oneline(p['error'])} |")
            continue
        subs = p.get("sub_scores") or {}
        weakest = min(subs.items(), key=lambda kv: kv[1]) if subs else None
        weak = "—" if not weakest or weakest[1] >= 1.0 else f"{weakest[0]} {weakest[1]:.2f}"
        n = len(p.get("findings") or [])
        out.append(f"| `{p['path']}` | {p['design_score']:.2f} | {weak} | {n} |")
    out.append("")

    if detail:
        for p in scored:
            findings = list(p.get("findings") or [])
            if not findings:
                continue
            shown, hidden = _cap(findings, findings_cap)
            if hidden:
                dropped.append(f"{hidden} finding(s) on `{p['path']}`")
            out += [f"<details><summary><code>{p['path']}</code> — "
                    f"design_score {p['design_score']:.2f}, {len(findings)} finding(s)</summary>",
                    ""]
            out.append(" · ".join(f"{k} {v:.2f}" for k, v in (p.get("sub_scores") or {}).items()))
            out.append("")
            out += [f"- {_oneline(f)}" for f in shown]
            if hidden:
                out.append(f"- _…{hidden} more not shown here._")
            out += ["", "</details>", ""]
    elif any(p.get("findings") for p in scored):
        dropped.append("every per-plugin findings list")

    # Said explicitly because the obvious reading is wrong: `--static-only` exits non-zero
    # only when a plugin fails to ANALYZE. A design_score of 0.50 still exits 0, so calling
    # this comment a pass would claim a gate that does not exist.
    out += ["_A low score does not fail this job: `--static-only` exits non-zero only when a "
            "plugin cannot be analyzed. Gate on the score yourself if you want it enforced._"]
    out += _dropnote(dropped)
    return "\n".join(out)


# ------------------------------------------------------------------------ behavioral layer


def _render_cases(report: dict, *, findings_cap, detail: bool, diagram: bool) -> str:
    cases = list(report.get("cases") or [])
    dropped: list[str] = []
    out = ["## 100xeval — plugin evals", ""]

    if not cases:
        out += ["**No cases ran.** A selection that matches nothing exits 0, so this check "
                "proves nothing — check the `--tag` or `--case` filter.", ""]
        return "\n".join(out)

    passed, total = report.get("casesPassed", 0), report.get("casesTotal", len(cases))
    mark = "✅" if passed == total else "❌"
    out += [f"{mark} **{passed}/{total} cases passed · overall {report.get('overallScore', 0):.2f} · "
            f"${report.get('costUsd', 0):.4f}** "
            f"(runs ${report.get('runCostUsd', 0):.4f} + judges ${report.get('judgeCostUsd', 0):.4f})",
            ""]

    if diagram:
        out += _mermaid(cases) + [""]
    else:
        dropped.append("the flow diagram")

    for plugin, group in _by_plugin(cases):
        # Failing first, matching the diagram's order. Stable, so cases that share an outcome
        # keep report order; without this the table and the diagram above it list the same
        # group in two different orders, which reads as a bug in one of them.
        group = sorted(group, key=lambda c: c["passed"])
        out += [f"### {plugin}", ""]
        out += ["| Case | Harness / model | Score | Passed | Cost |",
                "| --- | --- | --- | --- | --- |"]
        for c in group:
            m = "✅" if c["passed"] else "❌"
            label = f"{c.get('harness') or '—'}/{c.get('model') or 'default'}"
            out.append(f"| {c['name']} | `{label}` | {c['score']:.2f} | {m} | "
                       f"${c.get('costUsd', 0):.4f} |")
        out.append("")

        if not detail:
            continue
        for c in group:
            failing = [g for g in c.get("graders") or [] if g["passRate"] < 1.0]
            if not failing and not c.get("error"):
                continue
            out += [f"<details><summary><code>{c['name']}</code> — "
                    f"score {c['score']:.2f}</summary>", ""]
            if c.get("error"):
                out += [f"> ⚠️ {_oneline(c['error'])}", ""]
            for g in failing:
                out.append(f"- **{g['name']}** ({g['type']}) — {g['passRate']:.0%}")
                runs = [r for r in g.get("runs") or [] if r.get("detail")]
                shown, hidden = _cap(runs, findings_cap)
                for i, r in enumerate(shown, 1):
                    rm = "✅" if r["passed"] else "❌"
                    out.append(f"    - {rm} run {i}: {_oneline(r['detail'])}")
                if hidden:
                    dropped.append(f"{hidden} run detail line(s) on `{c['name']}`")
                    out.append(f"    - _…{hidden} more run(s) not shown here._")
            out += ["", "</details>", ""]
    if not detail and any(g["passRate"] < 1.0 for c in cases for g in c.get("graders") or []):
        dropped.append("every per-grader run detail")

    out += _dropnote(dropped)
    return "\n".join(out)


def _by_plugin(cases: list) -> list:
    """Cases grouped under the first plugin each declares, in first-seen order.

    A case may exercise more than one plugin; it is listed once, under the first, rather than
    repeated — a case counted twice would make the group totals disagree with the headline.
    Cases declaring no plugin are grouped last under an explicit label instead of vanishing.
    """
    groups: dict[str, list] = {}
    for c in cases:
        names = list(c.get("plugins") or [])
        key = names[0] if names else "_(no plugin declared)_"
        groups.setdefault(key, []).append(c)
    return list(groups.items())


def _mermaid(cases: list) -> list[str]:
    """`flowchart` of plugin → case → grader, each node carrying its outcome.

    Deliberately `flowchart` and not `xychart-beta`: a diagram type the renderer does not
    know renders as an error box inside the comment, which is worse than no diagram, and
    `flowchart` is the long-stable one.

    Nodes are budgeted. Past the budget, failing cases are kept — they are the reason anyone
    is reading — and the passing remainder collapses to a count.
    """
    lines = ["```mermaid", "flowchart LR"]
    budget = MERMAID_NODES
    skipped = 0
    for pi, (plugin, group) in enumerate(_by_plugin(cases)):
        pid = f"P{pi}"
        lines.append(f'  {pid}["{_mlabel(plugin)}"]')
        budget -= 1
        # Failing cases first, so a tight budget spends itself on what broke. `_render_cases`
        # sorts its tables the same way, so the two never disagree.
        for ci, c in enumerate(sorted(group, key=lambda c: c["passed"])):
            cid = f"{pid}C{ci}"
            graders = c.get("graders") or []
            if budget - (1 + len(graders)) < 0:
                skipped += 1
                continue
            m = "✅" if c["passed"] else "❌"
            lines.append(f'  {pid} --> {cid}["{_mlabel(c["name"])} {m} {c["score"]:.2f}"]')
            budget -= 1
            for gi, g in enumerate(graders):
                gm = "✅" if g["passRate"] >= 1.0 else ("⚠️" if g["passRate"] > 0 else "❌")
                lines.append(f'  {cid} --> {cid}G{gi}["{_mlabel(g["name"])} {gm} '
                             f'{g["passRate"]:.0%}"]')
                budget -= 1
    if skipped:
        lines.append(f'  MORE["…{skipped} more case(s) not drawn"]')
    lines.append("```")
    return lines


def _mlabel(text: str) -> str:
    """Make a string safe inside a quoted mermaid node label.

    Mermaid ends a quoted label at the first `"`, and treats unbalanced brackets as syntax,
    so an unsanitized case name breaks the whole diagram rather than one node. Truncated
    because a long label stretches the chart past the comment's width.
    """
    s = str(text).replace('"', "'").replace("[", "(").replace("]", ")")
    s = " ".join(s.split())                     # newlines would end the statement
    return s[:40] + "…" if len(s) > 40 else s


# --------------------------------------------------------------------------------- helpers


def _cap(items: list, cap):
    """(shown, hidden_count). `cap=None` shows everything, `0` shows nothing."""
    if cap is None:
        return list(items), 0
    return list(items[:cap]), max(0, len(items) - cap)


def _oneline(text: str) -> str:
    """Collapse to one line: a newline inside a table cell or list item breaks the markdown."""
    return " ".join(str(text).split())
