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


def check_okf_conformance() -> list[str]:
    """Every non-reserved .md needs frontmatter with a non-empty `type`."""
    errors = []
    for path in bundle_docs():
        rel = os.path.relpath(path, REPO)
        text = read(path)
        if os.path.basename(path) in RESERVED:
            # Reserved files carry no frontmatter; flag it if one crept in, since a
            # consumer following the spec will not look for it there.
            if text.startswith("---"):
                errors.append(f"{rel}: reserved file must not have frontmatter")
            continue
        if not text.startswith("---"):
            errors.append(f"{rel}: no YAML frontmatter block")
            continue
        lines = text.splitlines()
        end = next((i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---"), None)
        if end is None:
            errors.append(f"{rel}: frontmatter block is not closed")
            continue
        fm = {}
        for ln in lines[1:end]:
            m = re.match(r"^([A-Za-z_][\w.-]*):\s*(.*)$", ln)
            if m:
                fm[m.group(1)] = m.group(2).strip()
        if not fm.get("type"):
            errors.append(f"{rel}: missing or empty `type` (the only field OKF requires)")
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
