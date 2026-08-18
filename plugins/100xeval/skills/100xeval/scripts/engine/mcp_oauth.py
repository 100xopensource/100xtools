"""OAuth client-credentials support for MCP servers.

The runner can mint its own short-lived MCP access token instead of being handed a
long-lived static key. A server declares credentials in the environment, on the same
naming convention as the static key:

    MCP_<SERVER>_CLIENT_ID       MCP_<SERVER>_TOKEN_URL    (optional — discovered if unset)
    MCP_<SERVER>_CLIENT_SECRET   MCP_<SERVER>_SCOPE        (optional — usually omit, see below)
                                 MCP_<SERVER>_AUTH_STYLE   (optional — basic | post)

`env_for_servers` returns `{MCP_<SERVER>_API_KEY: <minted token>}`, which the caller adds
to the *child process* environment. The minted value therefore travels the same route a
static key does, and the config written to disk still holds only the `${VAR}` reference —
no credential reaches any file this tool writes. See `references/mcp-auth.md`.

Three defaults are set by what real authorization servers do, not by what the RFC permits:

* **HTTP Basic for the client credentials** (`client_secret_basic`). Form-encoded
  credentials (`client_secret_post`) are equally legal and are what many examples show, but
  connectors observed in practice want Basic. Override per server with `_AUTH_STYLE=post`.
* **No `scope` unless you set one.** An authorization server typically assigns the client's
  own resource-server scope, and sending a scope it does not expect — `openid` especially —
  is *rejected* rather than ignored. Leave it unset unless you know the server wants one.
* **The token endpoint is discovered** from the MCP server's URL (RFC 9728 protected-resource
  metadata, then RFC 8414 authorization-server metadata), so the same configuration works
  against staging and production without naming an endpoint. `_TOKEN_URL` skips discovery.

Every failure raises `Abort`. Falling back to an unauthenticated run would surface as
`tool_used` "called 0x" rather than as an auth error, which reads as a broken skill and
costs an afternoon.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .harnesses.base import Abort

HTTP_TIMEOUT_S = 30

# Re-mint this far before expiry. A token that lapses mid-suite fails the later cases only,
# which reads as a flaky skill rather than as an expiry — so never run one to the edge.
EXPIRY_MARGIN_S = 300

# Keyed by token endpoint, not by server: two servers behind one authorization server share
# a token, and minting twice for the same endpoint is a wasted round trip.
_CACHE: dict[str, tuple[str, float]] = {}

_REQUIRED = ("CLIENT_ID", "CLIENT_SECRET")


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
    style = (os.environ.get(f"MCP_{key}_AUTH_STYLE") or "basic").lower()
    if style not in ("basic", "post"):
        raise Abort(f"MCP_{key}_AUTH_STYLE must be 'basic' or 'post', got {style!r}")
    cfg = {
        "client_id": present["CLIENT_ID"],
        "client_secret": present["CLIENT_SECRET"],
        "token_url": os.environ.get(f"MCP_{key}_TOKEN_URL") or None,
        "scope": os.environ.get(f"MCP_{key}_SCOPE") or None,
        "auth_style": style,
        "env_key": key,
    }
    if cfg["token_url"] and not cfg["token_url"].lower().startswith("https://"):
        # A client secret sent over cleartext HTTP is a disclosed client secret.
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


def env_for_servers(servers) -> dict[str, str]:
    """`{api_key_var: token}` for every server that mints, ready to overlay onto os.environ.

    `servers` maps server name -> MCP URL; the URL is only needed when the token endpoint
    has to be discovered. A server with a static key is skipped — an explicitly set key
    wins, so behaviour stays deterministic and no network call happens for a server that
    did not need one.
    """
    if not isinstance(servers, dict):                     # tolerate a bare name sequence
        servers = {name: "" for name in servers}
    overlay: dict[str, str] = {}
    for name, url in servers.items():
        if not mintable(name):
            continue
        cfg = credentials_for(name)
        token_url = cfg["token_url"] or discover_token_endpoint(name, url)
        cached = _CACHE.get(token_url)
        if cached and cached[1] - EXPIRY_MARGIN_S > time.time():
            overlay[api_key_var(name)] = cached[0]
            continue
        token, expires_in = _mint(name, cfg, token_url)
        _CACHE[token_url] = (token, time.time() + expires_in)
        overlay[api_key_var(name)] = token
    return overlay


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode())


def discover_token_endpoint(server_name: str, mcp_url: str) -> str:
    """MCP URL -> token endpoint, per RFC 9728 then RFC 8414.

    Both hops are unauthenticated public metadata. Errors name the URL that failed, because
    "discovery broke" and "credentials are wrong" need different fixes and one generic
    message sends people to the wrong one.
    """
    key = _env_key(server_name)
    if not mcp_url:
        raise Abort(
            f"cannot discover a token endpoint for MCP server {server_name!r} — its URL is "
            f"unknown. Set MCP_{key}_TOKEN_URL explicitly."
        )
    parts = urllib.parse.urlparse(mcp_url)
    prm = f"{parts.scheme}://{parts.netloc}/.well-known/oauth-protected-resource{parts.path}"
    try:
        meta = _get_json(prm)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        # The path-inserted form is what the spec describes, but some deployments serve the
        # plain well-known at the resource prefix. Try that before giving up.
        try:
            meta = _get_json(f"{mcp_url.rsplit('/', 1)[0]}/.well-known/oauth-protected-resource")
        except Exception:
            raise Abort(
                f"protected-resource metadata not readable at {prm} ({exc.__class__.__name__}) "
                f"— set MCP_{key}_TOKEN_URL to skip discovery"
            ) from exc

    servers = meta.get("authorization_servers") or []
    if not servers:
        raise Abort(f"{prm} lists no authorization_servers — set MCP_{key}_TOKEN_URL")
    issuer = str(servers[0]).rstrip("/")
    ip = urllib.parse.urlparse(issuer)
    for candidate in (
        f"{ip.scheme}://{ip.netloc}/.well-known/oauth-authorization-server{ip.path}",
        f"{issuer}/.well-known/oauth-authorization-server",
    ):
        try:
            token_url = _get_json(candidate).get("token_endpoint")
        except Exception:
            continue
        if token_url:
            return token_url
    raise Abort(
        f"no token_endpoint discoverable for issuer {issuer} — set MCP_{key}_TOKEN_URL"
    )


def _mint(server_name: str, cfg: dict, token_url: str) -> tuple[str, int]:
    """One client_credentials exchange (RFC 6749 §4.4). Returns (token, expires_in).

    Only the RFC's own `error` / `error_description` fields are surfaced on failure — never
    the raw body, which can carry a token.
    """
    fields = {"grant_type": "client_credentials"}
    if cfg["scope"]:
        fields["scope"] = cfg["scope"]
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    if cfg["auth_style"] == "basic":
        pair = f"{cfg['client_id']}:{cfg['client_secret']}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(pair).decode()
    else:
        fields["client_id"] = cfg["client_id"]
        fields["client_secret"] = cfg["client_secret"]

    req = urllib.request.Request(
        token_url, data=urllib.parse.urlencode(fields).encode(),
        headers=headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise Abort(_http_error_message(server_name, cfg, exc)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Abort(
            f"could not reach the token endpoint {token_url} for MCP server "
            f"{server_name!r} ({exc.__class__.__name__}) — check the URL and egress"
        ) from exc
    except json.JSONDecodeError as exc:
        raise Abort(
            f"token endpoint {token_url} did not return JSON for MCP server {server_name!r}"
        ) from exc

    token = payload.get("access_token")
    if not token or not isinstance(token, str):
        raise Abort(
            f"token endpoint for MCP server {server_name!r} returned no access_token "
            f"(keys: {', '.join(sorted(payload)) or 'none'})"
        )
    return token, int(payload.get("expires_in") or 3600)


def _http_error_message(server_name: str, cfg: dict, exc) -> str:
    """Status plus the RFC's own error fields. The raw body is never included."""
    code = getattr(exc, "code", "?")
    detail = ""
    try:
        body = json.loads(exc.read().decode("utf-8", "replace"))
        parts = [str(body[k]) for k in ("error", "error_description") if body.get(k)]
        if parts:
            detail = f": {' — '.join(parts)}"
    except Exception:
        pass  # a non-JSON body tells us nothing safe to print
    msg = (f"client_credentials rejected for MCP server {server_name!r} "
           f"(HTTP {code}){detail}")
    if code in (400, 401) and cfg["auth_style"] == "basic":
        msg += (f". If this server wants form-encoded credentials, set "
                f"MCP_{cfg['env_key']}_AUTH_STYLE=post")
    if code in (400, 401) and cfg["scope"]:
        msg += (f". Some servers reject any explicit scope — try unsetting "
                f"MCP_{cfg['env_key']}_SCOPE")
    return msg


def reset_cache() -> None:
    """Drop minted tokens. For tests, and for a caller that wants a fresh exchange."""
    _CACHE.clear()
