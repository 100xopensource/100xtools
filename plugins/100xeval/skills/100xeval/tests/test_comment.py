"""Comment shaping. Synthetic report dicts only — no plugin on disk, no model call.

Every behaviour is asserted in BOTH directions, per the repo's rule for checks: a size cap
that only ever fires is as useless as one that never does, and a "trimmed" note that is
always present tells a reader nothing.
"""

import unittest

from engine import comment


def _static(n_plugins=1, findings_per=0, score=1.0, error=None):
    plugins = []
    for i in range(n_plugins):
        p = {
            "path": f"plugins/acme-{i}",
            "design_score": score,
            "sub_scores": {"frontmatter_quality": 1.0, "reference_hygiene": score,
                           "security": 1.0},
            "findings": [f"skills/s/SKILL.md: [RH1] finding number {j} on plugin {i}"
                         for j in range(findings_per)],
        }
        if error:
            p = {"path": f"plugins/acme-{i}", "design_score": 0.0, "sub_scores": {},
                 "error": error}
        plugins.append(p)
    return {"scoringVersion": 1, "plugins": plugins, "ok": error is None}


def _cases(n=1, passed=True, plugins=("acme-north",), grader_runs=1):
    cases = []
    for i in range(n):
        cases.append({
            "name": f"case-{i}",
            "plugins": list(plugins),
            "score": 1.0 if passed else 0.5,
            "passed": passed,
            "error": None,
            "harness": "claude_code",
            "model": "claude-sonnet-5",
            "costUsd": 0.02, "runCostUsd": 0.015, "judgeCostUsd": 0.005,
            "durationMs": 250,
            "graders": [{
                "name": "queried-right-data", "type": "tool_used", "weight": 1,
                "passRate": 1.0 if passed else 0.0,
                "runs": [{"passed": passed, "detail": f"called sql {j} times"}
                         for j in range(grader_runs)],
            }],
        })
    return {
        "schemaVersion": "2.1", "cases": cases, "casesTotal": n,
        "casesPassed": n if passed else 0,
        "overallScore": 1.0 if passed else 0.5,
        "costUsd": 0.02 * n, "runCostUsd": 0.015 * n, "judgeCostUsd": 0.005 * n,
    }


class TestStaticComment(unittest.TestCase):
    def test_headline_leads_with_the_outcome(self):
        body = comment.static_comment(_static(n_plugins=2, findings_per=2, score=0.75))
        head = body.splitlines()[:3]
        self.assertIn("100xeval — static design quality", head[0])
        self.assertIn("lowest design_score 0.75", "\n".join(head))
        self.assertIn("4 finding(s)", "\n".join(head))

    def test_never_claims_the_score_passed_a_gate(self):
        # --static-only exits non-zero only when a plugin cannot be ANALYZED, so a score
        # headline saying "passed" would claim a gate that does not exist.
        body = comment.static_comment(_static(score=0.5))
        self.assertNotIn("passed", body.split("_A low score")[0])
        self.assertIn("does not fail this job", body)

    def test_one_row_per_plugin(self):
        body = comment.static_comment(_static(n_plugins=3))
        for i in range(3):
            self.assertIn(f"| `plugins/acme-{i}` |", body)

    def test_analysis_error_is_surfaced_not_scored(self):
        body = comment.static_comment(_static(n_plugins=2, error="not a plugin"))
        self.assertIn("could not be analyzed", body)
        self.assertIn("not a plugin", body)

    def test_empty_report_says_nothing_was_scored(self):
        # A cheerful comment over zero plugins is the "green build that evaluated nothing"
        # failure this tool exists to catch.
        body = comment.static_comment({"scoringVersion": 1, "plugins": [], "ok": True})
        self.assertIn("No plugins were analyzed", body)

    def test_static_comment_carries_no_diagram(self):
        body = comment.static_comment(_static(n_plugins=3, findings_per=3))
        self.assertNotIn("```mermaid", body)


