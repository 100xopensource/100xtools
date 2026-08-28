"""Pulling a publication back: what is verified, and what is refused."""

from __future__ import annotations

import io
import os
import pathlib
import tempfile
import unittest
import unittest.mock
import urllib.error

from engine import download, keys, wire

BODY = b"a gzipped bundle would be here"
DIGEST = keys.content_digest(BODY)
MINT = {
    "url": "https://store.example.com/bucket/key?X-Amz-Signature=abc",
    "required_headers": {"x-amz-checksum-mode": "ENABLED"},
}


class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def getcode(self) -> int:
        return self.status


class _FakeOpener:
    """Answers with `body` instead of reaching the network."""

    def __init__(self, body: bytes = BODY, status: int = 200, error: Exception | None = None):
        self.body = body
        self.status = status
        self.error = error
        self.request = None

    def open(self, request, timeout=None):
        self.request = request
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.body, self.status)


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.out = self.tmp / "bundle.zip"
        self.enterContext(unittest.mock.patch.dict(os.environ, {}, clear=False))
        os.environ.pop(wire.ALLOWED_HOSTS_ENV, None)

    def fetch(self, *, body=BODY, status=200, error=None, mint=None, **kwargs):
        opener = _FakeOpener(body=body, status=status, error=error)
        result = download.download(
            self.out, mint or MINT, opener_factory=lambda: opener, **kwargs
        )
        return result, opener


class SuccessTests(_Case):
    def test_the_bytes_land_and_are_reported(self) -> None:
        result, _ = self.fetch()
        self.assertEqual(self.out.read_bytes(), BODY)
        self.assertEqual(result["sha256"], DIGEST)
        self.assertEqual(result["bytes"], len(BODY))
        self.assertEqual(result["receipt"], "http_2xx")

    def test_the_method_is_get(self) -> None:
        _, opener = self.fetch()
        self.assertEqual(opener.request.get_method(), "GET")

    def test_required_headers_are_sent_verbatim(self) -> None:
        # A presigned URL commits to the headers it was signed with.
        _, opener = self.fetch()
        self.assertEqual(opener.request.get_header("X-amz-checksum-mode"), "ENABLED")

    def test_a_matching_digest_is_recorded_as_verified(self) -> None:
        result, _ = self.fetch(expected_sha256=DIGEST)
        self.assertTrue(result["verified"])

    def test_no_expected_digest_still_works_but_says_so(self) -> None:
        result, _ = self.fetch()
        self.assertFalse(result["verified"])

    def test_no_temporary_file_survives(self) -> None:
        self.fetch()
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["bundle.zip"])


class VerificationTests(_Case):
    def test_the_wrong_bundle_is_not_written(self) -> None:
        # A wrong bundle under the right filename is the one failure here that
        # would otherwise look exactly like success.
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(expected_sha256="b" * 64)
        self.assertEqual(caught.exception.code, "digest_mismatch")
        self.assertFalse(self.out.exists())

    def test_an_expected_digest_that_is_not_a_digest_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.fetch(expected_sha256="nope")

    def test_an_empty_response_is_refused(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(body=b"")
        self.assertEqual(caught.exception.code, "empty_body")

    def test_an_oversized_response_stops_being_read(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(max_bytes=4)
        self.assertEqual(caught.exception.code, "body_too_large")
        self.assertFalse(self.out.exists())


class RefusalTests(_Case):
    def test_plain_http_is_refused(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(mint={"url": "http://store.example.com/key"})
        self.assertEqual(caught.exception.code, "insecure_url")

    def test_credentials_in_the_url_are_refused(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(mint={"url": "https://user:pass@store.example.com/key"})
        self.assertEqual(caught.exception.code, "credentials_in_url")

    def test_a_mint_with_no_url_is_refused(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(mint={"required_headers": {}})
        self.assertEqual(caught.exception.code, "bad_mint")

    def test_the_host_pin_is_enforced_when_set(self) -> None:
        os.environ[wire.ALLOWED_HOSTS_ENV] = "other.example.net"
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch()
        self.assertEqual(caught.exception.code, "host_not_allowed")

    def test_the_host_pin_admits_a_listed_host(self) -> None:
        os.environ[wire.ALLOWED_HOSTS_ENV] = "store.example.com, other.example.net"
        result, _ = self.fetch()
        self.assertTrue(result["ok"])

    def test_a_redirect_is_refused_rather_than_followed(self) -> None:
        # On the way down, following one would accept a bundle from a host the
        # operator never named.
        handler = wire.NoRedirects()
        with self.assertRaises(wire.TransferError) as caught:
            handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example.net/x")
        self.assertEqual(caught.exception.code, "unexpected_redirect")


class FailureTests(_Case):
    def _code(self, status: int) -> str:
        error = urllib.error.HTTPError(MINT["url"], status, "no", {}, None)
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(error=error)
        return caught.exception.code

    def test_403_reads_as_an_expired_presign(self) -> None:
        self.assertEqual(self._code(403), "url_expired_or_forbidden")

    def test_404_is_a_missing_target(self) -> None:
        self.assertEqual(self._code(404), "target_missing")

    def test_500_is_the_store_being_unavailable(self) -> None:
        self.assertEqual(self._code(500), "store_unavailable")

    def test_a_network_failure_is_unreachable(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(error=urllib.error.URLError("dns"))
        self.assertEqual(caught.exception.code, "unreachable")

    def test_a_non_2xx_success_status_is_rejected(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            self.fetch(status=304)
        self.assertEqual(caught.exception.code, "not_accepted")


if __name__ == "__main__":
    unittest.main()
