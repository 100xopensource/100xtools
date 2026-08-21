#!/usr/bin/env python3
"""validate_plugins.py — install-time correctness for the plugins in this repo.

Two linters run over a plugin here, and they own different questions:

    this script          will the plugin LOAD? manifest, layout, marketplace entry,
                         agent frontmatter, hooks/MCP config — pass/fail
    100xeval's lint.py   is the plugin any GOOD? skill design, progressive disclosure,
                         reference hygiene, security smells — scored 0..1

Neither repeats the other. A skill folder with no SKILL.md is invisible to the design
linter, which walks SKILL.md files; a vague skill description is invisible here. Run
both — `.claude/skills/lint-plugin` drives them together.

Grounded in https://code.claude.com/docs/en/plugins-reference and /hooks.

Stdlib only, like everything else in this repo.

Usage:
    python3 scripts/validate_plugins.py                    # every plugin + the marketplace
    python3 scripts/validate_plugins.py plugins/100xeval   # one plugin, no marketplace checks
    python3 scripts/validate_plugins.py --strict           # warnings fail too
    python3 scripts/validate_plugins.py --format json      # machine-readable

Exit codes: 0 clean, 1 findings that fail, 2 the script could not run.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from dataclasses import dataclass, field

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+].+)?$")

MANIFEST_KEYS = {
    "$schema", "name", "displayName", "version", "description", "author",
    "homepage", "repository", "license", "keywords", "metadata", "defaultEnabled",
    "skills", "commands", "agents", "workflows", "hooks", "mcpServers",
    "outputStyles", "lspServers", "experimental", "userConfig", "channels",
    "dependencies",
}
# Manifest fields holding ./-relative paths we can existence-check. `hooks` and
# `mcpServers` also accept an inline object, so non-string values are skipped.
PATH_FIELDS = ("skills", "commands", "agents", "workflows", "hooks", "mcpServers",
               "outputStyles", "lspServers")

# Component directories the docs place at the plugin root. Inside .claude-plugin/ they
# are simply not found, and the plugin installs looking empty.
ROOT_ONLY_DIRS = {"skills", "commands", "agents", "workflows", "hooks",
                  "output-styles", "themes", "monitors", "bin", "scripts"}

HOOK_EVENTS = {
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion", "PreToolUse",
    "PermissionRequest", "PermissionDenied", "PostToolUse", "PostToolUseFailure",
    "PostToolBatch", "Notification", "MessageDisplay", "SubagentStart", "SubagentStop",
    "TaskCreated", "TaskCompleted", "Stop", "StopFailure", "TeammateIdle",
    "InstructionsLoaded", "ConfigChange", "CwdChanged", "DirectoryAdded", "FileChanged",
    "WorktreeCreate", "WorktreeRemove", "PreCompact", "PostCompact", "Elicitation",
    "ElicitationResult", "SessionEnd",
}
HOOK_TYPES = {"command", "http", "mcp_tool", "prompt", "agent"}

AGENT_KEYS = {
    "name", "description", "model", "effort", "maxTurns", "tools", "disallowedTools",
    "skills", "memory", "background", "isolation",
}
# Plugin agents may not grant themselves hooks, servers, or a permission mode: the
# plugin author is not the person whose machine it runs on.
AGENT_FORBIDDEN = {"hooks", "mcpServers", "permissionMode"}

# `description` and `when_to_use` are concatenated in the skill listing and truncated at
# this length. Over the cap, the tail silently never reaches the model — and the tail is
# usually the "do NOT use this for…" half that stops the skill firing on the wrong turn.
LISTING_MAX = 1536


@dataclass
class Finding:
    level: str   # "error" | "warn"
    where: str
    msg: str
    hint: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def err(self, where, msg, hint=""):
        self.findings.append(Finding("error", where, msg, hint))

    def warn(self, where, msg, hint=""):
        self.findings.append(Finding("warn", where, msg, hint))

    @property
    def errors(self):
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == "warn"]


def parse_frontmatter(path: str) -> tuple[dict, str | None]:
    """Top-level keys of a leading `---` fenced block, or (·, error). Folds block
    scalars (`>`, `|`, and their strip/keep variants), which is how a long description
    is usually written. Presence-and-format lint needs no more YAML than this."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        return {}, f"cannot read: {e}"
    if not text.startswith("---"):
        return {}, "no frontmatter — the file must start with '---'"
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, "frontmatter is never closed with '---'"

    fm: dict[str, str] = {}
    body, i = lines[1:end], 0
    while i < len(body):
        ln = body[i]
        if not ln.strip() or ln.lstrip().startswith("#") or ln[0] in " \t":
            i += 1
            continue
        m = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s?(.*)$", ln)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in (">", ">-", ">+", "|", "|-", "|+"):
            joiner = " " if val[0] == ">" else "\n"
            chunk, i = [], i + 1
            while i < len(body) and (not body[i].strip() or body[i][0] in " \t"):
                chunk.append(body[i].strip())
                i += 1
            val = joiner.join(c for c in chunk if c)
        else:
            i += 1
        fm[key] = val.strip().strip("\"'")
    return fm, None


