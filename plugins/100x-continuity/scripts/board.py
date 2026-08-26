#!/usr/bin/env python3
"""The board a setup run is watched on, and the record it leaves behind.

`set-up-handoff` runs once and unattended for most of its length. This writes the whole
run down as tasks *before* the first file is written, so the Operator approves a plan
they can see rather than a paragraph, and marks each one off as it finishes. What was
proven, what was only stood in for, and what is still theirs then outlives the
conversation that produced it.

    python3 board.py outline
    python3 board.py init --into ../acme-plugins --name acme-handoff \\
        --store folder --root '~/OneDrive - Acme/Continuity'
    python3 board.py set  --into ../acme-plugins emit --status done --evidence "29 files"
    python3 board.py show --into ../acme-plugins

The board is the Operator's record of one run, not part of the Kit: it is written beside
their repo's plugins, never inside the directory a Teammate installs.

Every string that reaches the file is redacted first. The board is written into a repo
that other people clone, and its evidence lines are composed from real run output — a
`.env` read back, a server's reply, a command that echoed more than it meant to. The
redactor prefers recall, so a false positive costs a mangled evidence line and a missed
credential costs the repo. Do not remove that call.

Prints JSON, except `show`, which prints the board. Exit 0, or 2 on a refusal that names
what to fix.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from emit import operator_items  # noqa: E402
from engine import redact  # noqa: E402

FACTORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
BOARD_TEMPLATE = FACTORY_ROOT / "templates" / "status" / "board.html"
BOARD_DIRNAME = "status"
TASKS_NAME = "tasks.json"

# The columns the page renders, in the order it renders them. `needsyou` is the one that
# earns its place: a task nobody is blocked on but nobody can finish without a decision
# is otherwise filed as done or as blocked, and both are lies.
COLUMNS = (
    ("backlog", "Backlog"),
    ("todo", "Todo"),
    ("in_progress", "In Progress"),
    ("blocked", "Blocked"),
    ("needsyou", "Needs you"),
    ("done", "Done"),
)
STATUSES = tuple(col for col, _ in COLUMNS)
PROOFS = ("proven", "stand-in")
ASSIGNEES = ("claude", "operator")

# Fields whose text is written by the model from what it just saw happen.
_REDACTED_FIELDS = ("title", "body", "evidence")

_GLYPHS = {
    "done": "[x]",
    "in_progress": "[~]",
    "blocked": "[!]",
    "needsyou": "[?]",
    "todo": "[ ]",
    "backlog": "[ ]",
}


class BoardError(Exception):
    """A refusal the Operator can act on."""


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def board_dir(into: str | pathlib.Path) -> pathlib.Path:
    return pathlib.Path(into).expanduser() / BOARD_DIRNAME


def id_prefix(name: str) -> str:
    """A short chip for the cards, derived from the Kit's name.

    Three letters, because the id is read off a card rather than typed. Falls back to
    KIT rather than to something clever: a name with no letters in it is somebody
    else's problem, not a reason to refuse to draw a board.
    """
    letters = [c for c in name.upper() if c.isalpha()]
    return "".join(letters[:3]) if len(letters) >= 3 else "KIT"


# The run itself, as the Factory performs it. Ordered, because the ids are handed out in
# this order and an Operator reading `ACM-4` on a card should find it where they expect.
# `key` is what a skill addresses a task by; `id` is what a person sees. None of these
# carry `blocked_by`: the order is a sequence, and a sequence filed as seven blocked
# cards is the opposite of showing somebody their plan.
def _setup_tasks(store: str) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = [
        {
            "key": "read-the-repo",
            "title": "Read the repo and settle what to build",
            "body": (
                "Which repo, what its marketplace already ships, whether a Kit is already "
                "here. A fact that could be read is a question not worth asking."
            ),
            "labels": ["repo"],
            "priority": "high",
        },
        {
            "key": "plan",
            "title": "Write the plan and get one explicit yes",
            "body": (
                "`continuity-plan.md`, with the access consequence of the store choice "
                "stated before it is locked in. This is the only gate a person stands at."
            ),
            "labels": ["kit"],
            "priority": "high",
        },
        {
            "key": "emit",
            "title": "Emit the Kit into the repo",
            "body": (
                "One script, so that every Kit is written the same way. It also writes the "
                "marked section in the repo's CLAUDE.md saying what this is and what is "
                "left."
            ),
            "labels": ["kit"],
            "priority": "high",
        },
        {
            "key": "marketplace",
            "title": "Add the marketplace row without touching the others",
            "body": (
                "`source` is relative to the repo root. Getting it wrong yields a manifest "
                "that validates and an install that finds nothing."
            ),
            "labels": ["kit", "repo"],
            "priority": "medium",
        },
    ]
    if store == "service":
        tasks += [
            {
                "key": "copy-store-service",
                "title": "Copy the store service out, to a directory outside the plugin repo",
                "body": (
                    "A marketplace is a git clone: installing one plugin copies the whole "
                    "repository to every Teammate's machine. Server source in there is "
                    "server source on all of them."
                ),
                "labels": ["store"],
                "priority": "high",
            },
            {
                "key": "credential-uncommittable",
                "title": "Make the storage credential uncommittable",
                "body": (
                    "`.env` git-ignored, confirmed before the credential goes into it, and "
                    "never pasted into the chat. A committed credential is a worse outcome "
                    "than no store at all."
                ),
                "labels": ["store", "security"],
                "priority": "urgent",
            },
            {
                "key": "server-answers",
                "title": "The server runs here and lists the four contract tools",
                "body": (
                    "Proves the credentials work and the code runs. It does not prove the "
                    "deployed one will, and it is not the same thing as registered."
                ),
                "labels": ["store", "test"],
                "priority": "high",
            },
        ]
    tasks += [
        {
            "key": "contract-test",
            "title": "The contract test passes",
            "body": (
                "Packing, redaction, reproducibility, the credential refusal, reading back, "
                "and both damage kinds. Deterministic, and it runs against a synthetic "
                "session in a throwaway home rather than a real conversation."
            ),
            "labels": ["kit", "test"],
            "priority": "high",
        },
        {
            "key": "baked-config",
            "title": "The Kit reads its own baked config, not a local override",
            "body": (
                "If an environment variable or a stray config file shadowed the baked "
                "value, what got tested is not what a Teammate receives."
            ),
            "labels": ["kit", "test"],
            "priority": "medium",
        },
        {
            "key": "round-trip",
            "title": "A real session packs and opens back",
            "body": (
                "The one test the synthetic session cannot stand in for: discovery finding "
                "an actual conversation on this machine, and the digest reading back as it."
            ),
            "labels": ["kit", "test"],
            "priority": "urgent",
        },
    ]
    return tasks


def seed(args: argparse.Namespace) -> dict[str, object]:
    """The whole run as tasks: what the Factory does, then what is left for the Operator.

    The Operator's half comes from `emit.operator_items` rather than being written again
    here, so the board and the checklist in their CLAUDE.md cannot come to disagree
    about what is outstanding.
    """
    prefix = id_prefix(args.name)
    rows = [dict(task, assignee="claude") for task in _setup_tasks(args.store)]
    rows += [dict(item, assignee="operator") for item in operator_items(args, args.kit_source or args.name)]

    ids = {task["key"]: f"{prefix}-{n}" for n, task in enumerate(rows, start=1)}
    tasks = []
    for task in rows:
        blocked_by = [ids[key] for key in task.get("blocked_by", []) if key in ids]
        tasks.append(
            {
                "id": ids[task["key"]],
                "key": task["key"],
                "title": task["title"],
                "status": "todo",
                "priority": task.get("priority", "medium"),
                "labels": list(task.get("labels", [])),
                "assignee": task["assignee"],
                "body": task["body"],
                "blockedBy": blocked_by,
            }
        )
    for task in tasks:
        blocks = [t["id"] for t in tasks if task["id"] in t["blockedBy"]]
        if blocks:
            task["blocks"] = blocks
    return {
        "project": args.name,
        "subtitle": args.subtitle or "",
        "updated": _stamp(),
        "verdict": {
            "state": "blocked",
            "line": (
                "Nothing has been written yet. This is the plan, and it is waiting on "
                "your yes."
            ),
        },
        "columns": [{"id": col, "name": name} for col, name in COLUMNS],
        "tasks": tasks,
    }


def scrub(data: dict[str, object]) -> dict[str, int]:
    """Redact every model-written string in place, and report what was removed."""
    counts: dict[str, int] = {}

    def clean(text: str) -> str:
        result = redact.redact_text(text)
        for name, hits in result.counts.items():
            counts[name] = counts.get(name, 0) + hits
        return result.value

    verdict = data.get("verdict")
    if isinstance(verdict, dict) and isinstance(verdict.get("line"), str):
        verdict["line"] = clean(verdict["line"])
    if isinstance(data.get("subtitle"), str):
        data["subtitle"] = clean(data["subtitle"])
    for task in data.get("tasks", []):
        for field in _REDACTED_FIELDS:
            if isinstance(task.get(field), str):
                task[field] = clean(task[field])
    return counts


def relieve(data: dict[str, object]) -> None:
    """Move tasks between `todo` and `blocked` to match their blockers.

    Only those two, so a task somebody deliberately parked in `needsyou` stays there.
    Doing it here means a skill only ever has to say what finished.
    """
    done = {task["id"] for task in data["tasks"] if task.get("status") == "done"}
    for task in data["tasks"]:
        waiting = [b for b in task.get("blockedBy", []) if b not in done]
        if task.get("status") == "todo" and waiting:
            task["status"] = "blocked"
        elif task.get("status") == "blocked" and not waiting:
            task["status"] = "todo"


def load(into: str | pathlib.Path) -> dict[str, object]:
    path = board_dir(into) / TASKS_NAME
    if not path.is_file():
        raise BoardError(f"no board at {path}. Run `board.py init` first")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BoardError(f"{path} is not readable as JSON: {exc}") from exc


def save(into: str | pathlib.Path, data: dict[str, object]) -> dict[str, int]:
    relieve(data)
    redacted = scrub(data)
    data["updated"] = _stamp()
    directory = board_dir(into)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / TASKS_NAME).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    return redacted


def find(data: dict[str, object], wanted: str) -> dict[str, object]:
    """A task by the id on its card or by the key a skill knows it as."""
    for task in data["tasks"]:
        if task["id"].lower() == wanted.lower() or task.get("key") == wanted:
            return task
    known = ", ".join(sorted(t.get("key", t["id"]) for t in data["tasks"]))
    raise BoardError(f"no task {wanted!r} on this board. Known: {known}")


def render(data: dict[str, object]) -> str:
    """The board as text, for the chat. The page is for watching; this is for saying."""
    lines = [f"{data['project']} · setup board"]
    verdict = data.get("verdict") or {}
    if verdict.get("line"):
        head = "Not shippable." if verdict.get("state") == "blocked" else "Status."
        lines.append(f"{head} {verdict['line']}")
    for column in data["columns"]:
        rows = [t for t in data["tasks"] if t.get("status", "backlog") == column["id"]]
        if not rows:
            continue
        lines.append("")
        lines.append(f"{column['name']} ({len(rows)})")
        width = max(len(t["id"]) for t in rows)
        for task in rows:
            glyph = _GLYPHS.get(task.get("status", "backlog"), "[ ]")
            who = "you" if task.get("assignee") == "operator" else "me"
            lines.append(f"  {glyph} {task['id'].ljust(width)}  {task['title']}  ({who})")
    return "\n".join(lines)


def outline() -> str:
    """The shape of the run, before a single answer is in.

    Said at the top of a setup, where the store is not settled yet and so a real board
    cannot be seeded. Rendered from the same task list rather than written out in the
    skill, because a run described in two places is a run described differently in two
    places.
    """
    folder = {t["key"] for t in _setup_tasks("folder")}
    lines = ["This is the whole run. Nothing is written until you say yes.", ""]
    for number, task in enumerate(_setup_tasks("service"), start=1):
        only = "" if task["key"] in folder else "   (only for a store service)"
        gate = "   <- the one place you are needed" if task["key"] == "plan" else ""
        lines.append(f"  {number}. {task['title']}{only}{gate}")
    lines += [
        "",
        "Then what is left is yours: sharing the folder or registering the server, "
        "releasing it, and telling the team what to say. Those go on the board too, "
        "once the answers say which of them apply.",
    ]
    return "\n".join(lines)


def cmd_outline(args: argparse.Namespace) -> dict[str, object]:
    return {"ok": True, "text": outline()}


def cmd_init(args: argparse.Namespace) -> dict[str, object]:
    directory = board_dir(args.into)
    existing = directory / TASKS_NAME
    if directory.exists() and any(directory.iterdir()) and not existing.is_file() and not args.force:
        raise BoardError(
            f"{directory} already has files in it and no {TASKS_NAME}, so it is not a "
            "board this factory wrote. Pass --force only if replacing it is what you mean"
        )
    if existing.is_file() and not args.restart:
        raise BoardError(
            f"{existing} already exists. Pass --restart to throw away that run's progress "
            "and seed a fresh board"
        )
    data = seed(args)
    redacted = save(args.into, data)
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BOARD_TEMPLATE, directory / "board.html")
    return {
        "ok": True,
        "board": str(directory / "board.html"),
        "tasks": str(existing),
        "count": len(data["tasks"]),
        "yours": sum(1 for t in data["tasks"] if t["assignee"] == "operator"),
        "redacted": redacted,
        "watch": f"cd {directory} && python3 -m http.server 4173",
        "text": render(data),
    }


def cmd_set(args: argparse.Namespace) -> dict[str, object]:
    data = load(args.into)
    task = find(data, args.task)
    if args.status:
        task["status"] = args.status
    if args.proof:
        task["proof"] = args.proof
    if args.evidence:
        task["evidence"] = args.evidence
    if args.body:
        task["body"] = args.body
    redacted = save(args.into, data)
    return {"ok": True, "task": find(data, args.task), "redacted": redacted}


def cmd_add(args: argparse.Namespace) -> dict[str, object]:
    """A task the run turned up that no plan could have predicted."""
    data = load(args.into)
    prefix = id_prefix(str(data["project"]))
    numbers = [
        int(t["id"].rsplit("-", 1)[-1])
        for t in data["tasks"]
        if t["id"].rsplit("-", 1)[-1].isdigit()
    ]
    task = {
        "id": f"{prefix}-{max(numbers, default=0) + 1}",
        "key": args.key or "",
        "title": args.title,
        "status": args.status,
        "priority": args.priority,
        "labels": [label.strip() for label in (args.labels or "").split(",") if label.strip()],
        "assignee": args.assignee,
        "body": args.body or "",
        "blockedBy": [find(data, b)["id"] for b in (args.blocked_by or [])],
    }
    data["tasks"].append(task)
    redacted = save(args.into, data)
    return {"ok": True, "task": task, "redacted": redacted}


def cmd_verdict(args: argparse.Namespace) -> dict[str, object]:
    data = load(args.into)
    data["verdict"] = {"state": args.state, "line": args.line}
    redacted = save(args.into, data)
    return {"ok": True, "verdict": data["verdict"], "redacted": redacted}


def cmd_show(args: argparse.Namespace) -> dict[str, object]:
    return {"ok": True, "text": render(load(args.into))}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="command", required=True)

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--into", required=True, help="the repo the Kit is written into")

    start = subs.add_parser("init", help="seed the board for one setup run")
    common(start)
    start.add_argument("--name", required=True, help="the Kit's name")
    start.add_argument("--store", required=True, choices=("folder", "service"))
    start.add_argument("--root", default=None, help="the synced directory, for a folder store")
    start.add_argument("--service-name", default=None, help="the name the server is registered under")
    start.add_argument("--server-route", default="org", choices=("org", "mcp-json"))
    start.add_argument("--server-location", default=None, help="where the server's source will live")
    start.add_argument("--kit-source", default=None, help="the Kit's path from the repo root")
    start.add_argument("--subtitle", default=None, help="one line under the name")
    start.add_argument("--restart", action="store_true", help="replace a board from an earlier run")
    start.add_argument("--force", action="store_true", help="write over a status/ this factory did not make")
    start.set_defaults(handler=cmd_init)

    change = subs.add_parser("set", help="mark one task, by its id or its key")
    common(change)
    change.add_argument("task")
    change.add_argument("--status", choices=STATUSES)
    change.add_argument("--proof", choices=PROOFS, help="proven here, or against a stand-in")
    change.add_argument("--evidence", help="what actually came back, in its own words")
    change.add_argument("--body", help="replace the task's description")
    change.set_defaults(handler=cmd_set)

    extra = subs.add_parser("add", help="a task this run turned up")
    common(extra)
    extra.add_argument("--title", required=True)
    extra.add_argument("--body", default=None)
    extra.add_argument("--key", default=None, help="a short name to address it by later")
    extra.add_argument("--labels", default=None, help="comma separated")
    extra.add_argument("--assignee", default="operator", choices=ASSIGNEES)
    extra.add_argument("--priority", default="medium", choices=("urgent", "high", "medium", "low"))
    extra.add_argument("--status", default="todo", choices=STATUSES)
    extra.add_argument("--blocked-by", action="append", default=None)
    extra.set_defaults(handler=cmd_add)

    call = subs.add_parser("verdict", help="the one line across the top")
    common(call)
    call.add_argument("--state", required=True, choices=("blocked", "ok"))
    call.add_argument("--line", required=True)
    call.set_defaults(handler=cmd_verdict)

    shape = subs.add_parser("outline", help="the shape of a run, before any answers")
    shape.set_defaults(handler=cmd_outline)

    look = subs.add_parser("show", help="print the board for the chat")
    common(look)
    look.set_defaults(handler=cmd_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except BoardError as exc:
        print(json.dumps({"ok": False, "say": str(exc)}, indent=2))
        return 2
    if args.command in ("show", "outline"):
        print(result["text"])
        return 0
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
