#!/usr/bin/env python3
"""Write a Kit — a tailored handoff plugin — into someone else's repository.

Scripted rather than done by hand, for one reason: this writes into a repo other
people ship from. A copy-and-substitute done from a skill is a copy-and-substitute
that is slightly different every time, and the difference only shows up in a
Teammate's session weeks later.

    python3 emit.py --into ../acme-plugins/plugins/acme-handoff \\
        --name acme-handoff --team "the Acme analytics team" --org Acme \\
        --store folder --root '~/OneDrive - Acme/Continuity' --namespace analytics

Prints JSON. Exit status is 0 on success, 2 on a refusal that names what to fix.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

FACTORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
FACTORY_URL = "https://github.com/100xopensource/100xtools"
KIT_CONFIG_NAME = "kit.json"
PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")

# How a Teammate's Claude reaches the store server. `org` — the Operator registers it
# with their organisation's connectors, so every Teammate has it without installing
# anything. `mcp-json` — the Kit carries a `.mcp.json` declaring the server itself,
# which is the answer for a team that cannot register one org-wide.
SERVER_ROUTES = ("org", "mcp-json")

# RFC 2606 reserves example.com precisely so a placeholder cannot resolve to somebody's
# host. A Kit emitted before its server exists ships this and says so in the notes.
PLACEHOLDER_SERVER_URL = "https://store.example.com/mcp"

# The Operator's own notes live in the destination repo's CLAUDE.md, between these.
# Everything outside them is somebody else's writing and is never touched. They carry the
# Kit's name because one repository can ship two Kits — a repo-wide marker would let the
# second emit silently eat the first one's notes.
NOTES_MARKER = "<!-- 100x-continuity:{name}:{edge} -->"

# Copied verbatim into every Kit. The Kit is a plugin someone installs, so it carries
# its own engine — nothing here is imported from the factory at runtime.
ENGINE_FILES = ("run.py",)
# Rendered on the way out, and checked for leftovers. `.yaml` is here for the eval
# cases: they carry no placeholder today, and including them is what stops one being
# added later and shipping as four braces and a word.
SUBSTITUTED_SUFFIXES = {".md", ".json", ".yaml", ".yml"}

# Eval cases that belong to one store only, by directory name. A folder Kit carrying a
# case about an unreachable server would be scoring a route that team never set up.
EXTRA_CASES = {"hand-off-stops-when-the-store-is-unreachable": "service"}


class EmitError(Exception):
    """A refusal the Operator can act on."""


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def factory_version() -> str:
    manifest = FACTORY_ROOT / ".claude-plugin" / "plugin.json"
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown")
    except (OSError, json.JSONDecodeError):
        return "unknown"


def store_sentence(store: str, *, root: str | None, service_name: str | None) -> str:
    """One plain sentence for the Kit's README — what a Teammate needs to know."""
    if store == "folder":
        return (
            f"Handoffs are kept in `{root}`, which your cloud drive syncs. Anyone who can "
            "open that folder can open every handoff in it, so treat one as visible to "
            "the whole team rather than to one person."
        )
    return (
        f"Handoffs are kept in object storage behind the `{service_name}` server your "
        "organisation runs. Each one is readable only by the people it was shared with, "
        "and the person who sent it decides who those are."
    )


# Which sync client owns a root, recognised from the path itself, plus the one thing about
# that client a Teammate's session has to know. A Kit is built for one store, so the client
# is knowable at emit time — and a skill told "don't go looking" has to be told where things
# are, or looking is the only thing left to do.
_SYNC_CLIENTS = (
    ("Mobile Documents/com~apple~CloudDocs", "iCloud Drive",
     "iCloud drops file contents to save disk and leaves the name in place, so a read can "
     "come back short. That means wait for it, never empty."),
    ("OneDrive", "OneDrive or SharePoint",
     "Under a single tenant the part after the home directory is usually identical on every "
     "machine, so this path travels."),
    ("Google Drive", "Google Drive",
     "In streaming mode Google Drive drops file contents and leaves the name, so a read can "
     "come back short. That means wait for it, never empty."),
    ("Dropbox", "Dropbox",
     "With Smart Sync on, Dropbox drops file contents and leaves the name, so a read can "
     "come back short. That means wait for it, never empty."),
)


