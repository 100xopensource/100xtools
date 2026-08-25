"""The publish boundary: what gets scrubbed, and what honestly does not.

Every credential-shaped fixture here is **assembled at run time**. A literal one
would be flagged forever by this repo's own secret linter, which scans every text
file — including this one — and the security sub-score it feeds would stop meaning
anything.
"""

import unittest

from engine import redact


def aws_key() -> str:
    return "AKIA" + "J" * 16


def github_token() -> str:
    return "ghp" + "_" + "b" * 36


def slack_token() -> str:
    return "xox" + "b-" + "1" * 12 + "-" + "a" * 24


def anthropic_key() -> str:
    return "sk-" + "ant-" + "x" * 32


def stripe_key() -> str:
    return "sk" + "_" + "live" + "_" + "c" * 24


def google_key() -> str:
    return "AIza" + "d" * 35


def npm_token() -> str:
    return "npm" + "_" + "e" * 36


def jwt() -> str:
    return "eyJ" + "abcdefghij" + "." + "klmnopqrst" + "." + "uvwxyz1234"


def private_key_block() -> str:
    begin = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
    end = "-----END " + "RSA PRIVATE KEY" + "-----"
    return f"{begin}\nMIIEow{'A' * 40}\n{end}"


class TextRuleTests(unittest.TestCase):
    def assert_scrubbed(self, text: str, rule: str) -> None:
        result = redact.redact_text(text)
        self.assertIn(rule, result.counts, f"{rule} did not fire on {text[:24]!r}")
        self.assertNotIn(text.strip(), result.value)

    def test_aws_access_key(self) -> None:
        self.assert_scrubbed(aws_key(), "aws-access-key")

    def test_github_token(self) -> None:
        self.assert_scrubbed(github_token(), "github-token")

    def test_slack_token(self) -> None:
        self.assert_scrubbed(slack_token(), "slack-token")

    def test_anthropic_style_key(self) -> None:
        self.assert_scrubbed(anthropic_key(), "secret-key-literal")

    def test_stripe_key(self) -> None:
        self.assert_scrubbed(stripe_key(), "stripe-key")

    def test_google_api_key(self) -> None:
        self.assert_scrubbed(google_key(), "google-api-key")

    def test_npm_token(self) -> None:
        self.assert_scrubbed(npm_token(), "npm-token")

    def test_jwt(self) -> None:
        self.assert_scrubbed(jwt(), "jwt")

    def test_private_key_block_goes_whole(self) -> None:
        result = redact.redact_text(private_key_block())
        self.assertIn("private-key", result.counts)
        self.assertNotIn("MIIEow", result.value)

    def test_authorization_header_keeps_the_header_name(self) -> None:
        # The shape of the request stays readable; only the credential goes.
        result = redact.redact_text("Authorization: Bearer " + "z" * 30)
        self.assertIn("authorization-header", result.counts)
        self.assertIn("Authorization", result.value)
        self.assertNotIn("z" * 30, result.value)

    def test_labelled_credential_is_redacted_whatever_its_shape(self) -> None:
        # A short ordinary word no shape rule would match.
        result = redact.redact_text("password=correcthorse")
        self.assertIn("labelled-credential", result.counts)
        self.assertNotIn("correcthorse", result.value)

    def test_placeholder_is_redacted_too(self) -> None:
        # The repo linter exempts self-describing placeholders to keep its score
        # honest. A redactor must not: the cost of scrubbing one is zero.
        result = redact.redact_text("api_key: your-api-key-here")
        self.assertIn("labelled-credential", result.counts)

    def test_several_secrets_in_one_string_all_go(self) -> None:
        text = f"key={aws_key()} and token={github_token()}"
        result = redact.redact_text(text)
        self.assertNotIn(aws_key(), result.value)
        self.assertNotIn(github_token(), result.value)

    def test_ordinary_prose_is_untouched(self) -> None:
        text = "We decided to ship the local backend first and defer the bucket."
        result = redact.redact_text(text)
        self.assertEqual(result.value, text)
        self.assertTrue(result.clean)

    def test_a_path_is_not_a_secret(self) -> None:
        text = "/Users/someone/Desktop/proj/report.md"
        self.assertTrue(redact.redact_text(text).clean)

    def test_a_sha_is_not_a_secret(self) -> None:
        # Content digests are everywhere in this plugin's own records; treating
        # them as secrets would redact the ledger's own structure.
        self.assertTrue(redact.redact_text("a" * 64).clean)

    def test_a_uuid_is_not_a_secret(self) -> None:
        self.assertTrue(
            redact.redact_text("fad672f6-791b-4576-a0e7-c660dd1a8e63").clean
        )


