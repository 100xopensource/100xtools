"""OAuth client-credentials minting. Offline: `urlopen` is patched in every test."""
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from engine import mcp_oauth
from engine.harnesses.base import Abort

CREDS = {
    "MCP_ACME_CLIENT_ID": "cid",
    "MCP_ACME_CLIENT_SECRET": "csecret",
    "MCP_ACME_TOKEN_URL": "https://idp.example.com/oauth2/token",
}


def _response(payload: dict):
    """A urlopen context manager returning `payload` as JSON."""
    body = io.BytesIO(json.dumps(payload).encode())
    cm = mock.MagicMock()
    cm.__enter__.return_value = body
    cm.__exit__.return_value = False
    return cm


class TestCredentialDiscovery(unittest.TestCase):
    def setUp(self):
        mcp_oauth.reset_cache()

    def test_none_when_nothing_declared(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(mcp_oauth.credentials_for("Acme"))

    def test_partial_config_names_the_missing_var(self):
        env = {"MCP_ACME_CLIENT_ID": "cid"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(Abort) as ctx:
                mcp_oauth.credentials_for("Acme")
        msg = str(ctx.exception)
        self.assertIn("MCP_ACME_CLIENT_SECRET", msg)
        # TOKEN_URL is optional — it is discovered when absent, so it is not "missing".
        self.assertNotIn("MCP_ACME_TOKEN_URL", msg)

    def test_http_token_url_refused(self):
        env = dict(CREDS, MCP_ACME_TOKEN_URL="http://idp.example.com/token")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(Abort) as ctx:
                mcp_oauth.credentials_for("Acme")
        self.assertIn("https://", str(ctx.exception))

    def test_static_key_wins_over_client_credentials(self):
        # Deterministic and network-free beats a mint nobody asked for.
        env = dict(CREDS, MCP_ACME_API_KEY="static")
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(mcp_oauth.mintable("Acme"))
            with mock.patch("urllib.request.urlopen") as urlopen:
                self.assertEqual(mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"}), {})
            urlopen.assert_not_called()

    def test_server_name_normalised(self):
        env = {
            "MCP_ACME_FEEDBACK_CLIENT_ID": "cid",
            "MCP_ACME_FEEDBACK_CLIENT_SECRET": "csecret",
            "MCP_ACME_FEEDBACK_TOKEN_URL": "https://idp.example.com/token",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(mcp_oauth.mintable("Acme-Feedback"))
        self.assertEqual(mcp_oauth.api_key_var("Acme-Feedback"), "MCP_ACME_FEEDBACK_API_KEY")


class TestMint(unittest.TestCase):
    def setUp(self):
        mcp_oauth.reset_cache()

    def test_sends_basic_auth_and_no_scope_by_default(self):
        # Both defaults are set by what real authorization servers accept: connectors
        # observed in practice want Basic, and reject an explicit scope rather than
        # ignoring it.
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "tok-abc"})) as urlopen:
                overlay = mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        self.assertEqual(overlay, {"MCP_ACME_API_KEY": "tok-abc"})
        req = urlopen.call_args[0][0]
        body = req.data.decode()
        self.assertEqual(req.method, "POST")
        self.assertIn("grant_type=client_credentials", body)
        self.assertTrue(req.headers.get("Authorization", "").startswith("Basic "))
        self.assertNotIn("scope", body)
        self.assertNotIn("client_secret", body)  # in the header, never the body

    def test_auth_style_post_moves_credentials_into_the_body(self):
        env = dict(CREDS, MCP_ACME_AUTH_STYLE="post")
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "t"})) as urlopen:
                mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        req = urlopen.call_args[0][0]
        self.assertIsNone(req.headers.get("Authorization"))
        self.assertIn("client_secret=csecret", req.data.decode())

    def test_bad_auth_style_rejected(self):
        with mock.patch.dict(os.environ, dict(CREDS, MCP_ACME_AUTH_STYLE="hmac"), clear=True):
            with self.assertRaises(Abort):
                mcp_oauth.credentials_for("Acme")

    def test_scope_included_only_when_explicitly_set(self):
        with mock.patch.dict(os.environ, dict(CREDS, MCP_ACME_SCOPE="mcp:read"), clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "t"})) as urlopen:
                mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        self.assertIn("scope=mcp%3Aread", urlopen.call_args[0][0].data.decode())

    def test_http_error_reports_status_without_body(self):
        # An error body can carry a token, so it must never reach the message.
        err = urllib.error.HTTPError(
            "https://idp.example.com/token", 401, "Unauthorized", {},
            io.BytesIO(b'{"error":"invalid_client","leaked":"tok-SECRET"}'))
        self.addCleanup(err.close)
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaises(Abort) as ctx:
                    mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        msg = str(ctx.exception)
        self.assertIn("401", msg)
        self.assertNotIn("tok-SECRET", msg)          # the raw body never reaches the message
        self.assertIn("invalid_client", msg)         # the RFC's own error field does
        self.assertIn("AUTH_STYLE=post", msg)        # and the most likely remedy

    def test_unreachable_endpoint_aborts(self):
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            side_effect=urllib.error.URLError("no route")):
                with self.assertRaises(Abort) as ctx:
                    mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        self.assertIn("could not reach", str(ctx.exception))

    def test_missing_access_token_aborts(self):
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"token_type": "Bearer"})):
                with self.assertRaises(Abort) as ctx:
                    mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        self.assertIn("no access_token", str(ctx.exception))

    def test_non_json_response_aborts(self):
        body = io.BytesIO(b"<html>gateway error</html>")
        cm = mock.MagicMock()
        cm.__enter__.return_value = body
        cm.__exit__.return_value = False
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=cm):
                with self.assertRaises(Abort) as ctx:
                    mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        self.assertIn("did not return JSON", str(ctx.exception))

    def test_one_exchange_per_process(self):
        # Two calls (the run, then the judge) must not hit the IdP twice.
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "t"})) as urlopen:
                first = mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
                second = mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        self.assertEqual(first, second)
        self.assertEqual(urlopen.call_count, 1)

    def test_nearly_expired_token_is_re_minted(self):
        # A token that lapses mid-suite fails only the later cases, which reads as a flaky
        # skill. Re-minting inside the margin is what stops that.
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            side_effect=[_response({"access_token": "t1", "expires_in": 60}),
                                         _response({"access_token": "t2", "expires_in": 3600})]):
                first = mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
                second = mcp_oauth.env_for_servers({"Acme": "https://x.test/mcp"})
        self.assertEqual(first["MCP_ACME_API_KEY"], "t1")
        self.assertEqual(second["MCP_ACME_API_KEY"], "t2")

    def test_cache_is_shared_across_servers_on_one_endpoint(self):
        # Two servers, one authorization server: minting twice is a wasted round trip.
        env = dict(CREDS,
                   MCP_OTHER_CLIENT_ID="cid", MCP_OTHER_CLIENT_SECRET="csecret",
                   MCP_OTHER_TOKEN_URL=CREDS["MCP_ACME_TOKEN_URL"])
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "shared"})) as urlopen:
                overlay = mcp_oauth.env_for_servers({"Acme": "https://a.test/mcp",
                                                     "Other": "https://b.test/mcp"})
        self.assertEqual(overlay, {"MCP_ACME_API_KEY": "shared",
                                   "MCP_OTHER_API_KEY": "shared"})
        self.assertEqual(urlopen.call_count, 1)


