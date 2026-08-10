import os
import tempfile
import unittest

from engine.harnesses import claude_code
from engine.harnesses.base import Abort
from engine.models import Case

# Verbatim shape of real `claude mcp list` output (spaces in names, mixed statuses).
MCP_LIST = """\
Checking MCP server health…

claude.ai Acme-Feedback: https://mcp.example.com/acme-feedback/mcp - ✔ Connected
claude.ai Mailer: https://mcp.example.net/mailer/mcp - ! Needs authentication
claude.ai Acme: https://mcp.example.com/acme/mcp - ✔ Connected
plugin:demo-observability:observability: https://mcp.example.com/acme/observability/mcp (HTTP) - ! Needs authentication
claude.ai Docs: https://mcp.example.net/docs/mcp - ⏸ Pending approval
"""

ACME_MCP_JSON = """\
{"mcpServers": {
  "Acme": {"type": "http", "url": "https://mcp.example.com/acme/mcp"},
  "Acme-Feedback": {"type": "http", "url": "https://mcp.example.com/acme-feedback/mcp"}
}}
"""


class TestParseMcpList(unittest.TestCase):
    def test_transport_annotated_line_keeps_the_whole_url(self):
        """A plugin-scoped registration prints " (HTTP)" before the status. The URL must
        survive intact — a truncated one silently fails to match the declared server."""
        line = ("plugin:demo:observability: https://mcp.example.com/acme/agent-hub/mcp "
                "(HTTP) - ! Needs authentication")
        entries = claude_code.parse_mcp_list(line)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["url"], "https://mcp.example.com/acme/agent-hub/mcp")
        self.assertFalse(entries[0]["connected"])

    def test_hyphenated_url_is_not_split_at_a_hyphen(self):
        line = "claude.ai Acme: https://mcp.example.com/acme-agent-hub-tools/mcp - ✔ Connected"
        entries = claude_code.parse_mcp_list(line)
        self.assertEqual(entries[0]["url"], "https://mcp.example.com/acme-agent-hub-tools/mcp")
        self.assertTrue(entries[0]["connected"])

    def test_parses_all_entries(self):
        entries = claude_code.parse_mcp_list(MCP_LIST)
        self.assertEqual(len(entries), 5)
        by_url = {e["url"]: e for e in entries}
        self.assertTrue(by_url["https://mcp.example.com/acme/mcp"]["connected"])
        self.assertFalse(by_url["https://mcp.example.net/docs/mcp"]["connected"])  # pending
        self.assertFalse(by_url["https://mcp.example.net/mailer/mcp"]["connected"])  # needs auth

    def test_url_appearing_both_ways(self):
        # observability URL only appears not-connected here → not in connected set
        entries = claude_code.parse_mcp_list(MCP_LIST)
        connected = {e["url"] for e in entries if e["connected"]}
        self.assertNotIn(
            "https://mcp.example.com/acme/observability/mcp", connected
        )


class TestVerifyMcpAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin = os.path.join(self.tmp.name, "acme")
        os.makedirs(self.plugin)
        with open(os.path.join(self.plugin, ".mcp.json"), "w") as fh:
            fh.write(ACME_MCP_JSON)
        self.case = Case(name="c", prompt="p", path=self.tmp.name, plugins=["acme"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_connected_passes(self):
        # Both Acme + Acme-Feedback are Connected in the fixture → no abort.
        claude_code.verify_mcp_auth(self.case, list_output=MCP_LIST)

    def test_needs_auth_aborts_with_names(self):
        broken = MCP_LIST.replace(
            "https://mcp.example.com/acme/mcp - ✔ Connected",
            "https://mcp.example.com/acme/mcp - ! Needs authentication",
        )
        with self.assertRaises(Abort) as ctx:
            claude_code.verify_mcp_auth(self.case, list_output=broken)
        self.assertIn("Acme", str(ctx.exception))
        self.assertIn("mcp login", str(ctx.exception))

    def test_missing_server_aborts(self):
        with self.assertRaises(Abort) as ctx:
            claude_code.verify_mcp_auth(self.case, list_output="Checking MCP server health…\n")
        self.assertIn("not registered", str(ctx.exception))

    def test_no_mcp_json_is_noop(self):
        plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(plain)
        case = Case(name="c2", prompt="p", path=self.tmp.name, plugins=["plain"])
        claude_code.verify_mcp_auth(case, list_output="")  # no .mcp.json → nothing to verify

    def test_no_plugins_is_noop(self):
        claude_code.verify_mcp_auth(Case(name="c3", prompt="p"), list_output="")


if __name__ == "__main__":
    unittest.main()
