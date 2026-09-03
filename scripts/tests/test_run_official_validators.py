"""Contracts for an offline, discovery-safe official-validator wrapper."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run_official_validators.py"


def load_wrapper():
    spec = importlib.util.spec_from_file_location("official_validators", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfficialValidatorWrapperTest(unittest.TestCase):
    def setUp(self):
        self.wrapper = load_wrapper()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_discovers_only_allowlisted_validator_and_locked_checksum(self):
        validator = self.root / "quick_validate.py"
        validator.write_text("print('ok')\n", encoding="utf-8")
        result = self.wrapper.discover(self.root, allowlist={"quick_validate.py"}, checksums={"quick_validate.py": "0" * 64})
        self.assertFalse(result["accepted"])
        self.assertIn("checksum", " ".join(result["errors"]).lower())

    def test_rejects_unapproved_discovery_and_never_uses_network(self):
        (self.root / "unexpected.py").write_text("print('network')\n", encoding="utf-8")
        result = self.wrapper.discover(self.root, allowlist=set(), checksums={})
        self.assertFalse(result["accepted"])
        self.assertTrue(result["offline"])


if __name__ == "__main__":
    unittest.main()
