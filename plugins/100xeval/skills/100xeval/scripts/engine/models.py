"""Core dataclasses for 100xeval — the data model in.

Kept plain and stdlib-only. Loading/validation lives in loader.py; these types just
hold shape + defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Grader:
    """One check applied to a RunResult. Discriminated on `type`.

    Per-type fields live in `params` (e.g. tool_used: tool/input_match/min/max;
    regex: pattern/target/match/flags; llm: criteria/focus/allowed_tools;
    static: min_score). Graders own their own field validation in graders.py.
    """

    type: str
    name: str
    weight: float = 1.0
    params: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Full serialization — `params` is flattened back to the case.yaml spelling."""
        return {"type": self.type, "name": self.name, "weight": self.weight, **self.params}


@dataclass
class Case:
    name: str
    prompt: str
    path: str = ""                       # case directory, set by the loader
    description: str = ""
    plugins: list[str] = field(default_factory=list)   # paths relative to `path`
    tags: list[str] = field(default_factory=list)
    model: str | None = None             # the ONE runner model this case executes on
    # harness = the RUNTIME executing the turn; entrypoint = the SURFACE emulated (its
    # system prompt, engine/entrypoints/<name>.md). `none` = the harness's own prompt.
    harness: str = "claude_code"
    entrypoint: str = "none"
    max_turns: int = 15
    timeout_s: int = 300         # per-RUN wall clock; a report build needs far more
    allowed_tools: list[str] = field(default_factory=list)
    append_system_prompt: str | None = None
    mcp_config: str | None = None        # path (rel to case dir) to an MCP config JSON → strict mode
    runs: int = 3
    skip: str = ""               # non-empty = excluded from runs; the value is the reason
    graders: list[Grader] = field(default_factory=list)

    def label(self) -> str:
        """Human-readable execution identity, e.g. `claude_code/claude-sonnet-5`."""
        return f"{self.harness}/{self.model or 'default'}"

    def as_dict(self) -> dict:
        """EVERY field of the case, for the run's `cases.json`.

        The run folder has to be auditable on its own — months later you must be able to
        read exactly what was executed (prompt, plugin, tools, graders) without going back
        to a `case.yaml` that may have changed since. So this dumps the whole Case, not a
        summary. `mcp_config` is a PATH; no token or secret ever passes through here.
        """
        return {
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "plugins": list(self.plugins),
            "tags": list(self.tags),
            "runs": self.runs,
            "skip": self.skip,
            "execution": {
                "prompt": self.prompt,
                "model": self.model,
                "harness": self.harness,
                "entrypoint": self.entrypoint,
                "max_turns": self.max_turns,
                "timeout_s": self.timeout_s,
                "allowed_tools": list(self.allowed_tools),
                "append_system_prompt": self.append_system_prompt,
                "mcp_config": self.mcp_config,
            },
            "graders": [g.as_dict() for g in self.graders],
        }


@dataclass
class ToolCall:
    name: str
    input_str: str = ""


@dataclass
class RunResult:
    """The observable outcome of one plugin invocation."""

    final_text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    cost_usd: float = 0.0
    tokens: dict = field(default_factory=dict)   # input/output/cache_read/cache_creation
    duration_ms: int = 0
    session_id: str | None = None
    transcript_path: str | None = None    # ~/.claude/projects/**/<session_id>.jsonl
    error: str | None = None
    # Raw invocation capture for debugging (not the parsed result).
    command: list[str] = field(default_factory=list)   # argv, giant --system-prompt redacted
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    debug_log: str | None = None          # claude --debug-file output (rich CLI debug trace)


@dataclass
class GraderOutcome:
    name: str
    type: str
    weight: float
    passed: bool
    detail: str = ""
    cost_usd: float = 0.0        # what grading itself spent (llm judge votes)
    tokens: dict = field(default_factory=dict)


@dataclass
class Scorecard:
    """Aggregated result for one case across its `runs` repetitions.

    One case = one harness + one model, so the card is flat: the graders and the
    per-run executions hang directly off it (no matrix cells).
    """

    name: str
    passed: bool = False
    score: float = 0.0
    cost_usd: float = 0.0        # the plugin runs
    judge_cost_usd: float = 0.0  # the llm graders' votes
    tokens: dict = field(default_factory=dict)        # tokens across the plugin runs
    judge_tokens: dict = field(default_factory=dict)  # tokens across the judge votes
    duration_ms: int = 0         # MEAN per run (runs are concurrent; a sum is meaningless)
    harness: str = ""
    model: str | None = None
    # graders[i] = {name, type, weight, passRate, runs:[{passed, detail}]}
    graders: list = field(default_factory=list)
    # executions[i] = {run, session_id, transcript_path, cost_usd, duration_ms, error, …}
    executions: list = field(default_factory=list)
    # Plugin NAMES, not `Case.plugins`' case-relative paths — a report grouped under
    # `../../plugins/acme-north` names the case's directory layout, not the plugin.
    # Resolved at the construction site in orchestrator.py.
    plugins: list = field(default_factory=list)
    error: str | None = None

    def label(self) -> str:
        return f"{self.harness}/{self.model or 'default'}"
