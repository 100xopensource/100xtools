"""Find and read the session transcript the host already wrote.

The host writes the whole conversation to a JSONL file as it happens, and that
file is reachable from inside the session. So there is nothing to record: the
transcript *is* the record, and this plugin's job is to find it, read it, redact
it, and save it.

Everything here follows from one rule learned the hard way:

    **List the directory. Never construct its name.**

The project directory name is the working directory with separators, colons *and*
underscores all replaced by `-`, and runs are not collapsed. A constructed name
matches often enough to look correct and then silently misses — on a path with an
underscore, on Windows, on a cwd with a colon. Listing cannot miss.

Two roots, checked in order, because the same code runs on both surfaces:

| Root | Where you are |
| --- | --- |
| `~/mnt/.claude/projects` | inside a Cowork session (the host's tree, mounted) |
| `~/.claude/projects` | a terminal on the host |

Both hold `<project-dir>/<session-id>.jsonl`. Nothing else about them differs, and
a caller never needs to know which one answered.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
from typing import Any

from engine import keys

# Checked in order. The mounted root comes first: inside a session it is the one
# that holds this conversation, and a host root may also exist there but describe
# a different machine's work.
ROOTS = (
    pathlib.PurePosixPath("mnt/.claude/projects"),
    pathlib.PurePosixPath(".claude/projects"),
)

# A Cowork session directory. The outer id is this segment of a record's `cwd`.
SESSION_PREFIX = "local_"

# How many records from the end to read when confirming a transcript is this
# conversation. Enough to contain a recent turn, small enough to stay cheap.
CONFIRM_TAIL = 40

_SEPARATORS = re.compile(r"[\\/]+")


def split_path(value: str) -> list[str]:
    """Path components, splitting on both separators by hand.

    A record's `cwd` can be a Windows path while the interpreter reading it is
    POSIX-flavoured. `pathlib` splits only its own flavour, so `C:\\a\\local_x`
    collapses to one component, the session anchor is never found, and the outer
    id comes back empty with no error to notice.
    """
    return [part for part in _SEPARATORS.split(str(value)) if part]


def outer_id(cwd: str | None) -> str | None:
    """The `local_<uuid>` segment of `cwd`, or None when there is not one.

    None is the ordinary answer outside a Cowork session and is not a failure.
    """
    if not cwd:
        return None
    for part in reversed(split_path(cwd)):
        if part.startswith(SESSION_PREFIX):
            return part
    return None


@dataclasses.dataclass(frozen=True)
class Found:
    """A transcript that was located, plus what the search saw getting there.

    `notes` carries every degradation as a plain sentence. A caller reports them
    rather than discarding them: "no transcript found" and "found one but could
    not confirm it is this conversation" are different situations and a reader
    cannot tell them apart from an empty result.
    """

    path: pathlib.Path | None
    root: pathlib.Path | None
    candidates: int = 0
    directories: int = 0
    confirmed: bool | None = None
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.path is not None


def roots(home: pathlib.Path | None = None) -> list[pathlib.Path]:
    """The project roots that exist here, in precedence order."""
    base = home or pathlib.Path.home()
    out = []
    for candidate in ROOTS:
        path = base / candidate
        try:
            if path.is_dir():
                out.append(path)
        except OSError:
            continue
    return out


def discover(
    *,
    session_id: str | None = None,
    home: pathlib.Path | None = None,
) -> Found:
    """Locate this session's transcript by listing, never by building a name.

    With a `session_id`, prefers the file named for it — that is exact, and the
    filename is the one part of the layout that is a plain id rather than an
    encoding. Falls back to the most recently written file, which is what a
    session that does not know its own id has to rely on.
    """
    available = roots(home)
    if not available:
        return Found(
            path=None,
            root=None,
            notes=("no transcript directory exists on this machine",),
        )

    notes: list[str] = []
    for root in available:
        directories = sorted(entry for entry in root.iterdir() if entry.is_dir())
        files = [path for directory in directories for path in directory.glob("*.jsonl")]
        if not files:
            notes.append(
                f"listed {len(directories)} directories under {root} and found "
                "no transcript files"
            )
            continue

        if session_id:
            exact = [path for path in files if path.stem == session_id]
            if exact:
                return Found(
                    path=exact[0],
                    root=root,
                    candidates=len(files),
                    directories=len(directories),
                    notes=tuple(notes),
                )
            notes.append(
                f"no transcript named for session {session_id}; used the most "
                "recently written file instead"
            )

        newest = max(files, key=lambda path: path.stat().st_mtime)
        return Found(
            path=newest,
            root=root,
            candidates=len(files),
            directories=len(directories),
            notes=tuple(notes),
        )

    return Found(path=None, root=None, notes=tuple(notes))


def read(path: pathlib.Path, *, max_bytes: int | None = None) -> list[dict[str, Any]]:
    """Every record in a transcript, skipping lines that will not parse.

    A malformed line is skipped rather than raised on: transcripts are written
    live, so the last line can be half-written at the moment we read, and losing
    the whole session over one truncated line would be absurd.
    """
    data = path.read_bytes()
    if max_bytes is not None and len(data) > max_bytes:
        data = data[:max_bytes]
        data = data[: data.rfind(b"\n") + 1]
    rows = []
    for line in data.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def confirm(rows: list[dict[str, Any]], needle: str, *, tail: int = CONFIRM_TAIL) -> bool:
    """Whether `needle` appears near the end — is this transcript this conversation?

    Worth doing because `discover` may have fallen back to "most recently
    written", and on a machine running two sessions at once that is a coin flip.
    Publishing someone else's conversation is the failure this prevents.
    """
    if not needle:
        return False
    blob = json.dumps(rows[-tail:], ensure_ascii=False)
    return needle in blob


def identify(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    """The session's own ids, read from its records rather than from the caller.

    `sessionId` on a record is the inner id and names the transcript file. The
    outer id — the Cowork session directory — is not a field at all; it is the
    `local_<uuid>` segment of `cwd`, which is why `cwd` is read here.
    """
    inner = None
    outer = None
    title = None
    for row in rows:
        inner = inner or row.get("sessionId") or row.get("session_id")
        outer = outer or outer_id(row.get("cwd"))
        if row.get("type") == "ai-title":
            # `aiTitle` is the field the host actually writes; `title` is accepted
            # only as a fallback. Reading the plausible-looking name alone returned
            # None for every real session, silently, which is exactly the kind of
            # miss a listing cannot show you.
            title = row.get("aiTitle") or row.get("title") or title
        if inner and outer and title:
            break
    return {
        "inner_id": str(inner) if inner else None,
        "outer_id": str(outer) if outer else None,
        "title": str(title) if title else None,
    }


def subagents(path: pathlib.Path, inner_id: str | None) -> list[pathlib.Path]:
    """Subagent transcripts beside the main one, when a fan-out run produced any.

    They live at `<project-dir>/<sessionId>/subagents/agent-*.jsonl`. A run with
    no subagents has no such directory, which is the common case and not a note.
    """
    if not inner_id:
        return []
    directory = path.parent / inner_id / "subagents"
    try:
        return sorted(directory.glob("agent-*.jsonl"))
    except OSError:
        return []


def as_records(
    rows: list[dict[str, Any]],
    *,
    source: str = "transcript",
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Wrap transcript rows in the envelope the digest and redactor expect.

    The envelope carries provenance; the row itself goes in `payload` untouched.
    Wrapping here rather than teaching those two modules a second input shape
    keeps the boundary transform reading exactly one thing.

    `event_id` and `integrity_hash` are content-derived, so publishing the same
    transcript twice produces identical ids. That is what lets a reader compare
    two published copies of one session, and it is why the id is computed from the
    row rather than from a counter.
    """
    resolved = session_id or (identify(rows)["inner_id"] if rows else None) or "unknown"
    out = []
    for index, row in enumerate(rows, 1):
        cursor = {"kind": "jsonl", "position": index}
        out.append(
            {
                "event_id": keys.stable_event_id(
                    source=source, session_id=resolved, source_cursor=cursor
                ),
                "source": source,
                "source_event": str(row.get("type") or "record"),
                "session_id": resolved,
                "source_timestamp": row.get("timestamp"),
                "sequence": index,
                "source_cursor": cursor,
                "integrity_hash": keys.integrity_hash(row),
                "payload": row,
            }
        )
    return out
