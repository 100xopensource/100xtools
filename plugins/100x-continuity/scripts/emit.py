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
import shutil
import sys

FACTORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
FACTORY_URL = "https://github.com/100xopensource/100xtools"
KIT_CONFIG_NAME = "kit.json"
PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")

# Copied verbatim into every Kit. The Kit is a plugin someone installs, so it carries
# its own engine — nothing here is imported from the factory at runtime.
ENGINE_FILES = ("run.py",)
# Rendered on the way out, and checked for leftovers. `.yaml` is here for the eval
# cases: they carry no placeholder today, and including them is what stops one being
# added later and shipping as four braces and a word.
SUBSTITUTED_SUFFIXES = {".md", ".json", ".yaml", ".yml"}


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


def _substitutions(args: argparse.Namespace, emitted_at: str) -> dict[str, str]:
    return {
        "KIT_NAME": args.name,
        "KIT_DESCRIPTION": args.description
        or "Hand a Claude session to a colleague, and pick up one they handed to you.",
        "KIT_VERSION": args.kit_version,
        "ORG": args.org,
        "TEAM": args.team,
        "SERVICE_NAME": args.service_name or "",
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


def _plan_files(store: str) -> list[tuple[pathlib.Path, str]]:
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
    scripts = FACTORY_ROOT / "scripts"
    for name in ENGINE_FILES:
        files.append((scripts / name, f"scripts/{name}"))
    for path in sorted((scripts / "engine").glob("*.py")):
        files.append((path, f"scripts/engine/{path.name}"))
    return files


def _kit_paths(kit: pathlib.Path) -> list[tuple[pathlib.Path, str]]:
    """Everything under templates/kit except the fragments, which are spliced."""
    out = []
    for path in sorted(kit.rglob("*")):
        if path.is_file() and path.relative_to(kit).parts[0] != "fragments":
            out.append((path, str(path.relative_to(kit))))
    return out


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

    # Resolved before anything is written: a marketplace path that cannot describe this
    # Kit is a wrong --into, and finding that out afterwards leaves a half-emitted plugin
    # in someone's repo.
    market_source = _source_path(into, args.marketplace)

    emitted_at = _stamp()
    values = _substitutions(args, emitted_at)
    values.update(_fragments(args.store, values))

    existing = into / KIT_CONFIG_NAME
    updating = existing.is_file()
    if into.exists() and not updating and any(into.iterdir()) and not args.force:
        raise EmitError(
            f"{into} already has files in it and no {KIT_CONFIG_NAME}, so it was not "
            "written by this factory. Pass --force only if replacing it is what you mean"
        )

    written, overwrote = [], []
    for template, rel in _plan_files(args.store):
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

    return {
        "ok": True,
        "updated": updating,
        "kit": str(into),
        "kit_config": kit_config,
        "files": sorted(set(written)),
        "overwrote": sorted(overwrote),
        "marketplace": marketplace,
        "marketplace_entry": entry,
        "dry_run": bool(args.dry_run),
        "next_step": (
            "run `verify` against this directory before anyone ships it"
            if args.store == "folder"
            else "stand the store service up and register it, then run `verify`"
        ),
    }


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
    parser.add_argument("--description", help="one line for the marketplace row")
    parser.add_argument("--kit-version", default="0.1.0")
    parser.add_argument("--marketplace", help="marketplace.json to add or refresh a row in")
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
