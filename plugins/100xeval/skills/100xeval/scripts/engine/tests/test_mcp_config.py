import os
import unittest
from unittest import mock

from engine.harnesses import claude_code
from engine.models import Case, ToolCall

SERVERS = {
    "Acme": {"type": "http", "url": "https://mcp.example.com/acme/mcp"},
    "Acme-Feedback": {"type": "http", "url": "https://mcp.example.com/acme-feedback/mcp"},
}


class TestCanonicalNaming(unittest.TestCase):
    def test_strips_account_prefix(self):
        self.assertEqual(
            claude_code.canonical_tool_name("mcp__claude_ai_Acme__run_query"),
            "mcp__Acme__run_query",
        )

    def test_plugin_scoped_unchanged(self):
        self.assertEqual(
            claude_code.canonical_tool_name("mcp__Acme__run_query"),
            "mcp__Acme__run_query",
        )

    def test_non_mcp_unchanged(self):
        self.assertEqual(claude_code.canonical_tool_name("Read"), "Read")

    def test_both_naming_schemes_match_after_canon(self):
        a = claude_code.canonical_tool_name("mcp__claude_ai_Acme__run_query")
        b = claude_code.canonical_tool_name("mcp__Acme__run_query")
        self.assertEqual(a, b)


class TestExpandAliases(unittest.TestCase):
    def test_expands_both_directions(self):
        out = claude_code.expand_tool_aliases(["mcp__claude_ai_Acme__q", "Read"])
        self.assertIn("mcp__claude_ai_Acme__q", out)
        self.assertIn("mcp__Acme__q", out)
        self.assertIn("Read", out)

    def test_plugin_scoped_gets_account_alias(self):
        out = claude_code.expand_tool_aliases(["mcp__Acme__q"])
        self.assertIn("mcp__Acme__q", out)
        self.assertIn("mcp__claude_ai_Acme__q", out)

    def test_dedupe(self):
        out = claude_code.expand_tool_aliases(["Read", "Read"])
        self.assertEqual(out.count("Read"), 1)


class TestStrictConfig(unittest.TestCase):
    def test_none_without_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(claude_code.build_strict_mcp_config(SERVERS))

    def test_default_token_applied_to_all(self):
        # Emits the ${VAR} reference (Claude expands it), never the token value.
        with mock.patch.dict(os.environ, {"EVAL_MCP_BEARER": "tok123"}, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertIsNotNone(cfg)
        for name in SERVERS:
            hdr = cfg["mcpServers"][name]["headers"]["Authorization"]
            self.assertEqual(hdr, "Bearer ${EVAL_MCP_BEARER}")

    def test_per_server_token_overrides(self):
        env = {"EVAL_MCP_BEARER": "default", "EVAL_MCP_BEARER_ACME": "special"}
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertEqual(cfg["mcpServers"]["Acme"]["headers"]["Authorization"], "Bearer ${EVAL_MCP_BEARER_ACME}")
        self.assertEqual(cfg["mcpServers"]["Acme-Feedback"]["headers"]["Authorization"], "Bearer ${EVAL_MCP_BEARER}")

    def test_no_token_value_ever_written(self):
        with mock.patch.dict(os.environ, {"EVAL_MCP_BEARER": "SECRET_TOKEN_VALUE"}, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertNotIn("SECRET_TOKEN_VALUE", str(cfg))  # only the ${VAR} ref is emitted

    def test_url_and_type_preserved(self):
        with mock.patch.dict(os.environ, {"EVAL_MCP_BEARER": "t"}, clear=True):
            cfg = claude_code.build_strict_mcp_config(SERVERS)
        self.assertEqual(cfg["mcpServers"]["Acme"]["url"], SERVERS["Acme"]["url"])
        self.assertEqual(cfg["mcpServers"]["Acme"]["type"], "http")


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
            with mock.patch.dict(os.environ, {"EVAL_MCP_BEARER": "T"}, clear=True):
                cfg = claude_code.load_case_mcp_config(case)
            self.assertEqual(cfg["mcpServers"]["Acme"]["headers"]["Authorization"], "Bearer ${EVAL_MCP_BEARER}")

    def test_preexisting_auth_header_not_overwritten(self):
        import tempfile
        cfg_text = '{"mcpServers": {"S": {"type":"http","url":"https://x/mcp","headers":{"Authorization":"Bearer ${MY_VAR}"}}}}'
        with tempfile.TemporaryDirectory() as d:
            case = self._case_with_config(d, cfg_text)
            with mock.patch.dict(os.environ, {"EVAL_MCP_BEARER": "ENV"}, clear=True):
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


class TestPreflightSkipsInTokenMode(unittest.TestCase):
    def test_token_mode_skips_account_check(self):
        # A case whose plugin declares Acme; token present → preflight must NOT abort
        # even though we pass an empty `claude mcp list` (which would otherwise abort).
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            plugdir = os.path.join(d, "p")
            os.makedirs(plugdir)
            with open(os.path.join(plugdir, ".mcp.json"), "w") as fh:
                fh.write('{"mcpServers": {"Acme": {"type":"http","url":"https://x/mcp"}}}')
            case = Case(name="c", prompt="p", path=d, plugins=["p"])
            with mock.patch.dict(os.environ, {"EVAL_MCP_BEARER": "tok"}, clear=True):
                claude_code.verify_mcp_auth(case, list_output="")  # no abort despite empty list


if __name__ == "__main__":
    unittest.main()
