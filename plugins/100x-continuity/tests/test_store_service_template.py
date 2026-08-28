"""The store service the Operator runs, checked as text rather than executed.

It needs `boto3` and `fastmcp`, which this repo does not depend on, so nothing here
imports it. These are the properties whose loss is expensive and silent: a reader would
have to already know they mattered to notice they were gone.
"""

import ast
import pathlib
import re
import unittest
import urllib.parse

TEMPLATE = pathlib.Path(__file__).resolve().parents[1] / "templates" / "store-service"
SERVER = TEMPLATE / "server.py"


class SigningTests(unittest.TestCase):
    """Presigning must be SigV4.

    Left to botocore's default it falls back to SigV2 for some endpoint and region
    combinations. R2 refuses SigV2 with a 401 that reads exactly like a bad credential,
    so the cost of losing this is an operator re-rolling tokens against a signing bug.
    Found against real R2, not theorised.
    """

    def setUp(self):
        self.source = SERVER.read_text(encoding="utf-8")

    def test_the_signature_version_is_pinned(self):
        self.assertIn('signature_version="s3v4"', self.source)

    def test_config_is_imported_from_botocore(self):
        self.assertIn("from botocore.config import Config", self.source)

    def test_every_client_carries_the_config(self):
        """One client today. A second one built without the config signs V2 again."""
        clients = re.findall(r"boto3\.client\((.*?)\)\n", self.source, re.S)
        self.assertTrue(clients, "no boto3 client found — has s3() been renamed?")
        for call in clients:
            self.assertIn("config=Config(", call)


class FailsClosedTests(unittest.TestCase):
    """The access model rests on `principal()` refusing an unnamed caller."""

    def setUp(self):
        self.source = SERVER.read_text(encoding="utf-8")

    def test_the_dev_principal_is_the_only_way_past_it(self):
        self.assertIn("CONTINUITY_DEV_PRINCIPAL", self.source)

    def test_the_env_example_warns_that_it_is_local_only(self):
        example = (TEMPLATE / ".env.example").read_text(encoding="utf-8")
        self.assertIn("CONTINUITY_DEV_PRINCIPAL", example)
        self.assertIn("Never set", example)


def _endpoint_check():
    """Pull `_check_endpoint` out of the template and run it for real.

    The module imports boto3 and fastmcp, which this repo does not depend on, so the
    function is compiled on its own. Worth the trouble: this is a guard against silent
    data misplacement and a text assertion would only prove somebody typed the words.
    """
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    node = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_check_endpoint"
    )

    class Refused(Exception):
        pass

    namespace = {"Refused": Refused, "urllib": urllib}
    exec(compile(ast.Module([node], []), "<template>", "exec"), namespace)  # noqa: S102
    return namespace["_check_endpoint"], Refused


class EndpointTests(unittest.TestCase):
    """An endpoint carrying a path silently misfiles every object.

    boto3 treats it as a prefix and `put_object` returns 200 either way, so a whole
    team's handoffs land where no correctly-configured server looks. Found against real
    R2 after the objects were already stranded.
    """

    def setUp(self):
        self.check, self.Refused = _endpoint_check()

    def test_a_bare_host_is_accepted(self):
        for endpoint in (
            "",
            "https://0a97396.r2.cloudflarestorage.com",
            "https://0a97396.r2.cloudflarestorage.com/",
            "https://s3.us-west-004.backblazeb2.com",
            "https://minio.example.net",
        ):
            with self.subTest(endpoint=endpoint):
                self.check(endpoint)

    def test_a_path_is_refused_rather_than_stripped(self):
        with self.assertRaises(self.Refused) as caught:
            self.check("https://0a97396.r2.cloudflarestorage.com/ost-dev-bucket")
        message = str(caught.exception)
        self.assertIn("ost-dev-bucket", message)
        self.assertIn("CONTINUITY_BUCKET", message)

    def test_every_documented_endpoint_passes_its_own_guard(self):
        """The four vendors in `.env.example` must not be refused by this."""
        example = (TEMPLATE / ".env.example").read_text(encoding="utf-8")
        endpoints = re.findall(r"^#\s*CONTINUITY_S3_ENDPOINT=(\S+)", example, re.M)
        self.assertGreaterEqual(len(endpoints), 3)
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.check(endpoint)


class ResolveTests(unittest.TestCase):
    """A row is written at mint time, before any bytes exist."""

    def test_the_object_is_checked_before_a_url_is_handed_out(self):
        source = SERVER.read_text(encoding="utf-8")
        resolve = source[source.index("def resolve_publication"):]
        resolve = resolve[: resolve.index("@mcp.tool")]
        self.assertIn("head_object", resolve)
        self.assertLess(
            resolve.index("head_object"),
            resolve.index("generate_presigned_url"),
            "the URL is minted before anything checks the object is there",
        )


if __name__ == "__main__":
    unittest.main()
