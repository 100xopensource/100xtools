"""One place where configuration precedence lives, and where `setup` writes.

Five tiers, highest first: **flag → environment → baked Kit → config file →
default.** The
config file is the tier this plugin adds over an environment-only design, and it
exists because of how the plugin is meant to be used: someone runs `setup` once,
gets a working store, and then may well copy this plugin into their own repo and
never think about it again. Answers that only lived in a shell export would not
survive that, and re-asking them on every machine is the failure mode `setup`
exists to remove.

**A Kit carries its own answers.** When this engine ships inside a Kit, the Factory has
already written `kit.json` beside it — the store, the namespace, and which Factory built
it. A Teammate has no shell profile, no environment, and no wizard to run, so anything
they would otherwise have to supply is decided at emit time and read from that file. It
is the tier that makes a Kit work for someone who never configured anything, and it is
why the Factory exists rather than a setup command. It outranks the config file on
purpose: a stray config left over from some other install must not silently redirect a
team's handoffs, while a flag or an environment variable — someone deliberately
debugging — still wins.

**Two store kinds, and only one of them is a path.**

- `folder` — a directory this plugin writes publications into, usually one a
  consumer sync client already watches. The plugin syncs nothing; the client that is
  already running does the work.
- `service` — object storage reached through an MCP server the operator runs. There
  is no path and no credential here: the server mints a short-lived presigned URL,
  the engine sends or receives bytes, and every access decision stays on the
  operator's side. `service_name` is recorded only so a skill can say which tool to
  call; nothing authenticates against it here.

**Where the *user* config file goes is a surface question, not a preference.** Inside a
Cowork session the sandbox home does not outlive the session, while `~/mnt/outputs`
is mounted from the host and does. So the mounted location is searched first and
written first when it exists — the same "mounted root wins" rule `transcript.py`
uses, for the same reason. Every command reports the file it read and the paths it
searched, so a setting that came from somewhere unexpected is diagnosable rather
than mysterious.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

STORE_KIND_ENV = "CONTINUITY_STORE"
STORE_ROOT_ENV = "CONTINUITY_ROOT"
NAMESPACE_ENV = "CONTINUITY_NAMESPACE"
SERVICE_ENV = "CONTINUITY_SERVICE"
CONFIG_ENV = "CONTINUITY_CONFIG"

# Written by the Factory into a Kit, beside `scripts/`. Its presence is what tells this
# engine it is running as somebody's Kit rather than as the Factory's own tooling.
KIT_CONFIG_NAME = "kit.json"

# Undocumented in the hooks/skills reference but present in current builds. A
# fallback only — `--session ${CLAUDE_SESSION_ID}` is the supported path.
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"

STORE_KINDS = ("folder", "service")
DEFAULT_STORE_KIND = "folder"
DEFAULT_NAMESPACE = "default"

# The Cowork mount. Its presence is what says "this is a sandbox whose own home is
# temporary", which is a fact about the surface rather than a guess about content.
MOUNT = pathlib.PurePosixPath("mnt/outputs")

# Config file locations, searched in this order. The mounted one first, so a Cowork
# session finds the answers a previous one wrote.
CONFIG_PATHS = (
    MOUNT / ".100x-continuity/config.json",
    pathlib.PurePosixPath(".config/100x-continuity/config.json"),
)

# The folder store's default name under whichever home answered. Visible, not
# hidden: the whole point of the folder store is that a person opens it, points a
# sync client at it, and shares it with whoever is continuing the work.
DEFAULT_ROOT_NAME = "Continuity"

_KNOWN_KEYS = frozenset({"store", "root", "namespace", "service_name", "written_at"})

# What a Kit's baked config may say. `kit_name`, `factory_version` and `emitted_at` are
# provenance: a Teammate reporting a problem names which Factory built their Kit, without
# having to know what a Factory is.
_KIT_KEYS = frozenset(
    {"store", "root", "namespace", "service_name", "kit_name", "factory_version", "emitted_at"}
)


class ConfigError(Exception):
    """The config file exists but cannot be used as configuration."""


def home(explicit: pathlib.Path | None = None) -> pathlib.Path:
    return explicit or pathlib.Path.home()


def plugin_root() -> pathlib.Path:
    """The directory this engine was installed into: `<plugin>/scripts/engine` → `<plugin>`.

    Derived from this file's own location rather than from an environment variable,
    because the variable that would name it is not reliable on every surface this runs
    on — and a Kit that could not find its own configuration would silently fall back to
    defaults nobody chose.
    """
    return pathlib.Path(__file__).resolve().parents[2]


def kit_config(*, root: pathlib.Path | None = None) -> dict[str, Any]:
    """What the Factory baked into this Kit, or an empty answer if this is not one.

    A malformed file **raises**: it was written by the Factory, so a Kit whose
    configuration will not parse is a broken emit, and falling through to defaults would
    publish a Teammate's work somewhere nobody chose.
    """
    path = (root or plugin_root()) / KIT_CONFIG_NAME
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return {"values": {}, "path": None}
    except OSError as exc:
        raise ConfigError(f"could not read this Kit's configuration at {path}: {exc}") from exc
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise ConfigError(
            f"this Kit's configuration at {path} is not valid JSON: {exc}. The Kit needs "
            "to be emitted again"
        ) from exc
    if not isinstance(value, dict):
        raise ConfigError(f"this Kit's configuration at {path} must be a JSON object")
    return {
        "values": {k: v for k, v in value.items() if k in _KIT_KEYS},
        "path": str(path),
    }


def config_paths(*, base: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every location a config file may live, in precedence order.

    `CONTINUITY_CONFIG` comes first when set, so a caller can point at one
    explicitly — the one tier that does not depend on which surface this is.
    """
    out: list[pathlib.Path] = []
    override = os.environ.get(CONFIG_ENV)
    if override:
        out.append(pathlib.Path(override).expanduser())
    root = home(base)
    out.extend(root / candidate for candidate in CONFIG_PATHS)
    return out


