"""Fold a captured session into something a later session can actually read.

The private ledger is the fidelity record, and it is far too large to hand to a
model: one working session runs to hundreds of records and megabytes of tool
output. A digest is the other end of that trade — a page of markdown carrying what
a later session needs to resume: what was asked, what was decided, which files were
touched, which tools ran, and what was left unfinished.

Everything here is a pure function of the records it is given. No clock, no
filesystem, no configuration — so a digest is reproducible from a stored ledger and
a test fixes its output exactly.

**Record shapes are defensive on purpose.** These are Claude Code's own transcript
records, verified against a real `~/.claude/projects` tree: `user` and `assistant`
carry `message.content` as either a string or a list of typed blocks
(`text`/`thinking`/`tool_use`/`tool_result`), and the file carries bookkeeping types
(`attachment`, `queue-operation`, `ai-title`, `file-history-*`) alongside them. That
shape is not a published contract, so an unrecognised record is skipped rather than
allowed to break a summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# A digest exists to be read into a later session's context, so it is capped.
# Without these one long session produces a "summary" nobody can afford to load,
# which defeats the purpose.
MAX_PROMPTS = 40
MAX_PROMPT_CHARS = 400
MAX_LAST_MESSAGE_CHARS = 2000
MAX_FILES = 60

# Injected context, not anything a person typed. Keeping it would fill a digest's
# prompt list with reminders the next session gets anyway.
_INJECTED_PREFIXES = ("<system-reminder>", "<ide_opened_file>", "<ide_selection>")

# Tool inputs name their target under one of these. Used to answer "what did this
# session actually touch", which is the first thing a resuming session wants.
_PATH_FIELDS = ("file_path", "path", "notebook_path")

_TEXT_BLOCKS = frozenset({"text"})


@dataclass
class Digest:
    """What one captured session amounted to."""

    session_id: str
    title: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    cwd: str | None = None
    git_branch: str | None = None
    models: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    prompts_omitted: int = 0
    last_assistant_text: str | None = None
    tools: dict[str, int] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    files_omitted: int = 0
    tokens: dict[str, int] = field(default_factory=dict)
    records: int = 0
    open_notes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def turns(self) -> int:
        return len(self.prompts) + self.prompts_omitted

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "models": self.models,
            "turns": self.turns,
            "prompts": self.prompts,
            "prompts_omitted": self.prompts_omitted,
            "last_assistant_text": self.last_assistant_text,
            "tools": self.tools,
            "files": self.files,
            "files_omitted": self.files_omitted,
            "tokens": self.tokens,
            "records": self.records,
            "open_notes": self.open_notes,
        }

    def to_markdown(self) -> str:
        """The form a resuming session reads. Markdown, because a model reads it."""
        lines: list[str] = [f"# Session {self.title or self.session_id}", ""]
        if self.title:
            lines += [f"Session id: `{self.session_id}`", ""]

        facts: list[str] = []
        if self.started_at:
            span = self.started_at
            if self.ended_at and self.ended_at != self.started_at:
                span = f"{self.started_at} → {self.ended_at}"
            facts.append(f"- When: {span}")
        if self.cwd:
            branch = f" (branch `{self.git_branch}`)" if self.git_branch else ""
            facts.append(f"- Where: `{self.cwd}`{branch}")
        if self.models:
            facts.append(f"- Model: {', '.join(self.models)}")
        facts.append(f"- Turns: {self.turns} · records captured: {self.records}")
        if self.tokens:
            facts.append(
                "- Tokens: "
                + ", ".join(f"{name} {count}" for name, count in sorted(self.tokens.items()))
            )
        lines += facts + [""]

        if self.prompts:
            lines += ["## What was asked", ""]
            lines += [f"{index}. {text}" for index, text in enumerate(self.prompts, 1)]
            if self.prompts_omitted:
                lines.append(
                    f"…and {self.prompts_omitted} earlier turns not listed here."
                )
            lines.append("")

        if self.last_assistant_text:
            lines += ["## Where it left off", "", self.last_assistant_text, ""]

        if self.files:
            lines += ["## Files touched", ""]
            lines += [f"- `{path}`" for path in self.files]
            if self.files_omitted:
                lines.append(f"- …and {self.files_omitted} more")
            lines.append("")

        if self.tools:
            ranked = sorted(self.tools.items(), key=lambda item: (-item[1], item[0]))
            lines += [
                "## Tools used",
                "",
                ", ".join(f"{name} ×{count}" for name, count in ranked),
                "",
            ]

        if self.open_notes:
            # Loss belongs in the digest, not only in the ledger: a resuming
            # session that cannot see a gap will assume the record is complete.
            lines += ["## Capture gaps", ""]
            lines += [
                f"- `{note.get('code')}` {note.get('details') or ''}".rstrip()
                for note in self.open_notes
            ]
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


def summarize(
    records: list[dict[str, Any]],
    *,
    open_notes: list[dict[str, Any]] | None = None,
    max_prompts: int = MAX_PROMPTS,
    max_prompt_chars: int = MAX_PROMPT_CHARS,
    max_files: int = MAX_FILES,
) -> Digest:
    """Summarize one session's ledger records.

    Accepts hook records and transcript records together and reads whichever
    carries each fact. Tool calls are counted by `tool_use_id` across both sources,
    so a session captured through hooks, through the transcript, or through both
    reports the same count — double counting was the obvious first bug here.
    """
    digest = Digest(session_id=_session_id(records))
    user_payloads: list[dict[str, Any]] = []
    tool_names: dict[str, str] = {}
    files: list[str] = []
    models: list[str] = []
    tokens: dict[str, int] = {}
    timestamps: list[str] = []

    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        source = record.get("source")
        stamp = record.get("source_timestamp") or record.get("observed_at")
        if isinstance(stamp, str) and stamp:
            timestamps.append(stamp)

        if source == "hook":
            _read_hook(payload, tool_names, files, digest)
            continue

        kind = str(payload.get("type") or "")
        if kind == "ai-title":
            title = payload.get("aiTitle")
            if isinstance(title, str) and title.strip():
                digest.title = title.strip()
            continue
        if kind == "file-history-delta":
            _append_unique(files, payload.get("trackingPath"))
            continue
        if kind not in {"user", "assistant"}:
            continue
        if payload.get("isSidechain"):
            # Subagent traffic. Real work, but it is the parent turn that a
            # resuming session needs to understand, and including it makes the
            # prompt list read as if the user said things they never said.
            continue

        digest.cwd = digest.cwd or _text_or_none(payload.get("cwd"))
        digest.git_branch = digest.git_branch or _text_or_none(payload.get("gitBranch"))

        message = payload.get("message")
        if not isinstance(message, dict):
            continue
        blocks = _blocks(message.get("content"))

        if kind == "user":
            user_payloads.append(payload)
            continue

        model = message.get("model")
        if isinstance(model, str) and model:
            _append_unique(models, model)
        _add_usage(tokens, message.get("usage"))
        text = _joined_text(blocks)
        if text:
            digest.last_assistant_text = _clip(text, MAX_LAST_MESSAGE_CHARS)
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            identifier = block.get("id")
            name = block.get("name")
            if isinstance(identifier, str) and isinstance(name, str):
                tool_names.setdefault(identifier, name)
            _collect_paths(block.get("input"), files)

    if timestamps:
        digest.started_at = min(timestamps)
        digest.ended_at = max(timestamps)
    digest.records = len(records)
    digest.models = models
    digest.tokens = tokens
    digest.open_notes = list(open_notes or [])

    counts: dict[str, int] = {}
    for name in tool_names.values():
        counts[name] = counts.get(name, 0) + 1
    digest.tools = counts

    prompts = _prompts(user_payloads, max_prompt_chars)
    files = _absolute_paths(files, digest.cwd)

    if len(prompts) > max_prompts:
        # Keep the most recent turns: a resuming session cares far more about
        # where things stand than about how they started.
        digest.prompts_omitted = len(prompts) - max_prompts
        prompts = prompts[-max_prompts:]
    digest.prompts = prompts

    if len(files) > max_files:
        digest.files_omitted = len(files) - max_files
        files = files[:max_files]
    digest.files = files

    return digest


def _prompts(payloads: list[dict[str, Any]], max_chars: int) -> list[str]:
    """The turns a person actually typed, out of every `user` record.

    A `user` record is not the same thing as a prompt. The transcript files tool
    results and injected skill bodies under the same type, and a skill body reads
    as an enormous prompt the user never wrote — verified against a real session,
    where invoking one slash command added a 60-line "question".

    Claude Code marks a genuine prompt with `origin: {"kind": "human"}`, but that
    field is not a published contract, so it is used only when the session shows it
    at all: if no record carries an origin, every record with human-readable text
    counts. Filtering unconditionally on a field a build might not emit would
    summarise a whole session as having been asked nothing.
    """
    marked = [
        payload
        for payload in payloads
        if isinstance(payload.get("origin"), dict) and payload["origin"].get("kind")
    ]
    if marked:
        payloads = [
            payload
            for payload in marked
            if str(payload["origin"].get("kind")) == "human"
        ]
    prompts: list[str] = []
    for payload in payloads:
        message = payload.get("message")
        if not isinstance(message, dict):
            continue
        text = _joined_text(_blocks(message.get("content")))
        if text:
            prompts.append(_clip(text, max_chars))
    return prompts


def _absolute_paths(paths: list[str], cwd: str | None) -> list[str]:
    """Resolve relative tool paths against the session's cwd, then dedupe.

    One file edited twice — once by absolute path, once by the repo-relative path a
    tool call happened to use — is one file, and listing it twice makes a digest
    look like more work happened than did.
    """
    if not cwd:
        return paths
    seen: list[str] = []
    base = cwd.rstrip("/")
    for path in paths:
        resolved = path if path.startswith(("/", "~")) else f"{base}/{path}"
        if resolved not in seen:
            seen.append(resolved)
    return seen


def _session_id(records: list[dict[str, Any]]) -> str:
    for record in records:
        value = record.get("session_id")
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _read_hook(
    payload: dict[str, Any],
    tool_names: dict[str, str],
    files: list[str],
    digest: Digest,
) -> None:
    """Facts only a hook payload carries."""
    digest.cwd = digest.cwd or _text_or_none(payload.get("cwd"))
    identifier = payload.get("tool_use_id")
    name = payload.get("tool_name")
    if isinstance(identifier, str) and isinstance(name, str):
        tool_names.setdefault(identifier, name)
    _collect_paths(payload.get("tool_input"), files)
    last = payload.get("last_assistant_message")
    if isinstance(last, str) and last.strip():
        # `Stop` carries the final message directly, and the docs single it out as
        # more reliable than the transcript, which can lag behind the hook.
        digest.last_assistant_text = _clip(last.strip(), MAX_LAST_MESSAGE_CHARS)


def _blocks(content: Any) -> list[dict[str, Any]]:
    """Message content as a block list, whichever shape it arrived in."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _joined_text(blocks: list[dict[str, Any]]) -> str:
    """The human-readable text of a message: no thinking, no tool plumbing.

    Injected context is dropped as well — a digest full of system reminders tells a
    resuming session nothing it will not already be told.
    """
    parts: list[str] = []
    for block in blocks:
        if block.get("type") not in _TEXT_BLOCKS:
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if not stripped or stripped.startswith(_INJECTED_PREFIXES):
            continue
        parts.append(stripped)
    return "\n\n".join(parts).strip()


def _collect_paths(tool_input: Any, files: list[str]) -> None:
    if not isinstance(tool_input, dict):
        return
    for field_name in _PATH_FIELDS:
        _append_unique(files, tool_input.get(field_name))


def _append_unique(target: list[str], value: Any) -> None:
    if isinstance(value, str) and value and value not in target:
        target.append(value)


def _add_usage(tokens: dict[str, int], usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    for name, value in usage.items():
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        tokens[name] = tokens.get(name, 0) + value


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _clip(text: str, limit: int) -> str:
    collapsed = " ".join(text.split()) if len(text) > limit else text
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"
