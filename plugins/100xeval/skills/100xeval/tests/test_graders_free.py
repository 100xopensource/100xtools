import unittest

from engine.graders import grade
from engine.models import Grader, RunResult, ToolCall


def rr(final="", calls=None):
    return RunResult(final_text=final, tool_calls=calls or [])


class TestToolUsed(unittest.TestCase):
    def test_pass_min(self):
        g = Grader("tool_used", "q", params={"tool": "sql", "min": 1})
        out = grade(g, rr(calls=[ToolCall("sql", '{"q":"x"}')]))
        self.assertTrue(out.passed)

    def test_input_match(self):
        g = Grader("tool_used", "q", params={"tool": "sql", "input_match": "Eastern", "min": 1})
        self.assertTrue(grade(g, rr(calls=[ToolCall("sql", "WHERE store=Eastern")])).passed)
        self.assertFalse(grade(g, rr(calls=[ToolCall("sql", "WHERE store=Western")])).passed)

    def test_max_bound(self):
        g = Grader("tool_used", "q", params={"tool": "sql", "min": 0, "max": 1})
        two = [ToolCall("sql", "a"), ToolCall("sql", "b")]
        self.assertFalse(grade(g, rr(calls=two)).passed)

    def test_zero_calls_detail(self):
        g = Grader("tool_used", "q", params={"tool": "sql", "min": 1})
        out = grade(g, rr(calls=[]))
        self.assertFalse(out.passed)
        self.assertIn("0x", out.detail)

    def test_missing_tool_param(self):
        out = grade(Grader("tool_used", "q", params={}), rr())
        self.assertFalse(out.passed)
        self.assertIn("missing", out.detail)

    def test_unsupported_harness(self):
        g = Grader("tool_used", "q", params={"tool": "sql", "min": 1})
        out = grade(g, rr(calls=[ToolCall("sql", "x")]), {"tool_calls_unavailable": True})
        self.assertFalse(out.passed)
        self.assertIn("unsupported", out.detail)


class TestRegex(unittest.TestCase):
    def test_contains(self):
        g = Grader("regex", "cite", params={"pattern": "Source:"})
        self.assertTrue(grade(g, rr(final="Source: Acme")).passed)
        self.assertFalse(grade(g, rr(final="no citation")).passed)

    def test_not_contains(self):
        g = Grader("regex", "nodisc", params={"pattern": "TODO", "match": "not_contains"})
        self.assertTrue(grade(g, rr(final="clean output")).passed)
        self.assertFalse(grade(g, rr(final="TODO fix")).passed)

    def test_flags(self):
        g = Grader("regex", "ci", params={"pattern": "source:", "flags": "IGNORECASE"})
        self.assertTrue(grade(g, rr(final="SOURCE: x")).passed)

    def test_target_trace(self):
        g = Grader("regex", "t", params={"pattern": "sql", "target": "trace"})
        self.assertTrue(grade(g, rr(calls=[ToolCall("sql", "q")])).passed)


class TestDispatch(unittest.TestCase):
    def test_unknown_type(self):
        out = grade(Grader("bogus", "x", params={}), rr())
        self.assertFalse(out.passed)
        self.assertIn("unknown", out.detail)


if __name__ == "__main__":
    unittest.main()


class TestToolUsedGlob(unittest.TestCase):
    """`tool` accepts a glob, which absence assertions depend on.

    Exact matching made `min: 0, max: 0` on `mcp__server__*` unfalsifiable: the pattern
    matched no call, so the grader reported "called 0x" and passed while the plugin hammered
    that server. You cannot enumerate the tools of a server you do not have, so the glob is
    the only way to express "nothing from here".
    """

    def _grade(self, calls, tool, **params):
        r = RunResult(tool_calls=[ToolCall(c, "") for c in calls])
        return grade(Grader("tool_used", "t", params={"tool": tool, **params}), r, {})

    def test_absence_assertion_fails_when_the_server_was_used(self):
        out = self._grade(["mcp__internal-gl__query"] * 3, "mcp__internal-gl__*", min=0, max=0)
        self.assertFalse(out.passed)
        self.assertIn("3x", out.detail)

    def test_absence_assertion_passes_when_nothing_was_called(self):
        self.assertTrue(self._grade([], "mcp__internal-gl__*", min=0, max=0).passed)

    def test_absence_assertion_ignores_a_different_server(self):
        out = self._grade(["mcp__office__excel_write"], "mcp__internal-gl__*", min=0, max=0)
        self.assertTrue(out.passed)

    def test_glob_counts_positively_too(self):
        out = self._grade(["mcp__gl__a", "mcp__gl__b"], "mcp__gl__*", min=1)
        self.assertTrue(out.passed)
        self.assertIn("2x", out.detail)

    def test_exact_names_still_match_exactly(self):
        self.assertTrue(self._grade(["mcp__Acme__run_query"], "mcp__Acme__run_query", min=1).passed)
        self.assertFalse(self._grade(["mcp__Acme__other"], "mcp__Acme__run_query", min=1).passed)

    def test_glob_matching_is_case_sensitive_on_the_server_name(self):
        # Strict config is the only MCP path, so a tool is spelled exactly as the server
        # declares itself. A grader that gets the case wrong reports "called 0x" — the same
        # symptom as bad auth, which is why this is asserted rather than assumed.
        self.assertTrue(self._grade(["mcp__Acme__nav"], "mcp__Acme__*", min=1).passed)
        self.assertFalse(self._grade(["mcp__Acme__nav"], "mcp__acme__*", min=1).passed)

    def test_glob_composes_with_input_match(self):
        r = RunResult(tool_calls=[ToolCall("mcp__gl__query", "entity 400")])
        g = Grader("tool_used", "t", params={"tool": "mcp__gl__*", "input_match": "entity 400", "min": 1})
        self.assertTrue(grade(g, r, {}).passed)
        g2 = Grader("tool_used", "t", params={"tool": "mcp__gl__*", "input_match": "entity 999", "min": 1})
        self.assertFalse(grade(g2, r, {}).passed)
