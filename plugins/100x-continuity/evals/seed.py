#!/usr/bin/env python3
"""Build the fixture stores the behavioral cases run against.

Every case here starts from state a prompt cannot produce for itself: a session
transcript waiting to be published, a store already holding somebody else's
publication, and a publication whose bytes a sync client evicted. Producing any of
those from the prompt would test the setup rather than the skill, so they are laid
down here and the graders verify against what this script wrote.

The publish fixture writes a **transcript tree** — a fake HOME holding
`.claude/projects/<dir>/<id>.jsonl` — which the case prompt points the run at. Seeding
the developer's real `~/.claude/projects` was never an option: that is not a fixture,
it is their actual session history, and discovery would find the live session instead
of the planted one.

Every Kit-facing case also gets a **freshly emitted Kit**, because that is what a
Teammate actually installs — the factory ships no `hand-off` skill of its own, so a
case pointed at the factory would be testing a plugin that cannot do the thing. Emitting
it here is also the only way the store stays baked in rather than named in the prompt.

Idempotent: every case root is rebuilt from scratch, so a rerun after a failed eval
starts where the first one did.

    python3 plugins/100x-continuity/evals/seed.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path("/tmp/100x-continuity-evals")

# Imported from the plugin under test on purpose: a fixture written against a
# hand-copied layout would keep passing after the real one changed.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import emit as emit_mod  # noqa: E402
from engine import bundle, store, transcript as transcript_mod  # noqa: E402

NAMESPACE = "evals"
SESSION = "gamma-2026-08-18"
STAMP = "20260818T093000Z"

# The working directory the seeded session ran in. Its encoded form is the project
# directory name discovery has to list for.
CAPTURED_CWD = "/repo/acme-importer"

# Invented Acme material, per the repo's fixture convention — it must not read as
# anyone's real internal notes, and it has to be distinctive enough that a model
# cannot produce it by guessing. A passing grader then means the store was genuinely
# read rather than plausibly imagined.
HANDOVER = b"""# Handover

