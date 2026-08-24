import json
import unittest

from engine import reporter
from engine.models import Scorecard


def _card(name, score, passed):
    c = Scorecard(name=name, score=score, passed=passed, cost_usd=0.02, duration_ms=250,
                  harness="claude_code", model="claude-sonnet-5", plugins=["acme-north"])
    c.graders = [
        {"name": "q", "type": "tool_used", "weight": 1, "passRate": score,
         "runs": [{"passed": passed, "detail": "called sql 1x"}]},
        {"name": "cite", "type": "regex", "weight": 1, "passRate": score,
         "runs": [{"passed": passed, "detail": "pattern found"}]},
    ]
    return c


class TestReporter(unittest.TestCase):
    def test_json_schema_shape(self):
        report = reporter.build_report([_card("a", 1.0, True), _card("b", 0.5, False)])
        self.assertEqual(report["schemaVersion"], "2.1")
        self.assertEqual(report["casesTotal"], 2)
        self.assertEqual(report["casesPassed"], 1)
        self.assertAlmostEqual(report["overallScore"], 0.75)
        # round-trips as valid JSON
        parsed = json.loads(reporter.to_json(report))
        case = parsed["cases"][0]
        self.assertEqual(case["name"], "a")
        # Flat: harness/model + graders sit on the case, no `cells` map.
        self.assertNotIn("cells", case)
        self.assertEqual(case["harness"], "claude_code")
        # 2.1 added this, additively — a report can be grouped by plugin, not only by case.
        self.assertEqual(case["plugins"], ["acme-north"])
        self.assertEqual(case["model"], "claude-sonnet-5")
        self.assertEqual([g["name"] for g in case["graders"]], ["q", "cite"])

    def test_markdown_renders_flat_grader_table(self):
        md = reporter.to_markdown(reporter.build_report([_card("a", 1.0, True)]))
        self.assertIn("# 100xeval report", md)
        self.assertIn("| Grader | Type | Weight | passRate |", md)
        self.assertIn("claude_code/claude-sonnet-5", md)
        self.assertNotIn("Cell (harness/model)", md)
        self.assertIn("✅", md)

    def test_html_self_contained(self):
        html = reporter.to_html(reporter.build_report([_card("a", 1.0, True), _card("b", 0.0, False)]))
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("100xeval report", html)
        self.assertIn("prefers-color-scheme: dark", html)   # theme-aware
        self.assertNotIn("http://", html)                    # no external assets
        self.assertNotIn("https://", html)
        self.assertIn("claude_code/claude-sonnet-5", html)

    def test_markdown_shows_failing_detail(self):
        md = reporter.to_markdown(reporter.build_report([_card("b", 0.0, False)]))
        self.assertIn("❌", md)
        # failing runs surface their detail for debugging
        self.assertIn("called sql 1x", md)


if __name__ == "__main__":
    unittest.main()
