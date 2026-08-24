"""Scrub credential-shaped content on the way out of the private ledger.

Capture stores raw prompts, tool inputs, and tool output. Publishing copies that
into shared storage — often a folder a sync client uploads. This module is the
transform between the two, and it is the only reason publishing a raw record is
defensible at all.

**What it promises, exactly.** It removes values that *look like* credentials:
known key prefixes, `Authorization` headers, JWTs, PEM blocks, and any value whose
key names it as a secret. That is a real reduction in exposure and it is *not* a
guarantee of safety. It cannot recognise:

- a credential that looks like ordinary prose or a plain word,
- an internal hostname, customer name, or ticket id,
- personal data in a prompt someone typed,
- a secret inside a base64 blob or an image.

Say that plainly to anyone deciding what to publish. The other defensible answer to
the same question is to never let a raw archive leave the machine at all;
publishing redacted raw is a different trade, and the person making it deserves to
know which risk they are accepting.

**Why the patterns here are not the repo linter's `SECRET_PATTERNS`.** They look
similar and pull in opposite directions. The linter optimizes for *precision* — a
false positive there costs a plugin its security sub-score, so it exempts
self-describing placeholders like `password: 'your-password-here'`. A redactor
optimizes for *recall*: redacting a placeholder costs nothing, and missing one
real credential costs everything. Sharing a list would force one of the two to be
wrong.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# What redaction does and does not promise. Kept here, next to the rules it
# describes, and repeated verbatim by every surface that reports a redaction
# count: a count of 0 means the scrubber matched nothing, which is not the same
# claim as "there was nothing to find".
CAVEAT = (
    "redaction removes credential-shaped values; it cannot recognise a secret "
    "that reads like prose, or personal data in a prompt"
)

PLACEHOLDER = "[redacted:{name}]"

# Values are replaced wholesale when their *key* names them a secret, whatever
# their shape. This is what catches `{"password": "hunter2"}`, which no
# shape-matching rule can: the value is an ordinary word and only its key gives it
# away. Matched against the key with separators ignored, so `api_key`, `apiKey`,
# and `API-KEY` all hit.
# One list, two consumers: the text rule below and `_is_sensitive_key`. Kept in one
# place because the two drifting apart is how `AWS_SECRET_ACCESS_KEY` ends up caught in
# a prompt and missed in a tool argument.
_CREDENTIAL_WORDS = (
    r"api[_-]?key|api[_-]?secret|auth[_-]?token|access[_-]?token|access[_-]?key"
    r"|secret[_-]?key|client[_-]?secret|refresh[_-]?token|private[_-]?key"
    r"|password|passwd|secret|token|credential"
)
_CREDENTIAL_WORD_RE = re.compile(rf"(?i)(?:{_CREDENTIAL_WORDS})")

SENSITIVE_KEYS = (
    "apikey",
    "apisecret",
    "accesskey",
    "accesskeyid",
    "accesstoken",
    "auth",
    "authorization",
    "bearer",
    "clientsecret",
    "connectionstring",
    "cookie",
    "credential",
    "credentials",
    "dsn",
    "env",
    "idtoken",
    "password",
    "passwd",
    "privatekey",
    "pwd",
    "refreshtoken",
    "secret",
    "secretaccesskey",
    "secretkey",
    "sessiontoken",
    "setcookie",
    "token",
)

_KEY_SEPARATORS = re.compile(r"[^a-z0-9]+")


@dataclass
class Redaction:
    """A redacted value and what was removed to get it."""

    value: Any
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def clean(self) -> bool:
        return self.total == 0


def _sub(name: str) -> str:
    return PLACEHOLDER.format(name=name)


# Ordered: earlier rules win, so a PEM block is removed whole before its base64
# body can be matched piecemeal, and a labelled assignment is caught before a bare
# token shape inside it.
TEXT_RULES: tuple[tuple[str, re.Pattern[str], "str | Callable[[re.Match[str]], str]"], ...] = (
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        _sub("private-key"),
    ),
    (
        "certificate",
        re.compile(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL
        ),
        _sub("certificate"),
    ),
    (
        # The header form, so a captured HTTP request or a curl command in a tool
        # input does not carry a live token.
        "authorization-header",
        re.compile(r"(?i)\b(authorization\s*[:=]\s*)(bearer|basic|token)\s+\S+"),
        r"\1" + _sub("authorization"),
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        _sub("jwt"),
    ),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b"), _sub("aws-access-key")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"), _sub("github-token")),
    ("slack-token", re.compile(r"\bxox[baprse]-[A-Za-z0-9-]{10,}\b"), _sub("slack-token")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), _sub("google-api-key")),
    (
        "stripe-key",
        re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b"),
        _sub("stripe-key"),
    ),
    (
        "secret-key-literal",
        re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b"),
        _sub("secret-key-literal"),
    ),
    (
        "npm-token",
        re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"),
        _sub("npm-token"),
    ),
    (
        # A labelled assignment: the value is redacted whatever it looks like, and
        # a self-describing placeholder is redacted too. Deliberately unlike the
        # linter, which exempts placeholders to keep its score honest.
        "labelled-credential",
        re.compile(
            # The credential word may sit ANYWHERE inside the key, not only at its
            # start. Anchoring with \b missed `AWS_SECRET_ACCESS_KEY=` outright —
            # `_` is a word character, so there is no boundary before `SECRET`, and
            # the separator does not follow the word either. That is the single most
            # common credential name there is, and it was travelling verbatim.
            r"(?i)([A-Za-z0-9_.\[\]-]*"
            r"(?:" + _CREDENTIAL_WORDS + r")"
            r"[A-Za-z0-9_.\[\]-]*)"
            r"(\s*[:=]\s*)"
            r"(\"[^\"]{4,}\"|'[^']{4,}'|[^\s,;)\]}]{4,})"
        ),
        lambda m: f"{m.group(1)}{m.group(2)}{_sub('labelled-credential')}",
    ),
)


def redact_text(text: str) -> Redaction:
    """Replace every credential-shaped run in one string."""
    counts: dict[str, int] = {}
    for name, pattern, replacement in TEXT_RULES:
        text, hits = pattern.subn(replacement, text)
        if hits:
            counts[name] = counts.get(name, 0) + hits
    return Redaction(text, counts)


def _is_sensitive_key(key: str) -> bool:
    """Whether a key names its value a secret, ignoring separators and plurals.

    A trailing `s` is dropped only when the singular is in the closed set above, so
    `tokens` and `cookies` hit while `access` and `author` do not.
    """
    folded = _KEY_SEPARATORS.sub("", key.lower())
    if folded in SENSITIVE_KEYS:
        return True
    if folded.endswith("s") and folded[:-1] in SENSITIVE_KEYS:
        return True
    # Anything that merely CONTAINS a credential word counts. The closed set alone
    # missed every vendor-prefixed name a real environment is full of —
    # `AWS_SECRET_ACCESS_KEY`, `DEPLOY_TOKEN`, `myClientSecret`. Recall is the whole
    # job here: redacting `tokenizer` costs nothing, missing one costs everything.
    return bool(_CREDENTIAL_WORD_RE.search(key))


def redact_value(value: Any) -> Redaction:
    """Walk a JSON value, redacting strings and any value under a sensitive key.

    Structure is preserved: a redacted string stays a string and a redacted
    container stays a container of the same shape, so a published record still
    parses and still reads like the record it came from.
    """
    counts: dict[str, int] = {}

    def bump(other: dict[str, int]) -> None:
        for name, hits in other.items():
            counts[name] = counts.get(name, 0) + hits

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            result = redact_text(node)
            bump(result.counts)
            return result.value
        if isinstance(node, dict):
            out: dict[str, Any] = {}
            for key, item in node.items():
                if isinstance(key, str) and _is_sensitive_key(key):
                    # The key alone is enough. Descending would leave a plain-word
                    # credential in place, which is the case this rule exists for.
                    out[key] = _sub("sensitive-key")
                    bump({"sensitive-key": 1})
                    continue
                out[key] = walk(item)
            return out
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, tuple):
            return [walk(item) for item in node]
        return node

    return Redaction(walk(value), counts)


# Envelope fields describe *where a record came from*, not what was said, so they
# pass through untouched — redacting them would break the ordering, dedup, and
# provenance a reader needs to make sense of the rest.
_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "source",
        "source_event",
        "session_id",
        "observed_at",
        "source_timestamp",
        "sequence",
        "source_cursor",
        "completeness",
        "integrity_hash",
    }
)


def redact_record(record: dict[str, Any]) -> Redaction:
    """Redact one ledger record, marking it as transformed.

    The returned record keeps the **original** `integrity_hash`, and carries
    `redacted: {...}` saying so. That is deliberate: verifying a published record
    against that hash is *expected* to fail, and the failure is the signal that
    what you are holding is not what was captured. A recomputed hash would erase
    exactly the distinction a reader needs.
    """
    result = redact_value(
        {key: value for key, value in record.items() if key not in _ENVELOPE_FIELDS}
    )
    out = {key: value for key, value in record.items() if key in _ENVELOPE_FIELDS}
    out.update(result.value)
    out["redacted"] = {
        "counts": result.counts,
        "integrity_hash_covers": "the record before redaction",
    }
    return Redaction(out, result.counts)


def redact_records(records: list[dict[str, Any]]) -> Redaction:
    """Redact a whole ledger, totalling what was removed across it."""
    out: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for record in records:
        result = redact_record(record)
        out.append(result.value)
        for name, hits in result.counts.items():
            counts[name] = counts.get(name, 0) + hits
    return Redaction(out, counts)
