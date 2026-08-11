"""yamlmin — a dependency-free loader for the YAML subset 100xeval cases use.

Why we own this instead of depending on PyYAML: NFR-1 keeps the engine stdlib-only
so it runs in CI with zero setup. The subset is exactly what `case.yaml` needs and
no more:

  - block mappings (`key: value`, or `key:` then an indented block)
  - block sequences (`- item`), where an item may be a scalar, an inline flow
    collection, or a nested `key: value` mapping
  - inline flow collections: `[a, b]` and `{k: v, k2: v2}` (may nest)
  - scalars typed as: null (`null`, `~`, empty), bool (`true`/`false`), int, float,
    single/double-quoted strings, everything else a plain string
  - block scalars: literal `|` (keep newlines) and folded `>` (join lines with
    spaces, blank line = paragraph break), with `-` / `+` chomping. Content is
    taken verbatim — `#` inside a block scalar is text, not a comment.
  - `#` comments: a full-line comment, or an inline comment introduced by ` #`
    (space then hash) outside quotes

Block scalars were originally excluded ("if a case needs those, the case is wrong"),
but cases legitimately embed multi-line SQL as judge ground truth — one unreadable
1,200-character line is worse than supporting the feature YAML already has for this.

Deliberately unsupported (raises YamlError): anchors/aliases, multi-document `---`,
complex keys, tags.
"""

from __future__ import annotations


class YamlError(ValueError):
    """Raised on input outside the supported subset, with line context."""


def load(text: str):
    """Parse a YAML-subset document into Python data (dict/list/scalars)."""
    lines = _logical_lines(text)
    if not lines:
        return None
    value, idx = _parse_block(lines, 0, lines[0][0])
    if idx != len(lines):
        raise YamlError(f"line {lines[idx][2]}: unexpected content {lines[idx][1]!r}")
    return value


# Each logical line is (indent, content_without_comment, original_line_number,
# block_value). `block_value` is None normally; for a `key: |` / `key: >` header it
# carries the already-resolved block string (the parser then uses it as the value).
def _logical_lines(text: str) -> list[tuple[int, str, int, str | None]]:
    out: list[tuple[int, str, int, str | None]] = []
    raw_lines = text.splitlines()
    n = 0
    while n < len(raw_lines):
        raw = raw_lines[n]
        lineno = n + 1
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError(f"line {lineno}: tab in indentation (use spaces)")
        indent = len(raw) - len(raw.lstrip(" "))
        content = _strip_comment(raw.strip())
        if content == "":
            n += 1
            continue
        header = _block_scalar_header(content)
        if header:
            head, style, chomp = header
            # Block lines belong to the KEY, so they must out-indent where the key
            # starts — not the line — or `- key: |` would swallow its own siblings.
            key_indent = indent + (len(content) - len(content.lstrip("- ")))
            value, n = _read_block_scalar(raw_lines, n + 1, key_indent, style, chomp)
            out.append((indent, head, lineno, value))
            continue
        out.append((indent, content, lineno, None))
        n += 1
    return out


def _block_scalar_header(content: str):
    """`key: |-` → ('key:', '|', '-'); None when the line isn't a block header."""
    stripped = content.rstrip()
    for style in ("|", ">"):
        for chomp in ("-", "+", ""):
            if stripped.endswith(style + chomp):
                head = stripped[: len(stripped) - len(style + chomp)].rstrip()
                if head.endswith(":"):
                    return head, style, chomp
    return None