def load_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _rel(path: str, start: str | None = None) -> str:
    """Repo-relative when that is shorter to read, absolute when it would escape upward."""
    rel = os.path.relpath(path, start) if start else os.path.relpath(path)
    return path if rel.startswith("..") else rel


def _near(key: str, known: set[str]) -> str:
    close = difflib.get_close_matches(key, known, n=1)
    return f"did you mean {close[0]!r}?" if close else "ignored at load time"


def validate_manifest(plugin_dir: str, rep: Report) -> dict:
    path = os.path.join(plugin_dir, ".claude-plugin", "plugin.json")
    rel = _rel(path)
    if not os.path.isfile(path):
        rep.err(_rel(plugin_dir), "no .claude-plugin/plugin.json")
        return {}
    try:
        manifest = load_json(path)
    except json.JSONDecodeError as e:
        rep.err(rel, f"invalid JSON: {e}")
        return {}

    name = manifest.get("name")
    if not name:
        rep.err(rel, "'name' is required")
    elif not KEBAB.match(str(name)):
        rep.err(rel, f"'name' must be kebab-case (got {name!r})",
                "the name becomes the command namespace, /<plugin>:<skill>")

    if "version" in manifest and not SEMVER.match(str(manifest["version"])):
        rep.warn(rel, f"'version' {manifest['version']!r} is not semver")
    if "keywords" in manifest and not isinstance(manifest["keywords"], list):
        rep.err(rel, "'keywords' must be an array")
    if "author" in manifest and not isinstance(manifest["author"], (dict, str)):
        rep.warn(rel, "'author' should be an object with name/email/url")

    for key in manifest:
        if key not in MANIFEST_KEYS:
            rep.warn(rel, f"unrecognized manifest field {key!r}", _near(key, MANIFEST_KEYS))

    for fname in PATH_FIELDS:
        val = manifest.get(fname)
        entries = val if isinstance(val, list) else [val]
        for c in entries:
            if not isinstance(c, str):
                continue
            if not c.startswith("./"):
                rep.err(rel, f"{fname} path {c!r} must start with './'")
            if not os.path.exists(os.path.normpath(os.path.join(plugin_dir, c))):
                rep.err(rel, f"{fname} path {c!r} does not exist")
    return manifest


def check_layout(plugin_dir: str, rep: Report):
    cp = os.path.join(plugin_dir, ".claude-plugin")
    if not os.path.isdir(cp):
        return
    for entry in sorted(os.listdir(cp)):
        if entry in ROOT_ONLY_DIRS and os.path.isdir(os.path.join(cp, entry)):
            rep.err(_rel(os.path.join(cp, entry)),
                    f"'{entry}/' belongs at the plugin root, not inside .claude-plugin/",
                    "only plugin.json lives in .claude-plugin/; components here are never found")