def sync_client(root: str | None) -> tuple[str, str]:
    """The client that owns this root, and its one sharp edge. Generic if unrecognised."""
    for needle, name, note in _SYNC_CLIENTS:
        if needle.lower() in (root or "").lower():
            return name, note
    return (
        "a synced folder",
        "Whatever syncs it may drop file contents and leave the name in place, so a read "
        "can come back short. That means wait for it, never empty.",
    )


def tool_prefix(store: str, route: str, service_name: str | None) -> str:
    """How the store server's tools are most likely spelled in a Teammate's session.

    A server registered with an organisation's connectors arrives with a `claude_ai_`
    infix and a slugified name; one declared in a `.mcp.json` arrives under the name as
    written. Neither is a guarantee, which is why the skills are told to match on how a
    tool name *ends* and to treat this as the likely spelling rather than the rule.
    """
    if store != "service" or not service_name:
        return ""
    if route == "org":
        return f"mcp__claude_ai_{re.sub(r'[^A-Za-z0-9]', '_', service_name)}__"
    return f"mcp__{service_name}__"


def _substitutions(args: argparse.Namespace, emitted_at: str) -> dict[str, str]:
    return {
        "KIT_NAME": args.name,
        "KIT_DESCRIPTION": args.description
        or "Hand a Claude session to a colleague, and pick up one they handed to you.",
        "KIT_VERSION": args.kit_version,
        "LABEL": args.label or args.name,
        "ORG": args.org,
        "TEAM": args.team,
        "SERVICE_NAME": args.service_name or "",
        "STORE_ROOT": args.root or "",
        "NAMESPACE": args.namespace,
        "SYNC_CLIENT": sync_client(args.root)[0],
        "SYNC_NOTE": sync_client(args.root)[1],
        "SERVER_URL": args.server_url or PLACEHOLDER_SERVER_URL,
        "TOOL_PREFIX": tool_prefix(args.store, args.server_route, args.service_name),
        "STORE_SENTENCE": store_sentence(
            args.store, root=args.root, service_name=args.service_name
        ),
        "FACTORY_URL": FACTORY_URL,
        "FACTORY_VERSION": factory_version(),
        "EMITTED_AT": emitted_at,
    }


def _fragments(store: str, values: dict[str, str]) -> dict[str, str]:
    """The store-specific passages spliced into the skills, rendered on the way in.

    A Kit is built for one store and must not describe the other: a skill that offers
    two routes invites the model to try the one this team never set up.

    Rendering them here rather than relying on the splice is not tidiness. Substitution
    is a single pass, so a `{{TEAM}}` carried in by a fragment would never be filled —
    it would reach the Teammate's plugin as four braces and a word.
    """
    root = FACTORY_ROOT / "templates" / "kit" / "fragments"
    names = {
        "HANDOFF_STEPS": f"hand-off.{store}.md",
        "PICKUP_STEPS": f"pick-up.{store}.md",
        "CODE_SHAPE": f"codes.{store}.md",
        # A bad read means different things in the two stores. In a folder a sync
        # client can leave a placeholder, so short bytes mean wait; against a server
        # nothing is syncing and both damage kinds come back as one digest mismatch.
        # Shipping the folder wording to a service Kit told people to wait for a
        # download that was never going to arrive.
        "BAD_READ": f"damage.{store}.md",
        # The README's picture of how a handoff actually moves. Store-specific for the
        # same reason as everything else here: a diagram of a server this team never ran
        # is a diagram of somebody else's system.
        "ARCHITECTURE": f"diagram.{store}.md",
    }
    out = {}
    for key, filename in names.items():
        path = root / filename
        if not path.is_file():
            raise EmitError(f"the factory is missing {filename}, so no {store} Kit can be written")
        out[key] = render(path.read_text(encoding="utf-8").strip(), values)
    return out