def _read_block_scalar(raw_lines, start, key_indent, style, chomp):
    """Collect the block's raw lines verbatim, dedent, and fold. Returns (value, next)."""
    body: list[str] = []
    n = start
    block_indent = None
    while n < len(raw_lines):
        raw = raw_lines[n]
        if raw.strip() == "":
            body.append("")           # blank lines belong to the block
            n += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent <= key_indent:
            break
        if block_indent is None:
            block_indent = indent     # first non-blank line sets the dedent baseline
        body.append(raw[block_indent:] if len(raw) >= block_indent else raw.lstrip(" "))
        n += 1
    while body and body[-1] == "":
        body.pop()

    if style == "|":
        text = "\n".join(body)
    else:                             # folded: join within a paragraph, blank = break
        paras, cur = [], []
        for line in body:
            if line == "":
                paras.append(" ".join(cur))
                cur = []
            else:
                cur.append(line.strip())
        paras.append(" ".join(cur))
        text = "\n\n".join(p for p in paras if p != "")

    if chomp == "-":
        return text, n
    return (text + "\n" if text else text), n


def _strip_comment(s: str) -> str:
    in_single = in_double = False
    for i, ch in enumerate(s):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            # A comment starts at line-start or after whitespace.
            if i == 0 or s[i - 1] == " ":
                return s[:i].rstrip()
    return s


def _parse_block(lines, idx, indent):
    """Parse a mapping or sequence whose entries sit at column `indent`."""
    if lines[idx][1].startswith("- "):
        return _parse_sequence(lines, idx, indent)
    return _parse_mapping(lines, idx, indent)


def _parse_sequence(lines, idx, indent):
    items = []
    while idx < len(lines):
        cur_indent, content, lineno, block = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise YamlError(f"line {lineno}: unexpected indent in sequence")
        if not content.startswith("-"):
            break
        rest = content[1:].lstrip()
        if rest == "":
            # Nested block owned by this item on the following lines.
            idx += 1
            if idx >= len(lines) or lines[idx][0] <= indent:
                items.append(None)
                continue
            value, idx = _parse_block(lines, idx, lines[idx][0])
            items.append(value)
        elif _looks_like_mapping_entry(rest):
            # `- key: value` — an inline mapping whose keys continue on deeper lines.
            item_indent = cur_indent + (len(content) - len(rest))
            synthetic = [(item_indent, rest, lineno, block)]
            j = idx + 1
            while j < len(lines) and lines[j][0] >= item_indent and not (
                lines[j][0] == cur_indent and lines[j][1].startswith("-")
            ):
                synthetic.append(lines[j])
                j += 1
            value, consumed = _parse_mapping(synthetic, 0, item_indent)
            if consumed != len(synthetic):
                raise YamlError(f"line {lineno}: could not parse sequence item")
            items.append(value)
            idx = j
        else:
            items.append(_scalar_or_flow(rest, lineno))
            idx += 1
    return items, idx


def _parse_mapping(lines, idx, indent):
    mapping: dict = {}
    while idx < len(lines):
        cur_indent, content, lineno, block = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise YamlError(f"line {lineno}: unexpected indent in mapping")
        if content.startswith("- "):
            break
        key, sep, value_str = _split_key(content, lineno)
        value_str = value_str.strip()
        if block is not None:
            mapping[key] = block            # `key: |` / `key: >` — resolved by the lexer
            idx += 1
        elif value_str != "":
            mapping[key] = _scalar_or_flow(value_str, lineno)
            idx += 1
        else:
            # Value is a nested block on the following, deeper-indented lines.
            idx += 1
            if idx < len(lines) and lines[idx][0] > indent:
                value, idx = _parse_block(lines, idx, lines[idx][0])
                mapping[key] = value
            elif idx < len(lines) and lines[idx][0] == indent and lines[idx][1].startswith("- "):
                value, idx = _parse_sequence(lines, idx, indent)
                mapping[key] = value
            else:
                mapping[key] = None
    return mapping, idx


def _split_key(content, lineno):
    in_single = in_double = False
    for i, ch in enumerate(content):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            if i + 1 == len(content) or content[i + 1] == " ":
                return _unquote(content[:i].strip()), ":", content[i + 1 :]
    raise YamlError(f"line {lineno}: expected 'key: value', got {content!r}")


