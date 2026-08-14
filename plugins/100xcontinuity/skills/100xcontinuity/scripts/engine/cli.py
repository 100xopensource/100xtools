"""Command-line surface: `save`, `load`, `list`, and `where`.

Claude drives the plugin through this module, so every command prints **JSON on
stdout and nothing else** — a human-readable line would have to be parsed back
out of the model's context, and a half-parsed status is worse than none. Errors
print a JSON object with `ok: false` and a `hint` naming the remedy, then exit
non-zero.

Configuration resolves flag → environment → default, so a caller can set the
store once in the environment and never pass it again:

| Setting | Flag | Environment | Default |
| --- | --- | --- | --- |
| backend | `--backend` | `CONTINUITY_BACKEND` | `local` |
| root | `--root` | `CONTINUITY_ROOT` | `~/Continuity` |
| namespace | `--namespace` | `CONTINUITY_NAMESPACE` | `default` |
| session | `--session` | `CLAUDE_SESSION_ID` | unattributed |
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

from engine import keys, session as session_mod, store as store_mod


DEFAULT_ROOT = "~/Continuity"


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
        store_mod.StoreError,
        session_mod.SessionError,
        ValueError,
        OSError,
    ) as exc:
        _emit({"ok": False, "error": type(exc).__name__, "hint": str(exc)})
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="continuity",
        description="Save and restore session artifacts across Claude sessions.",
    )
    sub = parser.add_subparsers(dest="command")

    def shared(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--backend", help="local | s3 (default: local)")
        p.add_argument("--root", help="directory for the local backend")
        p.add_argument("--namespace", help="separates unrelated projects in one store")
        p.add_argument("--session", help="session id (default: $CLAUDE_SESSION_ID)")
        return p

    save = shared(sub.add_parser("save", help="save one artifact into a session"))
    save.add_argument("--name", required=True, help="artifact name within the session")
    save.add_argument("--file", help="file to read; omit to read stdin")
    save.add_argument("--media-type", help="media type recorded on the entry")
    save.set_defaults(handler=_cmd_save)

    load = shared(sub.add_parser("load", help="write one artifact back out"))
    load.add_argument("--name", required=True)
    load.add_argument("--out", help="file to write; omit to write stdout")
    load.set_defaults(handler=_cmd_load)

    listing = shared(sub.add_parser("list", help="what a session currently holds"))
    listing.add_argument(
        "--history", action="store_true", help="include every save, not just current"
    )
    listing.set_defaults(handler=_cmd_list)

    where = shared(sub.add_parser("where", help="resolved configuration and paths"))
    where.set_defaults(handler=_cmd_where)
    return parser


def _settings(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve configuration: flag, then environment, then default."""
    return {
        "backend": args.backend or os.environ.get("CONTINUITY_BACKEND") or "local",
        "root": args.root or os.environ.get("CONTINUITY_ROOT") or DEFAULT_ROOT,
        "namespace": args.namespace or os.environ.get("CONTINUITY_NAMESPACE"),
        # An unset session id is normal, not an error: it lands in the
        # unattributed slot and the caller is told so in the result.
        "session": args.session or os.environ.get("CLAUDE_SESSION_ID"),
    }


def _open_store(cfg: dict[str, Any]) -> store_mod.ObjectStore:
    return store_mod.get_store(cfg["backend"], root=cfg["root"])


def _cmd_save(args: argparse.Namespace) -> dict[str, Any]:
    cfg = _settings(args)
    data = (
        pathlib.Path(args.file).expanduser().read_bytes()
        if args.file
        else sys.stdin.buffer.read()
    )
    entry = session_mod.save_artifact(
        _open_store(cfg),
        namespace=cfg["namespace"],
        session_id=cfg["session"],
        name=args.name,
        data=data,
        media_type=args.media_type,
    )
    return {"ok": True, "saved": entry, **_session_note(cfg, entry["resolved"])}


def _cmd_load(args: argparse.Namespace) -> dict[str, Any]:
    cfg = _settings(args)
    data = session_mod.load_artifact(
        _open_store(cfg),
        namespace=cfg["namespace"],
        session_id=cfg["session"],
        name=args.name,
    )
    if args.out:
        out = pathlib.Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return {"ok": True, "name": args.name, "bytes": len(data), "path": str(out)}
    # No --out: the bytes are the point, so they go to stdout raw and the JSON
    # envelope is skipped. Signalled to _emit by the sentinel key.
    return {"__raw__": data}


def _cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    cfg = _settings(args)
    state = session_mod.read_session(
        _open_store(cfg), namespace=cfg["namespace"], session_id=cfg["session"]
    )
    result = {
        "ok": True,
        "session_digest": state["session_digest"],
        "namespace": state["namespace"],
        "artifacts": sorted(state["artifacts"].values(), key=lambda e: e["name"]),
        "damaged": state["damaged"],
        **_session_note(cfg, state["resolved"]),
    }
    if args.history:
        result["history"] = state["history"]
    return result


def _cmd_where(args: argparse.Namespace) -> dict[str, Any]:
    cfg = _settings(args)
    root = pathlib.Path(cfg["root"]).expanduser()
    digest = keys.session_digest(cfg["namespace"], cfg["session"])
    resolved = keys.normalize_session_id(cfg["session"]) is not None
    return {
        "ok": True,
        "backend": cfg["backend"],
        "root": str(root),
        "root_exists": root.exists(),
        "namespace": keys.normalize_namespace(cfg["namespace"]),
        "session_digest": digest,
        "session_path": str(root / keys.session_prefix(digest)),
        **_session_note(cfg, resolved),
    }


def _session_note(cfg: dict[str, Any], resolved: bool) -> dict[str, Any]:
    """Say plainly when a save landed unattributed, and how to attribute it.

    Silence here is how a user ends up with a store full of artifacts they cannot
    find: everything works, nothing is wrong, and the session id never resolved.
    """
    if resolved:
        return {"session_resolved": True}
    return {
        "session_resolved": False,
        "hint": (
            f"no session id resolved, so this used the '{keys.UNATTRIBUTED}' slot — "
            "pass --session or set CLAUDE_SESSION_ID to keep sessions apart"
        ),
    }


def _emit(result: dict[str, Any]) -> None:
    """Write a result: raw bytes for a stdout load, JSON for everything else."""
    if "__raw__" in result:
        sys.stdout.buffer.write(result["__raw__"])
        return
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
