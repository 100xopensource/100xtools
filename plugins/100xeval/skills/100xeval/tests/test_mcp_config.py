import os
import unittest
from unittest import mock

from engine.harnesses import claude_code
from engine.models import Case, ToolCall

SERVERS = {
    "Acme": {"type": "http", "url": "https://mcp.example.com/acme/mcp"},
    "Acme-Feedback": {"type": "http", "url": "https://mcp.example.com/acme-feedback/mcp"},
}


class TestStrictConfig(unittest.TestCase):
    def test_none_only_when_nothing_is_declared(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(claude_code.build_strict_mcp_config({}))

    def test_credential_less_server_is_still_declared(self):
        """There is no unauthenticated fallback to drop back to, so the server is passed
        through without an Authorization header rather than the config becoming None."""
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertEqual(set(cfg["mcpServers"]), set(SERVERS))
        for entry in cfg["mcpServers"].values():
            self.assertNotIn("Authorization", entry.get("headers", {}))

    def test_each_server_gets_its_own_var(self):
        # Emits the ${VAR} reference (Claude expands it), never the key value. Each server
        # names its own variable — there is no shared key that reaches every server.
        env = {"MCP_ACME_API_KEY": "a", "MCP_ACME_FEEDBACK_API_KEY": "b"}
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["mcpServers"]["Acme"]["headers"]["Authorization"],
                         "Bearer ${MCP_ACME_API_KEY}")
        self.assertEqual(cfg["mcpServers"]["Acme-Feedback"]["headers"]["Authorization"],
                         "Bearer ${MCP_ACME_FEEDBACK_API_KEY}")

    def test_unset_server_gets_no_auth_header(self):
        # One server keyed, the other not. The unkeyed one is still included (strict mode
        # must not hide a declared server) but carries no Authorization header — one
        # vendor's key is never handed to another vendor's server.
        with mock.patch.dict(os.environ, {"MCP_ACME_API_KEY": "a"}, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertIn("Acme-Feedback", cfg["mcpServers"])
        self.assertNotIn("Authorization",
                         cfg["mcpServers"]["Acme-Feedback"].get("headers", {}))

    def test_no_token_value_ever_written(self):
        with mock.patch.dict(os.environ, {"MCP_ACME_API_KEY": "SECRET_TOKEN_VALUE"}, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertNotIn("SECRET_TOKEN_VALUE", str(cfg))  # only the ${VAR} ref is emitted

    def test_url_and_type_preserved(self):
        with mock.patch.dict(os.environ, {"MCP_ACME_API_KEY": "t"}, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertEqual(cfg["mcpServers"]["Acme"]["url"], SERVERS["Acme"]["url"])
        self.assertEqual(cfg["mcpServers"]["Acme"]["type"], "http")

    def test_oauth_server_emits_var_ref_with_no_value(self):
        # The variable is not in os.environ yet — it is added to the child's environment at
        # spawn time — but the config must still name it, or the OAuth path writes a server
        # with no Authorization header at all.
        env = {
            "MCP_ACME_CLIENT_ID": "cid",
            "MCP_ACME_CLIENT_SECRET": "csecret",
            "MCP_ACME_TOKEN_URL": "https://idp.example.com/token",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertEqual(cfg["mcpServers"]["Acme"]["headers"]["Authorization"],
                         "Bearer ${MCP_ACME_API_KEY}")
        self.assertNotIn("csecret", str(cfg))  # the secret never reaches the config

    def test_server_name_normalized_into_var_name(self):
        # Non-alphanumerics become underscores and the name uppercases, so `Acme-Feedback`
        # reads MCP_ACME_FEEDBACK_API_KEY. Asserted directly: a silent change here would
        # look like a missing key rather than a renamed variable.
        self.assertEqual(claude_code._bearer_var_name("Acme-Feedback"),
                         "MCP_ACME_FEEDBACK_API_KEY")


class TestCaseMcpConfig(unittest.TestCase):
    def _case_with_config(self, d, config_text):
        import os as _os
        _os.makedirs(_os.path.join(d, "sub"), exist_ok=True)
        with open(_os.path.join(d, "sub", "mcp.json"), "w") as fh:
            fh.write(config_text)
        return Case(name="c", prompt="p", path=d, mcp_config="sub/mcp.json")

    def test_loads_case_config_and_injects_var_ref(self):
        import tempfile
        cfg_text = '{"mcpServers": {"Acme": {"type":"http","url":"https://x/mcp"}}}'
        with tempfile.TemporaryDirectory() as d:
            case = self._case_with_config(d, cfg_text)
            with mock.patch.dict(os.environ, {"MCP_ACME_API_KEY": "T"}, clear=True):
                cfg = claude_code.load_case_mcp_config(case)
            self.assertEqual(cfg["mcpServers"]["Acme"]["headers"]["Authorization"], "Bearer ${MCP_ACME_API_KEY}")

    def test_preexisting_auth_header_not_overwritten(self):
        import tempfile
        cfg_text = '{"mcpServers": {"S": {"type":"http","url":"https://x/mcp","headers":{"Authorization":"Bearer ${MY_VAR}"}}}}'
        with tempfile.TemporaryDirectory() as d:
            case = self._case_with_config(d, cfg_text)
            with mock.patch.dict(os.environ, {"MCP_S_API_KEY": "ENV"}, clear=True):
                cfg = claude_code.load_case_mcp_config(case)
            self.assertEqual(cfg["mcpServers"]["S"]["headers"]["Authorization"], "Bearer ${MY_VAR}")

    def test_resolve_prefers_case_config_over_autobuild(self):
        import tempfile
        cfg_text = '{"mcpServers": {"Only": {"type":"http","url":"https://only/mcp"}}}'
        with tempfile.TemporaryDirectory() as d:
            case = self._case_with_config(d, cfg_text)
            with mock.patch.dict(os.environ, {}, clear=True):
                cfg = claude_code.resolve_strict_mcp_config(case)   # no token, but case config wins
            self.assertEqual(list(cfg["mcpServers"]), ["Only"])

    def test_no_config_no_token_is_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(claude_code.resolve_strict_mcp_config(Case(name="c", prompt="p")))


class TestChildEnvOverlay(unittest.TestCase):
    """The minted token reaches the child process, and nothing else is lost doing it."""

    def setUp(self):
        from engine import mcp_oauth
        mcp_oauth.reset_cache()

    def _case_with_plugin_mcp(self, d, servers='{"Acme": {"type":"http","url":"https://x/mcp"}}'):
        plugdir = os.path.join(d, "p")
        os.makedirs(plugdir, exist_ok=True)
        with open(os.path.join(plugdir, ".mcp.json"), "w") as fh:
            fh.write('{"mcpServers": %s}' % servers)
        return Case(name="c", prompt="p", path=d, plugins=["p"])

    def test_overlay_carries_minted_token(self):
        import io
        import json as _json
        import tempfile
        from unittest.mock import MagicMock

        body = io.BytesIO(_json.dumps({"access_token": "tok-xyz"}).encode())
        cm = MagicMock()
        cm.__enter__.return_value = body
        cm.__exit__.return_value = False
        env = {
            "MCP_ACME_CLIENT_ID": "cid",
            "MCP_ACME_CLIENT_SECRET": "csecret",
            "MCP_ACME_TOKEN_URL": "https://idp.example.com/token",
            "PATH": "/usr/bin",
        }
        with tempfile.TemporaryDirectory() as d:
            case = self._case_with_plugin_mcp(d)
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch("urllib.request.urlopen", return_value=cm):
                    overlay = claude_code.mcp_env_overlay(case)
                    child = {**os.environ, **overlay}
        self.assertEqual(overlay, {"MCP_ACME_API_KEY": "tok-xyz"})
        # env= replaces the child's whole environment, so the overlay must extend os.environ
        # rather than stand in for it — without PATH the `claude` binary is not found.
        self.assertEqual(child["PATH"], "/usr/bin")

    def test_overlay_empty_for_static_key(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            case = self._case_with_plugin_mcp(d)
            with mock.patch.dict(os.environ, {"MCP_ACME_API_KEY": "static"}, clear=True):
                with mock.patch("urllib.request.urlopen") as urlopen:
                    self.assertEqual(claude_code.mcp_env_overlay(case), {})
                urlopen.assert_not_called()

    def test_overlay_empty_without_mcp(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(claude_code.mcp_env_overlay(Case(name="c", prompt="p")), {})


if __name__ == "__main__":
    unittest.main()
