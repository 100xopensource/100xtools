import unittest

from engine import judge as judge_mod
from engine.graders import grade
from engine.models import Grader, RunResult, ToolCall


def rr(final="Source: Acme\n| hour | sales |\nDisclaimer: …"):
    return RunResult(final_text=final, tool_calls=[ToolCall("sql", "WHERE store=Eastern")])


def stub_runner(verdicts):
    """Return a runner yielding canned judge outputs in order."""
    seq = iter(verdicts)

    def _run(prompt, model, allowed_tools):
        return next(seq)

    _run.last_allowed = allowed_tools
    return _run


class TestJudge(unittest.TestCase):
    def test_majority_pass(self):
        passed, detail, _cost, _tok = judge_mod.judge(
            "cites source", "answer", votes=3,
            runner=lambda p, m, a: "PASS\nlooks good",
        )
        self.assertTrue(passed)
        self.assertIn("3/3 PASS", detail)

    def test_majority_fail(self):
        seq = iter(["PASS\nok", "FAIL\nno table", "FAIL\nno disclaimer"])
        passed, detail, _cost, _tok = judge_mod.judge("x", "a", votes=3, runner=lambda p, m, a: next(seq))
        self.assertFalse(passed)
        self.assertIn("1/3 PASS", detail)

    def test_format_mode_passes_no_tools(self):
        captured = {}

        def run(prompt, model, allowed_tools):
            captured["allowed"] = allowed_tools
            captured["prompt"] = prompt
            return "PASS\nfine"

        judge_mod.judge("crit", "ans", agentic=False, votes=1, runner=run)
        self.assertIsNone(captured["allowed"])              # format mode → no tools
        self.assertIn("do NOT check", captured["prompt"])   # format prompt forbids numbers

    def test_agentic_mode_passes_tools(self):
        captured = {}

        def run(prompt, model, allowed_tools):
            captured["allowed"] = allowed_tools
            return "PASS\nverified"

        judge_mod.judge("crit", "ans", agentic=True, votes=1,
                        allowed_tools=["mcp__x__query"], runner=run)
        self.assertEqual(captured["allowed"], ["mcp__x__query"])
        self.assertTrueish = self.assertTrue


class TestLlmGrader(unittest.TestCase):
    def test_format_grader_via_dispatch(self):
        g = Grader("llm", "presentation", params={"criteria": "cites source", "focus": "last_message"})
        ctx = {"judge_votes": 1, "judge_runner": lambda p, m, a: "PASS\nok"}
        out = grade(g, rr(), ctx)
        self.assertTrue(out.passed)
        self.assertEqual(out.type, "llm")

    def test_agentic_grader_receives_tools(self):
        seen = {}

        def run(prompt, model, allowed_tools):
            seen["allowed"] = allowed_tools
            return "FAIL\nnumbers off"

        g = Grader("llm", "accuracy", params={
            "criteria": "figures correct", "allowed_tools": ["mcp__Acme__run_query"],
        })
        out = grade(g, rr(), {"judge_votes": 1, "judge_runner": run})
        self.assertFalse(out.passed)
        self.assertEqual(seen["allowed"], ["mcp__Acme__run_query"])

    def test_missing_criteria(self):
        out = grade(Grader("llm", "x", params={}), rr(), {"judge_runner": lambda p, m, a: "PASS"})
        self.assertFalse(out.passed)
        self.assertIn("criteria", out.detail)


if __name__ == "__main__":
    unittest.main()


class TestJudgeReasonExtraction(unittest.TestCase):
    """The reason is the payload of a failing grader — a ground-truth SQL error has to
    reach the scorecard. Indexing line 1 blindly returned the blank line that judges
    commonly put after the verdict, so every reason rendered empty."""

    def test_reason_survives_blank_line_after_verdict(self):
        from engine import judge
        text = "FAIL\n\n[TABLE_OR_VIEW_NOT_FOUND] acme_inventory_snapshot cannot be found"
        self.assertFalse(judge._verdict(text))
        self.assertIn("TABLE_OR_VIEW_NOT_FOUND", judge._reason(text))

    def test_reason_joins_multiple_lines(self):
        from engine import judge
        text = "FAIL\n\nQuery error:\nAnalysisException: column stock_quantity missing"
        self.assertIn("AnalysisException", judge._reason(text))

    def test_verdict_tolerates_leading_blank_lines(self):
        from engine import judge
        self.assertTrue(judge._verdict("\n\nPASS\nall good"))

    def test_detail_says_so_when_judge_gave_no_reason(self):
        from engine import judge
        passed, detail, _cost, _tok = judge.judge("c", "x", votes=1, runner=lambda *a, **k: "FAIL")
        self.assertFalse(passed)
        self.assertIn("no reason", detail)


