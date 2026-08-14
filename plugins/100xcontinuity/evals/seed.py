#!/usr/bin/env python3
"""Build the fixture stores the behavioral cases run against.

Two of the four cases start from a store that already holds something — one from
an earlier session, one whose bytes a sync client has evicted. Neither state can
be produced by the case prompt without the prompt itself doing the setup, which
would test the setup rather than the skill. So they are seeded here, before the
run, and the graders verify against what this script laid down.

Idempotent: every case root is rebuilt from scratch, so a rerun after a failed
eval starts from the same state as the first run.

    python3 plugins/100xcontinuity/evals/seed.py
"""

from __future__ import annotations

import pathlib
import shutil
import sys


ROOT = pathlib.Path("/tmp/100xcontinuity-evals")

# Imported from the plugin under test on purpose: a fixture written against a
# hand-copied key scheme would keep passing after the real one changed.
ENGINE = pathlib.Path(__file__).resolve().parents[1] / "skills/100xcontinuity/scripts"
sys.path.insert(0, str(ENGINE))

from engine import keys, session, store  # noqa: E402


NAMESPACE = "evals"

# What the restore case must find. Invented Acme material, per the repo's fixture
# convention — it must not read as anyone's real internal notes. Still distinctive
# enough that a model cannot produce it by guessing, so a passing grader means the
# store was genuinely read rather than plausibly imagined.
EARLIER_SESSION = "alpha-2026-08-11"
EARLIER_NOTES = b"""# Session alpha

Decisions:
- Ship the Acme widget importer behind a flag, default off.
- Drop the nightly stock-count job; it has not flagged anything in 90 days.
- Blocked on: the Acme platform team raising the request quota.
"""


def reset(name: str) -> pathlib.Path:
    """An empty store root for one case."""
    path = ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def seed_empty(name: str) -> pathlib.Path:
    """A store that exists but holds nothing — the happy path starts here."""
    return reset(name)


def seed_earlier_session(name: str) -> pathlib.Path:
    """A store holding one artifact saved under an earlier session id."""
    root = reset(name)
    session.save_artifact(
        store.LocalStore(root),
        namespace=NAMESPACE,
        session_id=EARLIER_SESSION,
        name="notes.md",
        data=EARLIER_NOTES,
        media_type="text/markdown",
        stamp="2026-08-11T14-22-05-000000Z",
    )
    return root


def seed_evicted(name: str) -> pathlib.Path:
    """A store whose blob has been evicted by a sync client.

    Reproduces what iCloud Drive leaves behind: the file is present and readable
    but zero bytes, with a `.<name>.icloud` placeholder sibling. The entry still
    names it, so the artifact looks present right up until the bytes are read.
    """
    root = reset(name)
    local = store.LocalStore(root)
    session.save_artifact(
        local,
        namespace=NAMESPACE,
        session_id=EARLIER_SESSION,
        name="notes.md",
        data=EARLIER_NOTES,
        media_type="text/markdown",
        stamp="2026-08-11T14-22-05-000000Z",
    )
    digest = keys.session_digest(NAMESPACE, EARLIER_SESSION)
    blob = root / keys.blob_key(digest, keys.content_digest(EARLIER_NOTES))
    blob.write_bytes(b"")
    (blob.parent / f".{blob.name}.icloud").write_bytes(b"")
    return root


def main() -> int:
    built = {
        "saves-a-summary": seed_empty("saves-a-summary"),
        "restores-an-earlier-session": seed_earlier_session("restores-an-earlier-session"),
        "unattributed-save-is-surfaced": seed_empty("unattributed-save-is-surfaced"),
        "evicted-artifact-is-not-empty": seed_evicted("evicted-artifact-is-not-empty"),
    }
    for name, path in built.items():
        files = sum(1 for _ in path.rglob("*") if _.is_file())
        print(f"ok  {name}: {path} ({files} files)")
    print(f"\nsession digest for {EARLIER_SESSION!r}: "
          f"{keys.session_digest(NAMESPACE, EARLIER_SESSION)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
