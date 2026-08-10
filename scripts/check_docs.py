#!/usr/bin/env python3
"""Validate the docs/ knowledge bundle. Stdlib only; run from the repo root.

Three checks, each catching a way documentation rots:

1. **OKF conformance** — the spec's actual bar: every non-reserved `.md` under `docs/`
   carries parseable YAML frontmatter with a non-empty `type`.
2. **Check-ID sync** — the IDs documented in `docs/100xeval/check-ids.md` must exactly
   match those `engine/lint.py` emits, and each prefix must map to the sub-score
   `engine/static.py` assigns it. A reference page that silently falls behind the code is
   worse than no reference page, because it is believed.
3. **Internal links resolve** — every relative markdown link inside the bundle points at a
   file that exists. OKF tolerates broken links; a bundle we ship should not have them.

Deliberately a repo-level script rather than a plugin unit test: the plugin's suite has to
pass for someone who installed only the plugin, where `docs/` does not exist.

    python3 scripts/check_docs.py        # exit 0 clean, 1 with a report of what is wrong
"""

from __future__ import annotations

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")
ENGINE = os.path.join(REPO, "plugins", "100xeval", "skills", "100xeval", "scripts", "engine")
CHECK_IDS_DOC = os.path.join(DOCS, "100xeval", "check-ids.md")

RESERVED = {"index.md", "log.md"}
OKF_VERSION = "0.2"
ROOT_INDEX = os.path.join(DOCS, "index.md")

# v0.1 fields that v0.2 replaced. Left in place they parse fine and mean nothing, so the
# only thing that catches them is naming them.
REMOVED_FIELDS = {"timestamp": "generated: { by, at }"}

# §7 actor convention for identity fields: <producer>/<version>, human:<id>, process:<id>.
_ACTOR = re.compile(r"^(?:[\w.-]+/[\w.-]+|human:[\w.-]+|process:[\w.-]+)$")

# `  FM1  frontmatter name does not match …` inside lint.py's Check IDs block. One space
# is enough after the ID: the longer `SEC1` entries align with one, and cosmetic alignment
# must not decide whether a check counts as documented.
_LINT_ID = re.compile(r"^\s{2}([A-Z]{2,3}\d+)\s+\S")
# `FM — frontmatter_quality` — the prefix heading in the same block.
_LINT_PREFIX = re.compile(r"^([A-Z]{2,3})\s+—\s+(\w+)\s*$")
# `| `FM1` | fires when … |` in the docs table.
_DOC_ID = re.compile(r"^\|\s*`([A-Z]{2,3}\d+)`\s*\|")
# `## `FM` — frontmatter_quality`
_DOC_PREFIX = re.compile(r"^##\s+`([A-Z]{2,3})`\s+—\s+(\w+)\s*$")
# Markdown links, skipping external URLs and anchors.
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def bundle_docs() -> list[str]:
    out = []
    for dirpath, dirnames, files in os.walk(DOCS):
        dirnames.sort()
        for fn in sorted(files):
            if fn.endswith(".md"):
                out.append(os.path.join(dirpath, fn))
    return out