class TestJudgeSystemPrompt(unittest.TestCase):
    """The judge runs headless. Without its own system prompt it inherits Claude Code's
    interactive persona and asks a human for permission — an observed real failure."""

    def test_agentic_prompt_forbids_asking_for_approval(self):
        from engine import judge
        sp = judge.system_prompt_for(agentic=True)
        self.assertIn("NOBODY WILL ANSWER YOU", sp)
        self.assertIn("Never ask for permission", sp)
        self.assertIn("EXACTLY as written", sp)      # run the hardcoded SQL verbatim

    def test_format_prompt_forbids_judging_numbers(self):
        from engine import judge
        sp = judge.system_prompt_for(agentic=False)
        self.assertIn("PRESENTATION ONLY", sp)
        self.assertIn("no access to the underlying data", sp)

    def test_both_modes_state_the_output_contract(self):
        from engine import judge
        for agentic in (True, False):
            sp = judge.system_prompt_for(agentic)
            self.assertIn("PASS or FAIL", sp)

    def test_override_replaces_the_default(self):
        from engine import judge
        self.assertEqual(judge.system_prompt_for(True, "custom text"), "custom text")

    def test_runner_receives_system_prompt_flag(self):
        import subprocess
        from unittest import mock
        from engine import judge
        completed = subprocess.CompletedProcess([], 0, stdout='{"result":"PASS\\nok"}', stderr="")
        with mock.patch.object(judge.subprocess, "run", return_value=completed) as run:
            judge._claude_runner("p", "m", ["mcp__X__t"], system_prompt="GRADER RULES")
        cmd = run.call_args[0][0]
        self.assertIn("--system-prompt", cmd)
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], "GRADER RULES")

    def test_cli_flag_reads_a_file_or_falls_back_to_literal_text(self):
        import tempfile
        from engine import cli
        self.assertIsNone(cli._load_judge_system_prompt(None))
        self.assertEqual(cli._load_judge_system_prompt("inline rules"), "inline rules")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write("from file")
            path = fh.name
        self.assertEqual(cli._load_judge_system_prompt(path), "from file")


class TestJudgeDetailIsCompact(unittest.TestCase):
    """A unanimous panel repeats itself. Printing all N reasons made the scorecard
    thousands of characters wide; the dissent is the part worth reading."""

    @staticmethod
    def _votes(seq):
        it = iter(seq)
        return lambda p, m, a: next(it)

    def test_unanimous_shows_one_reason_not_all(self):
        from engine import judge
        passed, detail, _cost, _tok = judge.judge("c", "x", votes=3, runner=self._votes(
            ["PASS\n\nfirst reason", "PASS\n\nsecond reason", "PASS\n\nthird reason"]))
        self.assertTrue(passed)
        self.assertIn("first reason", detail)
        self.assertNotIn("second reason", detail)
        self.assertNotIn("dissent", detail)

    def test_split_panel_surfaces_the_dissent(self):
        from engine import judge
        passed, detail, _cost, _tok = judge.judge("c", "x", votes=3, runner=self._votes(
            ["PASS\n\nlooks right", "FAIL\n\n62% error", "PASS\n\nfine"]))
        self.assertTrue(passed)                      # 2/3 majority
        self.assertIn("2/3 PASS", detail)
        self.assertIn("dissent (1/3)", detail)
        self.assertIn("62% error", detail)           # the minority view is preserved

    def test_unanimous_fail_reports_the_reason(self):
        from engine import judge
        passed, detail, _cost, _tok = judge.judge("c", "x", votes=3, runner=self._votes(
            ["FAIL\n\nturn 0.24 vs 0.148", "FAIL\n\nwrong", "FAIL\n\nwrong"]))
        self.assertFalse(passed)
        self.assertIn("0/3 PASS", detail)
        self.assertIn("turn 0.24 vs 0.148", detail)