class SensitiveKeyTests(unittest.TestCase):
    def test_value_under_a_sensitive_key_goes_wholesale(self) -> None:
        result = redact.redact_value({"password": "hunter2"})
        self.assertNotIn("hunter2", str(result.value))
        self.assertEqual(result.counts, {"sensitive-key": 1})

    def test_key_spelling_variants_all_hit(self) -> None:
        for key in ("api_key", "apiKey", "API-KEY", "Api Key"):
            with self.subTest(key=key):
                result = redact.redact_value({key: "whatever-it-is"})
                self.assertNotIn("whatever-it-is", str(result.value))

    def test_plural_key_names_hit(self) -> None:
        for key in ("tokens", "cookies", "passwords", "credentials"):
            with self.subTest(key=key):
                result = redact.redact_value({key: "the-value"})
                self.assertNotIn("the-value", str(result.value))

    def test_a_word_merely_starting_with_a_secret_name_does_not_hit(self) -> None:
        # `author` starts with `auth`, and `access` ends in `s`. Neither is a secret,
        # and redacting them would gut ordinary records.
        payload = {"author": "quang", "access": "read-only"}
        self.assertEqual(redact.redact_value(payload).value, payload)

    def test_nested_sensitive_key_is_found(self) -> None:
        payload = {"tool_input": {"headers": {"authorization": "Bearer abc"}}}
        result = redact.redact_value(payload)
        self.assertNotIn("Bearer abc", str(result.value))

    def test_env_map_is_removed_whole(self) -> None:
        # Variable names are lost along with the values. That is the trade: an env
        # map is a credential store often enough that keeping the keys is not worth
        # the risk of a value slipping through by shape.
        result = redact.redact_value({"env": {"HOME": "/x", "TOKEN": "abc"}})
        self.assertNotIn("abc", str(result.value))

    def test_ordinary_keys_are_kept(self) -> None:
        payload = {"file_path": "/x/report.md", "old_string": "before"}
        result = redact.redact_value(payload)
        self.assertEqual(result.value, payload)
        self.assertTrue(result.clean)

    def test_structure_is_preserved(self) -> None:
        payload = {"a": [{"b": "text"}, 2, None, True]}
        self.assertEqual(redact.redact_value(payload).value, payload)

    def test_non_string_scalars_survive(self) -> None:
        payload = {"size": 12, "ok": False, "ratio": 1.5, "nothing": None}
        self.assertEqual(redact.redact_value(payload).value, payload)


