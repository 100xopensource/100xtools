"""Claude Code harness — the proven `claude -p` runtime contract.

This adapter is named for the RUNTIME it drives (the Claude Code CLI), not for any
surface. Which surface a case emulates is the orthogonal `entrypoint` axis — that
surface's real system prompt, layered on top of this runtime. With the default
`entrypoint: none` a case runs on Claude Code's own prompt; supply an entrypoint file
when your users are on a different surface that runs on this same engine (see
`engine/entrypoints/README.md`).

Single-turn `claude -p --output-format json` (never --resume/stream-json — they drop
MCP servers). Tool calls come from the session transcript, not the JSON result
(which omits them), so `tool_used` reads `~/.claude/projects/**/<session_id>.jsonl`.

MCP is always driven through `--mcp-config … --strict-mcp-config`, so a declared server
resolves the same way locally and in CI. claude.ai account connectors are deliberately
NOT a supported path — they load only under an interactive claude.ai login, so a run that
depended on one could never be reproduced headlessly.

The two parse functions are pure and unit-tested against fixtures (no live call).
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile

from .. import mcp_oauth
from ..models import Case, RunResult, ToolCall
from .base import Abort, register_harness

TIMEOUT_S = 300      # default only; a case may raise it via `execution.timeout_s`


class ClaudeCodeHarness:
    name = "claude_code"

    def supports(self, grader_type: str) -> bool:
        # Claude Code exposes tool calls via the session transcript, so every grader works.
        return grader_type in ("tool_used", "regex", "llm", "static")

    def preflight(self, case: Case) -> None:
        if shutil.which("claude") is None:
            raise Abort("`claude` CLI not found on PATH — install Claude Code to run behavioral evals")
        verify_entrypoint(case)

    def run(self, case: Case, model: str | None, workspace: str | None = None) -> RunResult:
        # Persistent workspace (under .runs/<run_id>/…) when given, else ephemeral temp.
        if workspace:
            os.makedirs(workspace, exist_ok=True)
            return self._run_in(case, model, workspace)
        with tempfile.TemporaryDirectory(prefix="100xeval-") as tmp:
            return self._run_in(case, model, tmp)

    def _run_in(self, case: Case, model: str | None, tmp: str) -> RunResult:
        # Absolute, because we invoke with cwd=tmp — relative --plugin-dir / --mcp-config
        # would otherwise resolve against tmp itself and not be found.
        tmp = os.path.abspath(tmp)
        timeout_s = int(getattr(case, "timeout_s", None) or TIMEOUT_S)
        entry = _load_entrypoint(case)
        if True:
            plugin_copy = _stage_plugin(case, tmp)
            cmd = ["claude", "-p", case.prompt, "--output-format", "json"]
            if plugin_copy:
                cmd += ["--plugin-dir", plugin_copy]
            if model:
                cmd += ["--model", model]
            # `--max-turns` is absent from `claude --help` but IS accepted (verified
            # 2026-08-06: the result JSON reports `num_turns`). Without it a case's
            # `max_turns` was parsed, stored in cases.json, and silently ignored — so a
            # long report build could not be given more turns than the CLI default.
            if case.max_turns:
                cmd += ["--max-turns", str(case.max_turns)]

            # The case's `mcp_config`, else one auto-built from the plugin's .mcp.json.
            # None only when nothing declares a server; there is no ambient fallback.
            strict_cfg = resolve_strict_mcp_config(case)
            if strict_cfg is not None:
                cfg_path = os.path.join(tmp, "mcp-config.json")
                with open(cfg_path, "w", encoding="utf-8") as fh:
                    json.dump(strict_cfg, fh)
                cmd += ["--mcp-config", cfg_path, "--strict-mcp-config"]

            if case.allowed_tools:
                # Strict config gives exactly one MCP naming scheme, `mcp__<Server>__<tool>`,
                # so a granted tool is spelled the way the server declares it. Note the
                # server-name CASE is significant here and in `tool_used` graders.
                cmd += ["--allowedTools", ",".join(case.allowed_tools)]
            # REPLACES the prompt (not --append-*): we want the surface's, not Claude Code's
            # plus it. Empty with `entrypoint: none`. Not ARG_MAX-bound — no shell involved.
            if entry:
                cmd += ["--system-prompt", entry]
            if case.append_system_prompt:
                cmd += ["--append-system-prompt", case.append_system_prompt]
            # Claude writes its own rich debug trace to this file (implicitly enables debug
            # mode); it persists in the run dir for post-mortem.
            debug_log = os.path.join(tmp, "claude-debug.log")
            cmd += ["--debug-file", debug_log]
            redacted = _redact_cmd(cmd)  # for logs: no 257KB prompt, no token
            # A minted OAuth token travels here and nowhere else — the config on disk holds
            # only `${VAR}`, and Claude Code expands it from this environment. Overlay onto
            # os.environ rather than replacing it: the child needs PATH and the caller's own
            # auth as much as it needs this.
            child_env = {**os.environ, **mcp_env_overlay(case)}
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout_s,
                    cwd=tmp,  # neutral cwd so nothing else loads
                    env=child_env,
                )
            except subprocess.TimeoutExpired:
                return RunResult(error=f"timeout after {timeout_s}s", command=redacted, debug_log=debug_log)
            if proc.returncode != 0:
                return RunResult(
                    error=f"claude exited {proc.returncode}: {proc.stderr[:500]}",
                    command=redacted, returncode=proc.returncode,
                    stdout=proc.stdout, stderr=proc.stderr, debug_log=debug_log,
                )
            final_text, session_id, cost, duration = parse_cli_json(proc.stdout)
            usage = parse_usage(proc.stdout)
            transcript_path = find_transcript_path(session_id) if session_id else None
            tool_calls = []
            if transcript_path:
                with open(transcript_path, encoding="utf-8") as fh:
                    tool_calls = parse_transcript_tool_calls(fh.read())
            return RunResult(
                final_text=final_text, tool_calls=tool_calls, cost_usd=cost, tokens=usage,
                duration_ms=duration, session_id=session_id, transcript_path=transcript_path,
                command=redacted, returncode=proc.returncode, stderr=proc.stderr, debug_log=debug_log,
            )


def _redact_cmd(cmd: list[str]) -> list[str]:
    """Copy argv for logging, replacing the ~257KB --system-prompt value with a marker."""
    out = []
    skip = False
    for i, arg in enumerate(cmd):
        if skip:
            out.append(f"<{len(arg)} chars>")
            skip = False
            continue
        out.append(arg)
        if arg == "--system-prompt":
            skip = True
    return out


def _stage_plugin(case: Case, tmp: str) -> str | None:
    """Copy the first plugin into tmp, dereferencing common/ symlinks; keep .mcp.json."""
    if not case.plugins:
        return None
    src = os.path.normpath(os.path.join(case.path, case.plugins[0]))
    dest = os.path.join(tmp, "plugin")
    shutil.copytree(src, dest, symlinks=False)  # -L: deref symlinks
    return dest


def _entrypoint_path(case: Case) -> str | None:
    """Absolute path to the surface's system-prompt file, or None if it doesn't exist."""
    engine_dir = os.path.dirname(os.path.dirname(__file__))  # …/scripts/engine/
    path = os.path.abspath(os.path.join(engine_dir, "entrypoints", f"{case.entrypoint}.md"))
    return path if os.path.isfile(path) else None


def available_entrypoints() -> list[str]:
    """Entrypoint names that ship with the engine, for error messages."""
    engine_dir = os.path.dirname(os.path.dirname(__file__))
    d = os.path.join(engine_dir, "entrypoints")
    if not os.path.isdir(d):
        return []
    return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md") and f != "README.md")


def verify_entrypoint(case: Case) -> None:
    """Abort when the named entrypoint has no file.

    `entrypoint: none` is the explicit "no surface" choice — the run uses the harness's
    own system prompt, which is what you want when evaluating a plugin in Claude Code
    itself. Any OTHER name must resolve to a file: naming a surface and silently getting
    no system prompt would score a case that emulated nothing, which is worse than a
    failure because it looks like a pass.
    """
    if case.entrypoint in ("none", "", None):
        return
    if _entrypoint_path(case) is not None:
        return
    names = available_entrypoints()
    have = ", ".join(names) if names else "(none found)"
    raise Abort(
        f"entrypoint {case.entrypoint!r} has no file at engine/entrypoints/{case.entrypoint}.md — "
        f"the run would emulate no surface at all. Available: {have}. "
        f"Fix `execution.entrypoint` in the case, or add the surface's real system prompt "
        f"(see engine/entrypoints/README.md)."
    )


def _load_entrypoint(case: Case) -> str:
    path = _entrypoint_path(case)
    if path:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return ""


def parse_cli_json(stdout: str):
    """Extract (final_text, session_id, cost_usd, duration_ms) from `-p --output-format json`."""
    try:
        obj = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout.strip(), None, 0.0, 0
    if isinstance(obj, list):  # some versions emit an event array
        obj = next((o for o in reversed(obj) if isinstance(o, dict) and o.get("type") == "result"), obj[-1])
    final = obj.get("result") or obj.get("text") or ""
    session = obj.get("session_id") or obj.get("sessionId")
    cost = float(obj.get("total_cost_usd") or obj.get("cost_usd") or 0.0)
    duration = int(obj.get("duration_ms") or obj.get("durationMs") or 0)
    return final, session, cost, duration


# The four token counters the CLI reports. Cache reads/creations are billed differently
# from plain input, so they are kept SEPARATE rather than folded into one number — a run
# that looks expensive is usually cache creation, and that only shows if you can see it.
TOKEN_FIELDS = ("input_tokens", "output_tokens",
                "cache_read_input_tokens", "cache_creation_input_tokens")


def parse_usage(stdout: str) -> dict:
    """Token usage from `-p --output-format json`; zeros when absent or unparseable."""
    empty = dict.fromkeys(TOKEN_FIELDS, 0)
    try:
        obj = json.loads(stdout)
    except json.JSONDecodeError:
        return empty
    if isinstance(obj, list):
        obj = next((o for o in reversed(obj) if isinstance(o, dict) and o.get("type") == "result"), obj[-1])
    usage = obj.get("usage") or {}
    if not isinstance(usage, dict):
        return empty
    return {k: int(usage.get(k) or 0) for k in TOKEN_FIELDS}


def add_tokens(*token_dicts) -> dict:
    """Element-wise sum of usage dicts (per-run → per-case totals)."""
    total = dict.fromkeys(TOKEN_FIELDS, 0)
    for d in token_dicts:
        for k in TOKEN_FIELDS:
            total[k] += int((d or {}).get(k) or 0)
    return total


def find_transcript_path(session_id: str) -> str | None:
    """Absolute path to the session transcript `.jsonl`, or None if not found yet."""
    home = os.path.expanduser("~/.claude/projects")
    matches = glob.glob(os.path.join(home, "**", f"{session_id}.jsonl"), recursive=True)
    return matches[0] if matches else None


def read_transcript_tool_calls(session_id: str) -> list[ToolCall]:
    """Find the session transcript and pull tool_use blocks out of it."""
    path = find_transcript_path(session_id)
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        return parse_transcript_tool_calls(fh.read())


def parse_transcript_tool_calls(jsonl_text: str) -> list[ToolCall]:
    """Pure: extract ToolCalls from a Claude Code session transcript (.jsonl)."""
    calls: list[ToolCall] = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        blocks = []
        msg = obj.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), list):
            blocks = msg["content"]
        elif isinstance(obj.get("content"), list):
            blocks = obj["content"]
        elif obj.get("type") == "tool_use":
            blocks = [obj]
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "")
                raw_input = block.get("input", {})
                input_str = json.dumps(raw_input, sort_keys=True) if not isinstance(raw_input, str) else raw_input
                calls.append(ToolCall(name=name, input_str=input_str))
    return calls


def plugin_mcp_server_configs(case: Case) -> dict:
    """{name: cfg} for HTTP MCP servers the case's first plugin declares, or {}."""
    if not case.plugins:
        return {}
    mcp_path = os.path.join(os.path.normpath(os.path.join(case.path, case.plugins[0])), ".mcp.json")
    if not os.path.isfile(mcp_path):
        return {}
    try:
        with open(mcp_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    servers = data.get("mcpServers", {}) or {}
    return {name: cfg for name, cfg in servers.items() if isinstance(cfg, dict) and cfg.get("url")}


def _env_key(server_name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in server_name).upper()


def _bearer_var_name(server_name: str) -> str:
    """The env-var name holding this server's key: `MCP_<SERVER>_API_KEY`.

    Per-server by design: there is deliberately no key that applies to every declared
    server. A plugin can declare servers from two different vendors, and one shared
    variable would hand each vendor the other's credential.

    Never read from disk / .mcp.json — no secret belongs in the repo. CI injects these
    env vars from its secret store.
    """
    return f"MCP_{_env_key(server_name)}_API_KEY"


def mcp_env_overlay(case: Case) -> dict:
    """Env additions for this case's child processes: minted OAuth tokens, if any.

    Empty for the static-key path and for a case with no MCP, so the common case pays
    nothing and behaves exactly as before.
    """
    servers = _strict_servers(case)
    return mcp_oauth.env_for_servers(servers) if servers else {}


def _strict_servers(case: Case) -> dict:
    """`{name: url}` for the servers this case authenticates — its mcp_config's, else the
    plugin's. The URL matters: it is what token-endpoint discovery walks from."""
    cfg = load_case_mcp_config(case) if case.mcp_config else None
    source = cfg.get("mcpServers", {}) if cfg else plugin_mcp_server_configs(case)
    return {name: (entry or {}).get("url", "") for name, entry in source.items()}


def _bearer_var_for(server_name: str) -> str | None:
    """Which env-var NAME holds this server's key, or None when it has no credential.

    A mintable server counts: the variable is absent from `os.environ` at config-build time
    and is added to the child's environment just before spawn, so the emitted `${VAR}`
    reference resolves there. The config still never carries a value.
    """
    var = _bearer_var_name(server_name)
    if os.environ.get(var):
        return var
    return var if mcp_oauth.mintable(server_name) else None


def _inject_bearer(server_configs: dict) -> dict:
    """Copy servers, adding `Authorization: Bearer ${VAR}` where a header is absent.

    We emit the `${VAR}` reference (Claude Code expands it from env at load — see the MCP
    docs, env-var expansion in headers), NOT the token value, so the secret never lands
    in any file 100xeval writes. A config that already sets an Authorization header
    (e.g. its own `${VAR}`) is passed through untouched.
    """
    out = {}
    for name, cfg in server_configs.items():
        entry = {"type": cfg.get("type", "http"), "url": cfg.get("url", "")}
        if cfg.get("headers"):
            entry["headers"] = dict(cfg["headers"])
        var = _bearer_var_for(name)
        if var and "Authorization" not in entry.get("headers", {}):
            entry.setdefault("headers", {})["Authorization"] = "Bearer ${" + var + "}"
        out[name] = entry
    return out


def build_strict_mcp_config(server_configs: dict):
    """Auto-build a `--mcp-config` dict from the plugin's servers + injected bearer headers.

    Returns None only when the plugin declares no server at all — there is no unauthenticated
    fallback to reach for, so a credential-less server is passed through and simply goes
    without an `Authorization` header. EVERY declared server is included: hiding one would
    change what the plugin under test receives, and `--strict-mcp-config` shows nothing else.

    A server left credential-less answers 401, which the graders report as `tool_used`
    "called 0x" — same symptom as a wrong key, so check the credential before the skill.
    """
    if not server_configs:
        return None
    return {"mcpServers": _inject_bearer(server_configs)}


def load_case_mcp_config(case: Case):
    """Load a case's `execution.mcp_config` file (rel to case dir), token-injected.

    The file declares servers (url/type[/headers]); the env bearer is added to any
    server lacking an Authorization header, so the file itself carries no secret.
    Returns the config dict, or None if the case names no mcp_config.
    """
    if not case.mcp_config:
        return None
    path = os.path.normpath(os.path.join(case.path, case.mcp_config))
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    servers = cfg.get("mcpServers", {}) or {}
    return {"mcpServers": _inject_bearer(servers)}


def resolve_strict_mcp_config(case: Case):
    """A case's explicit mcp_config wins; else auto-build from the plugin's .mcp.json."""
    if case.mcp_config:
        return load_case_mcp_config(case)
    return build_strict_mcp_config(plugin_mcp_server_configs(case))


register_harness(ClaudeCodeHarness())
