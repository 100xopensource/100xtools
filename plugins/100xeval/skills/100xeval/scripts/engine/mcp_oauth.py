"""OAuth client-credentials support for MCP servers.

The runner can mint its own short-lived MCP access token instead of being handed a
long-lived static key. A server declares credentials in the environment, on the same
naming convention as the static key:

    MCP_<SERVER>_CLIENT_ID       MCP_<SERVER>_TOKEN_URL
    MCP_<SERVER>_CLIENT_SECRET   MCP_<SERVER>_SCOPE      (optional)

`env_for_servers` returns `{MCP_<SERVER>_API_KEY: <minted token>}`, which the caller adds
to the *child process* environment. The minted value therefore travels the same route a
static key does, and the config written to disk still holds only the `${VAR}` reference —
no credential reaches any file this tool writes. See `references/mcp-auth.md`.

Every failure here raises `Abort`. Falling back to an unauthenticated run would surface as
`tool_used` "called 0x" rather than as an auth error, which reads as a broken skill and
costs an afternoon.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .harnesses.base import Abort

# One exchange per server per process. Both spawn sites (the harness and the agentic judge)
# ask for the same overlay, and a case at `runs: 3` asks repeatedly; without this the token
# endpoint would see one request per subprocess, which some IdPs rate-limit.
_CACHE: dict[str, str] = {}

MINT_TIMEOUT_S = 30

# Below this, a token is likely to expire part-way through a suite. The later cases then fail
# as "called 0x" while the earlier ones passed, which reads as flakiness rather than expiry.
SHORT_EXPIRY_S = 300

_REQUIRED = ("CLIENT_ID", "CLIENT_SECRET", "TOKEN_URL")


def _env_key(server_name: str) -> str:
    """`Acme-Feedback` -> `ACME_FEEDBACK`. Mirrors the static-key convention."""
    return "".join(ch if ch.isalnum() else "_" for ch in server_name).upper()


def api_key_var(server_name: str) -> str:
    """The variable a minted token is published under — the static-key name, reused."""
    return f"MCP_{_env_key(server_name)}_API_KEY"


def credentials_for(server_name: str) -> dict | None:
    """Client credentials declared for this server, or None if none are.

    Partially declared credentials raise rather than returning None: a caller who set
    CLIENT_ID and forgot CLIENT_SECRET wants to hear about it, not to get an
    unauthenticated run that fails three graders later for no visible reason.
    """
    key = _env_key(server_name)
    present = {name: os.environ.get(f"MCP_{key}_{name}") for name in _REQUIRED}
    if not any(present.values()):
        return None
    missing = [f"MCP_{key}_{name}" for name, val in present.items() if not val]
    if missing:
        raise Abort(
            f"MCP server {server_name!r} has incomplete OAuth client credentials — "
            f"missing {', '.join(missing)}. Set them, or unset the others to use "
            f"{api_key_var(server_name)} instead."
        )
    cfg = {
        "client_id": present["CLIENT_ID"],
        "client_secret": present["CLIENT_SECRET"],
        "token_url": present["TOKEN_URL"],
        "scope": os.environ.get(f"MCP_{key}_SCOPE") or None,
    }
    # A client secret sent over cleartext HTTP is a disclosed client secret. Refuse rather
    # than warn: the whole point of this path is to stop handling long-lived credentials
    # carelessly.
    if not cfg["token_url"].lower().startswith("https://"):
        raise Abort(
            f"MCP_{key}_TOKEN_URL must be https:// — refusing to send a client secret "
            f"in cleartext (got {cfg['token_url'].split('://')[0]}://…)"
        )
    return cfg


def mintable(server_name: str) -> bool:
    """True when this server can mint a token (and no static key overrides it)."""
    if os.environ.get(api_key_var(server_name)):
        return False
    return credentials_for(server_name) is not None


def env_for_servers(server_names) -> dict[str, str]:
    """`{api_key_var: token}` for every server that mints, ready to overlay onto os.environ.

    A server with a static key is skipped — an explicitly set key wins, so behaviour stays
    deterministic and no network call happens for a server that did not need one.
    """
    overlay: dict[str, str] = {}
    for name in server_names:
        if not mintable(name):
            continue
        if name not in _CACHE:
            _CACHE[name] = _mint(name, credentials_for(name))
        overlay[api_key_var(name)] = _CACHE[name]
    return overlay


def _mint(server_name: str, cfg: dict) -> str:
    """Exchange client credentials for an access token (RFC 6749 §4.4).

    Sends the credentials as form parameters (`client_secret_post`). No response body is
    ever put into an exception or a log line — an error body can carry a token.
    """
    fields = {
        "grant_type": "client_credentials",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }
    if cfg["scope"]:
        fields["scope"] = cfg["scope"]
    req = urllib.request.Request(
        cfg["token_url"],
        data=urllib.parse.urlencode(fields).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=MINT_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise Abort(
            f"token endpoint for MCP server {server_name!r} returned HTTP {exc.code} — "
            f"check MCP_{_env_key(server_name)}_CLIENT_ID / _CLIENT_SECRET / _SCOPE. "
            f"(Response body withheld: it can contain a token.)"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Abort(
            f"could not reach the token endpoint for MCP server {server_name!r} "
            f"({exc.__class__.__name__}) — check the URL and the runner's egress"
        ) from exc
    except json.JSONDecodeError as exc:
        raise Abort(
            f"token endpoint for MCP server {server_name!r} did not return JSON"
        ) from exc

    token = payload.get("access_token")
    if not token or not isinstance(token, str):
        raise Abort(
            f"token endpoint for MCP server {server_name!r} returned no access_token "
            f"(keys: {', '.join(sorted(payload)) or 'none'})"
        )
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in < SHORT_EXPIRY_S:
        # Not fatal, and not recoverable either — see the spec's non-goals. Saying it now is
        # what stops the expiry being diagnosed as a flaky skill later.
        print(
            f"  ! {server_name}: token expires in {int(expires_in)}s — shorter than a "
            f"typical suite. Later cases may fail as 'called 0x' when it lapses."
        )
    return token


def reset_cache() -> None:
    """Drop minted tokens. For tests, and for a caller that wants a fresh exchange."""
    _CACHE.clear()
