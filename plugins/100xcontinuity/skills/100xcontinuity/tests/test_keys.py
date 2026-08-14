"""Session normalization and the content-addressed key scheme."""

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


class SessionDigestTests(unittest.TestCase):
    def test_digest_is_stable(self) -> None:
        self.assertEqual(
            keys.session_digest("reports", SESSION),
            keys.session_digest("reports", SESSION),
        )

    def test_padded_and_clean_ids_agree(self) -> None:
        self.assertEqual(
            keys.session_digest("reports", f"  {SESSION}  "),
            keys.session_digest("reports", SESSION),
        )

    def test_namespaces_are_isolated(self) -> None:
        self.assertNotEqual(
            keys.session_digest("reports", SESSION),
            keys.session_digest("audits", SESSION),
        )

    def test_every_sentinel_lands_in_one_unattributed_slot(self) -> None:
        # The point of normalizing: unresolved sessions group under a single
        # inspectable slot instead of one slot per sentinel spelling.
        expected = keys.session_digest("reports", keys.UNATTRIBUTED)
        for sentinel in ("", "unknown", "unknown-session", "${CLAUDE_SESSION_ID}"):
            with self.subTest(sentinel=sentinel):
                self.assertEqual(keys.session_digest("reports", sentinel), expected)

    def test_digest_is_hex_sha256(self) -> None:
        self.assertRegex(keys.session_digest("reports", SESSION), r"\A[0-9a-f]{64}\Z")


class KeyBuildingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.digest = keys.session_digest("reports", SESSION)

    def test_identical_bytes_produce_one_blob_key(self) -> None:
        # The property that keeps a synced folder free of conflict copies.
        payload = b"same bytes from two machines"
        self.assertEqual(
            keys.blob_key(self.digest, keys.content_digest(payload)),
            keys.blob_key(self.digest, keys.content_digest(payload)),
        )

    def test_different_bytes_produce_different_blob_keys(self) -> None:
        self.assertNotEqual(
            keys.blob_key(self.digest, keys.content_digest(b"one")),
            keys.blob_key(self.digest, keys.content_digest(b"two")),
        )

    def test_blob_key_sits_under_its_session_prefix(self) -> None:
        key = keys.blob_key(self.digest, SHA_A)
        self.assertTrue(key.startswith(keys.session_prefix(self.digest)))

    def test_entries_at_one_instant_stay_distinct(self) -> None:
        # Two machines writing in the same second must not collapse to one entry.
        stamp = "2026-08-13T09-00-00Z"
        self.assertNotEqual(
            keys.entry_key(self.digest, stamp, SHA_A),
            keys.entry_key(self.digest, stamp, SHA_B),
        )

    def test_entry_keys_sort_chronologically(self) -> None:
        early = keys.entry_key(self.digest, "2026-08-13T09-00-00Z", SHA_A)
        late = keys.entry_key(self.digest, "2026-08-13T17-30-00Z", SHA_A)
        self.assertLess(early, late)

    def test_non_digest_segments_are_refused(self) -> None:
        # The one input that could smuggle a separator into a path.
        for bad in ("../escape", "", "NOTHEX" * 4, SHA_A.upper()):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    keys.blob_key(bad, SHA_A)
                with self.assertRaises(ValueError):
                    keys.blob_key(self.digest, bad)

    def test_ordinal_cannot_introduce_a_separator(self) -> None:
        with self.assertRaises(ValueError):
            keys.entry_key(self.digest, "../escape", SHA_A)
        with self.assertRaises(ValueError):
            keys.entry_key(self.digest, "", SHA_A)


if __name__ == "__main__":
    unittest.main()