class TestDiscovery(unittest.TestCase):
    """RFC 9728 protected-resource metadata, then RFC 8414 authorization-server metadata."""

    def setUp(self):
        mcp_oauth.reset_cache()

    NO_URL = {"MCP_ACME_CLIENT_ID": "cid", "MCP_ACME_CLIENT_SECRET": "csecret"}

    def test_walks_protected_resource_then_authorization_server(self):
        calls = []

        def fake(req, timeout=None):
            url = req if isinstance(req, str) else req.full_url
            calls.append(url)
            if "oauth-protected-resource" in url:
                return _response({"authorization_servers": ["https://idp.example.com"]})
            if "oauth-authorization-server" in url:
                return _response({"token_endpoint": "https://idp.example.com/t"})
            return _response({"access_token": "discovered"})

        with mock.patch.dict(os.environ, self.NO_URL, clear=True):
            with mock.patch("urllib.request.urlopen", side_effect=fake):
                overlay = mcp_oauth.env_for_servers({"Acme": "https://mcp.example.com/acme/mcp"})
        self.assertEqual(overlay, {"MCP_ACME_API_KEY": "discovered"})
        self.assertIn("https://mcp.example.com/.well-known/oauth-protected-resource/acme/mcp",
                      calls)

    def test_explicit_token_url_skips_discovery(self):
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "t"})) as urlopen:
                mcp_oauth.env_for_servers({"Acme": "https://mcp.example.com/acme/mcp"})
        self.assertEqual(urlopen.call_count, 1)  # the mint only — no metadata hops

    def test_unknown_url_asks_for_token_url(self):
        with mock.patch.dict(os.environ, self.NO_URL, clear=True):
            with self.assertRaises(Abort) as ctx:
                mcp_oauth.env_for_servers({"Acme": ""})
        self.assertIn("MCP_ACME_TOKEN_URL", str(ctx.exception))

    def test_metadata_without_authorization_servers_is_readable(self):
        with mock.patch.dict(os.environ, self.NO_URL, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=_response({})):
                with self.assertRaises(Abort) as ctx:
                    mcp_oauth.env_for_servers({"Acme": "https://mcp.example.com/acme/mcp"})
        self.assertIn("no authorization_servers", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