def _frontmatter(text: str) -> tuple[dict, str | None]:
    """Top-level `key: value` pairs, plus nested one-level mappings as `parent.child`."""
    if not text.startswith("---"):
        return {}, "no YAML frontmatter block"
    lines = text.splitlines()
    end = next((i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---"), None)
    if end is None:
        return {}, "frontmatter block is not closed"
    fm, parent = {}, None
    for ln in lines[1:end]:
        if not ln.strip():
            continue
        m = re.match(r"^([A-Za-z_][\w.-]*):\s*(.*)$", ln)
        if m:
            parent = m.group(1)
            fm[parent] = m.group(2).strip()
            continue
        m = re.match(r"^\s+([A-Za-z_][\w.-]*):\s*(.*)$", ln)
        if m and parent:
            fm[f"{parent}.{m.group(1)}"] = m.group(2).strip()
    return fm, None


def check_okf_conformance() -> list[str]:
    """OKF v0.2 §11: parseable frontmatter with a non-empty `type` on every concept doc."""
    errors = []
    root_fm, _ = _frontmatter(read(ROOT_INDEX)) if os.path.isfile(ROOT_INDEX) else ({}, None)
    if root_fm.get("okf_version", "").strip('"\'') != OKF_VERSION:
        errors.append(
            f"docs/index.md: bundle root must declare okf_version: \"{OKF_VERSION}\" "
            f"(found {root_fm.get('okf_version') or 'nothing'})")

    for path in bundle_docs():
        rel = os.path.relpath(path, REPO)
        text = read(path)
        fm, err = _frontmatter(text)

        if os.path.basename(path) in RESERVED:
            # §8: reserved files carry no frontmatter, with one exception — the bundle-root
            # index.md may declare okf_version, and nothing else.
            if not text.startswith("---"):
                continue
            if path != ROOT_INDEX:
                errors.append(f"{rel}: reserved file must not have frontmatter")
            elif set(fm) - {"okf_version"}:
                errors.append(
                    f"{rel}: bundle-root index.md may only carry okf_version, "
                    f"found {sorted(set(fm) - {'okf_version'})}")
            continue

        if err:
            errors.append(f"{rel}: {err}")
            continue
        if not fm.get("type"):
            errors.append(f"{rel}: missing or empty `type` (the only field OKF requires)")

        for dead, replacement in REMOVED_FIELDS.items():
            if dead in fm:
                errors.append(f"{rel}: `{dead}` was removed in OKF v0.2 — use `{replacement}`")

        # §7: identity fields name an agent, a human, or a process, in a known shape.
        for field in ("generated.by", "verified.by"):
            actor = fm.get(field)
            if actor and not _ACTOR.match(actor):
                errors.append(
                    f"{rel}: {field} {actor!r} does not match the actor convention "
                    f"(<producer>/<version>, human:<id>, or process:<id>)")
    return errors


def _lint_ids() -> tuple[dict[str, str], dict[str, str]]:
    """(id -> prefix, prefix -> sub-score) as documented in lint.py's docstring."""
    ids, prefixes = {}, {}
    in_block = False
    for ln in read(os.path.join(ENGINE, "lint.py")).splitlines():
        if ln.startswith("Check IDs"):
            in_block = True
            continue
        if in_block and ln.startswith('"""'):
            break
        if not in_block:
            continue
        m = _LINT_PREFIX.match(ln)
        if m:
            prefixes[m.group(1)] = m.group(2)
            continue
        m = _LINT_ID.match(ln)
        if m:
            cid = m.group(1)
            ids[cid] = re.match(r"[A-Z]{2,3}", cid).group(0)
    return ids, prefixes


def _static_prefixes() -> dict[str, str]:
    sys.path.insert(0, os.path.dirname(ENGINE))
    from engine import static  # noqa: PLC0415 — path has to be set first
    return dict(static._PREFIX_TO_SUBCHECK)


def check_id_sync() -> list[str]:
    """The docs table, lint.py's docstring, and static.py's map must agree."""
    errors = []
    lint_ids, lint_prefixes = _lint_ids()
    if not lint_ids:
        return ["engine/lint.py: could not parse any check IDs from the docstring — "
                "did the `Check IDs` block format change?"]

    doc_ids, doc_prefixes = set(), {}
    for ln in read(CHECK_IDS_DOC).splitlines():
        m = _DOC_ID.match(ln)
        if m:
            doc_ids.add(m.group(1))
        m = _DOC_PREFIX.match(ln)
        if m:
            doc_prefixes[m.group(1)] = m.group(2)

    rel = os.path.relpath(CHECK_IDS_DOC, REPO)
    for missing in sorted(set(lint_ids) - doc_ids):
        errors.append(f"{rel}: {missing} is emitted by lint.py but not documented here")
    for extra in sorted(doc_ids - set(lint_ids)):
        errors.append(f"{rel}: {extra} is documented here but lint.py never emits it")

    static_prefixes = _static_prefixes()
    for prefix, sub in sorted(doc_prefixes.items()):
        if static_prefixes.get(prefix) != sub:
            errors.append(
                f"{rel}: prefix {prefix} documented as '{sub}' but static.py maps it to "
                f"'{static_prefixes.get(prefix)}'")
    for prefix, sub in sorted(lint_prefixes.items()):
        if doc_prefixes.get(prefix) != sub:
            errors.append(
                f"{rel}: prefix {prefix} is '{sub}' in lint.py but "
                f"'{doc_prefixes.get(prefix)}' here")
    return errors


def check_links() -> list[str]:
    """Every relative link in the bundle must resolve to a real file."""
    errors = []
    for path in bundle_docs():
        rel = os.path.relpath(path, REPO)
        for target in _LINK.findall(read(path)):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = os.path.normpath(
                os.path.join(os.path.dirname(path), target.split("#")[0]))
            if not os.path.exists(resolved):
                errors.append(f"{rel}: link target does not exist: {target}")
    return errors


def main() -> int:
    if not os.path.isdir(DOCS):
        print("docs/ not found — nothing to check")
        return 0
    groups = [
        ("OKF conformance", check_okf_conformance()),
        ("check-ID sync", check_id_sync()),
        ("internal links", check_links()),
    ]
    failed = False
    for name, errors in groups:
        if errors:
            failed = True
            print(f"\n✗ {name}")
            for e in errors:
                print(f"    {e}")
        else:
            print(f"✓ {name}")
    if failed:
        print("\ndocs check failed")
        return 1
    print(f"\ndocs check passed ({len(bundle_docs())} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