def validate_skills(plugin_dir: str, rep: Report):
    sdir = os.path.join(plugin_dir, "skills")
    if not os.path.isdir(sdir):
        return
    for name in sorted(os.listdir(sdir)):
        sub = os.path.join(sdir, name)
        if not os.path.isdir(sub):
            continue
        skill_md = os.path.join(sub, "SKILL.md")
        if not os.path.isfile(skill_md):
            rep.err(_rel(sub), "skill folder has no SKILL.md",
                    "the folder ships and loads nothing; add SKILL.md or delete it")
            continue
        rel = _rel(skill_md)
        fm, err = parse_frontmatter(skill_md)
        if err:
            continue  # the design linter reports frontmatter shape (FM7)
        listing = len(fm.get("description", "")) + len(fm.get("when_to_use", ""))
        if listing > LISTING_MAX:
            rep.warn(rel, f"description + when_to_use is {listing} chars, over the "
                          f"{LISTING_MAX}-char listing cap",
                     "the tail is truncated out of the listing — put the trigger and the "
                     "'not for' clause first, move the rest into the body")
        fm_name = fm.get("name")
        if fm_name and not KEBAB.match(fm_name):
            rep.warn(rel, f"skill 'name' {fm_name!r} is not kebab-case",
                     "in a plugin skill the name becomes the command's last segment")


def validate_agents(plugin_dir: str, rep: Report):
    adir = os.path.join(plugin_dir, "agents")
    if not os.path.isdir(adir):
        return
    for fn in sorted(os.listdir(adir)):
        if not fn.endswith(".md"):
            continue
        rel = _rel(os.path.join(adir, fn))
        fm, err = parse_frontmatter(os.path.join(adir, fn))
        if err:
            rep.err(rel, err)
            continue
        for required in ("name", "description"):
            if not fm.get(required):
                rep.err(rel, f"agent frontmatter must set '{required}'")
        for forb in sorted(AGENT_FORBIDDEN):
            if forb in fm:
                rep.err(rel, f"a plugin agent may not set {forb!r}",
                        "the plugin author is not the person whose machine it runs on")
        if "isolation" in fm and fm["isolation"] != "worktree":
            rep.err(rel, f"agent 'isolation' may only be 'worktree' (got {fm['isolation']!r})")
        for key in fm:
            if key not in AGENT_KEYS and key not in AGENT_FORBIDDEN:
                rep.warn(rel, f"unrecognized agent field {key!r}", _near(key, AGENT_KEYS))


def validate_hooks(plugin_dir: str, rep: Report):
    path = os.path.join(plugin_dir, "hooks", "hooks.json")
    if not os.path.isfile(path):
        return
    rel = _rel(path)
    try:
        cfg = load_json(path)
    except json.JSONDecodeError as e:
        rep.err(rel, f"invalid JSON: {e}")
        return
    hooks = cfg.get("hooks")
    if hooks is None:
        rep.warn(rel, "no 'hooks' key — nothing here registers")
        return
    if not isinstance(hooks, dict):
        rep.err(rel, "'hooks' must be an object keyed by event name")
        return
    for event, entries in hooks.items():
        if event not in HOOK_EVENTS:
            rep.warn(rel, f"unknown hook event {event!r}",
                     "event names are case-sensitive; a misspelt one never fires")
        for entry in entries if isinstance(entries, list) else []:
            for h in entry.get("hooks", []) if isinstance(entry, dict) else []:
                if isinstance(h, dict) and h.get("type") not in HOOK_TYPES:
                    rep.warn(rel, f"hook type {h.get('type')!r} is not one of "
                                  f"{sorted(HOOK_TYPES)}")


def validate_mcp(plugin_dir: str, rep: Report):
    path = os.path.join(plugin_dir, ".mcp.json")
    if not os.path.isfile(path):
        return
    rel = _rel(path)
    try:
        cfg = load_json(path)
    except json.JSONDecodeError as e:
        rep.err(rel, f"invalid JSON: {e}")
        return
    if "mcpServers" not in cfg:
        rep.warn(rel, "no 'mcpServers' key — no server is declared")


