"""Transcript fixtures, built the way the host writes them.

Every test that needs a session builds one here rather than inline, so a change in
the host's record shape is one edit instead of a sweep. Not named `test_*` on
purpose: `unittest discover` must not collect it.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from engine import transcript

SESSION = "0f9c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"
CWD = "/Users/dev/mnt/outputs/local_11112222-3333-4444-5555-666677778888/work"


def rows(
    *,
    session_id: str = SESSION,
    cwd: str = CWD,
    prompt: str = "Wire the importer up to the new flags file.",
    secret: str | None = None,
    title: str = "Importer flags",
) -> list[dict[str, Any]]:
    """A short but complete session: a title, a human turn, an assistant turn."""
    text = prompt if secret is None else f"{prompt} Use the key {secret}."
    return [
        {"type": "ai-title", "aiTitle": title, "sessionId": session_id, "cwd": cwd},
        {
            "type": "user",
            "sessionId": session_id,
            "cwd": cwd,
            "gitBranch": "main",
            "timestamp": "2026-08-20T09:00:00.000Z",
            "origin": {"kind": "human"},
            "message": {"role": "user", "content": [{"type": "text", "text": text}]},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "cwd": cwd,
            "timestamp": "2026-08-20T09:04:00.000Z",
            "message": {
                "role": "assistant",
                "model": "claude-opus-5",
                "usage": {"input_tokens": 120, "output_tokens": 40},
                "content": [
                    {"type": "text", "text": "Flags file updated; store 41 still open."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Edit",
                        "input": {"file_path": "flags.yaml"},
                    },
                ],
            },
        },
    ]


def records(session_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Those rows in the envelope the digest and the redactor read."""
    return transcript.as_records(session_rows if session_rows is not None else rows())


def write_transcript(
    home: pathlib.Path,
    *,
    session_id: str = SESSION,
    project: str = "-Users-dev-mnt-outputs-work",
    session_rows: list[dict[str, Any]] | None = None,
    mounted: bool = False,
) -> pathlib.Path:
    """Write a transcript where `transcript.discover` will list it.

    `mounted` writes under the Cowork mount instead of the host root, which is the
    other of the two surfaces the same code has to serve.
    """
    root = home / ("mnt/.claude/projects" if mounted else ".claude/projects")
    directory = root / project
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    payload = session_rows if session_rows is not None else rows(session_id=session_id)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in payload), encoding="utf-8"
    )
    return path
