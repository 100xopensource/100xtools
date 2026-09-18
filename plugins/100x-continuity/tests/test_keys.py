"""Session normalization, and the names a publication is filed under."""

import unittest

from engine import keys


SESSION = "0f9c1a2b-4d5e-6f70-8192-a3b4c5d6e7f8"
SHA_A = "a" * 64
SHA_B = "b" * 64


class NormalizeSessionIdTests(unittest.TestCase):
    def test_resolved_id_survives(self) -> None:
        self.assertEqual(keys.normalize_session_id(SESSION), SESSION)

    def test_padding_is_trimmed(self) -> None:
        # A padded id and a clean one must address the same session, or a caller
        # that stringifies with whitespace silently starts a second session.
        self.assertEqual(keys.normalize_session_id(f"  {SESSION}\n"), SESSION)

    def test_sentinels_normalize_to_none(self) -> None:
        for sentinel in ("", "   ", "unknown", "unknown-session", "none", "null"):
            with self.subTest(sentinel=sentinel):
                self.assertIsNone(keys.normalize_session_id(sentinel))

    def test_unexpanded_template_normalizes_to_none(self) -> None:
        # A caller whose shell never expanded the variable passes the literal
        # template; storing that as a real id would collide every such caller.
        self.assertIsNone(keys.normalize_session_id("${CLAUDE_SESSION_ID}"))

    def test_sentinel_match_is_case_folded(self) -> None:
        for sentinel in ("Unknown", "UNKNOWN-SESSION", "${Claude_Session_Id}"):
            with self.subTest(sentinel=sentinel):
                self.assertIsNone(keys.normalize_session_id(sentinel))

    def test_none_stays_none(self) -> None:
        self.assertIsNone(keys.normalize_session_id(None))

    def test_id_merely_containing_a_sentinel_survives(self) -> None:
        # Only an EXACT sentinel means "unresolved". A real id that happens to
        # embed the word must not be thrown away.
        self.assertEqual(
            keys.normalize_session_id("unknown-session-42"), "unknown-session-42"
        )


class NormalizeNamespaceTests(unittest.TestCase):
    def test_absent_namespace_defaults(self) -> None:
        self.assertEqual(keys.normalize_namespace(None), "default")
        self.assertEqual(keys.normalize_namespace("   "), "default")

    def test_case_is_folded(self) -> None:
        # Two namespaces differing only by case must not address different slots
        # on a case-insensitive filesystem.
        self.assertEqual(
            keys.normalize_namespace("Reports"), keys.normalize_namespace("reports")
        )

    def test_separators_cannot_survive(self) -> None:
        for hostile in ("../etc", "a/b", "a\\b"):
            with self.subTest(hostile=hostile):
                folded = keys.normalize_namespace(hostile)
                self.assertNotIn("/", folded)
                self.assertNotIn("\\", folded)
                self.assertNotIn("..", folded)

    def test_unsafe_characters_escape_rather_than_vanish(self) -> None:
        # Stripping would fold "a/b" and "ab" onto one namespace; escaping keeps
        # every distinct namespace distinct.
        self.assertNotEqual(
            keys.normalize_namespace("a/b"), keys.normalize_namespace("ab")
        )


class SessionSlotTests(unittest.TestCase):
    def test_slot_is_readable_and_unique(self) -> None:
        slot = keys.session_slot(SESSION)
        # Readable, because a recipient is handed a path and has to recognise it;
        # suffixed, because two ids that escape to the same prefix must stay apart.
        self.assertTrue(slot.startswith(SESSION[:20]))
        self.assertRegex(slot, r"-[0-9a-f]{12}\Z")

    def test_slot_is_stable(self) -> None:
        self.assertEqual(keys.session_slot(SESSION), keys.session_slot(f" {SESSION} "))

    def test_ids_differing_only_in_unsafe_characters_stay_apart(self) -> None:
        # Escaping alone would fold these together and file two sessions in one
        # directory; the digest suffix is what prevents it.
        self.assertNotEqual(keys.session_slot("a/b"), keys.session_slot("a:b"))

    def test_every_sentinel_lands_in_the_unattributed_slot(self) -> None:
        for sentinel in ("", "unknown", "unknown-session", "${CLAUDE_SESSION_ID}", None):
            with self.subTest(sentinel=sentinel):
                self.assertEqual(keys.session_slot(sentinel), keys.UNATTRIBUTED)

    def test_slot_cannot_introduce_a_path(self) -> None:
        for hostile in ("../../etc/passwd", "a/b/c", "..", "  ../x  "):
            with self.subTest(hostile=hostile):
                slot = keys.session_slot(hostile)
                self.assertNotIn("/", slot)
                self.assertNotIn("..", slot.split("-")[0])


