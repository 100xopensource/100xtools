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