- Importer flag is on for store 41 only.
- The nightly stock-count job is still scheduled and must go before this widens.
- Blocked on the Acme platform team raising the request quota.
"""


# The file the seed writes the planted credential to, so the grader can search for it
# without any file in this repo containing the string.
NEEDLE_FILE = "planted-secret.txt"


def planted_secret() -> str:
    """A credential-shaped string, ASSEMBLED AT RUN TIME.

    A literal would be committed to this repo, where the pre-commit sweep and the
    linter's own secret patterns both match it — one blocks the commit, the other
    makes the security sub-score stop meaning anything. The grader that has to search
    for this string reads it out of NEEDLE_FILE rather than carrying a copy.
    """
    return "AKIA" + "V" * 16


def emit_kit(root: pathlib.Path) -> pathlib.Path:
    """Emit the Kit a Teammate would install, with this case's store baked into it.

    Through the real `emit`, not a hand-built directory: a fixture assembled by hand
    keeps passing after the emitter changes, which is the one regression these cases
    are positioned to catch.
    """
    kit = root / "kit"
    emit_mod.emit(
        argparse.Namespace(
            into=str(kit),
            name="acme-handoff",
            team="the Acme importer team",
            org="Acme",
            store="folder",
            root=str(root / "store"),
            namespace=NAMESPACE,
            service_name=None,
            description=None,
            kit_version="0.1.0",
            marketplace=None,
            force=False,
            dry_run=False,
        )
    )
    return kit


def reset(name: str) -> pathlib.Path:
    path = ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _records() -> list[dict]:
    """One realistic session: a prompt carrying a secret, a tool call, an answer."""
    return [
        {"type": "ai-title", "aiTitle": "Acme importer flag rollout", "sessionId": SESSION},
        {
            "type": "user",
            "sessionId": SESSION,
            "origin": {"kind": "human"},
            "cwd": CAPTURED_CWD,
            "gitBranch": "flag-rollout",
            "timestamp": "2026-08-18T09:15:00.000Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Turn the Acme widget importer flag on for store 41 only. "
                            f"Deploy key is {planted_secret()} if you need it."
                        ),
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": SESSION,
            "cwd": CAPTURED_CWD,
            "timestamp": "2026-08-18T09:16:30.000Z",
            "message": {
                "role": "assistant",
                "model": "claude-opus-5",
                "usage": {"input_tokens": 4120, "output_tokens": 380},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_seed01",
                        "name": "Edit",
                        "input": {"file_path": "/repo/acme-importer/config/flags.yaml"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Enabled the importer for store 41 in config/flags.yaml. The "
                            "nightly stock-count job is still scheduled and should be "
                            "removed before this goes wider — that is the open item."
                        ),
                    },
                ],
            },
        },
    ]


def seed_session(name: str) -> tuple[pathlib.Path, pathlib.Path]:
    """An empty store, plus a fake HOME holding one finished session's transcript.

    The project directory name is encoded the way the host encodes it, so the case
    exercises the real listing path rather than a shortcut.
    """
    root = reset(name)
    home = root / "home"
    directory = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CAPTURED_CWD)
    directory.mkdir(parents=True)
    (directory / f"{SESSION}.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in _records()), encoding="utf-8"
    )
    work = root / "work"
    work.mkdir()
    (work / "handover.md").write_bytes(HANDOVER)
    emit_kit(root)
    # Written outside the store and outside `work`, so nothing being graded contains
    # it — the grader points `grep -f` at this file instead of quoting the value.
    (root / NEEDLE_FILE).write_text(planted_secret() + "\n", encoding="utf-8")
    return root, home


def seed_published(name: str) -> tuple[pathlib.Path, dict]:
    """A store holding one publication, as if somebody else had sent the handle."""
    root, home = seed_session(name)
    found = transcript_mod.discover(session_id=SESSION, home=home)
    rows = transcript_mod.read(found.path)
    artifacts, _ = bundle.plan_artifacts(
        [str(root / "work" / "handover.md")], root=str(root / "work")
    )
    built = bundle.write(
        root / "staging" / bundle.BUNDLE_NAME,
        transcript_mod.as_records(rows),
        session={"id": SESSION, "outer_id": None},
        artifacts=artifacts,
    )
    record = store.install(
        root / "store",
        built,
        namespace=NAMESPACE,
        session_id=SESSION,
        stamp=STAMP,
        source={"transcript": str(found.path), "selected_by": "session-id"},
    )
    shutil.rmtree(root / "staging")
    return root, record


def seed_evicted(name: str) -> tuple[pathlib.Path, dict]:
    """A publication whose bytes a sync client dropped.

    Reproduces what iCloud Drive leaves behind: the archive is present and readable
    but zero bytes, with a `.<name>.icloud` placeholder beside it. The publication
    looks complete right up until the bytes are read.
    """
    root, record = seed_published(name)
    archive = pathlib.Path(record["path"]) / bundle.BUNDLE_NAME
    archive.write_bytes(b"")
    (archive.parent / f".{archive.name}.icloud").write_bytes(b"")
    return root, record


def main() -> int:
    publish_root, publish_home = seed_session("publishes-a-handoff")
    continue_root, continue_record = seed_published("continues-from-a-handle")
    evicted_root, evicted_record = seed_evicted("evicted-bundle-is-not-an-empty-session")

    for name, path in (
        ("publishes-a-handoff", publish_root),
        ("continues-from-a-handle", continue_root),
        ("evicted-bundle-is-not-an-empty-session", evicted_root),
    ):
        files = sum(1 for entry in path.rglob("*") if entry.is_file())
        print(f"ok  {name}: {path} ({files} files, kit at {path / 'kit'})")

    factory_root = reset("emits-a-working-kit")
    (factory_root / "acme-plugins" / ".claude-plugin").mkdir(parents=True)
    (factory_root / "acme-plugins" / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "acme-plugins",
                "owner": {"name": "Acme"},
                # One unrelated row, so a factory that rewrites the whole manifest
                # instead of adding a row is visible rather than merely untested.
                "plugins": [{"name": "acme-lint", "source": "./plugins/acme-lint"}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"ok  emits-a-working-kit: {factory_root} (empty repo, 1 unrelated row)")

    print(f"\ntranscript home for {SESSION!r}: {publish_home}")
    print(f"handle to continue from:  {continue_record['handle']}")
    print(f"handle with evicted bytes: {evicted_record['handle']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
