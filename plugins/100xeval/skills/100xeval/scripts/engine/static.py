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
    # Scored on DISTINCT check IDs, not occurrences. One design flaw repeated across 30
    # skills is one flaw; counting it 30 times made the score a proxy for plugin size — a
    # 30-skill plugin floored at 0.16 while a 31-skill one with a lower defect rate scored
    # far higher. The findings list still reports every occurrence.
    seen: dict[str, set[str]] = {k: set() for k in _WEIGHTS}
    occurrences = 0
    for msg in finding_msgs:
        m = _ID_RE.match(msg)
        if m is None:
            continue          # untagged note — informational, scores nothing
        prefix = m.group(1)
        if prefix not in _PREFIX_TO_SUBCHECK:
            raise UnknownCheckPrefix(
                f"check-ID prefix {prefix!r} has no sub-score in _PREFIX_TO_SUBCHECK "
                f"(known: {', '.join(sorted(_PREFIX_TO_SUBCHECK))}) — from finding: {msg!r}")
        seen[_PREFIX_TO_SUBCHECK[prefix]].add(msg[1:msg.index("]")])
        occurrences += 1
    distinct = sum(len(v) for v in seen.values())

    sub_scores: dict[str, float] = {}
    for sub in _WEIGHTS:
        if sub == "token_efficiency":
            sub_scores[sub] = round(max(0.0, min(1.0, token_efficiency)), 3)
        else:
            # Each distinct check that fired in a category costs 0.25, floored at 0.
            sub_scores[sub] = round(max(0.0, 1.0 - 0.25 * len(seen[sub])), 3)

    weighted = sum(_WEIGHTS[s] * sub_scores[s] for s in _WEIGHTS)
    base = weighted / sum(_WEIGHTS.values())
    penalty = max(0.5, 1.0 - 0.05 * distinct)  # breadth of problems, not their volume
    design_score = round(base * penalty, 3)
    return {"design_score": design_score, "sub_scores": sub_scores,
            "flags": distinct, "occurrences": occurrences}


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


class TargetError(ValueError):
    """`--target` is not a plugin, or discovery found none. A usage error, not a low score."""


def _require_plugin(path: str) -> None:
    """Refuse to 'score' something that is not a plugin.

    Without this, a typo'd --target scored 0.92: `lint_plugin` on a non-existent directory
    finds no README and no skills/, emits exactly one ST1, and returns a respectable number.
    A gate that reports a passing score for a path that isn't there is worse than no gate,
    because nothing about the output says it evaluated nothing.
    """
    if not os.path.isdir(path):
        raise TargetError(f"--target {path!r} is not a directory")
    if not os.path.isfile(os.path.join(path, ".claude-plugin", "plugin.json")):
        raise TargetError(
            f"--target {path!r} is not a plugin — no .claude-plugin/plugin.json inside it")


def analyze(plugin_dir: str) -> dict:
    """Lint one plugin and compute its design score."""
    plugin_dir = os.path.abspath(plugin_dir)
    root = lint.find_repo_root(plugin_dir)
    findings = lint.lint_plugin(plugin_dir, root)
    result = score_from_findings([f.msg for f in findings], token_efficiency(plugin_dir))
    # `relpath` is "." whenever the plugin IS the detected root — the normal case for a
    # developer with a single plugin and no surrounding repo. "## ." names nothing.
    rel = os.path.relpath(plugin_dir, root)
    result["path"] = os.path.basename(plugin_dir) if rel == "." else rel
    result["findings"] = [f"{f.where}: {f.msg}" for f in findings]
    return result


def run(root: str, targets: list[str] | None = None) -> dict:
    """Analyze the given plugin paths, or discover every plugin under the repo.

    Raises TargetError rather than returning an empty, cheerful report: "scored nothing"
    and "scored everything and it passed" must not look the same to a caller.
    """
    if targets:
        for t in targets:
            _require_plugin(t)
    else:
        # `root` is the CASE root (`evals/`), which is the wrong place to look for plugins
        # and often does not exist yet. Fall back to the working directory so that running
        # this inside a project containing plugins just works.
        start = root if os.path.isdir(root) else os.getcwd()
        search_root = lint.find_repo_root(os.path.abspath(start))
        targets = lint.discover_plugins(search_root)
        if not targets:
            raise TargetError(
                f"no plugins found under {search_root} — a plugin is a directory containing "
                f".claude-plugin/plugin.json. Point at one with --target <dir>.")
    plugins = []
    ok = True
    for t in targets:
        try:
            plugins.append(analyze(t))
        except Exception as exc:  # a broken plugin shouldn't crash the whole static run
            plugins.append({"path": t, "design_score": 0.0, "sub_scores": {}, "error": str(exc)})
            ok = False
    return {"plugins": plugins, "ok": ok}
