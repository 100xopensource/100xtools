"""Static design-quality layer.

Deterministic, free, no model run. `lint.py` walks a plugin and emits `[FM3]`/`[PD1]`/…
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

# A check ID's PREFIX names the sub-check it feeds (`FM3` → frontmatter_quality), so the
# mapping is derived rather than hand-maintained. That is deliberate: the old per-ID table
# had to be edited in lockstep with lint.py, and forgetting made the new check silently
# score nothing — a check that looks live, fires, and changes no number.
_PREFIX_TO_SUBCHECK = {
    "FM": "frontmatter_quality",
    "PD": "progressive_disclosure",
    "RH": "reference_hygiene",
    "ST": "structural_completeness",
    "EC": "ecosystem_coherence",
    "SEC": "security",
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

# Anchored to the start: a finding's ID is always its first token. Scanning the whole
# message would also match bracketed text interpolated from the plugin under test (a
# frontmatter key, a domain), and since an unknown prefix now raises, that would turn
# someone else's content into a crash.
_ID_RE = re.compile(r"^\[([A-Z]{2,3})\d+\]")


class UnknownCheckPrefix(KeyError):
    """A finding carried a check-ID prefix with no sub-score behind it."""


def score_from_findings(finding_msgs: list[str], token_efficiency: float) -> dict:
    """Pure: map linter finding messages → sub-scores → design_score.

    finding_msgs: the `.msg` text of each finding for one plugin (each may carry a
    `[FM3]`-style tag). token_efficiency: a 0–1 metric computed by the caller.

    An unrecognized prefix RAISES rather than being skipped. Silently ignoring it is how
    a new check ends up firing while changing no number — the failure mode the derived
    mapping exists to prevent, so it must not be reintroduced here.
    """
    counts: dict[str, int] = {k: 0 for k in _WEIGHTS}
    flags = 0
    for msg in finding_msgs:
        m = _ID_RE.match(msg)
        if m is None:
            continue          # untagged note — informational, scores nothing
        prefix = m.group(1)
        if prefix not in _PREFIX_TO_SUBCHECK:
            raise UnknownCheckPrefix(
                f"check-ID prefix {prefix!r} has no sub-score in _PREFIX_TO_SUBCHECK "
                f"(known: {', '.join(sorted(_PREFIX_TO_SUBCHECK))}) — from finding: {msg!r}")
        counts[_PREFIX_TO_SUBCHECK[prefix]] += 1
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
    """Cheap proxy: penalize duplicate non-blank lines across a plugin's SKILL.md files.

    Copy-pasted blocks BETWEEN sibling skills are the most common way a plugin quietly
    doubles what it loads into context, so `seen` spans the whole plugin rather than
    resetting per file — scoped per file it only ever caught a skill repeating itself,
    which is the rarer and cheaper mistake. Repetition inside one skill still counts.

    This does not measure tokens; it measures the habit that wastes them.

    The score is independent of walk order: for a line in N files, exactly N-1 of its
    occurrences count as duplicates whichever file is visited first.
    """
    total = 0
    dupes = 0
    seen: set[str] = set()
    for dirpath, dirnames, files in os.walk(plugin_dir):
        dirnames.sort()  # stable traversal; the ratio doesn't depend on it, per-file reporting would
        for fn in sorted(files):
            if fn != "SKILL.md":
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8") as fh:
                    lines = [ln.strip() for ln in fh if ln.strip()]
            except OSError:
                continue
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
