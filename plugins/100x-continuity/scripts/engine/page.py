"""Render a Publication's Digest as a page a person can open without Claude.

A Bundle is a zip. Somebody double-clicks it, and what they find has to make sense
on its own — before any tooling, on a machine with nothing installed. That is what
this module is for: one self-contained HTML file, no scripts, no network, no fonts
to fetch, that says what the session was doing and what else is in the zip.

It renders the Digest's **fields**, not its markdown. Rendering the markdown would
mean shipping a markdown parser to solve a problem we do not have, and every value
here is already structured. Everything interpolated is escaped, because all of it
came out of somebody's conversation — a session that discussed HTML would otherwise
rewrite this page.
"""

from __future__ import annotations

import html
from typing import Any

from engine import digest as digest_mod

_STYLE = """
:root { color-scheme: light dark; }
body { margin: 0 auto; padding: 2.5rem 1.5rem; max-width: 46rem;
       font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
h2 { font-size: 1rem; text-transform: uppercase; letter-spacing: .06em;
     opacity: .6; margin: 2rem 0 .5rem; }
.sub { opacity: .6; margin: 0 0 2rem; font-size: .9rem; }
ol, ul { padding-left: 1.2rem; }
li { margin: .3rem 0; }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85em; }
.facts { display: grid; grid-template-columns: max-content 1fr; gap: .3rem 1rem; }
.facts dt { opacity: .6; }
.facts dd { margin: 0; }
.note { border-left: 3px solid currentColor; opacity: .75; padding: .5rem 0 .5rem .9rem;
        margin: 1.5rem 0; font-size: .9rem; }
"""


def render(summary: digest_mod.Digest, manifest: dict[str, Any]) -> str:
    """One standalone page describing this Publication."""
    title = summary.title or "Session"
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(title)}</title><style>{_STYLE}</style></head><body>",
        f"<h1>{_esc(title)}</h1>",
        f'<p class="sub">A session handed over with 100x-continuity. '
        f"{_esc(_when(summary))}</p>",
    ]

    parts.append("<h2>What was asked</h2>")
    parts.append(_list(summary.prompts, ordered=True, empty="No prompts were captured."))
    if summary.prompts_omitted:
        parts.append(
            f'<p class="sub">{summary.prompts_omitted} earlier turn(s) not shown here — '
            "the full record is in the zip.</p>"
        )

    if summary.last_assistant_text:
        parts.append("<h2>Where it left off</h2>")
        parts.append(f"<p>{_esc(summary.last_assistant_text)}</p>")

    if summary.files:
        parts.append("<h2>Files touched</h2>")
        parts.append(_list(summary.files, mono=True))

    parts.append("<h2>What came with this session</h2>")
    parts.append(
        _list(
            [f"{entry['path']} ({entry['size']} bytes)" for entry in manifest.get("files", [])],
            mono=True,
            empty="Nothing — which should not happen.",
        )
    )

    parts.append("<h2>Session</h2>")
    parts.append(_facts(summary, manifest))

    redacted = manifest.get("redacted") or {}
    total = sum(redacted.values()) if isinstance(redacted, dict) else 0
    caveat = manifest.get("redaction_caveat") or ""
    parts.append(
        f'<div class="note"><strong>{total} credential-shaped value(s) were removed '
        f"from the conversation on the way in.</strong> {_esc(caveat)}</div>"
    )
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def _when(summary: digest_mod.Digest) -> str:
    if summary.started_at and summary.ended_at:
        return f"{summary.started_at} → {summary.ended_at}"
    return summary.started_at or summary.ended_at or "Time not recorded."


def _facts(summary: digest_mod.Digest, manifest: dict[str, Any]) -> str:
    session = manifest.get("session") or {}
    rows: list[tuple[str, str]] = [
        ("Session id", str(session.get("id") or "unattributed")),
        ("Turns", str(summary.turns)),
        ("Records", str(summary.records)),
    ]
    if summary.cwd:
        rows.append(("Working directory", summary.cwd))
    if summary.git_branch:
        rows.append(("Branch", summary.git_branch))
    if summary.models:
        rows.append(("Model", ", ".join(summary.models)))
    if summary.tools:
        rows.append(
            ("Tools", ", ".join(f"{name} ×{count}" for name, count in sorted(summary.tools.items())))
        )
    cells = "".join(
        f"<dt>{_esc(label)}</dt><dd class='mono'>{_esc(value)}</dd>" for label, value in rows
    )
    return f'<dl class="facts">{cells}</dl>'


def _list(items: list[str], *, ordered: bool = False, mono: bool = False, empty: str = "") -> str:
    if not items:
        return f'<p class="sub">{_esc(empty)}</p>' if empty else ""
    tag = "ol" if ordered else "ul"
    css = ' class="mono"' if mono else ""
    body = "".join(f"<li{css}>{_esc(str(item))}</li>" for item in items)
    return f"<{tag}>{body}</{tag}>"


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)
