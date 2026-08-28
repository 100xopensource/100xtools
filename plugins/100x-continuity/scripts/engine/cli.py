"""The command surface: JSON in, JSON out, one command per thing a skill does.

Claude drives this plugin through this module, so every command prints **JSON on
stdout and nothing else** — a human-readable line would have to be parsed back out of
the model's context, and a half-parsed status is worse than none. A failure carries
`ok: false` and an `error` object — `code`, `op`, `origin`, `fix_by`, `remedy` and a
quarantined `hint` — then exits non-zero. See `ERROR_CODES` for the closed set.

The commands split three ways, which is also how the three skills split:

- **`config`, `where`, `sessions`** — what is set up, and what this machine can see.
- **`pack`, `publish`** — take this session across the boundary. `publish` files the
  bundle in a folder store; `pack` stops with the bundle on disk, which is what the
  service store needs before it can ask its server to mint an upload URL.
- **`fetch`, `open`** — the receiving side. `open` verifies and unpacks a bundle,
  whether it came from a shared folder or a download.

`upload` and `fetch` are the only commands that touch the network, and both send bytes
to a URL something else minted — see `wire.py` for what they refuse.

Configuration resolves flag → environment → config file → default, so `setup` writes
the answers once and nothing has to pass them again. `--session` is the supported way
to name a session: a skill writes `${CLAUDE_SESSION_ID}` in its markdown and the
engine substitutes it before the model reads it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import tempfile
from typing import Any

from engine import (
    bundle as bundle_mod,
    config,
    digest as digest_mod,
    keys,
    redact,
    store as store_mod,
    transcript as transcript_mod,
    download as download_mod,
    upload as upload_mod,
    wire,
)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run one command, print its JSON result."""
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2
    try:
        _emit(args.handler(args))
        return 0
    except (
        bundle_mod.BundleError,
        config.ConfigError,
        store_mod.StoreError,
        wire.TransferError,
        ValueError,
        OSError,
    ) as exc:
        _emit({"ok": False, "error": describe(exc, getattr(args, "command", None))})
        return 1


# --- how a failure is described ----------------------------------------------
#
# A failure is not a sentence. It is a set of facts a caller acts on: which command was
# running, which component broke, who can do anything about it, and what that person
# would do. The Kit's skills compose from those; a script branches on `code`.
#
# There used to be a `say` here — one pre-written sentence a skill repeated verbatim.
# It was replaced because its fallback, which is by construction the branch every
# unrecognised failure lands in, read "nothing was sent". True while publishing, a lie
# while picking up: the sender's half had worked and only the reading back had failed,
# and the person was told their colleague had failed them.
#
# `hint` stays quarantined. It is this engine's own wording — bundle, transcript,
# manifest — and it is there to be understood, never quoted at a Teammate.


class UnknownCode(Exception):
    """A code with no row in the registry. Raised rather than passed through.

    An unregistered code is one somebody added in a hurry, and it reaches whoever
    drives this engine from their own code as a string they cannot branch on.
    """


# Which half of the exchange a command belongs to. This is the distinction the old
# single fallback sentence did not have, and not having it is what let a failed
# *receive* be reported as "nothing was sent".
SENDING_OPS = frozenset({"pack", "publish", "upload"})
RECEIVING_OPS = frozenset({"fetch", "open"})


def side(op: str | None) -> str:
    if op in SENDING_OPS:
        return "sending"
    if op in RECEIVING_OPS:
        return "receiving"
    return "neither"


