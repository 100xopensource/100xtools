"""Finding and reading the transcript the host already wrote.

Every fixture here builds a real directory tree, because the thing under test is
directory *listing*. A test that stubbed the filesystem would pass while the one
bug this module exists to prevent — a constructed directory name that does not
match the real one — sailed through.
"""

import json
import pathlib
import tempfile
import unittest

from engine import transcript


class _Tree(unittest.TestCase):
    """A fake home holding a transcript tree, in either surface's shape."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = pathlib.Path(self._tmp.name)

    def write(
        self,
        *,
        mount: bool = False,
        project: str = "-repo-acme",
        session_id: str = "s1",
        rows: list[dict] | None = None,
    ) -> pathlib.Path:
        base = self.home / ("mnt/.claude/projects" if mount else ".claude/projects")
        directory = base / project
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{session_id}.jsonl"
        rows = rows if rows is not None else [{"type": "user", "sessionId": session_id}]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return path


class RootTests(_Tree):
    def test_no_tree_means_no_roots(self) -> None:
        self.assertEqual(transcript.roots(self.home), [])

    def test_the_host_root_is_found(self) -> None:
        self.write()
        self.assertEqual(
            transcript.roots(self.home), [self.home / ".claude" / "projects"]
        )

    def test_the_mounted_root_comes_first(self) -> None:
        # Inside a session the mount holds THIS conversation; a host root visible
        # there would describe different work, so precedence is not cosmetic.
        self.write(mount=True)
        self.write()
        found = transcript.roots(self.home)
        self.assertEqual(len(found), 2)
        self.assertIn("mnt", str(found[0]))


class DiscoverTests(_Tree):
    def test_nothing_anywhere_is_reported_not_raised(self) -> None:
        found = transcript.discover(home=self.home)
        self.assertFalse(found.ok)
        self.assertTrue(found.notes)

    def test_a_single_transcript_is_found(self) -> None:
        path = self.write()
        found = transcript.discover(home=self.home)
        self.assertEqual(found.path, path)
        self.assertEqual(found.candidates, 1)
        self.assertEqual(found.directories, 1)

    def test_an_empty_root_says_what_it_listed(self) -> None:
        # "found nothing" and "never looked" must not read the same.
        (self.home / ".claude" / "projects" / "-repo").mkdir(parents=True)
        found = transcript.discover(home=self.home)
        self.assertFalse(found.ok)
        self.assertIn("listed 1 directories", found.notes[0])

    def test_the_session_id_wins_over_recency(self) -> None:
        wanted = self.write(session_id="wanted", project="-a")
        newer = self.write(session_id="newer", project="-b")
        # Make the unwanted one newer, so recency would pick it.
        newer.touch()
        found = transcript.discover(session_id="wanted", home=self.home)
        self.assertEqual(found.path, wanted)
        self.assertEqual(found.notes, ())

    def test_an_unknown_session_id_falls_back_and_says_so(self) -> None:
        self.write(session_id="only-one")
        found = transcript.discover(session_id="absent", home=self.home)
        self.assertTrue(found.ok)
        self.assertTrue(any("absent" in note for note in found.notes))

    def test_the_most_recent_file_wins_without_an_id(self) -> None:
        import os
        import time

        old = self.write(session_id="old", project="-a")
        new = self.write(session_id="new", project="-b")
        os.utime(old, (time.time() - 500, time.time() - 500))
        self.assertEqual(transcript.discover(home=self.home).path, new)

    def test_it_searches_across_every_project_directory(self) -> None:
        self.write(project="-a", session_id="a")
        self.write(project="-b", session_id="b")
        self.write(project="-c", session_id="c")
        found = transcript.discover(home=self.home)
        self.assertEqual(found.directories, 3)
        self.assertEqual(found.candidates, 3)

    def test_a_directory_name_with_underscores_is_still_found(self) -> None:
        # The real encoding replaces underscores too, which is exactly why the
        # name is listed rather than built. A constructed name misses here.
        path = self.write(project="-Users-q-my-repo-v2-outputs", session_id="s9")
        self.assertEqual(transcript.discover(home=self.home).path, path)

    def test_the_mount_is_preferred_when_both_exist(self) -> None:
        mounted = self.write(mount=True, session_id="inside", project="-x")
        self.write(session_id="outside", project="-y")
        self.assertEqual(transcript.discover(home=self.home).path, mounted)


class ReadTests(_Tree):
    def test_every_record_is_returned(self) -> None:
        path = self.write(rows=[{"type": "user"}, {"type": "assistant"}])
        self.assertEqual(len(transcript.read(path)), 2)

    def test_a_torn_final_line_is_skipped_not_fatal(self) -> None:
        # Transcripts are written live, so the last line can be half-written at
        # the moment we read. Losing the session over it would be absurd.
        path = self.write(rows=[{"type": "user"}])
        with path.open("ab") as handle:
            handle.write(b'{"type": "assist')
        self.assertEqual(len(transcript.read(path)), 1)

    def test_blank_lines_are_ignored(self) -> None:
        path = self.write(rows=[{"type": "user"}])
        with path.open("ab") as handle:
            handle.write(b"\n\n")
        self.assertEqual(len(transcript.read(path)), 1)

    def test_a_non_object_line_is_skipped(self) -> None:
        path = self.write(rows=[{"type": "user"}])
        with path.open("ab") as handle:
            handle.write(b'"just a string"\n[1,2]\n')
        self.assertEqual(len(transcript.read(path)), 1)

    def test_a_byte_cap_stops_at_a_line_boundary(self) -> None:
        path = self.write(rows=[{"type": "user", "n": i} for i in range(50)])
        rows = transcript.read(path, max_bytes=100)
        self.assertLess(len(rows), 50)
        self.assertTrue(all(isinstance(r, dict) for r in rows))


class ConfirmTests(unittest.TestCase):
    def test_a_phrase_from_the_end_confirms(self) -> None:
        rows = [{"text": "earlier"}, {"text": "the latest thing"}]
        self.assertTrue(transcript.confirm(rows, "the latest thing"))

    def test_an_absent_phrase_does_not(self) -> None:
        # Assembled so the literal never lands in this repo's own transcripts.
        absent = "z" * 8 + "-" + "nowhere" + "-" + "4" * 6
        self.assertFalse(transcript.confirm([{"text": "hello"}], absent))

    def test_an_empty_needle_never_confirms(self) -> None:
        # Truthy-by-default would make every transcript "this conversation".
        self.assertFalse(transcript.confirm([{"text": "hello"}], ""))

    def test_only_the_tail_is_searched(self) -> None:
        rows = [{"text": "very old"}] + [{"text": "filler"}] * 60
        self.assertFalse(transcript.confirm(rows, "very old", tail=10))


class OuterIdTests(unittest.TestCase):
    def test_a_cowork_cwd_yields_the_session_directory(self) -> None:
        self.assertEqual(
            transcript.outer_id("/S/local-agent-mode-sessions/a/b/local_c0ffee/outputs"),
            "local_c0ffee",
        )

    def test_an_ordinary_cwd_yields_nothing(self) -> None:
        self.assertIsNone(transcript.outer_id("/Users/q/proj/acme"))

    def test_missing_cwd_yields_nothing(self) -> None:
        self.assertIsNone(transcript.outer_id(None))
        self.assertIsNone(transcript.outer_id(""))

    def test_the_innermost_session_wins(self) -> None:
        self.assertEqual(
            transcript.outer_id("/s/local_outer/x/local_inner/outputs"), "local_inner"
        )

    def test_a_windows_form_path_still_resolves(self) -> None:
        # pathlib collapses a backslash path to one component under a POSIX
        # flavour, so the anchor would never be found and the id would come back
        # empty with no error to notice.
        self.assertEqual(
            transcript.outer_id(r"C:\C\local-agent\a\local_xy\outputs"), "local_xy"
        )

    def test_a_lookalike_directory_is_not_a_session(self) -> None:
        self.assertIsNone(transcript.outer_id("/x/localhost/outputs"))


class IdentifyTests(unittest.TestCase):
    def test_the_inner_id_comes_from_the_records(self) -> None:
        rows = [{"type": "user", "sessionId": "abc-123"}]
        self.assertEqual(transcript.identify(rows)["inner_id"], "abc-123")

    def test_the_outer_id_comes_from_cwd(self) -> None:
        rows = [{"type": "user", "cwd": "/s/local_deadbeef/outputs"}]
        self.assertEqual(transcript.identify(rows)["outer_id"], "local_deadbeef")

    def test_the_two_ids_are_different_things(self) -> None:
        # Substituting one for the other names a file that does not exist.
        rows = [{"sessionId": "7b0b23e9", "cwd": "/s/local_72fc8af5/outputs"}]
        identity = transcript.identify(rows)
        self.assertNotEqual(identity["inner_id"], identity["outer_id"])

    def test_a_title_record_is_picked_up(self) -> None:
        rows = [{"type": "ai-title", "title": "Fix the importer"}]
        self.assertEqual(transcript.identify(rows)["title"], "Fix the importer")

    def test_nothing_known_is_reported_as_none(self) -> None:
        self.assertEqual(
            transcript.identify([{"type": "user"}]),
            {"inner_id": None, "outer_id": None, "title": None},
        )

    def test_an_empty_transcript_does_not_raise(self) -> None:
        self.assertIsNone(transcript.identify([])["inner_id"])


class SubagentTests(_Tree):
    def test_none_present_is_not_an_error(self) -> None:
        path = self.write()
        self.assertEqual(transcript.subagents(path, "s1"), [])

    def test_they_are_found_beside_the_main_transcript(self) -> None:
        path = self.write(session_id="s1")
        directory = path.parent / "s1" / "subagents"
        directory.mkdir(parents=True)
        for name in ("agent-b", "agent-a"):
            (directory / f"{name}.jsonl").write_text("{}\n")
        found = transcript.subagents(path, "s1")
        self.assertEqual([p.stem for p in found], ["agent-a", "agent-b"])

    def test_without_an_inner_id_there_is_nowhere_to_look(self) -> None:
        self.assertEqual(transcript.subagents(self.write(), None), [])


class AsRecordsTests(unittest.TestCase):
    def test_the_row_is_carried_untouched(self) -> None:
        row = {"type": "user", "message": {"content": "hi"}}
        self.assertEqual(transcript.as_records([row])[0]["payload"], row)

    def test_the_envelope_names_the_source_and_event(self) -> None:
        record = transcript.as_records([{"type": "assistant"}])[0]
        self.assertEqual(record["source"], "transcript")
        self.assertEqual(record["source_event"], "assistant")

    def test_sequence_starts_at_one(self) -> None:
        records = transcript.as_records([{"type": "a"}, {"type": "b"}])
        self.assertEqual([r["sequence"] for r in records], [1, 2])

    def test_ids_are_stable_across_two_runs(self) -> None:
        # Two publishes of one session must be comparable; a counter-derived or
        # clock-derived id would make every copy look like different work.
        rows = [{"type": "user", "sessionId": "s1"}]
        first = transcript.as_records(rows)
        second = transcript.as_records(rows)
        self.assertEqual(first[0]["event_id"], second[0]["event_id"])
        self.assertEqual(first[0]["integrity_hash"], second[0]["integrity_hash"])

    def test_different_content_gets_a_different_integrity_hash(self) -> None:
        a = transcript.as_records([{"type": "user", "sessionId": "s1", "x": 1}])
        b = transcript.as_records([{"type": "user", "sessionId": "s1", "x": 2}])
        self.assertNotEqual(a[0]["integrity_hash"], b[0]["integrity_hash"])

    def test_the_session_id_is_read_from_the_rows(self) -> None:
        record = transcript.as_records([{"type": "user", "sessionId": "found-me"}])[0]
        self.assertEqual(record["session_id"], "found-me")

    def test_an_explicit_session_id_is_honoured(self) -> None:
        record = transcript.as_records([{"type": "user"}], session_id="given")[0]
        self.assertEqual(record["session_id"], "given")

    def test_an_unidentifiable_session_is_marked_rather_than_guessed(self) -> None:
        self.assertEqual(
            transcript.as_records([{"type": "user"}])[0]["session_id"], "unknown"
        )

    def test_no_rows_yields_no_records(self) -> None:
        self.assertEqual(transcript.as_records([]), [])


if __name__ == "__main__":
    unittest.main()


class TitleTests(unittest.TestCase):
    """The host writes `aiTitle`. Reading `title` alone returned None every time."""

    def test_the_hosts_field_is_read(self) -> None:
        rows = [{"type": "ai-title", "aiTitle": "Importer flags", "sessionId": "s1"}]
        self.assertEqual(transcript.identify(rows)["title"], "Importer flags")

    def test_a_plain_title_field_still_works(self) -> None:
        rows = [{"type": "ai-title", "title": "Older shape", "sessionId": "s1"}]
        self.assertEqual(transcript.identify(rows)["title"], "Older shape")

    def test_a_session_with_no_title_reports_none(self) -> None:
        rows = [{"type": "user", "sessionId": "s1"}]
        self.assertIsNone(transcript.identify(rows)["title"])
