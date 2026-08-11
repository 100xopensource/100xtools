import unittest

from engine import yamlmin

# The design §5 example case, verbatim shape.
CASE = """
name: asksales-slowest-hours              # required, unique
description: askFastScore returns the slowest hours for a store.
plugins: ["../../plugins/acme-analytics"]
tags: [asksales]
runs: 3
execution:
  prompt: "For Acme Eastern, what were my slowest hours last week?"
  model: claude-sonnet-5
  entrypoint: cowork
  max_turns: 15
  allowed_tools: [Read, Glob, Grep, Skill, mcp__claude_ai_Acme__run_query]
  append_system_prompt: null
graders:
  - {type: tool_used, name: filtered-to-store, tool: mcp__claude_ai_Acme__run_query, input_match: Eastern, min: 1}
  - {type: llm, name: presentation, focus: last_message, criteria: "cites source; ranked hourly table; disclaimer"}
"""


class TestYamlmin(unittest.TestCase):
    def setUp(self):
        self.data = yamlmin.load(CASE)

    def test_top_level_scalars(self):
        self.assertEqual(self.data["name"], "asksales-slowest-hours")
        self.assertEqual(self.data["runs"], 3)
        self.assertEqual(self.data["description"], "askFastScore returns the slowest hours for a store.")

    def test_flow_lists(self):
        self.assertEqual(self.data["plugins"], ["../../plugins/acme-analytics"])
        self.assertEqual(self.data["tags"], ["asksales"])
        self.assertIn("mcp__claude_ai_Acme__run_query", self.data["execution"]["allowed_tools"])
        self.assertEqual(len(self.data["execution"]["allowed_tools"]), 5)

    def test_nested_mapping(self):
        ex = self.data["execution"]
        self.assertEqual(ex["prompt"], "For Acme Eastern, what were my slowest hours last week?")
        self.assertEqual(ex["max_turns"], 15)
        self.assertIsNone(ex["append_system_prompt"])

    def test_sequence_of_flow_maps(self):
        graders = self.data["graders"]
        self.assertEqual(len(graders), 2)
        self.assertEqual(graders[0]["type"], "tool_used")
        self.assertEqual(graders[0]["min"], 1)
        self.assertEqual(graders[0]["input_match"], "Eastern")
        self.assertEqual(graders[1]["criteria"], "cites source; ranked hourly table; disclaimer")

    def test_scalar_typing(self):
        self.assertIs(yamlmin.load("k: true")["k"], True)
        self.assertIs(yamlmin.load("k: false")["k"], False)
        self.assertIsNone(yamlmin.load("k: null")["k"])
        self.assertEqual(yamlmin.load("k: 42")["k"], 42)
        self.assertEqual(yamlmin.load("k: 3.5")["k"], 3.5)
        self.assertEqual(yamlmin.load("k: plain text")["k"], "plain text")

    def test_comment_stripping(self):
        self.assertEqual(yamlmin.load("k: v  # trailing")["k"], "v")
        self.assertEqual(yamlmin.load("# whole line\nk: v")["k"], "v")
        # A hash inside quotes is NOT a comment.
        self.assertEqual(yamlmin.load('k: "a # b"')["k"], "a # b")

    def test_block_sequence_of_scalars(self):
        data = yamlmin.load("items:\n  - one\n  - two\n  - three")
        self.assertEqual(data["items"], ["one", "two", "three"])

    def test_nested_flow_map(self):
        data = yamlmin.load("g: {a: 1, b: [x, y], c: {d: 2}}")
        self.assertEqual(data["g"], {"a": 1, "b": ["x", "y"], "c": {"d": 2}})

    def test_tab_indent_rejected(self):
        with self.assertRaises(yamlmin.YamlError):
            yamlmin.load("k:\n\t- bad")


if __name__ == "__main__":
    unittest.main()


BLOCKS = '''
graders:
  - type: llm
    name: ground-truth
    criteria: |-
      Run EXACTLY this SQL:
      SELECT location, SUM(quantity) AS units  -- not a # comment
      FROM t
      WHERE location = 'SB Northgate'

      Then compare within 5 percent.
    weight: 2
  - {type: regex, name: r, pattern: hi}
note: >-
  folded one
  folded two

  second para
kept: |
  keeps one trailing newline
after: done
'''


class TestBlockScalars(unittest.TestCase):
    """Cases embed multi-line SQL as judge ground truth — `|` must survive verbatim."""

    def setUp(self):
        self.data = yamlmin.load(BLOCKS)

    def test_literal_preserves_newlines_and_hashes(self):
        crit = self.data["graders"][0]["criteria"]
        self.assertIn("SELECT location, SUM(quantity) AS units  -- not a # comment", crit)
        self.assertEqual(crit.count("\n"), 5)          # incl. the blank paragraph line
        self.assertTrue(crit.startswith("Run EXACTLY"))
        self.assertTrue(crit.endswith("5 percent."))   # `-` chomps the trailing newline

    def test_block_does_not_swallow_siblings(self):
        # The regression that makes this hard: `- key: |` must stop at the next key.
        self.assertEqual(self.data["graders"][0]["weight"], 2)
        self.assertEqual(self.data["graders"][1], {"type": "regex", "name": "r", "pattern": "hi"})
        self.assertEqual(self.data["after"], "done")

    def test_folded_joins_lines_and_keeps_paragraphs(self):
        self.assertEqual(self.data["note"], "folded one folded two\n\nsecond para")

    def test_clip_chomping_keeps_one_newline(self):
        self.assertEqual(self.data["kept"], "keeps one trailing newline\n")

    def test_sql_survives_a_round_trip_into_a_grader(self):
        crit = self.data["graders"][0]["criteria"]
        self.assertIn("'SB Northgate'", crit)    # quotes intact


class TestDoubleQuotedEscapes(unittest.TestCase):
    """Double-quoted scalars process escapes, as YAML requires.

    `\\\\` was not handled at all, so a grader pattern written "\\\\s*%" reached `re` as a
    literal backslash and matched nothing — and a not_contains grader whose pattern matches
    nothing is one that cannot fail. Chained .replace() also turned an escaped backslash
    followed by n into a newline.
    """

    def _v(self, src):
        return yamlmin.load(src)["a"]

    def test_escaped_backslash_becomes_one(self):
        self.assertEqual(self._v(r'a: "x\\by"'), r"x\by")

    def test_regex_pattern_survives_intact(self):
        self.assertEqual(self._v(r'a: "[0-9]+(\\.[0-9]+)?\\s*%"'), r"[0-9]+(\.[0-9]+)?\s*%")

    def test_newline_escape(self):
        self.assertEqual(self._v(r'a: "line\nnext"'), "line\nnext")

    def test_escaped_backslash_then_n_is_not_a_newline(self):
        self.assertEqual(self._v(r'a: "lit\\nnext"'), r"lit\nnext")

    def test_escaped_quote(self):
        self.assertEqual(self._v(r'a: "say \"hi\""'), 'say "hi"')

    def test_regex_escapes_are_kept_verbatim(self):
        # `\s` is not a YAML escape; dropping the backslash would break the pattern.
        self.assertEqual(self._v(r'a: "\s+\d\b"'), r"\s+\d\b")

    def test_single_quotes_are_literal(self):
        self.assertEqual(self._v(r"a: '\s+'"), r"\s+")
