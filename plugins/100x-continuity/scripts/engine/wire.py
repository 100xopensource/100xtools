"""The rules for talking to a URL somebody else minted, in one place.

Both directions of the service store — sending a bundle up, pulling one back down —
go through a URL this plugin did not create and cannot verify by itself. The refusals
below are the whole protection on that path, so they live here once rather than in
each direction, where one copy could quietly drift into being the lenient one.

- **`https` only**, refused before any bytes move.
- **No credentials in the URL.** A `user:pass@host` URL is refused outright.
- **No redirects, ever.** A presigned URL is signed for one host and one path.
  Following a redirect on the way up would replay the payload — prompts and tool
  output included — to a location nobody signed for; on the way down it would accept
  a bundle from a host the operator never named.
- **An optional host pin.** The mint is supposed to be the operator's own service,
  but the URL arrives through a model turn, and a confused or manipulated turn could
  name any host. Unset means "trust the mint", which is the default because this
  plugin cannot know the operator's bucket host.

Headers are sent exactly as the mint supplied them. A presigned URL commits to the
headers it was signed with, so adding, reordering, or "fixing" one invalidates the
signature and the store answers 403.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_HOSTS_ENV = "CONTINUITY_ALLOWED_HOSTS"

DEFAULT_TIMEOUT_SECONDS = 120


class TransferError(Exception):
    """A transfer could not be attempted, or did not complete.

    Carries a stable `code` so a caller can distinguish "mint again" from "fix the
    configuration" without matching on prose.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect rather than follow it to a host nobody signed for."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise TransferError(
            "unexpected_redirect",
            f"the minted URL redirected to {newurl}; refusing to follow it",
        )


def opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(NoRedirects)


def validate_url(url: str) -> str:
    """Return `url` if this plugin is willing to talk to it; raise if it is not."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise TransferError(
            "insecure_url",
            f"the minted URL must be https, got {parsed.scheme or 'nothing'}",
        )
    if not parsed.hostname:
        raise TransferError("invalid_url", "the minted URL has no host")
    if parsed.username or parsed.password:
        raise TransferError(
            "credentials_in_url", "the minted URL embeds credentials; refusing to use it"
        )
    allowed = os.environ.get(ALLOWED_HOSTS_ENV)
    if allowed:
        hosts = {host.strip().lower() for host in allowed.split(",") if host.strip()}
        if parsed.hostname.lower() not in hosts:
            raise TransferError(
                "host_not_allowed", f"{parsed.hostname} is not in {ALLOWED_HOSTS_ENV}"
            )
    return url


def read_mint(mint: object) -> tuple[str, dict[str, str]]:
    """The two fields a mint result must carry, validated.

    Only `url` and `required_headers` are read. Anything else the operator's tool
    returns is ignored rather than second-guessed — it is their protocol, not ours.
    """
    if not isinstance(mint, dict):
        raise TransferError("bad_mint", "the mint result must be a JSON object")
    url = mint.get("url")
    if not isinstance(url, str) or not url:
        raise TransferError("bad_mint", "the mint result carries no url")
    headers = mint.get("required_headers") or {}
    if not isinstance(headers, dict):
        raise TransferError("bad_mint", "required_headers must be a JSON object")
    return url, {str(k): str(v) for k, v in headers.items()}


def http_code(status: int) -> str:
    """Map a status to a stable code, so callers act rather than parse prose."""
    if status in (401, 403):
        # Overwhelmingly an expired presign rather than a permissions change: the
        # remedy is to mint again, not to touch access rules.
        return "url_expired_or_forbidden"
    if status == 404:
        return "target_missing"
    if status == 413:
        return "body_too_large"
    if 500 <= status < 600:
        return "store_unavailable"
    return "not_accepted"


def send(
    request: urllib.request.Request,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    opener_factory=None,
    reader=None,
):
    """Perform one request, mapping every failure to a coded `TransferError`.

    `opener_factory` exists so tests exercise this without a network; production
    callers leave it alone. `reader` is handed the live response so a caller can
    stream a body without this function deciding how much to hold in memory.
    """
    factory = opener_factory or opener
    try:
        with factory().open(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            payload = reader(response) if reader else None
    except urllib.error.HTTPError as exc:
        raise TransferError(http_code(exc.code), f"the store answered {exc.code}") from exc
    except TransferError:
        raise
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise TransferError("unreachable", f"could not reach the store: {exc}") from exc
    if not 200 <= int(status) < 300:
        raise TransferError("not_accepted", f"the store answered {status}")
    return int(status), payload
