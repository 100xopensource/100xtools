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
        self.assertIn("MCP_ACME_TOKEN_URL", msg)

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
                self.assertEqual(mcp_oauth.env_for_servers(["Acme"]), {})
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

    def test_posts_client_credentials_grant(self):
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "tok-abc"})) as urlopen:
                overlay = mcp_oauth.env_for_servers(["Acme"])
        self.assertEqual(overlay, {"MCP_ACME_API_KEY": "tok-abc"})
        req = urlopen.call_args[0][0]
        body = req.data.decode()
        self.assertEqual(req.method, "POST")
        self.assertIn("grant_type=client_credentials", body)
        self.assertIn("client_id=cid", body)
        self.assertIn("client_secret=csecret", body)
        self.assertNotIn("scope=", body)  # omitted when unset, not sent empty

    def test_scope_included_when_set(self):
        with mock.patch.dict(os.environ, dict(CREDS, MCP_ACME_SCOPE="mcp:read"), clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "t"})) as urlopen:
                mcp_oauth.env_for_servers(["Acme"])
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
                    mcp_oauth.env_for_servers(["Acme"])
        msg = str(ctx.exception)
        self.assertIn("401", msg)
        self.assertNotIn("tok-SECRET", msg)
        self.assertNotIn("invalid_client", msg)

    def test_unreachable_endpoint_aborts(self):
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            side_effect=urllib.error.URLError("no route")):
                with self.assertRaises(Abort) as ctx:
                    mcp_oauth.env_for_servers(["Acme"])
        self.assertIn("could not reach", str(ctx.exception))

    def test_missing_access_token_aborts(self):
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"token_type": "Bearer"})):
                with self.assertRaises(Abort) as ctx:
                    mcp_oauth.env_for_servers(["Acme"])
        self.assertIn("no access_token", str(ctx.exception))

    def test_non_json_response_aborts(self):
        body = io.BytesIO(b"<html>gateway error</html>")
        cm = mock.MagicMock()
        cm.__enter__.return_value = body
        cm.__exit__.return_value = False
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=cm):
                with self.assertRaises(Abort) as ctx:
                    mcp_oauth.env_for_servers(["Acme"])
        self.assertIn("did not return JSON", str(ctx.exception))

    def test_one_exchange_per_process(self):
        # Two calls (the run, then the judge) must not hit the IdP twice.
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "t"})) as urlopen:
                first = mcp_oauth.env_for_servers(["Acme"])
                second = mcp_oauth.env_for_servers(["Acme"])
        self.assertEqual(first, second)
        self.assertEqual(urlopen.call_count, 1)

    def test_short_expiry_warns(self):
        with mock.patch.dict(os.environ, CREDS, clear=True):
            with mock.patch("urllib.request.urlopen",
                            return_value=_response({"access_token": "t", "expires_in": 60})):
                with mock.patch("builtins.print") as printed:
                    mcp_oauth.env_for_servers(["Acme"])
        self.assertTrue(any("expires in 60s" in str(c) for c in printed.call_args_list))


if __name__ == "__main__":
    unittest.main()