def load_file(*, base: pathlib.Path | None = None) -> dict[str, Any]:
    """Read the first config file that exists, and report what was searched.

    A file that is present but unreadable **raises**: it was written on purpose, so
    silently falling through to defaults would publish into a store the user did not
    choose. A file that is simply absent is not an error.
    """
    searched = config_paths(base=base)
    for path in searched:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ConfigError(f"could not read the config at {path}: {exc}") from exc
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise ConfigError(
                f"the config at {path} is not valid JSON: {exc}. Fix it, or delete it "
                "and run setup again"
            ) from exc
        if not isinstance(value, dict):
            raise ConfigError(f"the config at {path} must be a JSON object")
        unknown = sorted(set(value) - _KNOWN_KEYS)
        return {
            "values": {k: v for k, v in value.items() if k in _KNOWN_KEYS},
            "path": str(path),
            "searched": [str(entry) for entry in searched],
            "unknown_keys": unknown,
        }
    return {
        "values": {},
        "path": None,
        "searched": [str(entry) for entry in searched],
        "unknown_keys": [],
    }


def default_root(*, base: pathlib.Path | None = None) -> str:
    """Where the folder store goes when nobody has said.

    Under the Cowork mount when there is one, because the sandbox home is discarded
    with the session and a store written there would be lost exactly when someone
    tried to continue from it.
    """
    root = home(base)
    if (root / MOUNT).is_dir():
        return str(root / MOUNT / DEFAULT_ROOT_NAME)
    return str(root / DEFAULT_ROOT_NAME)


def default_config_path(*, base: pathlib.Path | None = None) -> pathlib.Path:
    """Where `setup` writes when the caller does not name a file.

    The mounted location when the mount exists, so a Cowork session's answers
    survive it; otherwise the ordinary per-user location.
    """
    override = os.environ.get(CONFIG_ENV)
    if override:
        return pathlib.Path(override).expanduser()
    root = home(base)
    if (root / MOUNT).is_dir():
        return root / CONFIG_PATHS[0]
    return root / CONFIG_PATHS[1]


def check_store_kind(kind: str) -> str:
    """Reject a store kind this build does not have, naming the two that exist.

    `s3` is called out by name because it is the wrong shape rather than a missing
    feature, and someone will try it: this engine addresses a store it can list and
    read back, and a presigned PUT can do neither. Object storage is reached as a
    `service` store, where the operator's own server mints the URLs.
    """
    if kind in STORE_KINDS:
        return kind
    if kind in ("s3", "minio", "bucket", "object"):
        raise ConfigError(
            f"there is no {kind!r} store kind: object storage is reached as a "
            "'service' store, where an MCP server you run mints a presigned URL and "
            "this plugin holds no credential — see references/service-store.md"
        )
    raise ConfigError(
        f"unknown store {kind!r} — the store is 'folder' or 'service'"
    )


