"""The presigned handoff: what is sent, what is refused, and what counts as a receipt."""

from __future__ import annotations

import io
import unittest
import unittest.mock
import urllib.error

from engine import upload, wire


class _FakeResponse(io.BytesIO):
    def __init__(self, status: int = 200) -> None:
        super().__init__(b"")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def getcode(self) -> int:
        return self.status


class _FakeOpener:
    """Records the request instead of sending it."""

    def __init__(self, status: int = 200, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, timeout=None):
        self.request = request
        self.timeout = timeout
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.status)


MINT = {
    "url": "https://store.example.com/bucket/key?X-Amz-Signature=abc",
    "required_headers": {"Content-Length": "5", "x-amz-checksum-sha256": "Zm9v"},
}


def send(payload=b"bytes", mint=None, status=200, error=None):
    opener = _FakeOpener(status=status, error=error)
    result = upload.upload(payload, mint or MINT, opener_factory=lambda: opener)
    return result, opener


class SuccessTests(unittest.TestCase):
    def test_two_hundred_is_the_receipt(self) -> None:
        # There is no finalize step and nothing to poll. The 2xx is the proof.
        result, _ = send()
        self.assertEqual(result["receipt"], "http_2xx")
        self.assertTrue(result["ok"])

    def test_any_2xx_counts(self) -> None:
        for status in (200, 201, 204):
            with self.subTest(status=status):
                result, _ = send(status=status)
                self.assertEqual(result["status"], status)

    def test_method_is_put(self) -> None:
        _result, opener = send()
        self.assertEqual(opener.request.get_method(), "PUT")

    def test_headers_are_sent_verbatim(self) -> None:
        # A presigned URL commits to the headers it was signed with; adding or
        # "fixing" one invalidates the signature and the store answers 403.
        _result, opener = send()
        self.assertEqual(opener.request.get_header("Content-length"), "5")
        self.assertEqual(opener.request.get_header("X-amz-checksum-sha256"), "Zm9v")

    def test_body_is_sent_unchanged_and_digested(self) -> None:
        result, opener = send(b"exact bytes")
        self.assertEqual(opener.request.data, b"exact bytes")
        self.assertEqual(result["bytes"], 11)
        self.assertEqual(len(result["sha256"]), 64)

    def test_a_file_path_is_read(self) -> None:
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "bundle.jsonl"
            path.write_bytes(b"from disk")
            result, opener = send(path)
            self.assertEqual(opener.request.data, b"from disk")
            self.assertEqual(result["bytes"], 9)


class RefusalTests(unittest.TestCase):
    def assert_code(self, code: str, **kwargs) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            send(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_http_scheme_is_refused(self) -> None:
        self.assert_code("insecure_url", mint={**MINT, "url": "http://store.example.com/k"})

    def test_credentials_in_the_url_are_refused(self) -> None:
        self.assert_code(
            "credentials_in_url", mint={**MINT, "url": "https://u:p@store.example.com/k"}
        )

    def test_empty_body_is_refused(self) -> None:
        self.assert_code("empty_body", payload=b"")

    def test_mint_without_a_url_is_refused(self) -> None:
        self.assert_code("bad_mint", mint={"required_headers": {}})

    def test_mint_that_is_not_an_object_is_refused(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            upload.upload(b"x", ["not", "an", "object"])  # type: ignore[arg-type]
        self.assertEqual(caught.exception.code, "bad_mint")

    def test_headers_that_are_not_an_object_are_refused(self) -> None:
        self.assert_code("bad_mint", mint={**MINT, "required_headers": "Content-Length: 5"})

    def test_unreadable_file_is_refused(self) -> None:
        self.assert_code("body_unreadable", payload="/nonexistent/bundle.jsonl")

    def test_host_allowlist_is_enforced_when_set(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ", {wire.ALLOWED_HOSTS_ENV: "other.example.net"}, clear=False
        ):
            self.assert_code("host_not_allowed")

    def test_host_allowlist_admits_a_listed_host(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ",
            {wire.ALLOWED_HOSTS_ENV: "store.example.com, other.example.net"},
            clear=False,
        ):
            result, _ = send()
            self.assertTrue(result["ok"])


class FailureCodeTests(unittest.TestCase):
    def http_error(self, status: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError(MINT["url"], status, "no", {}, None)  # type: ignore[arg-type]

    def assert_code(self, status: int, code: str) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            send(error=self.http_error(status))
        self.assertEqual(caught.exception.code, code)

    def test_403_reads_as_an_expired_presign(self) -> None:
        # Overwhelmingly an expired URL rather than a permissions change: the
        # remedy is to mint again with the same bytes.
        self.assert_code(403, "url_expired_or_forbidden")

    def test_401_reads_the_same_way(self) -> None:
        self.assert_code(401, "url_expired_or_forbidden")

    def test_404_is_a_missing_target(self) -> None:
        self.assert_code(404, "target_missing")

    def test_413_is_too_large(self) -> None:
        self.assert_code(413, "body_too_large")

    def test_500_is_the_store_being_unavailable(self) -> None:
        self.assert_code(500, "store_unavailable")

    def test_unexpected_status_is_not_accepted(self) -> None:
        self.assert_code(418, "not_accepted")

    def test_network_failure_is_unreachable(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            send(error=urllib.error.URLError("dns"))
        self.assertEqual(caught.exception.code, "unreachable")

    def test_timeout_is_unreachable(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            send(error=TimeoutError("slow"))
        self.assertEqual(caught.exception.code, "unreachable")

    def test_non_2xx_success_status_is_rejected(self) -> None:
        with self.assertRaises(wire.TransferError) as caught:
            send(status=302)
        self.assertEqual(caught.exception.code, "not_accepted")


class RedirectTests(unittest.TestCase):
    def test_a_redirect_is_refused_rather_than_followed(self) -> None:
        # Following it would replay prompts and tool output to a host nobody
        # signed for — the one failure here that leaks rather than loses.
        handler = wire.NoRedirects()
        with self.assertRaises(wire.TransferError) as caught:
            handler.redirect_request(
                None, None, 307, "temp", {}, "https://elsewhere.example.net/k"
            )
        self.assertEqual(caught.exception.code, "unexpected_redirect")


if __name__ == "__main__":
    unittest.main()
