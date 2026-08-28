"""Folding a captured session into the page a later session reads.

Record shapes here mirror a real `~/.claude/projects` transcript, including the
bookkeeping types that sit alongside the conversation.
"""

import unittest

from engine import digest


def hook(event: str, **payload):
    return {
        "source": "hook",
        "source_event": event,
        "session_id": "sess-1",
        "observed_at": "2026-08-19T06:00:00.000000Z",
        "payload": {"hook_event_name": event, "session_id": "sess-1", **payload},
    }


def transcript(kind: str, *, stamp="2026-08-19T06:00:00.000Z", **payload):
    return {
        "source": "transcript",
        "source_event": kind,
        "session_id": "sess-1",
        "observed_at": stamp,
        "source_timestamp": stamp,
        "payload": {"type": kind, **payload},
    }


def user(text: str, *, human=True, **extra):
    payload = {
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
        "cwd": "/repo",
        "gitBranch": "main",
        **extra,
    }
    if human:
        payload["origin"] = {"kind": "human"}
    return transcript("user", **payload)


def assistant(*blocks, model="claude-opus-5", usage=None, **extra):
    message = {"role": "assistant", "content": list(blocks), "model": model}
    if usage:
        message["usage"] = usage
    return transcript("assistant", message=message, cwd="/repo", **extra)


class SummaryTests(unittest.TestCase):
    def test_empty_session_summarizes_without_failing(self) -> None:
        result = digest.summarize([])
        self.assertEqual(result.records, 0)
        self.assertEqual(result.turns, 0)
        self.assertIn("Session unknown", result.to_markdown())

    def test_prompts_are_collected_in_order(self) -> None:
        result = digest.summarize([user("first"), user("second")])
        self.assertEqual(result.prompts, ["first", "second"])
        self.assertEqual(result.turns, 2)

    def test_injected_skill_body_is_not_a_prompt(self) -> None:
        # Verified against a real session: invoking a slash command files the
        # skill's whole body as a `user` record, which read as a 60-line question
        # the user never asked.
        records = [user("real question"), user("# Skill body", human=False)]
        self.assertEqual(digest.summarize(records).prompts, ["real question"])

    def test_without_origin_markers_every_text_turn_counts(self) -> None:
        # A build that does not emit `origin` must not summarise as "asked
        # nothing" — the filter only applies when the session shows the field.
        records = [user("one", human=False), user("two", human=False)]
        self.assertEqual(digest.summarize(records).prompts, ["one", "two"])

    def test_tool_results_are_not_prompts(self) -> None:
        result = digest.summarize(
            [
                user("do it"),
                transcript(
                    "user",
                    message={
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
                        ],
                    },
                ),
            ]
        )
        self.assertEqual(result.prompts, ["do it"])

    def test_injected_context_blocks_are_dropped(self) -> None:
        result = digest.summarize(
            [
                transcript(
                    "user",
                    origin={"kind": "human"},
                    message={
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "<system-reminder>noise</system-reminder>"},
                            {"type": "text", "text": "the actual ask"},
                        ],
                    },
                )
            ]
        )
        self.assertEqual(result.prompts, ["the actual ask"])

    def test_thinking_blocks_never_reach_the_digest(self) -> None:
        result = digest.summarize(
            [assistant({"type": "thinking", "thinking": "private"}, {"type": "text", "text": "public"})]
        )
        self.assertEqual(result.last_assistant_text, "public")
        self.assertNotIn("private", result.to_markdown())

    def test_string_content_is_accepted(self) -> None:
        result = digest.summarize(
            [transcript("user", origin={"kind": "human"}, message={"role": "user", "content": "plain"})]
        )
        self.assertEqual(result.prompts, ["plain"])

    def test_sidechain_records_are_skipped(self) -> None:
        result = digest.summarize([user("main ask"), user("subagent ask", isSidechain=True)])
        self.assertEqual(result.prompts, ["main ask"])

    def test_title_comes_from_the_ai_title_record(self) -> None:
        result = digest.summarize([transcript("ai-title", aiTitle="Refactor the ledger")])
        self.assertEqual(result.title, "Refactor the ledger")
        self.assertIn("# Session Refactor the ledger", result.to_markdown())

    def test_cwd_and_branch_are_recovered(self) -> None:
        result = digest.summarize([user("hi")])
        self.assertEqual(result.cwd, "/repo")
        self.assertEqual(result.git_branch, "main")

    def test_model_and_tokens_accumulate(self) -> None:
        result = digest.summarize(
            [
                assistant({"type": "text", "text": "a"}, usage={"input_tokens": 10, "output_tokens": 2}),
                assistant({"type": "text", "text": "b"}, usage={"input_tokens": 5, "output_tokens": 3}),
            ]
        )
        self.assertEqual(result.models, ["claude-opus-5"])
        self.assertEqual(result.tokens, {"input_tokens": 15, "output_tokens": 5})

    def test_time_span_spans_every_record(self) -> None:
        result = digest.summarize(
            [user("a", stamp="2026-08-19T06:00:00.000Z"), user("b", stamp="2026-08-19T07:00:00.000Z")]
        )
        self.assertEqual(result.started_at, "2026-08-19T06:00:00.000Z")
        self.assertEqual(result.ended_at, "2026-08-19T07:00:00.000Z")

    def test_last_assistant_message_wins_from_the_stop_hook(self) -> None:
        # The docs single this field out as more reliable than the transcript,
        # which can lag behind the hook that fires.
        result = digest.summarize(
            [assistant({"type": "text", "text": "mid-turn"}), hook("Stop", last_assistant_message="final word")]
        )
        self.assertEqual(result.last_assistant_text, "final word")


