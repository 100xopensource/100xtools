"""Discover, parse, and validate `case.yaml` files into Case objects.

Discovery walks `evals/**/case.yaml`. Selection filters by `--tag` (every named tag
must be present) and `--case` (fnmatch on `name`). A malformed case reports its file
and reason and is dropped; the others still load.
"""

from __future__ import annotations

import fnmatch
import os

from . import yamlmin
from .models import Case, Grader


class CaseError(ValueError):
    """A case that cannot be loaded; message names the file + reason."""


# Fields that live under `execution:` in the design format but flatten onto Case.
_EXECUTION_FIELDS = {
    "prompt", "model", "entrypoint", "max_turns", "allowed_tools",
    "append_system_prompt", "harness", "mcp_config", "timeout_s",
}

# Retired plural forms from the old matrix model (one case ran N harnesses × N models).
# A case is now one harness + one model, so silently honouring the first entry of a list
# would change what gets executed without saying so — name them instead.
_RETIRED_FIELDS = {
    "harnesses": "harness",
    "models": "model",
}

# `harness` names a RUNTIME, never a surface — the surface is `entrypoint`. Surfaces
# named here are rejected with the correct spelling rather than silently running
# something else, because the two are easy to confuse and the failure is invisible.
_RENAMED_HARNESSES = {
    "cowork": "`harness: cowork` names a surface, not a runtime. Cowork runs ON the Claude "
              "Code engine, so use `harness: claude_code` with `entrypoint: cowork` and "
              "supply that surface's system prompt (see engine/entrypoints/README.md).",
    "claude_chat": "`harness: claude_chat` names a surface, not a runtime. Use "
                   "`harness: claude_code` with `entrypoint: chat`.",
}


def discover(root: str) -> list[str]:
    """Every `case.yaml` path under `root`, sorted for stable ordering."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip engine internals and run outputs.
        dirnames[:] = [d for d in dirnames if d not in ("100xeval-plugin", "results", "artifacts", "__pycache__")]
        if "case.yaml" in filenames:
            found.append(os.path.join(dirpath, "case.yaml"))
    return sorted(found)


def load_case(path: str) -> Case:
    """Parse one `case.yaml` into a validated Case, or raise CaseError."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = yamlmin.load(fh.read())
    except (OSError, yamlmin.YamlError) as exc:
        raise CaseError(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CaseError(f"{path}: top level must be a mapping")

    case_dir = os.path.dirname(path)
    execution = data.get("execution") or {}
    if not isinstance(execution, dict):
        raise CaseError(f"{path}: `execution` must be a mapping")

    def pick(key, default):
        # execution.* wins over top-level; both accepted for flexibility.
        if key in execution:
            return execution[key]
        return data.get(key, default)

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise CaseError(f"{path}: `name` is required and must be a string")

    prompt = pick("prompt", None)
    if not prompt or not isinstance(prompt, str):
        raise CaseError(f"{path}: `execution.prompt` (or `prompt`) is required")

    graders = _load_graders(path, data.get("graders"))

    for retired, replacement in _RETIRED_FIELDS.items():
        if retired in execution or retired in data:
            raise CaseError(
                f"{path}: `{retired}` is no longer supported — a case runs ONE harness and "
                f"ONE model. Use `execution.{replacement}: <value>` instead."
            )
    harness = pick("harness", None) or "claude_code"
    if not isinstance(harness, str):
        raise CaseError(f"{path}: `harness` must be a string")
    if harness in _RENAMED_HARNESSES:
        raise CaseError(f"{path}: {_RENAMED_HARNESSES[harness]}")

    case = Case(
        name=name,
        prompt=prompt,
        path=case_dir,
        description=data.get("description", "") or "",
        plugins=list(data.get("plugins") or []),
        tags=list(data.get("tags") or []),
        model=pick("model", None),
        harness=harness,
        entrypoint=pick("entrypoint", "none") or "none",
        max_turns=int(pick("max_turns", 15) or 15),
        timeout_s=int(pick("timeout_s", 300) or 300),
        allowed_tools=list(pick("allowed_tools", []) or []),
        append_system_prompt=pick("append_system_prompt", None),
        mcp_config=pick("mcp_config", None),
        runs=int(data.get("runs", 3) or 3),
        skip=str(data.get("skip") or ""),
        graders=graders,
    )
    _validate_plugin_paths(path, case)
    return case


def _load_graders(path: str, raw) -> list[Grader]:
    if not isinstance(raw, list) or len(raw) < 1:
        raise CaseError(f"{path}: at least one grader is required")
    graders: list[Grader] = []
    seen: set[str] = set()
    for i, g in enumerate(raw):
        if not isinstance(g, dict):
            raise CaseError(f"{path}: grader #{i + 1} must be a mapping")
        gtype = g.get("type")
        gname = g.get("name")
        if not gtype:
            raise CaseError(f"{path}: grader #{i + 1} missing `type`")
        if not gname:
            raise CaseError(f"{path}: grader #{i + 1} missing `name`")
        if gname in seen:
            raise CaseError(f"{path}: duplicate grader name {gname!r}")
        seen.add(gname)
        params = {k: v for k, v in g.items() if k not in ("type", "name", "weight")}
        graders.append(Grader(type=gtype, name=gname, weight=float(g.get("weight", 1) or 1), params=params))
    return graders


def _validate_plugin_paths(path: str, case: Case) -> None:
    for rel in case.plugins:
        resolved = os.path.normpath(os.path.join(case.path, rel))
        if not os.path.isdir(resolved):
            raise CaseError(f"{path}: plugin path {rel!r} does not resolve to a directory ({resolved})")


def select(cases: list[Case], tags: list[str] | None, case_glob: str | None,
           include_skipped: bool = False) -> list[Case]:
    """Filter by `--tag` (all present) and `--case` (fnmatch on name).

    A case with a non-empty `skip:` is excluded — it stays in the corpus with its
    reason recorded, rather than being deleted or quietly untagged.
    """
    out = cases
    if not include_skipped:
        out = [c for c in out if not c.skip]
    if tags:
        out = [c for c in out if all(t in c.tags for t in tags)]
    if case_glob:
        out = [c for c in out if fnmatch.fnmatch(c.name, case_glob)]
    return out


def load_all(root: str, tags=None, case_glob=None, include_skipped: bool = False):
    """Return (cases, errors). Errors are (path, message) for malformed cases."""
    cases: list[Case] = []
    errors: list[tuple[str, str]] = []
    for path in discover(root):
        try:
            cases.append(load_case(path))
        except CaseError as exc:
            errors.append((path, str(exc)))
    return select(cases, tags, case_glob, include_skipped), errors