def settings(
    *,
    store_flag: str | None = None,
    root_flag: str | None = None,
    namespace_flag: str | None = None,
    session_flag: str | None = None,
    base: pathlib.Path | None = None,
    kit_root: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Every resolved setting, plus where each tier's answer came from.

    The provenance is not decoration. "It published somewhere I did not expect" is
    the complaint this design has to be able to answer, and the answer is which of
    the five tiers won.
    """
    loaded = load_file(base=base)
    values = loaded["values"]
    kit = kit_config(root=kit_root)
    baked = kit["values"]

    store = check_store_kind(
        store_flag
        or os.environ.get(STORE_KIND_ENV)
        or baked.get("store")
        or values.get("store")
        or DEFAULT_STORE_KIND
    )
    root = (
        root_flag
        or os.environ.get(STORE_ROOT_ENV)
        or baked.get("root")
        or values.get("root")
        or default_root(base=base)
    )
    namespace = (
        namespace_flag
        or os.environ.get(NAMESPACE_ENV)
        or baked.get("namespace")
        or values.get("namespace")
        or DEFAULT_NAMESPACE
    )
    service_name = (
        os.environ.get(SERVICE_ENV)
        or baked.get("service_name")
        or values.get("service_name")
    )
    session = session_flag or os.environ.get(SESSION_ENV)

    return {
        "store": store,
        "root": str(pathlib.Path(root).expanduser()),
        "namespace": namespace,
        "service_name": service_name,
        "session": session,
        "config_path": loaded["path"],
        "config_searched": loaded["searched"],
        "config_unknown_keys": loaded["unknown_keys"],
        "kit": {
            "path": kit["path"],
            "name": baked.get("kit_name"),
            "factory_version": baked.get("factory_version"),
            "emitted_at": baked.get("emitted_at"),
        },
        "sources": {
            "store": _source(store_flag, STORE_KIND_ENV, baked, values, "store"),
            "root": _source(root_flag, STORE_ROOT_ENV, baked, values, "root"),
            "namespace": _source(namespace_flag, NAMESPACE_ENV, baked, values, "namespace"),
        },
    }


def _source(
    flag: str | None, env: str, baked: dict[str, Any], values: dict[str, Any], key: str
) -> str:
    """Which tier answered. Reported on every command, because "it published somewhere
    I did not expect" is the complaint this design has to be able to answer."""
    if flag:
        return "flag"
    if os.environ.get(env):
        return "environment"
    if baked.get(key):
        return "kit"
    if values.get(key):
        return "config-file"
    return "default"


def write(
    *,
    store: str,
    root: str | None = None,
    namespace: str | None = None,
    service_name: str | None = None,
    stamp: str,
    path: pathlib.Path | None = None,
    base: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Persist the answers `setup` collected; return the file and what it holds.

    Written whole rather than merged, so the file always states the complete
    configuration — a half-updated config that pairs a `service` store with a stale
    folder root is the one outcome worth designing out.

    A `folder` store keeps its root. A `service` store does not get one: it has no
    path, and leaving a plausible-looking directory in the file invites the next
    reader to believe publications are landing there.
    """
    check_store_kind(store)
    target = path or default_config_path(base=base)
    values: dict[str, Any] = {
        "store": store,
        "namespace": namespace or DEFAULT_NAMESPACE,
        "written_at": stamp,
    }
    if store == "folder":
        values["root"] = str(pathlib.Path(root or default_root(base=base)).expanduser())
    if service_name:
        values["service_name"] = service_name

    target.parent.mkdir(parents=True, exist_ok=True)
    # Written through a temporary file in the same directory, then renamed: a config
    # read while it is being rewritten would otherwise be half a file, and this one
    # can live in a folder a sync client is watching.
    scratch = target.with_name(f".tmp-{target.name}")
    scratch.write_bytes(json.dumps(values, indent=2, sort_keys=True).encode() + b"\n")
    scratch.replace(target)
    return {"path": str(target), "config": values}
