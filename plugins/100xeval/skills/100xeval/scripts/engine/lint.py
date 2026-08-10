"""Plugin conformance linter — the deterministic half of the static layer.

Walks a Claude Code plugin directory and emits tagged findings about its *design*:
frontmatter shape, progressive disclosure, reference hygiene, and a few security
smells. No model, no network, no third-party packages — pure stdlib, so it runs
free on every commit.

Each finding carries a bracketed check ID (`[P2]`, `[S5]`, `[X1]`, …). `static.py`
maps those IDs onto sub-scores; nothing else depends on the wording, so messages are
free to improve.

The checks encode *published* Claude Code skill guidance (code.claude.com/docs/en/skills)
plus the generic hygiene any plugin wants. They are intentionally conservative: a
finding should mean "this is probably wrong", not "this differs from how we write
skills". Add house-style rules in your own fork rather than here.

Check IDs
---------
P2  frontmatter shape — name/description validity, unknown keys
P3  ecosystem coherence — references a companion skill that does not exist
P4  plugin has no README.md
S2  progressive disclosure — SKILL.md body over the 500-line cap
S4  ships references/ but never tells the model to read them
S5  dangling or empty references/
S7  a "self-check" section that is not a real checklist
S11 reference files that point at further reference files
S13 description not in third person; Windows-style paths
X1  possible secret committed in plugin content
X3  network destination outside the allowed set
X4  path traversal ('../') escaping the component directory
"""

from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass

# Official SKILL.md frontmatter fields, plus the metadata-ish keys Anthropic's own
# skills repo uses. Anything else is a likely typo.
SKILL_FM_KNOWN = {
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools",
    "disallowed-tools", "model", "effort", "context", "agent", "hooks",
    "paths", "shell", "license", "version", "metadata",
}

VAGUE_SKILL_NAMES = {"helper", "helpers", "util", "utils", "tools", "misc"}
RESERVED_NAME_WORDS = ("anthropic", "claude")
SKILL_NAME_MAX = 64
SKILL_BODY_MAX_LINES = 500

SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("secret-key literal", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("hardcoded credential", re.compile(
        r"(?i)\b(api[_-]?key|auth[_-]?token|secret|password)\b\s*[:=]\s*"
        r"['\"][A-Za-z0-9+/_-]{16,}['\"]")),
]

# X3 flags URLs outside this set. Docs/vendor hosts a plugin legitimately links to.
# Point `EVAL_LINT_ALLOWED_DOMAINS` (comma-separated) at your own list to extend it —
# an unknown host is a notice, not a failure, so a false positive costs little.
URL_ALLOWED_DOMAINS = {
    "code.claude.com", "docs.claude.com", "platform.claude.com", "claude.com",
    "claude.ai", "anthropic.com", "github.com", "example.com", "localhost",
}

_TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".sh", ".js"}

# X3/X4 read a file as *instructions to the model*, so they only apply to skill prose.
# Bundled source legitimately handles relative paths and names hosts in test fixtures;
# flagging that produced findings on every plugin that ships a script, which is exactly
# the kind of noise that trains people to ignore the security sub-score. X1 (secrets)
# still runs over every text file — a committed credential is a problem anywhere.
_PROSE_SUFFIXES = {".md", ".txt"}

# X4 fires on a read INSTRUCTION that escapes the skill directory ("Load ../../config"),
# not on every `../` in the file. Relative paths are ordinary in config examples — a case
# file's `plugins: ["../../plugins/x"]` is data the skill never opens — and flagging those
# buried the one pattern worth seeing.
_TRAVERSAL_RE = re.compile(
    r"(?i)\b(read|load|open|import|include|source|cat|fetch|access)\b[^\n]{0,40}\.\./")


@dataclass
class Finding:
    """One conformance observation. `msg` carries the `[ID]` tag static.py reads."""

    where: str
    msg: str
    level: str = "notice"   # notice | warn


# --- small parsing helpers ----------------------------------------------------