# code -> (origin, fix_by, remedy). `origin` is the component that broke; `fix_by` is
# the person who can act, and they are not the same — a publication whose bytes are
# gone breaks at the store and is fixable only by whoever sent it.
#
# Every row is part of the contract with whoever drives the engine from their own code,
# so the set is closed, `UnknownCode` is raised for anything outside it, and
# `emit.error_codes()` renders it into the Operator's notes. `remedy` is written for a
# person: this engine's own vocabulary belongs in `hint` and nowhere else.
ERROR_CODES: dict[str, tuple[str, str, str | None]] = {
    "session.not_found": (
        "input", "user",
        "open this in the conversation you want to send, or name it with --session",
    ),
    "session.not_materialized": (
        "input", "user",
        "wait for your cloud drive to finish fetching it, then try again",
    ),
    "input.credential_detected": (
        "input", "user",
        "take the value out, leave that file behind, or send without it",
    ),
    "input.file_missing": (
        "input", "user",
        "that file is not where it was named; check the path and try again",
    ),
    "input.not_a_bundle": (
        "input", "user",
        "what was pointed at is not a packaged handoff; pack one first",
    ),
    "usage.invalid": (
        "input", "user",
        "one of the values given was not usable; nothing was changed",
    ),
    "config.rejected": (
        "input", "operator",
        "this build cannot work the way it has been configured",
    ),
    "bundle.digest_mismatch": (
        "network", "sender",
        "ask them to send it again; it costs them nothing",
    ),
    "bundle.damaged": (
        "input", "sender",
        "what arrived cannot be opened; ask them to send it again",
    ),
    "store.unreachable": (
        "store", "operator",
        "the store is not answering from here",
    ),
    "store.object_missing": (
        "store", "sender",
        "ask them to hand it over again, which will give them a new code",
    ),
    "store.url_expired": (
        "store", "sender",
        "ask them to hand it over again; the address they gave you has run out",
    ),
    "store.access_denied": (
        "store", "sender",
        "ask whoever sent it to share it with you",
    ),
    "store.too_large": (
        "store", "user",
        "this is too big for the store to take; leave the largest files out",
    ),
    "store.bad_answer": (
        "store", "operator",
        "the store's reply was not usable, so nothing was transferred",
    ),
    "handle.unknown": (
        "input", "user",
        "check the code with the person who sent it",
    ),
    "network.refused": (
        "network", "operator",
        "the address this was pointed at is not one it will use",
    ),
    # The catch-all carries no remedy on purpose. Anything written here would be a
    # claim about a failure nothing recognised, and the last one of those was wrong.
    "engine.unknown": ("engine", "operator", None),
}

FALLBACK_CODE = "engine.unknown"

# `wire.TransferError` already carries a stable code for exactly this reason, so the
# transfer path is classified structurally rather than by matching on prose.
_TRANSFER_CODES: dict[str, str] = {
    "target_missing": "store.object_missing",
    "empty_body": "store.object_missing",
    "url_expired_or_forbidden": "store.url_expired",
    "store_unavailable": "store.unreachable",
    "unreachable": "store.unreachable",
    "body_too_large": "store.too_large",
    "digest_mismatch": "bundle.digest_mismatch",
    "not_accepted": "store.bad_answer",
    "bad_mint": "store.bad_answer",
    "body_unreadable": "store.bad_answer",
    "insecure_url": "network.refused",
    "invalid_url": "network.refused",
    "credentials_in_url": "network.refused",
    "unexpected_redirect": "network.refused",
    "host_not_allowed": "network.refused",
}

# An archive that will not open is the same fault with two different owners: pointing
# at the wrong file while sending, or being handed a broken one while receiving. Which
# it is comes from the command, not from the wording.
_BY_SIDE: dict[str, dict[str, str]] = {
    "archive": {"sending": "input.not_a_bundle", "receiving": "bundle.damaged"},
}

