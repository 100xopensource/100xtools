"""LLM judge — powers the `llm` grader.

Two modes:
  - format:  presentation only (citation, table, disclaimer). NEVER grades numbers.
  - agentic: the judge is granted data tools and verifies figures live by querying
             the data itself (replaces a hard-coded oracle).

Majority vote over `votes` independent verdicts smooths judge flakiness. The model
runner is injected (`runner=`) so graders unit-test with a stub — the default runner
shells `claude -p`.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
import tempfile

# Reuse the harness's result parser + tool-name alias expansion so the judge names
# tools exactly the way the run under test did.
from .harnesses.claude_code import add_tokens, expand_tool_aliases, parse_cli_json, parse_usage

DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"
AGENTIC_JUDGE_MODEL = "claude-sonnet-5"
JUDGE_TIMEOUT_S = 180
# How much of a judge's explanation to keep. 300 was enough for "0.24 vs 0.148", but a
# judge comparing ~20 clusters gets cut off mid-evidence — the verdict survives and the
# REASON does not, which is the half you need to tell a skill bug from a case bug.
REASON_LIMIT = 1500

# The judge runs headless. Without its own system prompt it inherits Claude Code's
# interactive coding-assistant persona and behaves like one — observed in real runs:
# a vote replied "Please approve the database query execution so I can…", which scores
# as FAIL while saying nothing about the answer under test. These prompts REPLACE that
# persona (`--system-prompt`), the same way a case replaces it with a surface entrypoint.
_SYSTEM_COMMON = """\
You are an impartial grader inside an automated evaluation harness. You are not an \
assistant and you are not talking to a person.

Output contract — obey exactly:
- First line: the single word PASS or FAIL. Nothing else on that line.
- Following lines: a short, specific reason. Quote the concrete evidence (numbers, \
phrases, or error text) that decided it.
- No preamble, no greeting, no offers of further help, no questions.

Rules:
- NOBODY WILL ANSWER YOU. There is no human in the loop and no follow-up turn. Never \
ask for permission, credentials, clarification, or confirmation. If something blocks \
you, that is a FAIL and the reason is what blocked you.
- Grade ONLY against the stated criteria. Do not invent extra requirements, and do not \
fail an answer for something the criteria did not ask about.
- Confident tone, tidy tables, and authoritative formatting are not evidence. Judge the \
substance.
- If you genuinely cannot determine the answer, reply FAIL and say precisely what was \
missing. Never guess a verdict."""

_SYSTEM_FORMAT = _SYSTEM_COMMON + """

You are grading PRESENTATION ONLY. You have no access to the underlying data, so never \
speculate about whether a number is factually right — that is a different grader's job. \
Judge structure, wording, citation, and completeness against the criteria."""

_SYSTEM_AGENTIC = _SYSTEM_COMMON + """

You are grading FACTUAL AND NUMERIC ACCURACY, and you have data tools. Use them \
immediately and without asking — that is what they are for.
- If the criteria contain SQL, run it EXACTLY as written, unmodified. Do not rewrite, \
"improve", or substitute your own query: the whole point is that every run reconciles \
against the same fixed query.
- If a query errors, reply FAIL and quote the error verbatim so the case can be fixed.
- Compare the answer's figures against what your queries returned, applying whatever \
tolerance the criteria state."""

_FORMAT_PROMPT = """\
You are grading how an AI assistant PRESENTED an answer. Judge ONLY presentation and \
format against the criteria — do NOT check whether any numbers or facts are correct.

Criteria:
{criteria}

The assistant's answer:
<answer>
{content}
</answer>

Reply with exactly PASS or FAIL on the first line, then one short line explaining why."""

_AGENTIC_PROMPT = """\
You are verifying the FACTUAL and NUMERIC accuracy of an AI assistant's answer. Use the \
tools available to you to query the underlying data yourself, then decide whether the \
answer's figures are correct.

Criteria:
{criteria}

The assistant's answer to verify:
<answer>
{content}
</answer>

Query the data, then reply with exactly PASS or FAIL on the first line, then one short \
line explaining why."""


