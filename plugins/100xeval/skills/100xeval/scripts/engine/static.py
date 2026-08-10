"""Static design-quality layer.

Deterministic, free, no model run. `lint.py` walks a plugin and emits `[P2]`/`[S2]`/…
tagged findings; this module maps those IDs onto 0–1 sub-scores and folds them into a
single `design_score`, plus a token-efficiency metric computed here.

The scorer is a pure function (`score_from_findings`) tested on synthetic findings;
`analyze()` wires it to the live linter. That split is deliberate: scoring policy is
what you will want to retune, and retuning it should not require building a plugin
fixture on disk.

Swapping in your own checks: anything exposing `lint_plugin(dir, root) -> [obj.msg]`
can replace `lint.py` — `analyze()` only reads `.msg` off each finding, and only the
bracketed ID inside it carries meaning here.
"""

from __future__ import annotations

import os
import re

from . import lint

# Each conformance-check ID → the sub-check it feeds. IDs the linter never emits are
# simply absent; a sub-check with nothing mapped to it would sit at 1.0 forever and
# quietly dilute the score, so every entry below is reachable.
_ID_TO_SUBCHECK = {
    "P2": "frontmatter_quality", "S13": "frontmatter_quality",
    "S2": "progressive_disclosure", "S5": "progressive_disclosure",
    "S4": "reference_hygiene", "S11": "reference_hygiene",
    "P4": "structural_completeness", "S7": "structural_completeness",
    "P3": "ecosystem_coherence",
    "X1": "security", "X3": "security", "X4": "security",
}

# Sub-check weights for the weighted mean. Security counts double — a leaked
# credential is not the same kind of problem as a long SKILL.md. token_efficiency is
# a proxy metric rather than a conformance finding, so it counts half.
_WEIGHTS = {
    "frontmatter_quality": 1.0,
    "progressive_disclosure": 1.0,
    "reference_hygiene": 1.0,
    "structural_completeness": 1.0,
    "token_efficiency": 0.5,
    "ecosystem_coherence": 1.0,
    "security": 2.0,
}

_ID_RE = re.compile(r"\[([PSX]\d+)\]")


def score_from_findings(finding_msgs: list[str], token_efficiency: float) -> dict:
    """Pure: map linter finding messages → sub-scores → design_score.

    finding_msgs: the `.msg` text of each finding for one plugin (each may carry a
    `[P2]`-style tag). token_efficiency: a 0–1 metric computed by the caller.
    """
    counts: dict[str, int] = {k: 0 for k in _WEIGHTS}
    flags = 0
    for msg in finding_msgs:
        for cid in _ID_RE.findall(msg):
            sub = _ID_TO_SUBCHECK.get(cid)
            if sub:
                counts[sub] += 1
                flags += 1

    sub_scores: dict[str, float] = {}
    for sub in _WEIGHTS:
        if sub == "token_efficiency":
            sub_scores[sub] = round(max(0.0, min(1.0, token_efficiency)), 3)
        else:
            # Each finding in a category costs 0.25, floored at 0.
            sub_scores[sub] = round(max(0.0, 1.0 - 0.25 * counts[sub]), 3)

    weighted = sum(_WEIGHTS[s] * sub_scores[s] for s in _WEIGHTS)
    base = weighted / sum(_WEIGHTS.values())
    penalty = max(0.5, 1.0 - 0.05 * flags)  # broad-but-shallow problems still cost
    design_score = round(base * penalty, 3)
    return {"design_score": design_score, "sub_scores": sub_scores, "flags": flags}


def token_efficiency(plugin_dir: str) -> float:
    """Cheap proxy: penalize duplicate non-blank lines across SKILL.md files.

    Copy-pasted blocks across skills are the most common way a plugin quietly doubles
    what it loads into context. This does not measure tokens; it measures the habit
    that wastes them.
    """
    total = 0
    dupes = 0
    for dirpath, _dirs, files in os.walk(plugin_dir):
        for fn in files:
            if fn != "SKILL.md":
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8") as fh:
                    lines = [ln.strip() for ln in fh if ln.strip()]
            except OSError:
                continue
            seen: set[str] = set()
            for ln in lines:
                if len(ln) < 20:  # ignore short/structural lines
                    continue
                total += 1
                if ln in seen:
                    dupes += 1
                seen.add(ln)
    if total == 0:
        return 1.0
    return max(0.0, 1.0 - dupes / total)


def analyze(plugin_dir: str) -> dict:
    """Lint one plugin and compute its design score."""
    plugin_dir = os.path.abspath(plugin_dir)
    root = lint.find_repo_root(plugin_dir)
    findings = lint.lint_plugin(plugin_dir, root)
    result = score_from_findings([f.msg for f in findings], token_efficiency(plugin_dir))
    result["path"] = os.path.relpath(plugin_dir, root)
    result["findings"] = [f"{f.where}: {f.msg}" for f in findings]
    return result


def run(root: str, targets: list[str] | None = None) -> dict:
    """Analyze the given plugin paths, or discover every plugin under the repo."""
    if not targets:
        targets = lint.discover_plugins(lint.find_repo_root(os.path.abspath(root)))
    plugins = []
    ok = True
    for t in targets:
        try:
            plugins.append(analyze(t))
        except Exception as exc:  # a broken plugin shouldn't crash the whole static run
            plugins.append({"path": t, "design_score": 0.0, "sub_scores": {}, "error": str(exc)})
            ok = False
    return {"plugins": plugins, "ok": ok}