# The engine's own wording -> a code, or a `_BY_SIDE` key. Ordered: the first match
# wins, so the specific cases sit above the catch-alls.
_CODE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"no transcript directory|no session|transcript.*not found", re.I),
     "session.not_found"),
    (re.compile(r"not materiali[sz]ed|short bytes|still (?:down)?loading", re.I),
     "session.not_materialized"),
    (re.compile(r"credential|secret|password|\.env\b|private key", re.I),
     "input.credential_detected"),
    (re.compile(r"digest|sha256|checksum", re.I), "bundle.digest_mismatch"),
    (re.compile(r"not a zip|no manifest|unsafe|refus\w+ member|absolute path"
                r"|symlink|outside|corrupt|archive", re.I), "archive"),
    (re.compile(r"no tool matching|not answering|unreachable", re.I),
     "store.unreachable"),
    (re.compile(r"never uploaded|no object|404", re.I), "store.object_missing"),
    # Above the access rule: a handle naming nothing is not a permission problem, and
    # telling somebody to ask for access to something that does not exist wastes both
    # their time and the sender's.
    (re.compile(r"no publication at that handle|nothing at that|unknown handle"
                r"|publication id", re.I), "handle.unknown"),
    (re.compile(r"not available to you|access denied|not yours", re.I),
     "store.access_denied"),
    (re.compile(r"^\[Errno 2\]|no such file or directory", re.I),
     "input.file_missing"),
    (re.compile(r"ConfigError", re.I), "config.rejected"),
    (re.compile(r"must (?:be|contain|carry)|is required|unrecognised argument", re.I),
     "usage.invalid"),
)


def classify(exc: Exception, hint: str, op: str | None = None) -> str:
    """Which registered code this failure is, or the catch-all."""
    if isinstance(exc, wire.TransferError) and exc.code in _TRANSFER_CODES:
        return _TRANSFER_CODES[exc.code]
    for pattern, code in _CODE_RULES:
        if pattern.search(hint) or pattern.search(type(exc).__name__):
            if code in _BY_SIDE:
                return _BY_SIDE[code].get(side(op), FALLBACK_CODE)
            return code
    return FALLBACK_CODE


