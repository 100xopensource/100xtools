"""The storage seam: one Protocol, a local backend, and a backend selector.

Everything above this module addresses objects by key (see `keys.py`) and never
learns which backend answered. That is the whole point of the seam — the same
save and restore path serves a plain directory and an S3-compatible bucket.

`LocalStore` is written for a directory a consumer sync client watches, which is
the ordinary way this plugin reaches the cloud: point it at a folder inside
iCloud Drive, OneDrive, Dropbox, or Google Drive and the sync client does the
uploading. The plugin never syncs anything itself. Three consequences shape the
code:

- **Every write is atomic.** Bytes go to a temp file in the destination directory
  and are then moved into place with `os.replace`, so a sync client watching the
  folder never observes a half-written file and upload it.
- **Nothing is ever rewritten.** Blobs are content-addressed and the entry log is
  append-only, so two machines editing one session cannot produce the diverging
  versions a sync client resolves by forking a conflict copy.
- **Evicted files are detected, not misread.** A sync client reclaiming disk
  replaces a file's contents while leaving its name in place, and reading one
  returns short or empty bytes with no error.

Eviction is caught in two places, and the split matters. This module only
recognises the *iCloud* form of it — a `.<name>.icloud` placeholder sibling —
because that is all a store can see when it has nothing to compare the bytes
against. Dropbox and Google Drive evict without leaving any such marker, so the
guarantee cannot live here. It lives in `session.load_artifact`, which knows the
digest the bytes are supposed to have and verifies it; that catches eviction by
any client, and truncation too. The check here is a fast path with a better
message, not the guarantee.

Reference: `references/synced-folders.md`.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from typing import Protocol, runtime_checkable

# A file iCloud Drive has evicted is replaced by a sibling `.<name>.icloud`
# placeholder while the visible entry reads as empty. Spotting the sibling is how
# an eviction is told apart from a genuinely empty object.
_ICLOUD_PLACEHOLDER = ".{name}.icloud"

# Names a sync client creates beside real objects. Never returned by a listing:
# they are the sync client's bookkeeping, not this store's contents.
_SYNC_ARTEFACT_SUFFIXES = (".icloud", ".tmp", ".partial", ".crdownload")


class StoreError(Exception):
    """Base for every storage failure raised through the seam."""


class ObjectNotFound(StoreError):
    """No object exists at the requested key."""


class ObjectNotMaterialized(StoreError):
    """The object exists but its bytes are not on this machine yet.

    Raised for a cloud-evicted placeholder. Distinct from `ObjectNotFound`
    because the remedy is different: wait for the sync client, or ask it to
    download the file — not re-save it.
    """


class BackendNotAvailable(StoreError):
    """A known backend that this build cannot use yet.

    A `StoreError` rather than `NotImplementedError` so it travels the same path
    as every other storage failure and reaches the caller as a modelled result.
    Raised as a bare `NotImplementedError` it escaped the CLI's error handling
    and printed a traceback, breaking the JSON-only contract on stdout.
    """


@runtime_checkable
class ObjectStore(Protocol):
    """The storage contract. Keys come from `keys.py`; bytes are opaque here."""

    def put(self, key: str, data: bytes) -> None:
        """Write `data` at `key`. Atomic, and a no-op if the bytes already match."""
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes at `key`, or raise `ObjectNotFound`."""
        ...

    def exists(self, key: str) -> bool:
        """Whether an object is present at `key`."""
        ...

    def list(self, prefix: str) -> list[str]:
        """Every key under `prefix`, sorted. Empty when the prefix has no objects."""
        ...


class LocalStore:
    """Filesystem backend, safe inside a folder a sync client watches.

    `root` is the user's directory and is created if missing, but its permissions
    are left alone: a synced folder's mode belongs to the sync client, and
    tightening it here would fight that client on every run. Objects are written
    under `root` with the process umask.
    """

    def __init__(self, root: pathlib.Path | str) -> None:
        self.root = pathlib.Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> pathlib.Path:
        """Resolve `key` under the root, refusing anything that escapes it.

        Keys are built by `keys.py`, which validates its own segments — this is
        the second gate, at the point where a key becomes a filesystem path.
        """
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"key escapes the store root: {key!r}")
        return candidate

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Content-addressed keys make a rewrite pointless: if the object is
        # already here with these bytes, touching it would only give the sync
        # client another upload to do.
        if path.exists() and path.read_bytes() == data:
            return
        # Temp file in the DESTINATION directory so the move is a rename within
        # one filesystem, which is what makes it atomic. A temp file elsewhere
        # would fall back to a copy and reopen the half-written window.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        tmp = pathlib.Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise ObjectNotFound(key)
        data = path.read_bytes()
        # An evicted file reads as empty with no error. The placeholder sibling
        # is what separates that from an object that is genuinely zero bytes.
        if not data and self._is_evicted(path):
            raise ObjectNotMaterialized(
                f"{key} is in the cloud but not on this machine yet — "
                f"ask the sync client to download {path} and retry"
            )
        return data

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.is_dir():
            return []
        root = self.root.resolve()
        return sorted(
            str(p.relative_to(root))
            for p in base.rglob("*")
            if p.is_file() and not self._is_sync_artefact(p)
        )

    @staticmethod
    def _is_evicted(path: pathlib.Path) -> bool:
        """Whether iCloud Drive has evicted this file's contents."""
        return (path.parent / _ICLOUD_PLACEHOLDER.format(name=path.name)).exists()

    @staticmethod
    def _is_sync_artefact(path: pathlib.Path) -> bool:
        """Whether a sync client (or an interrupted `put`) owns this file."""
        return path.name.startswith(".tmp-") or path.name.endswith(
            _SYNC_ARTEFACT_SUFFIXES
        )


def check_backend(backend: str) -> None:
    """Raise unless `backend` names something this build can actually use.

    Separate from `get_store` so a diagnostic can validate configuration without
    the side effect of creating a store root — `where` reports what is
    configured and must not bring it into existence while doing so.
    """
    if backend == "local":
        return
    if backend == "s3":
        raise BackendNotAvailable(
            "the S3-compatible backend is not wired up yet; use backend='local'"
        )
    raise ValueError(f"unknown backend {backend!r} (expected 'local' or 's3')")


def get_store(backend: str, *, root: str | None = None) -> ObjectStore:
    """Build the configured backend.

    `local` is the default and the only backend that needs no credentials. The
    S3-compatible backend is selected by name here so callers never branch on it
    themselves; it lands in `s3.py`.
    """
    check_backend(backend)
    if not root:
        raise ValueError("the local backend needs a root directory")
    return LocalStore(root)