class TestReporterPerRunDetail(unittest.TestCase):
    def test_markdown_lists_each_run_separately(self):
        from engine import reporter
        from engine.models import Scorecard
        card = Scorecard(name="c", passed=False, score=0.67, harness="claude_code", model="m")
        card.graders = [{"name": "gt", "type": "llm", "weight": 1, "passRate": 0.67, "runs": [
            {"passed": True, "detail": "matched"},
            {"passed": True, "detail": "matched"},
            {"passed": False, "detail": "0.24 vs 0.148"},
        ]}]
        md = reporter.to_markdown(reporter.build_report([card]))
        self.assertIn("- ✅ run 1: matched", md)
        self.assertIn("- ❌ run 3: 0.24 vs 0.148", md)

    def test_fully_passing_grader_prints_no_detail_noise(self):
        from engine import reporter
        from engine.models import Scorecard
        card = Scorecard(name="c", passed=True, score=1.0, harness="claude_code", model="m")
        card.graders = [{"name": "ok", "type": "regex", "weight": 1, "passRate": 1.0,
                         "runs": [{"passed": True, "detail": "pattern found"}]}]
        md = reporter.to_markdown(reporter.build_report([card]))
        self.assertNotIn("pattern found", md)

    def test_html_detail_is_not_inside_the_grader_table(self):
        from engine import reporter
        from engine.models import Scorecard
        card = Scorecard(name="c", passed=False, score=0.5, harness="claude_code", model="m")
        card.graders = [{"name": "gt", "type": "llm", "weight": 1, "passRate": 0.5, "runs": [
            {"passed": False, "detail": "a very long judge explanation"}]}]
        html = reporter.to_html(reporter.build_report([card]))
        self.assertIn('class="gdetail"', html)               # rendered below the table
        self.assertIn("<th>passRate</th></tr>", html)        # table has no detail column


class TestEvalCostAccounting(unittest.TestCase):
    """The report counted only the plugin runs. Judging is a real spend — N votes per
    llm grader per run — so a suite's true cost was understated, badly."""

    def test_judge_returns_the_cost_of_its_votes(self):
        import subprocess
        from unittest import mock
        from engine import judge
        payload = '{"result":"PASS\\nok","total_cost_usd":0.25}'
        completed = subprocess.CompletedProcess([], 0, stdout=payload, stderr="")
        with mock.patch.object(judge.subprocess, "run", return_value=completed):
            passed, _detail, cost, _tok = judge.judge("c", "x", votes=3)
        self.assertTrue(passed)
        self.assertAlmostEqual(cost, 0.75)      # 3 votes × $0.25

    def test_injected_stub_runner_reports_zero_cost(self):
        from engine import judge
        _p, _d, cost, _tok = judge.judge("c", "x", votes=2, runner=lambda p, m, a: "PASS\nok")
        self.assertEqual(cost, 0.0)

    def test_grader_outcome_carries_cost(self):
        from engine import graders
        from engine.models import Grader, GraderOutcome, RunResult
        graders.register_grader("_costly", lambda g, r, c: (True, "ok", 0.4))
        try:
            out = graders.grade(Grader("_costly", "x"), RunResult(), {})
        finally:
            graders._GRADERS.pop("_costly", None)
        self.assertIsInstance(out, GraderOutcome)
        self.assertAlmostEqual(out.cost_usd, 0.4)

    def test_two_tuple_graders_still_work(self):
        # tool_used / regex don't cost anything and return (passed, detail).
        from engine import graders
        from engine.models import Grader, RunResult
        out = graders.grade(Grader("regex", "r", params={"pattern": "hi"}),
                            RunResult(final_text="hi there"), {})
        self.assertTrue(out.passed)
        self.assertEqual(out.cost_usd, 0.0)

    def test_report_splits_run_judge_and_total(self):
        from engine import reporter
        from engine.models import Scorecard
        card = Scorecard(name="c", passed=True, score=1.0, harness="claude_code", model="m",
                         cost_usd=6.0, judge_cost_usd=9.0)
        rep = reporter.build_report([card])
        self.assertAlmostEqual(rep["runCostUsd"], 6.0)
        self.assertAlmostEqual(rep["judgeCostUsd"], 9.0)
        self.assertAlmostEqual(rep["costUsd"], 15.0)          # total, not just the runs
        md = reporter.to_markdown(rep)
        self.assertIn("$15.0000 total", md)
        self.assertIn("judges $9.0000", md)
        self.assertIn("| Run $ | Judge $ | Total $ |", md)


class TestReasonLimit(unittest.TestCase):
    def test_multi_item_comparison_is_not_truncated_mid_evidence(self):
        from engine import judge
        # A judge enumerating many clusters: the conclusion sits near the END.
        body = "\n".join(f"Cluster {i}: GT $1,000,000 vs answer $1,001,000 (0.1%)" for i in range(1, 21))
        text = "FAIL\n\n" + body + "\nCluster 20 is off by 9%, exceeding tolerance."
        reason = judge._reason(text)
        self.assertIn("Cluster 20 is off by 9%", reason)   # the part that explains the verdict
        self.assertLessEqual(len(reason), judge.REASON_LIMIT)