def describe(exc: Exception, op: str | None) -> dict[str, Any]:
    """The whole failure, as facts. Never a sentence to be repeated."""
    hint = str(exc)
    code = classify(exc, hint, op)
    if code not in ERROR_CODES:
        raise UnknownCode(f"{code!r} is not in ERROR_CODES")
    origin, fix_by, remedy = ERROR_CODES[code]
    return {
        "code": code,
        "op": op,
        "origin": origin,
        "fix_by": fix_by,
        "remedy": remedy,
        "hint": hint,
        "exception": type(exc).__name__,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="continuity",
        description="Publish a Claude session so someone else can continue it.",
    )
    sub = parser.add_subparsers(dest="command")

    def shared(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--store", help="folder or service (default: folder)")
        p.add_argument("--root", help="the folder store's root directory")
        p.add_argument("--namespace", help="separates unrelated projects in one store")
        p.add_argument("--session", help="session id (default: unattributed)")
        return p

    def staging(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument(
            "--artifact", action="append", default=[], help="a file to include (repeatable)"
        )
        p.add_argument(
            "--artifacts-from-dir",
            action="append",
            default=[],
            help="include every file under this directory (repeatable)",
        )
        p.add_argument(
            "--artifact-root",
            help="paths inside the bundle are taken relative to this (default: cwd)",
        )
        p.add_argument(
            "--no-record",
            action="store_true",
            help="include the digest but not the full transcript record",
        )
        p.add_argument(
            "--confirm",
            help="a phrase from this conversation, checked against the transcript's tail",
        )
        p.add_argument(
            "--allow-sensitive-names",
            action="store_true",
            help="include a file whose name usually holds credentials",
        )
        p.add_argument(
            "--allow-flagged-artifacts",
            action="store_true",
            help="include an artifact holding credential-shaped values, as it stands",
        )
        return p

    cfg = shared(sub.add_parser("config", help="show or write the stored configuration"))
    cfg.add_argument("--set-store", help="folder or service")
    cfg.add_argument("--set-root", help="the folder store's root directory")
    cfg.add_argument("--set-namespace")
    cfg.add_argument("--set-service", help="name of the MCP server that mints URLs")
    cfg.add_argument("--path", help="write to this file instead of the default location")
    cfg.set_defaults(handler=_cmd_config)

    where = shared(sub.add_parser("where", help="resolved settings and the paths behind them"))
    where.set_defaults(handler=_cmd_where)

    sessions = shared(sub.add_parser("sessions", help="this session, and what is published"))
    sessions.set_defaults(handler=_cmd_sessions)

    pack = staging(shared(sub.add_parser("pack", help="build a bundle without filing it")))
    pack.add_argument("--out", help="directory to write the bundle into")
    pack.set_defaults(handler=_cmd_pack)

    publish = staging(
        shared(sub.add_parser("publish", help="build a bundle and file it in the folder store"))
    )
    publish.set_defaults(handler=_cmd_publish)

    up = shared(sub.add_parser("upload", help="send a bundle to a minted upload URL"))
    up.add_argument("--bundle", required=True, help="the bundle file to send")
    up.add_argument("--mint-file", help="JSON mint result to read; omit to read stdin")
    up.set_defaults(handler=_cmd_upload)

    fetch = shared(sub.add_parser("fetch", help="pull a bundle from a minted download URL"))
    fetch.add_argument("--out", required=True, help="file to write the bundle to")
    fetch.add_argument("--mint-file", help="JSON mint result to read; omit to read stdin")
    fetch.add_argument("--sha256", help="the bundle digest the server reported")
    fetch.set_defaults(handler=_cmd_fetch)

    opened = shared(sub.add_parser("open", help="verify a bundle and read it back"))
    opened.add_argument("--handle", help="a publication path, or namespace/session/id")
    opened.add_argument("--bundle", help="a bundle file, e.g. one just fetched")
    opened.add_argument("--out", help="directory to unpack into (default: a temp directory)")
    opened.set_defaults(handler=_cmd_open)
    return parser


def _stamp(now: dt.datetime | None = None) -> str:
    """A filename-safe UTC stamp. The clock is read once per command, here."""
    moment = now or dt.datetime.now(dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso(now: dt.datetime | None = None) -> str:
    moment = now or dt.datetime.now(dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _settings(args: argparse.Namespace) -> dict[str, Any]:
    return config.settings(
        store_flag=getattr(args, "store", None),
        root_flag=getattr(args, "root", None),
        namespace_flag=getattr(args, "namespace", None),
        session_flag=getattr(args, "session", None),
    )


def _cmd_config(args: argparse.Namespace) -> dict[str, Any]:
    """Show the configuration, or write it — `setup`'s one write."""
    wants_write = any(
        (args.set_store, args.set_root, args.set_namespace, args.set_service)
    )
    if not wants_write:
        cfg = _settings(args)
        return {"ok": True, "wrote": False, **cfg}

    current = config.load_file()["values"]
    store = config.check_store_kind(args.set_store or current.get("store") or config.DEFAULT_STORE_KIND)
    written = config.write(
        store=store,
        root=args.set_root or current.get("root"),
        namespace=args.set_namespace or current.get("namespace"),
        service_name=args.set_service or current.get("service_name"),
        stamp=_iso(),
        path=pathlib.Path(args.path).expanduser() if args.path else None,
    )
    result = {"ok": True, "wrote": True, **written}
    if store == "folder":
        root = pathlib.Path(written["config"]["root"])
        result["root_exists"] = root.exists()
        # Not created here. `setup` shows the user the path before anything writes to
        # it, and a store root brought into existence by a diagnostic is how work
        # ends up in a directory nobody is syncing.
        result["note"] = (
            "the root is not created until the first publish — check it is the folder "
            "your sync client watches"
        )
    else:
        result["note"] = (
            "a service store holds no path: publish with `pack`, then have the MCP "
            "server mint an upload URL"
        )
    return result


def _cmd_where(args: argparse.Namespace) -> dict[str, Any]:
    """Everything resolved, and where each answer came from. Creates nothing."""
    cfg = _settings(args)
    found = transcript_mod.discover(session_id=cfg["session"])
    result = {
        "ok": True,
        "store": cfg["store"],
        "namespace": keys.normalize_namespace(cfg["namespace"]),
        "session_slot": keys.session_slot(cfg["session"]),
        "config_path": cfg["config_path"],
        "config_searched": cfg["config_searched"],
        "sources": cfg["sources"],
        "service_name": cfg["service_name"],
        # The word a Teammate pastes. `where` is the one command that answers "what did
        # this Kit actually resolve to", so it has to be here or nobody can check it.
        "label": cfg["label"],
        "transcript_roots": [str(root) for root in transcript_mod.roots()],
        "transcript": str(found.path) if found.ok else None,
        "transcript_notes": list(found.notes),
        **_session_note(keys.normalize_session_id(cfg["session"]) is not None),
    }
    if cfg["store"] == "folder":
        root = pathlib.Path(cfg["root"])
        result["root"] = str(root)
        result["root_exists"] = root.exists()
        result["session_path"] = str(
            root / result["namespace"] / result["session_slot"]
        )
    if cfg["config_unknown_keys"]:
        result["config_unknown_keys"] = cfg["config_unknown_keys"]
    return result


def _cmd_sessions(args: argparse.Namespace) -> dict[str, Any]:
    """Both halves of the picture: what is here, and what has been published.

    One list without the other has people concluding the plugin is broken when the
    session simply was never published — or looking for a publication on a machine
    whose transcript directory was never found.
    """
    cfg = _settings(args)
    found = transcript_mod.discover(session_id=cfg["session"])
    result: dict[str, Any] = {
        "ok": True,
        "store": cfg["store"],
        "transcript_roots": [str(root) for root in transcript_mod.roots()],
        "current": _describe(found),
    }
    if cfg["store"] == "folder":
        result["root"] = cfg["root"]
        result["published"] = [
            _summarize_publication(record)
            for record in store_mod.publications(cfg["root"], namespace=cfg["namespace"])
        ]
    else:
        result["published"] = None
        result["note"] = (
            "a service store is listed by the MCP server that owns it, not from here"
        )
    return result


def _summarize_publication(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "handle": record.get("handle"),
        "path": record.get("path"),
        "published_at": record.get("published_at"),
        "title": record.get("session", {}).get("title"),
        "session_id": record.get("session", {}).get("id"),
        "turns": record.get("transcript", {}).get("turns"),
        "artifacts": record.get("artifacts", {}).get("count"),
        "bytes": record.get("bundle", {}).get("size"),
    }


def _describe(found: transcript_mod.Found) -> dict[str, Any]:
    """What `discover` saw, in the shape a caller can report verbatim."""
    if not found.ok:
        return {
            "found": False,
            "directories_listed": found.directories,
            "notes": list(found.notes),
        }
    rows = transcript_mod.read(found.path)
    summary = digest_mod.summarize(transcript_mod.as_records(rows))
    identity = transcript_mod.identify(rows)
    return {
        "found": True,
        "path": str(found.path),
        "root": str(found.root),
        "candidates": found.candidates,
        "directories_listed": found.directories,
        **identity,
        "records": summary.records,
        "turns": summary.turns,
        "started_at": summary.started_at,
        "ended_at": summary.ended_at,
        "subagents": len(transcript_mod.subagents(found.path, identity["inner_id"])),
        "notes": list(found.notes),
    }


def _build(args: argparse.Namespace, cfg: dict[str, Any]) -> dict[str, Any]:
    """The shared half of pack and publish: find the transcript, build the bundle."""
    found = transcript_mod.discover(session_id=args.session)
    if not found.ok:
        raise bundle_mod.BundleError(
            "no transcript found: " + ("; ".join(found.notes) or "nothing was listed")
        )
    rows = transcript_mod.read(found.path)
    identity = transcript_mod.identify(rows)
    selected_by = "session-id" if args.session else "most-recent"

    notes: list[str] = list(found.notes)
    confirmed: bool | None = None
    if args.confirm:
        confirmed = transcript_mod.confirm(rows, args.confirm)
        if not confirmed:
            raise bundle_mod.BundleError(
                f"the phrase {args.confirm!r} does not appear near the end of "
                f"{found.path} — this is probably a different session's transcript, so "
                "nothing was published. Pass --session with this session's id"
            )
    elif selected_by == "most-recent":
        notes.append(
            "this transcript was chosen as the most recently written, not by id — pass "
            "--session, or --confirm with a phrase from this conversation, before "
            "telling anyone which session was published"
        )

    artifacts, artifact_notes = bundle_mod.plan_artifacts(
        args.artifact,
        from_dirs=args.artifacts_from_dir,
        root=args.artifact_root,
        allow_sensitive_names=args.allow_sensitive_names,
    )
    notes.extend(artifact_notes)

    # The id comes out of the records, never off the flag. The flag chooses WHICH
    # transcript; relabelling its contents would file the work under a session that
    # never happened.
    session_id = identity["inner_id"] or found.path.stem
    out_dir = pathlib.Path(
        getattr(args, "out", None) or tempfile.mkdtemp(prefix="100x-continuity-")
    ).expanduser()
    built = bundle_mod.write(
        out_dir / bundle_mod.BUNDLE_NAME,
        transcript_mod.as_records(rows),
        session={"id": session_id, "outer_id": identity["outer_id"]},
        artifacts=artifacts,
        include_record=not args.no_record,
        allow_flagged_artifacts=args.allow_flagged_artifacts,
    )
    return {
        "built": built,
        "session_id": session_id,
        "identity": identity,
        "source": {
            "transcript": str(found.path),
            "selected_by": selected_by,
            "confirmed": confirmed,
        },
        "notes": notes + list(built.notes),
        "resolved": keys.normalize_session_id(args.session) is not None,
    }


def _bundle_result(prepared: dict[str, Any]) -> dict[str, Any]:
    built = prepared["built"]
    return {
        "bundle": str(built.path),
        "sha256": built.sha256,
        "size": built.size,
        "manifest": built.manifest,
        "redacted": built.redacted,
        "redaction_tally": redact.tally(built.redacted),
        # Said on every publish, not only when something was removed: "0 redacted" is a
        # result the caller should repeat, because it means the scrubber matched
        # nothing — not that there was nothing to find.
        "redaction_caveat": redact.CAVEAT,
        "source": prepared["source"],
        "notes": prepared["notes"],
        **_session_note(prepared["resolved"]),
    }


def _cmd_pack(args: argparse.Namespace) -> dict[str, Any]:
    """Build the bundle and stop, so a service store can mint a URL for these bytes."""
    cfg = _settings(args)
    prepared = _build(args, cfg)
    result = {"ok": True, "filed": False, **_bundle_result(prepared)}
    result["next_step"] = (
        "ask the MCP store to mint an upload URL for this sha256 and size, then run "
        "`upload --bundle` with what it returns"
    )
    if cfg["service_name"]:
        result["service_name"] = cfg["service_name"]
    return result


def _cmd_publish(args: argparse.Namespace) -> dict[str, Any]:
    """Build the bundle and file it in the folder store, then say where it went."""
    cfg = _settings(args)
    if cfg["store"] != "folder":
        raise config.ConfigError(
            "the configured store is a service, which has no folder to file into: run "
            "`pack`, have the MCP server mint an upload URL, then `upload --bundle`"
        )
    prepared = _build(args, cfg)
    record = store_mod.install(
        cfg["root"],
        prepared["built"],
        namespace=cfg["namespace"],
        session_id=prepared["session_id"],
        stamp=_stamp(),
        source=prepared["source"],
    )
    return {
        "ok": True,
        "filed": True,
        "handle": record["handle"],
        "path": record.get("path"),
        "publication_id": record["publication_id"],
        "already_published": record["already_published"],
        "root": cfg["root"],
        **_bundle_result(prepared),
    }


def _read_mint(args: argparse.Namespace) -> dict[str, Any]:
    raw = (
        pathlib.Path(args.mint_file).expanduser().read_text(encoding="utf-8")
        if args.mint_file
        else sys.stdin.buffer.read().decode("utf-8", errors="replace")
    )
    try:
        mint = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"the mint result was not valid JSON: {exc}. Pass the object the MCP store "
            "returned, with its url and required_headers"
        ) from exc
    return mint


def _cmd_upload(args: argparse.Namespace) -> dict[str, Any]:
    path = pathlib.Path(args.bundle).expanduser()
    # Read the manifest first: uploading something that is not a bundle would put
    # bytes nobody can open into the operator's store, and the failure would only
    # surface for whoever tried to continue from it.
    manifest = bundle_mod.read_manifest(path)
    receipt = upload_mod.upload(path.read_bytes(), _read_mint(args))
    return {
        "ok": True,
        "bundle": str(path),
        "session_id": manifest.get("session", {}).get("id"),
        **receipt,
    }


def _cmd_fetch(args: argparse.Namespace) -> dict[str, Any]:
    """Pull the bytes, and check them against what the store said it holds.

    The digest defaults to the one in the mint answer. It used to come only from
    `--sha256`, which nothing passed — so the check the reading skill promises
    ("refuses anything whose contents don't match the digest the server named") was
    never performed, and a URL that answered with someone else's bytes was written to
    disk without complaint. Failing closed here is the whole point of the server
    returning a digest at all.
    """
    mint = _read_mint(args)
    expected = args.sha256 or mint.get("sha256")
    receipt = download_mod.download(args.out, mint, expected_sha256=expected)
    result = {"ok": True, **receipt}
    result["digest_source"] = (
        "flag" if args.sha256 else ("mint" if expected else None)
    )
    if not expected:
        result["note"] = (
            "the store did not report a digest and none was passed, so these bytes "
            "were not checked against what it holds; `open` still verifies the "
            "bundle's own manifest"
        )
    return result


def _cmd_open(args: argparse.Namespace) -> dict[str, Any]:
    """Verify a publication and read it back — the receiving half of a handoff."""
    cfg = _settings(args)
    if not (args.handle or args.bundle):
        raise ValueError(
            "pass --handle for a publication in the store, or --bundle for a file you "
            "already have"
        )
    record: dict[str, Any] | None = None
    if args.bundle:
        path = pathlib.Path(args.bundle).expanduser()
        expected = None
    else:
        record = store_mod.resolve(args.handle, root=cfg["root"])
        path = store_mod.bundle_path(record)
        expected = record.get("bundle", {}).get("sha256")

    destination = pathlib.Path(
        args.out or tempfile.mkdtemp(prefix="100x-continuity-open-")
    ).expanduser()
    opened = bundle_mod.extract(path, destination, expected_sha256=expected)
    manifest = opened["manifest"]
    digest_path = destination / bundle_mod.DIGEST_FILE
    return {
        "ok": True,
        "handle": (record or {}).get("handle"),
        "bundle": str(path),
        "unpacked_to": opened["path"],
        "session_id": manifest.get("session", {}).get("id"),
        "title": manifest.get("session", {}).get("title"),
        "transcript": manifest.get("transcript", {}),
        "artifacts": sorted(
            name for name in opened["files"] if name.startswith(f"{bundle_mod.ARTIFACT_DIR}/")
        ),
        "record": (
            str(destination / bundle_mod.RECORD_FILE)
            if bundle_mod.RECORD_FILE in opened["files"]
            else None
        ),
        "redacted": manifest.get("redacted", {}),
        "redaction_caveat": manifest.get("redaction_caveat", redact.CAVEAT),
        "digest": digest_path.read_text(encoding="utf-8"),
        "published_at": (record or {}).get("published_at"),
    }


def _session_note(resolved: bool) -> dict[str, Any]:
    """Say plainly when work was filed unattributed, and how to attribute it.

    Silence here is how someone ends up with a store full of publications nobody can
    find: everything works, nothing is wrong, and the session id never resolved.
    """
    if resolved:
        return {"session_resolved": True}
    return {
        "session_resolved": False,
        "hint": (
            f"no session id resolved, so this used the '{keys.UNATTRIBUTED}' slot — "
            "pass --session ${CLAUDE_SESSION_ID} to keep sessions apart"
        ),
    }


def _emit(result: dict[str, Any]) -> None:
    json.dump(result, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