def render(text: str, values: dict[str, str]) -> str:
    """Substitute, then refuse anything still unfilled.

    A `{{THING}}` that reaches a Teammate's plugin is worse than a failed emit: the
    skill still loads, still runs, and quietly instructs the model with a placeholder.
    """
    filled = PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
    leftover = sorted({m.group(1) for m in PLACEHOLDER.finditer(filled)})
    if leftover:
        raise EmitError(
            "nothing was written because these placeholders had no value: "
            + ", ".join(leftover)
        )
    return filled


def _check_target(into: pathlib.Path) -> None:
    resolved = into.expanduser().resolve()
    if resolved == FACTORY_ROOT or FACTORY_ROOT in resolved.parents:
        raise EmitError(
            "that path is inside the factory itself. A Kit belongs in the repository "
            "the team ships plugins from; writing one here helps nobody"
        )


def _plan_files(store: str, route: str) -> list[tuple[pathlib.Path, str]]:
    """Every file a Kit is made of, as (source, destination-relative-path)."""
    kit = FACTORY_ROOT / "templates" / "kit"
    files: list[tuple[pathlib.Path, str]] = []
    for path in sorted(kit.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(kit)
        if rel.parts[0] == "fragments":
            continue  # spliced in, never copied
        files.append((path, str(rel)))
    # Only a Kit that carries its own server declaration gets one. Shipping a `.mcp.json`
    # to a team whose server is an org connector would declare a second route to the same
    # place, and the one with the placeholder URL in it is the one that answers nothing.
    if store == "service" and route == "mcp-json":
        files.append((FACTORY_ROOT / "templates" / "kit-extras" / "mcp.json", ".mcp.json"))
    # Cases that only make sense for one store, for the same reason the skills split.
    extras = FACTORY_ROOT / "templates" / "kit-extras" / "evals"
    for path in sorted(extras.rglob("case.yaml")):
        if EXTRA_CASES.get(path.parent.name) == store:
            files.append((path, str(pathlib.PurePosixPath("evals") / path.parent.name / "case.yaml")))
    scripts = FACTORY_ROOT / "scripts"
    for name in ENGINE_FILES:
        files.append((scripts / name, f"scripts/{name}"))
    for path in sorted((scripts / "engine").glob("*.py")):
        files.append((path, f"scripts/engine/{path.name}"))
    return files


def operator_items(
    args: argparse.Namespace,
    kit_source: str,
    *,
    repo_root: pathlib.Path | None = None,
) -> list[dict[str, object]]:
    """What is left for the Operator after the Factory stops, as structured work.

    Built here rather than in the template because every line of it is a fact about the
    answers just given. A checklist assembled by hand in a skill is a checklist that
    quietly loses the item nobody remembered this time.

    Two surfaces read this: the checklist in the Operator's notes, which is a snapshot
    taken when the Kit was written, and the board, which stays live. They are generated
    from one list so they cannot come to disagree about what is outstanding.
    """
    items: list[dict[str, object]] = []
    # A marketplace is installed by cloning, so a destination that is not a repository
    # yet holds a plugin nobody can install however correct it is. Seen: a whole setup
    # run finished and the deliverable was unreachable for this reason alone.
    if repo_root is not None and not (repo_root / ".git").exists():
        items.append(
            {
                "key": "git-init",
                "title": f"Make `{repo_root.name}` a git repository",
                "body": (
                    "There is no `.git` here. A plugin marketplace is installed by "
                    "cloning, so until this is a repository your Teammates can reach, "
                    "nobody can install the Kit."
                ),
                "labels": ["repo"],
                "priority": "high",
            }
        )
    if args.store == "folder":
        items.append(
            {
                "key": "share-the-folder",
                "title": f"Share `{args.root}` with the team",
                "body": (
                    "Through whichever sync client owns it. Until that is done a handoff "
                    "opens only for the person who sent it, and the failure looks to them "
                    "like a bad code."
                ),
                "labels": ["store", "access"],
                "priority": "urgent",
            }
        )
    else:
        where = args.server_location or "wherever you decided to run it"
        items.append(
            {
                "key": "verified-principal",
                "title": "Replace `principal()` with an identity your infrastructure verified",
                "body": (
                    "It is the whole authorization model. Until it returns a caller the "
                    "deployment authenticated, and never one taken from a tool argument, "
                    "every caller is the same person. Remove `CONTINUITY_DEV_PRINCIPAL` "
                    "wherever it is set: it turns nobody into somebody."
                ),
                "labels": ["store", "security"],
                "priority": "urgent",
            }
        )
        items.append(
            {
                "key": "deploy",
                "title": f"Deploy the store server ({where})",
                "body": "The Dockerfile builds it; where it runs is yours.",
                "labels": ["store", "deploy"],
                "priority": "high",
                "blocked_by": ["verified-principal"],
            }
        )
        if args.server_route == "org":
            items.append(
                {
                    "key": "register",
                    "title": (
                        "Register the deployed server with your organisation's connectors "
                        f"under exactly the name `{args.service_name}`"
                    ),
                    "body": (
                        f"A Kit built against `{args.service_name}` and a server registered "
                        "under any other spelling never meet, and nothing reports it. The "
                        "tools are simply absent."
                    ),
                    "labels": ["store", "deploy"],
                    "priority": "urgent",
                    "blocked_by": ["deploy"],
                }
            )
        else:
            items.append(
                {
                    "key": "register",
                    "title": f"Put the deployed server's URL into `{kit_source}/.mcp.json`",
                    "body": (
                        f"Replacing `{PLACEHOLDER_SERVER_URL}`, which is a reserved example "
                        "domain and answers nothing on purpose. Re-run the factory with "
                        "`--server-url` rather than editing the file: a Kit is regenerated, "
                        "not edited."
                    ),
                    "labels": ["store", "deploy"],
                    "priority": "urgent",
                    "blocked_by": ["deploy"],
                }
            )
        items.append(
            {
                "key": "who-reads-what",
                "title": "Decide who reads what",
                "body": (
                    "A publication is readable by whoever sent it until they share it; "
                    "`set_publication_access` is the one place that list is edited."
                ),
                "labels": ["store", "access"],
                "priority": "medium",
            }
        )
        items.append(
            {
                "key": "retention",
                "title": "Set a retention policy on the bucket",
                "body": (
                    "Publications accumulate forever by default, and they hold redacted "
                    "prompts and whatever files people chose to send. Redacted is not the "
                    "same as safe. Decide the period rather than inheriting never delete."
                ),
                "labels": ["store", "security"],
                "priority": "medium",
            }
        )
        items.append(
            {
                "key": "re-verify",
                "title": "Run `verify` again against the registered server",
                "body": (
                    "The only thing that proves the Kit and the server found each other. "
                    "Everything proven during setup went through a local process this "
                    "machine was pointed at by hand."
                ),
                "labels": ["kit", "test"],
                "priority": "high",
                "blocked_by": ["register"],
            }
        )
    if args.store == "service":
        items.append(
            {
                "key": "stop-the-local-server",
                "title": "Stop the store server this run started on your machine",
                "body": (
                    "It holds a live storage credential in its environment and it does "
                    "not stop when the conversation does. One was found still listening "
                    "a day later with its source already in the Trash."
                ),
                "labels": ["store", "security"],
                "priority": "high",
            }
        )
    items.append(
        {
            "key": "run-the-evals",
            "title": "Run the Kit's eval suite once, and decide if it is worth repeating",
            "body": (
                "The contract test is free and proves the engine. These score what the "
                "*model* does with the two skills, which is the half a deterministic "
                "test cannot see, and they cost money — so nothing runs them for you. "
                f"From `{kit_source}`: `{eval_invocation(args.store)}`"
            ),
            "labels": ["kit", "test"],
            "priority": "medium",
        }
    )
    items.append(
        {
            "key": "release",
            "title": "Release it the way this repo releases plugins",
            "body": (
                "Nothing here was branched, committed, or pushed, and until the marketplace "
                f"row reaches your default branch nobody can install `{args.name}`."
            ),
            "labels": ["repo"],
            "priority": "high",
        }
    )
    items.append(
        {
            "key": "tell-the-team",
            "title": "Tell the team the two sentences that drive it",
            "body": (
                "*hand this over to <name>* at the end of a piece of work, and *pick up "
                "what <name> sent me — <code>* at the start."
            ),
            "labels": ["kit"],
            "priority": "medium",
            "blocked_by": ["release"],
        }
    )
    items.append(
        {
            "key": "teammate-pick-up",
            "title": "Have somebody else pick a handoff up",
            "body": (
                "From their own machine and their own account. This is the failure the "
                "whole exercise exists to catch, a Kit that works only for the person who "
                "built it, and until it happens the receiving half is unproven however "
                "green everything else looks."
            ),
            "labels": ["test"],
            "priority": "urgent",
            "blocked_by": ["release"],
        }
    )
    items.append(
        {
            "key": "re-run-contract",
            "title": "Re-run the contract test after anyone changes the Kit",
            "body": (
                f"`cd {kit_source} && python3 tests/contract_test.py`. It is deterministic, "
                "free, and needs no model."
            ),
            "labels": ["kit", "test"],
            "priority": "low",
        }
    )
    return items


def operator_todo(
    args: argparse.Namespace,
    kit_source: str,
    *,
    repo_root: pathlib.Path | None = None,
) -> str:
    """The same work as a checklist, for the Operator's notes."""
    return "\n".join(
        f"- [ ] **{item['title']}.** {item['body']}"
        for item in operator_items(args, kit_source, repo_root=repo_root)
    )


def error_codes() -> str:
    """The engine's failure codes, as a table in the Operator's notes.

    Rendered from the registry rather than written out, because the notes tell the
    Operator to drive the engine from their own code and a code they cannot branch on
    reliably is worse than no code at all. `cli.ERROR_CODES` is the only source.
    """
    sys.path.insert(0, str(FACTORY_ROOT / "scripts"))
    from engine import cli  # noqa: PLC0415

    rows = ["| `code` | `fix_by` | `remedy` |", "| --- | --- | --- |"]
    for code in sorted(cli.ERROR_CODES):
        origin, fix_by, remedy = cli.ERROR_CODES[code]
        rows.append(f"| `{code}` | `{fix_by}` | {remedy or '*nothing recognised it*'} |")
    return "\n".join(rows)


def board_note(repo_root: pathlib.Path | None) -> str:
    """A pointer to the board, but only for a repo that has one.

    This checklist is a snapshot taken the moment the Kit was written; the board keeps
    moving. Sending a reader to a file the run never made would be worse than sending
    them nowhere, so a Kit emitted without one says nothing about it.
    """
    if repo_root is None or not (repo_root / "status" / "tasks.json").is_file():
        return ""
    return (
        "The live version of this list is the board the setup run left behind. It holds "
        "the same items plus whatever that run turned up, and it says which are waiting "
        "on which:\n\n"
        "```bash\n"
        "cd status && python3 -m http.server 4173    # then open localhost:4173/board.html\n"
        "```\n"
    )


def engine_commands(store: str, kit_source: str) -> str:
    """The four commands worth knowing, for this Kit's store and no other.

    A Kit describes one store. Notes that list `publish` beside `pack` invite whoever
    reads them next to reach for the half this team never set up.
    """
    lines = [f"python3 {kit_source}/scripts/run.py where"]
    if store == "folder":
        lines += [
            f"python3 {kit_source}/scripts/run.py publish --help",
            f"python3 {kit_source}/scripts/run.py open --help",
        ]
        notes = ["which store, and what decided it", "package it and file it", "read one back"]
    else:
        lines += [
            f"python3 {kit_source}/scripts/run.py pack --help",
            f"python3 {kit_source}/scripts/run.py upload --help",
            f"python3 {kit_source}/scripts/run.py fetch --help",
        ]
        notes = [
            "which store, and what decided it",
            "package it, without sending it",
            "send it to a minted address",
            "read one back from a minted address",
        ]
    width = max(len(line) for line in lines)
    return "\n".join(f"{line.ljust(width)}   # {note}" for line, note in zip(lines, notes))


# What each Kit eval pins down, as the rows of the table in the Kit's evals/README.md.
# Rendered rather than copied so a Kit lists the cases it actually has.
_EVAL_ROWS = (
    ("hand-off-fires-on-natural-words", 'routing from "hand this over to Dana"', None),
    ("hand-off-stays-out-of-an-ordinary-write", "that saving a note does not package a session", None),
    ("hand-off-never-claims-what-it-did-not-do", "that a handoff which stopped is reported as stopped", None),
    ("hand-off-stops-when-the-store-is-unreachable", "that an unreachable store stops the handoff", "service"),
    ("pick-up-fires-on-a-pasted-code", "routing from a pasted code alone", None),
    ("pick-up-explains-an-unknown-code", "a code that opens nothing invents nothing", None),
    ("errors-stay-in-plain-words", "the failure path repeats `say`, never `hint`", None),
)


def eval_invocation(store: str) -> str:
    """How to run these cases, with the flags without which they do not run at all.

    `claude plugin eval` is an early-access command, and the environment variables are
    what admit you to it. The rest are not decoration either: scored on the wrong surface,
    or without the store's tools, every case fails in a way that reads like a broken skill.
    """
    grants = "Bash Write 'mcp__*'" if store == "service" else "Bash Write"
    lines = [
        "```bash",
        "CLAUDE_CODE_WALNUT_SPIRE=1 CLAUDE_CODE_ENTRYPOINT=remote_cowork \\",
        "  claude plugin eval . --ablation none --judge-model sonnet \\",
        f"    --allow-tools {grants}",
        "```",
        "",
        "Every part of that line is load-bearing:",
        "",
        "- `CLAUDE_CODE_WALNUT_SPIRE=1` — `claude plugin eval` is an early-access command",
        "  and does not run without it.",
        "- `CLAUDE_CODE_ENTRYPOINT=remote_cowork` — these skills are used in Cowork, so its",
        "  system prompt is the one they have to work under. Scored anywhere else, you are",
        "  scoring a surface nobody here has.",
        f"- `--allow-tools {grants}` — **the one to check first when every case passes and you",
        "  do not believe it.** `Bash` and `Write` are gated, and without the grant the skills",
        "  are refused the tool they need to reach their own engine. A refusal reads a lot like",
        "  a handoff that could not be made, so the cases go green having tested nothing.",
    ]
    if store == "service":
        lines += [
            "  `mcp__*` is there for the same reason: no store server tools, no handoff.",
        ]
    lines += [
        "- `--ablation none` — one arm, the plugin exactly as it ships.",
        "- `--judge-model sonnet` — the model behind the `llm` graders.",
    ]
    return "\n".join(lines)


def eval_table(store: str) -> str:
    return "\n".join(
        f"| `{name}` | {pins} |" for name, pins, only in _EVAL_ROWS if only in (None, store)
    )


def _notes_section(values: dict[str, str]) -> str:
    template = FACTORY_ROOT / "templates" / "operator-notes.md"
    if not template.is_file():
        raise EmitError("the factory is missing templates/operator-notes.md")
    return render(template.read_text(encoding="utf-8").strip(), values)


def notes_markers(kit_name: str) -> tuple[str, str]:
    """This Kit's own pair of markers in the destination repo's CLAUDE.md."""
    return (
        NOTES_MARKER.format(name=kit_name, edge="begin"),
        NOTES_MARKER.format(name=kit_name, edge="end"),
    )


def write_operator_notes(repo_root: pathlib.Path, section: str, kit_name: str) -> dict[str, str]:
    """Put the Operator's notes in the destination repo's CLAUDE.md.

    Marked, and merged rather than replaced: that file is usually somebody's own writing
    about their own repo, and a factory that overwrites it has destroyed the thing it was
    trying to add to. Only what sits between this Kit's own markers is ever rewritten.
    """
    path = repo_root / "CLAUDE.md"
    begin, end = notes_markers(kit_name)
    block = f"{begin}\n{section.strip()}\n{end}\n"
    if not path.exists():
        # Created about the handoff system and nothing else. Titling a fresh file after
        # the repository would claim to describe the whole of it, and this knows about
        # exactly one plugin in it — the rest is the Operator's to write, around ours.
        preamble = (
            "# CLAUDE.md\n\n"
            "Guidance for Claude Code working in this repository.\n\n"
            f"The marked section below is generated. It describes `{kit_name}`, the "
            "session-handoff plugin in this repo, and it is rewritten whenever that "
            "plugin is regenerated. Anything written outside the markers is left alone, "
            "so this is a good place to put the rest of what Claude should know here.\n\n"
        )
        path.write_text(preamble + block, encoding="utf-8")
        return {"path": str(path), "action": "created"}
    current = path.read_text(encoding="utf-8")
    if begin in current and end in current:
        head = current.split(begin)[0]
        tail = current.split(end, 1)[1]
        path.write_text(head + block.rstrip("\n") + tail, encoding="utf-8")
        return {"path": str(path), "action": "updated"}
    path.write_text(current.rstrip("\n") + "\n\n" + block, encoding="utf-8")
    return {"path": str(path), "action": "appended"}


def emit(args: argparse.Namespace) -> dict[str, object]:
    into = pathlib.Path(args.into).expanduser()
    _check_target(into)
    if args.store == "folder" and not args.root:
        raise EmitError("a folder Kit needs --root: the synced directory handoffs are filed in")
    if args.store == "service" and not args.service_name:
        raise EmitError(
            "a service Kit needs --service-name: the name the MCP server is registered "
            "under, which is the only way a Teammate's Claude finds it"
        )
    if args.server_route not in SERVER_ROUTES:
        raise EmitError(
            f"--server-route must be one of {', '.join(SERVER_ROUTES)}, not {args.server_route!r}"
        )

    # Resolved before anything is written: a marketplace path that cannot describe this
    # Kit is a wrong --into, and finding that out afterwards leaves a half-emitted plugin
    # in someone's repo.
    market_source = _source_path(into, args.marketplace)

    emitted_at = _stamp()
    values = _substitutions(args, emitted_at)
    values["OPERATOR_TODO"] = operator_todo(args, market_source, repo_root=_notes_root(args))
    values["ENGINE_COMMANDS"] = engine_commands(args.store, market_source)
    values["EVAL_TABLE"] = eval_table(args.store)
    values["EVAL_INVOCATION"] = eval_invocation(args.store)
    values["KIT_SOURCE"] = market_source
    values["BOARD_NOTE"] = board_note(_notes_root(args))
    values["ERROR_CODES"] = error_codes()
    values.update(_fragments(args.store, values))

    existing = into / KIT_CONFIG_NAME
    updating = existing.is_file()
    if into.exists() and not updating and any(into.iterdir()) and not args.force:
        raise EmitError(
            f"{into} already has files in it and no {KIT_CONFIG_NAME}, so it was not "
            "written by this factory. Pass --force only if replacing it is what you mean"
        )

    written, overwrote = [], []
    for template, rel in _plan_files(args.store, args.server_route):
        destination = into / rel
        body = template.read_bytes()
        if template.suffix in SUBSTITUTED_SUFFIXES:
            body = render(body.decode("utf-8"), values).encode("utf-8")
        if args.dry_run:
            written.append(rel)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != body:
            overwrote.append(rel)
        destination.write_bytes(body)
        written.append(rel)

    kit_config = {
        "store": args.store,
        "root": args.root or "",
        "namespace": args.namespace,
        "service_name": args.service_name or "",
        "label": args.label or args.name,
        "kit_name": args.name,
        "factory_version": values["FACTORY_VERSION"],
        "emitted_at": emitted_at,
    }
    if not args.dry_run:
        (into / KIT_CONFIG_NAME).write_text(
            json.dumps(kit_config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    written.append(KIT_CONFIG_NAME)

    entry = {
        "name": args.name,
        "source": market_source,
        "description": values["KIT_DESCRIPTION"],
        "version": args.kit_version,
    }
    marketplace = _update_marketplace(args, entry) if args.marketplace else None

    # The Factory runs once. Everything it knows that outlives the conversation goes in
    # the destination repo's CLAUDE.md, because that is the file the next person to open
    # this repo actually reads — including the next Claude.
    repo_root = _notes_root(args)
    notes: dict[str, str] | None = None
    if repo_root is None:
        notes = {"action": "skipped", "why": "no --marketplace or --repo, so no repo root"}
    elif args.dry_run:
        notes = {"path": str(repo_root / "CLAUDE.md"), "action": "skipped-dry-run"}
    else:
        notes = write_operator_notes(repo_root, _notes_section(values), args.name)

    return {
        "ok": True,
        "updated": updating,
        "kit": str(into),
        "kit_config": kit_config,
        "files": sorted(set(written)),
        "overwrote": sorted(overwrote),
        "marketplace": marketplace,
        "marketplace_entry": entry,
        "operator_notes": notes,
        "server_route": args.server_route if args.store == "service" else None,
        "dry_run": bool(args.dry_run),
        "next_step": (
            "run `verify` against this directory before anyone ships it"
            if args.store == "folder"
            else "stand the store service up and register it, then run `verify`"
        ),
    }


def _notes_root(args: argparse.Namespace) -> pathlib.Path | None:
    """The repo the Kit was written into, which is where the Operator's notes belong."""
    if args.repo:
        return pathlib.Path(args.repo).expanduser().resolve()
    if args.marketplace:
        return pathlib.Path(args.marketplace).expanduser().resolve().parent.parent
    return None


def _source_path(into: pathlib.Path, marketplace: str | None) -> str:
    """A marketplace `source` is relative to the repo root, not to the manifest.

    Getting this wrong produces a manifest that validates and an install that finds
    nothing, which is a worse failure than a manifest that refuses to parse.
    """
    if not marketplace:
        return str(into)
    root = pathlib.Path(marketplace).expanduser().resolve().parent.parent
    resolved = into.expanduser().resolve()
    try:
        return "./" + resolved.relative_to(root).as_posix()
    except ValueError:
        raise EmitError(
            f"{into} is outside {root}, so no marketplace row can point at it. Write the "
            "Kit inside the repo that owns that marketplace.json"
        ) from None


def _update_marketplace(args: argparse.Namespace, entry: dict[str, str]) -> dict[str, object]:
    """Add or refresh this Kit's row, leaving every other row exactly as it was."""
    path = pathlib.Path(args.marketplace).expanduser()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EmitError(
            f"{path} does not exist. Point --marketplace at the repo's "
            "`.claude-plugin/marketplace.json`, or leave it off and add the row by hand"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EmitError(f"{path} is not valid JSON ({exc}), so it was left untouched") from exc

    plugins = document.setdefault("plugins", [])
    if not isinstance(plugins, list):
        raise EmitError(f"{path} has a `plugins` key that is not a list, so it was left untouched")
    action = "added"
    for index, row in enumerate(plugins):
        if isinstance(row, dict) and row.get("name") == entry["name"]:
            plugins[index] = {**row, **entry}
            action = "updated"
            break
    else:
        plugins.append(entry)
    if not args.dry_run:
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path), "action": action, "plugins": len(plugins)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--into", required=True, help="the plugin directory to write")
    parser.add_argument("--name", required=True, help="the Kit's plugin name")
    parser.add_argument("--team", required=True, help="who it is for, in their own words")
    parser.add_argument("--org", required=True, help="the organisation it is built for")
    parser.add_argument("--store", required=True, choices=("folder", "service"))
    parser.add_argument("--root", help="folder store: the synced directory to file into")
    parser.add_argument("--namespace", default="default", help="the group within the store")
    parser.add_argument("--service-name", help="service store: the registered MCP server name")
    parser.add_argument(
        "--server-route",
        default="org",
        choices=SERVER_ROUTES,
        help="how Teammates reach the server: an org connector, or a .mcp.json in the Kit",
    )
    parser.add_argument(
        "--server-url",
        help="service store on the mcp-json route: the server's URL, if it exists yet",
    )
    parser.add_argument(
        "--server-location",
        help="where the server's source lives, in the Operator's words; for the notes only",
    )
    parser.add_argument("--description", help="one line for the marketplace row")
    parser.add_argument(
        "--label",
        default=None,
        help="what a person calls this work, used in the sentence a Teammate pastes "
        "(default: the Kit's name)",
    )
    parser.add_argument("--kit-version", default="0.1.0")
    parser.add_argument("--marketplace", help="marketplace.json to add or refresh a row in")
    parser.add_argument("--repo", help="the destination repo root; defaults to the marketplace's")
    parser.add_argument("--force", action="store_true", help="write into a non-empty directory")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = emit(args)
    except EmitError as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