class RecordTests(unittest.TestCase):
    def record(self, payload):
        return {
            "schema_version": 1,
            "event_id": "evt_" + "a" * 64,
            "source": "hook",
            "source_event": "PreToolUse",
            "session_id": "sess-1",
            "observed_at": "2026-08-19T06:00:00.000000Z",
            "source_timestamp": None,
            "sequence": 3,
            "source_cursor": {"kind": "hook", "position": "PreToolUse:x"},
            "completeness": {"state": "complete", "reasons": []},
            "integrity_hash": "sha256:" + "b" * 64,
            "payload": payload,
        }

    def test_envelope_survives_untouched(self) -> None:
        # Ordering, dedup, and provenance all read from these fields.
        original = self.record({"text": "hello"})
        out = redact.redact_record(original).value
        for field in ("event_id", "sequence", "source_cursor", "observed_at"):
            self.assertEqual(out[field], original[field])

    def test_payload_is_redacted(self) -> None:
        out = redact.redact_record(self.record({"cmd": f"curl -H 'x: {aws_key()}'"}))
        self.assertNotIn(aws_key(), str(out.value))

    def test_record_is_marked_as_transformed(self) -> None:
        out = redact.redact_record(self.record({"password": "hunter2"})).value
        self.assertEqual(out["redacted"]["counts"], {"sensitive-key": 1})

    def test_integrity_hash_still_describes_the_original(self) -> None:
        # Verifying a published record against this hash is meant to fail; that
        # failure is how a reader knows it is holding a transformed copy.
        original = self.record({"password": "hunter2"})
        out = redact.redact_record(original).value
        self.assertEqual(out["integrity_hash"], original["integrity_hash"])
        self.assertIn("before redaction", out["redacted"]["integrity_hash_covers"])

    def test_clean_record_is_still_marked(self) -> None:
        out = redact.redact_record(self.record({"text": "nothing secret"})).value
        self.assertEqual(out["redacted"]["counts"], {})

    def test_records_total_across_the_ledger(self) -> None:
        rows = [
            self.record({"a": aws_key()}),
            self.record({"password": "x"}),
            self.record({"b": "clean"}),
        ]
        result = redact.redact_records(rows)
        self.assertEqual(len(result.value), 3)
        self.assertEqual(result.counts["aws-access-key"], 1)
        self.assertEqual(result.counts["sensitive-key"], 1)
        self.assertEqual(result.total, 2)


if __name__ == "__main__":
    unittest.main()


class VendorPrefixedKeyTests(unittest.TestCase):
    """A credential word anywhere in the key is enough.

    Anchoring the pattern at a word boundary missed the most common credential name
    there is: `_` is a word character, so `AWS_SECRET_ACCESS_KEY=` has no boundary
    before `SECRET`, and the separator does not follow the word either. It travelled
    verbatim into every publication.
    """

    LABELLED = (
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI7MDENGbPxRfiCYEX",
        "DEPLOY_TOKEN=dpl_abcdefghijklmnopqrst",
        "my_deploy_token: dpl_abcdefghijklmnopqrst",
        "MY_CLIENT_SECRET = 'abcdefghijklmnop'",
        "cfg.api_key = zzzzzzzzzzzzzzzz",
    )

    CLEAN = (
        "the importer is on for store 41 only",
        "https://example.com/docs/secrets",
        "the access log shows nothing",
    )

    def test_a_vendor_prefixed_name_is_caught_in_prose(self) -> None:
        for line in self.LABELLED:
            with self.subTest(line=line):
                result = redact.redact_text(line)
                self.assertTrue(result.counts, f"{line!r} travelled verbatim")
                self.assertIn("[redacted:", result.value)

    def test_the_same_name_is_caught_as_a_structured_key(self) -> None:
        """Both paths, because a credential arrives as prose or as a tool argument."""
        payload = {"AWS_SECRET_ACCESS_KEY": "wJalr", "DEPLOY_TOKEN": "dpl_x", "note": "fine"}
        result = redact.redact_value(payload)
        self.assertEqual(result.value["note"], "fine")
        for key in ("AWS_SECRET_ACCESS_KEY", "DEPLOY_TOKEN"):
            self.assertIn("[redacted:", result.value[key], key)

    def test_ordinary_prose_is_left_alone(self) -> None:
        """Recall is the priority, but not at the cost of redacting a sentence."""
        for line in self.CLEAN:
            with self.subTest(line=line):
                self.assertFalse(redact.redact_text(line).counts, line)