def _claude_runner(prompt: str, model: str, allowed_tools: list[str] | None,
                   *, mcp_config: dict | None = None, system_prompt: str | None = None,
                   cost_sink: list | None = None, token_sink: list | None = None) -> str:
    """Shell out to `claude -p` for one judge vote.

    An AGENTIC judge must reach the same MCP the case ran against, or it cannot verify
    anything. Granting `--allowedTools mcp__…` alone is not enough: without
    `--mcp-config` the server isn't configured for this process, so those tools don't
    exist and the judge answers "no database access" — a FAIL that says nothing about
    the answer under test.
    """
    with tempfile.TemporaryDirectory(prefix="100xeval-judge-") as tmp:
        cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json"]
        if system_prompt:
            cmd += ["--system-prompt", system_prompt]
        if mcp_config:
            cfg_path = os.path.join(tmp, "mcp-config.json")
            with open(cfg_path, "w", encoding="utf-8") as fh:
                json.dump(mcp_config, fh)
            cmd += ["--mcp-config", cfg_path, "--strict-mcp-config"]
        if allowed_tools:
            cmd += ["--allowedTools", ",".join(expand_tool_aliases(allowed_tools))]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=JUDGE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return f"FAIL\njudge timed out after {JUDGE_TIMEOUT_S}s"
        if proc.returncode != 0:
            return f"FAIL\njudge invocation failed: {proc.stderr[:200]}"
        final, _session, cost, _dur = parse_cli_json(proc.stdout)
        # Judging is a real spend: N votes per grader per run, on top of the run itself.
        # Reporting only the run cost understated a suite by more than half.
        if cost_sink is not None:
            cost_sink.append(cost)
        if token_sink is not None:
            token_sink.append(parse_usage(proc.stdout))
        return final


def _nonempty_lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _verdict(text: str) -> bool:
    lines = _nonempty_lines(text)
    return bool(lines) and lines[0].upper().startswith("PASS")


def _reason(text: str, limit: int = REASON_LIMIT) -> str:
    """The judge's explanation: everything after the PASS/FAIL line.

    Blank lines are skipped, not counted — judges commonly answer "FAIL\\n\\n<why>",
    and indexing line 1 blindly returned the blank line, so every reason in the
    scorecard came out empty. The reason is the whole point of a failing grader
    (e.g. a ground-truth SQL error quoted verbatim), so keep several lines.
    """
    rest = _nonempty_lines(text)[1:]
    return " ".join(rest)[:limit]


def system_prompt_for(agentic: bool, override: str | None = None) -> str:
    """The judge's system prompt: the mode default, or a caller-supplied override."""
    if override:
        return override
    return _SYSTEM_AGENTIC if agentic else _SYSTEM_FORMAT


def judge(criteria: str, content: str, *, agentic: bool = False, model: str | None = None,
          votes: int = 3, allowed_tools: list[str] | None = None, runner=None,
          mcp_config: dict | None = None, system_prompt: str | None = None):
    """Run the judge `votes` times; PASS on a strict majority.

    Returns (passed, detail, cost_usd, tokens) — what every vote it just spent.

    `mcp_config` is the case's resolved MCP config — an agentic judge needs it to reach
    the data. `system_prompt` overrides the built-in grader persona (see
    `--judge-system-prompt`). Both are ignored when a `runner` is injected (tests stub
    the model call).
    """
    costs: list[float] = []
    tokens: list[dict] = []
    runner = runner or functools.partial(
        _claude_runner, mcp_config=mcp_config,
        system_prompt=system_prompt_for(agentic, system_prompt),
        cost_sink=costs,          # injected stubs never append → 0.0, which is correct
        token_sink=tokens,
    )
    model = model or (AGENTIC_JUDGE_MODEL if agentic else DEFAULT_JUDGE_MODEL)
    template = _AGENTIC_PROMPT if agentic else _FORMAT_PROMPT
    prompt = template.format(criteria=criteria, content=content)

    total = max(1, votes)
    won: list[str] = []
    lost: list[str] = []
    passes = 0
    for _ in range(total):
        text = runner(prompt, model, allowed_tools if agentic else None)
        ok = _verdict(text)
        passes += 1 if ok else 0
        (won if ok else lost).append(_reason(text) or "(judge gave no reason)")

    passed = passes > total / 2
    majority, minority = (won, lost) if passed else (lost, won)
    mode = "agentic" if agentic else "format"

    # Unanimous votes produce near-identical reasons — printing all three tripled the
    # scorecard's width for no information. Show ONE representative reason, and surface
    # the DISSENT when the panel split, since disagreement is the part worth reading.
    parts = [f"{mode} judge {passes}/{total} PASS"]
    if majority:
        parts.append(("— " if total == 1 else f"— majority: ") + majority[0])
    if minority:
        parts.append(f"| dissent ({len(minority)}/{total}): {minority[0]}")
    return passed, " ".join(parts), sum(costs), add_tokens(*tokens)
