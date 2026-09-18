#!/usr/bin/env python3
"""Validate the docs/ knowledge bundle. Stdlib only; run from the repo root.

Two checks, each catching a way documentation rots:

1. **OKF conformance** — the spec's actual bar: every non-reserved `.md` under `docs/`
   carries parseable YAML frontmatter with a non-empty `type`.
2. **Internal links resolve** — every relative markdown link inside the bundle points at a
   file that exists. OKF tolerates broken links; a bundle we ship should not have them.

Deliberately a repo-level script rather than a plugin unit test: the plugin's suite has to
pass for someone who installed only the plugin, where `docs/` does not exist.

    python3 scripts/check_docs.py        # exit 0 clean, 1 with a report of what is wrong
"""

from __future__ import annotations

import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")
RESERVED = {"index.md", "log.md"}

# `docs/adr/` is not part of the OKF bundle and is not checked against it. An ADR records
# one decision and the trade behind it; an OKF concept doc explains a thing that exists.
# Different genre, different format, and giving an ADR `type:` frontmatter to get it past
# this checker would be dressing it up as something it is not. Its links are still checked.
NOT_A_CONCEPT = {"adr"}
OKF_VERSION = "0.2"
ROOT_INDEX = os.path.join(DOCS, "index.md")

# v0.1 fields that v0.2 replaced. Left in place they parse fine and mean nothing, so the
# only thing that catches them is naming them.
REMOVED_FIELDS = {"timestamp": "generated: { by, at }"}

# §7 actor convention for identity fields: <producer>/<version>, human:<id>, process:<id>.
_ACTOR = re.compile(r"^(?:[\w.-]+/[\w.-]+|human:[\w.-]+|process:[\w.-]+)$")

# Markdown links, skipping external URLs and anchors.
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _markdown_under(root: str, *, skip: set[str] = frozenset()) -> list[str]:
    out = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        for fn in sorted(files):
            if fn.endswith(".md"):
                out.append(os.path.join(dirpath, fn))
    return out


def bundle_docs() -> list[str]:
    """The OKF concept docs — what conformance is checked against."""
    return _markdown_under(DOCS, skip=NOT_A_CONCEPT)


def linkable_docs() -> list[str]:
    """Every markdown file under docs/, ADRs included.

    A broken link is a broken link whatever the genre, so the link check is deliberately
    wider than the conformance check.
    """
    return _markdown_under(DOCS)


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


def check_links() -> list[str]:
    """Every relative link under docs/ must resolve to a real file."""
    errors = []
    for path in linkable_docs():
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
    concepts, linked = len(bundle_docs()), len(linkable_docs())
    adrs = linked - concepts
    extra = f" + {adrs} ADR{'s' if adrs != 1 else ''}" if adrs else ""
    print(f"\ndocs check passed ({concepts} concept files{extra})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