def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def parse_frontmatter(path: str) -> tuple[dict, str | None]:
    """Return (frontmatter dict, error). Flat `key: value` YAML only — that is all
    SKILL.md frontmatter is allowed to be, so a real YAML parser buys nothing."""
    text = _read_text(path)
    if not text.startswith("---"):
        return {}, "no frontmatter block"
    lines = text.splitlines()
    end = next((i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---"), None)
    if end is None:
        return {}, "frontmatter block is not closed"
    fm: dict[str, str] = {}
    key = None
    for ln in lines[1:end]:
        if not ln.strip():
            continue
        m = re.match(r"^([A-Za-z_][\w.-]*):\s*(.*)$", ln)
        if m:
            key = m.group(1)
            fm[key] = m.group(2).strip().strip("'\"")
        elif key:  # folded/continued value
            fm[key] = (fm[key] + " " + ln.strip()).strip()
    return fm, None


def skill_body(path: str) -> str:
    """Content after the closing `---` of the frontmatter."""
    text = _read_text(path)
    if not text.startswith("---"):
        return text
    lines = text.splitlines()
    end = next((i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---"), None)
    return "\n".join(lines[end + 1:]) if end is not None else text


def _section(body: str, titles: tuple[str, ...]) -> str:
    """Body of the first heading whose text contains one of `titles` (lowercased)."""
    out: list[str] = []
    capturing = False
    for ln in body.splitlines():
        if ln.startswith("#"):
            head = ln.lstrip("#").strip().lower()
            if capturing:
                break
            capturing = any(t in head for t in titles)
            continue
        if capturing:
            out.append(ln)
    return "\n".join(out)


def _skill_names(plugin_dir: str) -> set[str]:
    """Every skill in this plugin, by directory name and by frontmatter name."""
    names: set[str] = set()
    sdir = os.path.join(plugin_dir, "skills")
    if not os.path.isdir(sdir):
        return names
    for n in os.listdir(sdir):
        if not os.path.isdir(os.path.join(sdir, n)):
            continue
        names.add(n.lower())
        fm, _ = parse_frontmatter(os.path.join(sdir, n, "SKILL.md"))
        if fm.get("name"):
            names.add(fm["name"].lower())
    return names


def _allowed_domains() -> set[str]:
    extra = os.environ.get("EVAL_LINT_ALLOWED_DOMAINS", "")
    return URL_ALLOWED_DOMAINS | {d.strip().lower() for d in extra.split(",") if d.strip()}


# --- the checks ---------------------------------------------------------------

def _scan_text_file(path: str, rel: str, out: list[Finding], allowed: set[str]) -> None:
    """X1 over any text file; X3/X4 over skill prose only (see _PROSE_SUFFIXES)."""
    content = _read_text(path)
    for label, pat in SECRET_PATTERNS:
        if pat.search(content):
            out.append(Finding(rel, f"[X1] possible {label} committed in plugin content", "warn"))
            break
    if os.path.splitext(path)[1] not in _PROSE_SUFFIXES:
        return
    domains = {d.lower() for d in re.findall(r"https?://([\w.-]+)", content)}
    odd = {d for d in domains
           if not any(d == a or d.endswith("." + a) for a in allowed)}
    if odd:
        out.append(Finding(
            rel, f"[X3] network destination(s) outside the allowed set: "
                 f"{', '.join(sorted(odd)[:4])}"))
    for line in content.splitlines():
        if _TRAVERSAL_RE.search(line) and "CLAUDE_PLUGIN_ROOT" not in line \
                and "CLAUDE_SKILL_DIR" not in line:
            out.append(Finding(rel, "[X4] instructs reading a path ('../') outside the skill directory"))
            break


def _check_frontmatter(rel: str, dirname: str, fm: dict, out: list[Finding]) -> None:
    name = fm.get("name", "")
    desc = fm.get("description", "")
    if name and name != dirname:
        out.append(Finding(rel, f"[P2] frontmatter name {name!r} != directory name {dirname!r}"))
    if len(name) > SKILL_NAME_MAX:
        out.append(Finding(rel, f"[P2] skill name is {len(name)} chars (limit {SKILL_NAME_MAX})"))
    if any(w in name.lower() for w in RESERVED_NAME_WORDS):
        out.append(Finding(rel, f"[P2] skill name {name!r} contains a reserved word"))
    if name.lower() in VAGUE_SKILL_NAMES:
        out.append(Finding(rel, f"[P2] skill name {name!r} is too vague to trigger reliably"))
    if not desc:
        out.append(Finding(rel, "[P2] skill has no description — the model cannot decide when to load it"))
    for key in fm:
        if key not in SKILL_FM_KNOWN:
            close = difflib.get_close_matches(key, SKILL_FM_KNOWN, n=1)
            hint = f" (did you mean {close[0]!r}?)" if close else ""
            out.append(Finding(rel, f"[P2] unrecognized frontmatter key {key!r}{hint}"))
    # XML-ish tags load fine in Claude Code but the Skills API upload validation
    # rejects them — a portability nit, not a correctness bug.
    if re.search(r"<[A-Za-z][^>\n]*>", desc):
        out.append(Finding(
            rel, "[P2] description contains XML-like tags; fine in Claude Code, rejected "
                 "by Skills API upload — use [brackets] or backticks for portability"))
    if re.search(r"\b(I can|I'll|I will|You can use)\b", desc):
        out.append(Finding(rel, "[S13] description not in third person (harms skill discovery)"))


def _check_skill(sub: str, dirname: str, skill_names: set[str], root: str,
                 out: list[Finding], allowed: set[str]) -> None:
    skill_md = os.path.join(sub, "SKILL.md")
    rel = os.path.relpath(skill_md, root)
    body = skill_body(skill_md)
    refdir = os.path.join(sub, "references")

    for dirpath, _dirs, files in os.walk(sub):
        for fn in files:
            fp = os.path.join(dirpath, fn)
            if os.path.splitext(fn)[1] in _TEXT_SUFFIXES and not os.path.islink(fp):
                _scan_text_file(fp, os.path.relpath(fp, root), out, allowed)

    fm, err = parse_frontmatter(skill_md)
    if err:
        out.append(Finding(rel, f"[P2] {err}"))
        return
    _check_frontmatter(rel, dirname, fm, out)

    if re.search(r"(?:references|scripts)\\", body):
        out.append(Finding(rel, "[S13] Windows-style path (backslash) in skill content"))

    # S2 — compactness, measured on the BODY so frontmatter length doesn't count.
    n_lines = body.count("\n") + 1
    if n_lines > SKILL_BODY_MAX_LINES:
        out.append(Finding(
            rel, f"[S2] SKILL.md body is {n_lines} lines — over the {SKILL_BODY_MAX_LINES}-line "
                 f"cap; move detail into references/"))

    # S5 — dangling / empty references.
    referenced = set(re.findall(r"references/([A-Za-z0-9_.-]+\.[a-z]{2,4})", body))
    for rf in sorted(referenced):
        if not os.path.isfile(os.path.join(refdir, rf)):
            out.append(Finding(rel, f"[S5] references/{rf} is mentioned but the file is missing"))
    if os.path.isdir(refdir) and not os.listdir(refdir):
        out.append(Finding(rel, "[S5] references/ directory exists but is empty"))

    # S4 — shipping references nobody is told to open is dead weight in the bundle.
    gate2 = re.search(
        r"(?i)\b(read|load|open|consult|review)\b[^\n]{0,120}\breference"
        r"|\breferences?\b[^\n]{0,120}\b(read|load)\b", body)
    if os.path.isdir(refdir) and os.listdir(refdir) and not gate2:
        out.append(Finding(rel, "[S4] ships references/ but never instructs the model to read them"))

    # S11 — references must stay one level deep, or loading one pulls a chain.
    if os.path.isdir(refdir):
        for rf in sorted(os.listdir(refdir)):
            rp = os.path.join(refdir, rf)
            if os.path.isfile(rp) and "references/" in _read_text(rp):
                out.append(Finding(
                    os.path.relpath(rp, root),
                    "[S11] reference file points at further reference files "
                    "(keep references one level deep)"))

    # S7 — a self-check section that isn't a real checklist teaches nothing.
    selfcheck = _section(body, ("self-check", "self check"))
    if selfcheck:
        items = re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S", selfcheck, re.M)
        if len(items) < 5:
            out.append(Finding(rel, f"[S7] self-check has only {len(items)} item(s) (expect >= 5)"))

    # P3 — a companion skill that doesn't exist is a routing dead end.
    comp = _section(body, ("companion skill",))
    cand = {m.lower() for m in re.findall(r"[`*]{1,2}([a-z0-9][a-z0-9-]+)[`*]{1,2}", comp)
            if "-" in m}
    for c in sorted(cand - skill_names):
        out.append(Finding(
            rel, f"[P3] references companion skill {c!r} which does not exist in this plugin"))


def lint_plugin(plugin_dir: str, root: str | None = None) -> list[Finding]:
    """Every conformance finding for one plugin directory."""
    root = root or plugin_dir
    out: list[Finding] = []
    allowed = _allowed_domains()
    prel = os.path.relpath(plugin_dir, root)

    if not os.path.isfile(os.path.join(plugin_dir, "README.md")):
        out.append(Finding(prel, "[P4] plugin has no README.md at its root"))

    sdir = os.path.join(plugin_dir, "skills")
    if not os.path.isdir(sdir):
        return out
    skill_names = _skill_names(plugin_dir)
    for name in sorted(os.listdir(sdir)):
        sub = os.path.join(sdir, name)
        if not os.path.isdir(sub) or not os.path.isfile(os.path.join(sub, "SKILL.md")):
            continue
        _check_skill(sub, name, skill_names, root, out, allowed)
    return out


# --- discovery ----------------------------------------------------------------

def find_repo_root(start: str) -> str:
    """Nearest ancestor holding `.claude-plugin/marketplace.json`, `plugins/`, or `.git`."""
    cur = os.path.abspath(start)
    while True:
        for marker in (os.path.join(".claude-plugin", "marketplace.json"), "plugins", ".git"):
            if os.path.exists(os.path.join(cur, marker)):
                return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start)
        cur = parent


def discover_plugins(root: str) -> list[str]:
    """Every plugin under `root` — a directory holding `.claude-plugin/plugin.json`."""
    found = []
    for dirpath, dirnames, _files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "node_modules", ".git")]
        if os.path.isfile(os.path.join(dirpath, ".claude-plugin", "plugin.json")):
            found.append(dirpath)
            dirnames[:] = []  # a plugin does not nest inside another plugin
    return sorted(found)