class ToolAccountingTests(unittest.TestCase):
    def test_tools_are_counted_from_the_transcript(self) -> None:
        result = digest.summarize(
            [
                assistant({"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}),
                assistant({"type": "tool_use", "id": "t2", "name": "Bash", "input": {}}),
            ]
        )
        self.assertEqual(result.tools, {"Bash": 2})

    def test_tools_are_counted_from_hooks_alone(self) -> None:
        result = digest.summarize(
            [hook("PreToolUse", tool_use_id="t1", tool_name="Write", tool_input={})]
        )
        self.assertEqual(result.tools, {"Write": 1})

    def test_one_call_seen_by_both_sources_counts_once(self) -> None:
        # The obvious first bug: a session captured through hooks *and* the
        # transcript reported every tool call twice.
        result = digest.summarize(
            [
                hook("PreToolUse", tool_use_id="t1", tool_name="Bash", tool_input={}),
                hook("PostToolUse", tool_use_id="t1", tool_name="Bash", tool_input={}),
                assistant({"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}),
            ]
        )
        self.assertEqual(result.tools, {"Bash": 1})

    def test_files_come_from_tool_inputs(self) -> None:
        result = digest.summarize(
            [
                hook("PreToolUse", tool_use_id="t1", tool_name="Write", tool_input={"file_path": "/repo/a.md"}),
                assistant({"type": "tool_use", "id": "t2", "name": "Read", "input": {"path": "/repo/b.md"}}),
            ]
        )
        self.assertEqual(result.files, ["/repo/a.md", "/repo/b.md"])

    def test_relative_and_absolute_paths_are_one_file(self) -> None:
        result = digest.summarize(
            [
                user("edit it"),
                hook("PreToolUse", tool_use_id="t1", tool_name="Edit", tool_input={"file_path": "/repo/a.md"}),
                hook("PreToolUse", tool_use_id="t2", tool_name="Edit", tool_input={"file_path": "a.md"}),
            ]
        )
        self.assertEqual(result.files, ["/repo/a.md"])

    def test_file_history_paths_are_included(self) -> None:
        result = digest.summarize([transcript("file-history-delta", trackingPath="/repo/c.md")])
        self.assertEqual(result.files, ["/repo/c.md"])


class BoundsTests(unittest.TestCase):
    def test_prompts_are_capped_keeping_the_recent_ones(self) -> None:
        result = digest.summarize([user(f"ask {n}") for n in range(10)], max_prompts=3)
        self.assertEqual(result.prompts, ["ask 7", "ask 8", "ask 9"])
        self.assertEqual(result.prompts_omitted, 7)
        self.assertEqual(result.turns, 10)
        self.assertIn("7 earlier turns not listed", result.to_markdown())

    def test_long_prompt_is_clipped(self) -> None:
        result = digest.summarize([user("x" * 900)], max_prompt_chars=50)
        self.assertLessEqual(len(result.prompts[0]), 50)
        self.assertTrue(result.prompts[0].endswith("…"))

    def test_files_are_capped_and_the_remainder_reported(self) -> None:
        records = [
            hook("PreToolUse", tool_use_id=f"t{n}", tool_name="Write", tool_input={"file_path": f"/repo/{n}.md"})
            for n in range(10)
        ]
        result = digest.summarize(records, max_files=4)
        self.assertEqual(len(result.files), 4)
        self.assertEqual(result.files_omitted, 6)
        self.assertIn("6 more", result.to_markdown())


class MarkdownTests(unittest.TestCase):
    def test_gaps_reach_the_digest(self) -> None:
        # A resuming session that cannot see a gap will assume the record is whole.
        result = digest.summarize(
            [user("hi")],
            open_notes=[{"code": "transcript_read_capped", "details": {"max_bytes": 4}}],
        )
        self.assertIn("Capture gaps", result.to_markdown())
        self.assertIn("transcript_read_capped", result.to_markdown())

    def test_markdown_is_far_smaller_than_the_records(self) -> None:
        records = [user("ask " + "y" * 500) for _ in range(50)]
        rendered = digest.summarize(records).to_markdown()
        self.assertLess(len(rendered), 20_000)

    def test_dict_round_trip_carries_the_same_facts(self) -> None:
        result = digest.summarize([user("hi"), assistant({"type": "text", "text": "there"})])
        as_dict = result.to_dict()
        self.assertEqual(as_dict["prompts"], ["hi"])
        self.assertEqual(as_dict["last_assistant_text"], "there")
        self.assertEqual(as_dict["turns"], 1)

    def test_malformed_records_are_skipped_not_fatal(self) -> None:
        records = [
            {"source": "transcript", "payload": None},
            {"source": "transcript", "payload": {"type": "user", "message": "not a dict"}},
            {"nothing": "useful"},
            user("survives"),
        ]
        self.assertEqual(digest.summarize(records).prompts, ["survives"])


if __name__ == "__main__":
    unittest.main()