def validate_marketplace(root: str, rep: Report):
    path = os.path.join(root, ".claude-plugin", "marketplace.json")
    rel = _rel(path, root)
    if not os.path.isfile(path):
        rep.err(rel, "no marketplace.json at the repo root")
        return
    try:
        mkt = load_json(path)
    except json.JSONDecodeError as e:
        rep.err(rel, f"invalid JSON: {e}")
        return
    if not mkt.get("name"):
        rep.err(rel, "marketplace 'name' is required")

    listed, seen = [], set()
    for entry in mkt.get("plugins", []):
        name, src = entry.get("name"), entry.get("source")
        if not name:
            rep.err(rel, "a plugin entry has no 'name'")
            continue
        if name in seen:
            rep.err(rel, f"duplicate plugin name {name!r}")
        seen.add(name)
        if not isinstance(src, str) or not src:
            rep.err(rel, f"plugin {name!r} has no string 'source'")
            continue
        pdir = os.path.normpath(os.path.join(root, src))
        if not os.path.isdir(pdir):
            rep.err(rel, f"plugin {name!r} source {src!r} does not exist")
            continue
        listed.append(pdir)
        pj = os.path.join(pdir, ".claude-plugin", "plugin.json")
        if os.path.isfile(pj):
            try:
                got = load_json(pj).get("name")
            except json.JSONDecodeError:
                continue  # reported against the manifest itself
            if got != name:
                rep.err(rel, f"entry {name!r} but {src}/.claude-plugin/plugin.json "
                             f"says {got!r} — installs resolve by the manifest name")

    registered = {os.path.realpath(d) for d in listed}
    for d in discover_plugins(root):
        if os.path.realpath(d) not in registered:
            rep.err(rel, f"{_rel(d, root)} is not listed in the marketplace",
                    "an unlisted plugin is not installable by anyone")


def discover_plugins(root: str) -> list[str]:
    proot = os.path.join(root, "plugins")
    if not os.path.isdir(proot):
        return []
    return [os.path.join(proot, n) for n in sorted(os.listdir(proot))
            if os.path.isfile(os.path.join(proot, n, ".claude-plugin", "plugin.json"))]


def find_repo_root(start: str) -> str:
    cur = os.path.abspath(start)
    while cur != os.path.dirname(cur):
        if os.path.isfile(os.path.join(cur, ".claude-plugin", "marketplace.json")):
            return cur
        cur = os.path.dirname(cur)
    return os.path.abspath(start)


def validate_plugin(plugin_dir: str, rep: Report):
    validate_manifest(plugin_dir, rep)
    check_layout(plugin_dir, rep)
    validate_skills(plugin_dir, rep)
    validate_agents(plugin_dir, rep)
    validate_hooks(plugin_dir, rep)
    validate_mcp(plugin_dir, rep)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("targets", nargs="*", help="plugin dirs (default: all, plus the marketplace)")
    ap.add_argument("--strict", action="store_true", help="warnings fail as well")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args(argv)

    root = find_repo_root(os.getcwd())
    rep = Report()
    targets = [os.path.normpath(t) for t in args.targets] or discover_plugins(root)
    for t in targets:
        if not os.path.isdir(t):
            print(f"no such directory: {t}", file=sys.stderr)
            return 2
    if not targets:
        print(f"no plugins found under {os.path.join(root, 'plugins')}", file=sys.stderr)
        return 2

    for t in targets:
        validate_plugin(t, rep)
    if not args.targets:
        validate_marketplace(root, rep)

    failed = bool(rep.errors) or (args.strict and bool(rep.warnings))
    if args.format == "json":
        print(json.dumps({
            "targets": targets,
            "errors": [vars(f) for f in rep.errors],
            "warnings": [vars(f) for f in rep.warnings],
            "ok": not failed,
        }, indent=2))
        return 1 if failed else 0

    for f in rep.errors + rep.warnings:
        tag = "ERROR" if f.level == "error" else "warn "
        print(f"{tag}  {f.where}: {f.msg}")
        if f.hint:
            print(f"        → {f.hint}")
    n = len(targets)
    plural = "" if n == 1 else "s"
    if failed:
        print(f"\nFAIL — {len(rep.errors)} error(s), {len(rep.warnings)} warning(s) "
              f"across {n} plugin{plural}")
        return 1
    print(f"ok  {n} plugin{plural} valid"
          + (f" ({len(rep.warnings)} warning(s))" if rep.warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