class TestCasesComment(unittest.TestCase):
    def test_headline_leads_with_the_outcome(self):
        body = comment.cases_comment(_cases(n=2, passed=False))
        self.assertIn("0/2 cases passed", body.splitlines()[2])
        self.assertIn("❌", body.splitlines()[2])

    def test_cases_grouped_under_their_plugin(self):
        report = _cases(n=1, plugins=("acme-north",))
        report["cases"] += _cases(n=1, plugins=("acme-south",))["cases"]
        report["casesTotal"] = 2
        body = comment.cases_comment(report)
        self.assertIn("### acme-north", body)
        self.assertIn("### acme-south", body)

    def test_case_without_a_plugin_is_labelled_not_dropped(self):
        body = comment.cases_comment(_cases(plugins=()))
        self.assertIn("no plugin declared", body)

    def test_diagram_present_and_names_case_and_grader(self):
        body = comment.cases_comment(_cases(passed=False))
        self.assertIn("```mermaid", body)
        self.assertIn("flowchart LR", body)
        self.assertIn("case-0", body)
        self.assertIn("queried-right-data", body)

    def test_diagram_labels_are_mermaid_safe(self):
        report = _cases()
        report["cases"][0]["name"] = 'a "quoted" [bracketed]\nmultiline name'
        body = comment.cases_comment(report)
        diagram = body.split("```mermaid")[1].split("```")[0]
        self.assertNotIn('"quoted"', diagram)   # would end the label early
        self.assertNotIn("[bracketed]", diagram)
        self.assertNotIn("\nmultiline", diagram)

    def test_empty_report_says_nothing_ran(self):
        body = comment.cases_comment({"cases": [], "casesTotal": 0, "casesPassed": 0})
        self.assertIn("No cases ran", body)

    def test_passing_case_needs_no_detail_block(self):
        body = comment.cases_comment(_cases(passed=True))
        self.assertNotIn("<details>", body)

    def test_failing_case_shows_its_grader_detail(self):
        body = comment.cases_comment(_cases(passed=False))
        self.assertIn("<details>", body)
        self.assertIn("called sql 0 times", body)

    def test_table_and_diagram_agree_on_order(self):
        # Both list failing cases first. Two different orders for the same group reads as a
        # bug in one of them.
        report = _cases(n=1, passed=True)
        report["cases"] += _cases(n=1, passed=False)["cases"]
        report["cases"][1]["name"] = "failing-case"
        report["casesTotal"], report["casesPassed"] = 2, 1
        body = comment.cases_comment(report)
        diagram, tables = body.split("```")[1], body.split("```")[2]
        self.assertLess(diagram.index("failing-case"), diagram.index("case-0"))
        self.assertLess(tables.index("failing-case"), tables.index("case-0"))


class TestSizeCap(unittest.TestCase):
    def test_small_report_is_not_trimmed(self):
        body = comment.static_comment(_static(n_plugins=2, findings_per=2))
        self.assertLess(len(body), comment.MAX_BYTES)
        self.assertNotIn("Trimmed to fit", body)

    def test_oversized_static_report_is_capped_and_says_so(self):
        body = comment.static_comment(_static(n_plugins=40, findings_per=200, score=0.5))
        self.assertLessEqual(len(body), comment.MAX_BYTES)
        self.assertIn("Trimmed to fit", body)

    def test_oversized_cases_report_is_capped_and_says_so(self):
        body = comment.cases_comment(_cases(n=200, passed=False, grader_runs=40))
        self.assertLessEqual(len(body), comment.MAX_BYTES)
        self.assertIn("Trimmed to fit", body)

    def test_summary_survives_the_deepest_drop(self):
        # Whatever is dropped, the verdict and the per-plugin table stay — they are the
        # reason the comment exists.
        body = comment.static_comment(_static(n_plugins=40, findings_per=200, score=0.5))
        self.assertIn("static design quality", body)
        self.assertIn("| `plugins/acme-0` |", body)

    def test_absurd_cap_still_leaves_a_truncation_note(self):
        # Backstop path: even the barest rendering does not fit. A body that just stops is
        # indistinguishable from a complete one, so the note is not optional.
        body = comment.static_comment(_static(n_plugins=40), max_bytes=400)
        self.assertLessEqual(len(body), 400)
        self.assertIn("Truncated", body)

    def test_custom_cap_is_respected_in_both_directions(self):
        big = comment.cases_comment(_cases(n=30, passed=False), max_bytes=2000)
        self.assertLessEqual(len(big), 2000)
        small = comment.cases_comment(_cases(n=1), max_bytes=comment.MAX_BYTES)
        self.assertNotIn("Trimmed to fit", small)


if __name__ == "__main__":
    unittest.main()