def _looks_like_mapping_entry(s: str) -> bool:
    if s.startswith(("[", "{", '"', "'")):
        return False
    try:
        _split_key(s, 0)
        return True
    except YamlError:
        return False


def _scalar_or_flow(s: str, lineno: int):
    s = s.strip()
    if s.startswith("["):
        return _parse_flow(s, lineno)[0]
    if s.startswith("{"):
        return _parse_flow(s, lineno)[0]
    return _scalar(s)


def _parse_flow(s, lineno):
    """Parse an inline flow collection; returns (value, chars_consumed)."""
    if s[0] == "[":
        return _parse_flow_seq(s, lineno)
    if s[0] == "{":
        return _parse_flow_map(s, lineno)
    tok, consumed = _read_flow_scalar(s)
    return _scalar(tok), consumed


def _parse_flow_seq(s, lineno):
    assert s[0] == "["
    items = []
    i = 1
    while i < len(s):
        while i < len(s) and s[i] in " ,":
            i += 1
        if i < len(s) and s[i] == "]":
            return items, i + 1
        value, consumed = _parse_flow(s[i:], lineno)
        items.append(value)
        i += consumed
    raise YamlError(f"line {lineno}: unterminated '['")


def _parse_flow_map(s, lineno):
    assert s[0] == "{"
    mapping: dict = {}
    i = 1
    while i < len(s):
        while i < len(s) and s[i] in " ,":
            i += 1
        if i < len(s) and s[i] == "}":
            return mapping, i + 1
        key_tok, consumed = _read_flow_scalar(s[i:], stop=":")
        i += consumed
        if i >= len(s) or s[i] != ":":
            raise YamlError(f"line {lineno}: expected ':' in flow mapping")
        i += 1
        while i < len(s) and s[i] == " ":
            i += 1
        value, consumed = _parse_flow(s[i:], lineno)
        mapping[_scalar(key_tok.strip())] = value
        i += consumed
    raise YamlError(f"line {lineno}: unterminated '{{'")


def _read_flow_scalar(s, stop=""):
    """Read one scalar token from a flow context, respecting quotes/brackets."""
    if s and s[0] in "\"'":
        quote = s[0]
        j = 1
        while j < len(s):
            if s[j] == quote:
                return s[: j + 1], j + 1
            j += 1
        raise YamlError("unterminated quoted scalar")
    j = 0
    while j < len(s) and s[j] not in ",]}" and s[j] not in stop:
        j += 1
    return s[:j].strip(), j


def _scalar(tok: str):
    if tok == "" or tok in ("null", "~", "Null", "NULL"):
        return None
    if tok in ("true", "True", "TRUE"):
        return True
    if tok in ("false", "False", "FALSE"):
        return False
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return _unquote(tok)
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


_DQ_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "r": "\r",
               "0": "\0", "/": "/", " ": " "}


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        inner = tok[1:-1]
        if tok[0] != '"':
            return inner.replace("''", "'")
        # One left-to-right pass. Sequential .replace() got `\\` wrong twice over: it was
        # not handled at all, so a grader pattern written `"\\s*%"` reached `re` as a
        # literal backslash and matched nothing — and for a not_contains grader a pattern
        # that matches nothing is one that cannot fail. Chained replaces also mis-handle
        # `"\\n"`, turning an escaped backslash followed by n into a newline.
        out, i = [], 0
        while i < len(inner):
            ch = inner[i]
            if ch == "\\" and i + 1 < len(inner):
                nxt = inner[i + 1]
                if nxt in _DQ_ESCAPES:
                    out.append(_DQ_ESCAPES[nxt])
                    i += 2
                    continue
                # Not a YAML escape (`\s`, `\b`, `\d` …). Keep it verbatim: these are
                # regex escapes, and dropping the backslash would silently break them.
                out.append(ch)
                out.append(nxt)
                i += 2
                continue
            out.append(ch)
            i += 1
        return "".join(out)
    return tok