class PublicationIdTests(unittest.TestCase):
    def test_id_carries_the_stamp_and_the_digest(self) -> None:
        self.assertEqual(
            keys.publication_id("20260820T140311Z", SHA_A),
            "20260820T140311Z-" + "a" * 12,
        )

    def test_ids_sort_chronologically(self) -> None:
        early = keys.publication_id("20260820T140311Z", SHA_A)
        late = keys.publication_id("20260821T090000Z", SHA_A)
        self.assertLess(early, late)

    def test_changed_bytes_get_a_different_id(self) -> None:
        # This is what keeps a publish from ever overwriting an earlier one, which
        # is what keeps a synced folder free of conflict copies.
        self.assertNotEqual(
            keys.publication_id("20260820T140311Z", SHA_A),
            keys.publication_id("20260820T140311Z", SHA_B),
        )

    def test_a_non_digest_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            keys.publication_id("20260820T140311Z", "not-a-digest")

    def test_a_malformed_stamp_is_refused(self) -> None:
        for stamp in ("2026-08-20T14:03:11Z", "", "20260820", "../../etc"):
            with self.subTest(stamp=stamp):
                with self.assertRaises(ValueError):
                    keys.publication_id(stamp, SHA_A)

    def test_a_pasted_id_is_validated_before_it_becomes_a_path(self) -> None:
        # A recipient pastes this, so it arrives as untrusted text.
        good = keys.publication_id("20260820T140311Z", SHA_A)
        self.assertEqual(keys.require_publication_id(good), good)
        for hostile in ("../../etc", "20260820T140311Z-../x", "", "latest"):
            with self.subTest(hostile=hostile):
                with self.assertRaises(ValueError):
                    keys.require_publication_id(hostile)


class CanonicalJsonTests(unittest.TestCase):
    def test_key_order_does_not_change_the_bytes(self) -> None:
        self.assertEqual(
            keys.canonical_json({"a": 1, "b": 2}), keys.canonical_json({"b": 2, "a": 1})
        )

    def test_non_finite_numbers_are_refused_on_the_way_out(self) -> None:
        # JSON has no NaN; letting Python's spelling through would write a manifest
        # other readers reject.
        with self.assertRaises(ValueError):
            keys.canonical_json({"value": float("nan")})

    def test_non_finite_numbers_are_refused_on_the_way_in(self) -> None:
        with self.assertRaises(ValueError):
            keys.reject_nonfinite_json("NaN")

    def test_readable_json_is_indented_and_ends_in_a_newline(self) -> None:
        out = keys.readable_json({"a": 1}).decode()
        self.assertIn("\n  ", out)
        self.assertTrue(out.endswith("\n"))

    def test_content_digest_is_hex_sha256(self) -> None:
        self.assertRegex(keys.content_digest(b"hello"), r"\A[0-9a-f]{64}\Z")

    def test_integrity_hash_names_its_algorithm(self) -> None:
        self.assertTrue(keys.integrity_hash({"a": 1}).startswith("sha256:"))

    def test_event_ids_are_derived_from_position_not_arrival(self) -> None:
        # Publishing one transcript twice must produce the same ids, or two copies
        # of a session cannot be compared.
        cursor = {"kind": "jsonl", "position": 3}
        self.assertEqual(
            keys.stable_event_id(source="transcript", session_id=SESSION, source_cursor=cursor),
            keys.stable_event_id(source="transcript", session_id=SESSION, source_cursor=cursor),
        )
        self.assertNotEqual(
            keys.stable_event_id(source="transcript", session_id=SESSION, source_cursor=cursor),
            keys.stable_event_id(
                source="transcript", session_id=SESSION, source_cursor={"kind": "jsonl", "position": 4}
            ),
        )

    def test_require_digest_refuses_anything_that_is_not_one(self) -> None:
        for hostile in ("", "A" * 64, "abc", "a" * 63, "../" + "a" * 61):
            with self.subTest(hostile=hostile):
                with self.assertRaises(ValueError):
                    keys.require_digest(hostile, "field")


if __name__ == "__main__":
    unittest.main()
