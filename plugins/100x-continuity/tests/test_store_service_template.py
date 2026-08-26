"""The store service the Operator runs, checked as text rather than executed.

It needs `boto3` and `fastmcp`, which this repo does not depend on, so nothing here
imports it. These are the properties whose loss is expensive and silent: a reader would
have to already know they mattered to notice they were gone.
"""

import pathlib
import re
import unittest

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


if __name__ == "__main__":
    unittest.main()
