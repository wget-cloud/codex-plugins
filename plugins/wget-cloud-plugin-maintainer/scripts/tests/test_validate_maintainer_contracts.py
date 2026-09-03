"""Negative semantic fixtures for maintainer role and approval contracts."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "validate_maintainer_contracts.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("maintainer_contracts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MaintainerContractSemanticTest(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_rejects_missing_gate_and_protected_test_semantics(self):
        path = self.write("contract.md", "# Contract\nGate 1\n")
        self.assertTrue(any("protected" in item.lower() for item in self.validator.validate_contract(path)))

    def test_rejects_role_order_and_delivery_before_review(self):
        path = self.write("contract.md", "test-maker → implementor → delivery → reviewer → qa")
        self.assertTrue(any("order" in item.lower() for item in self.validator.validate_contract(path)))

    def test_rejects_raw_secret_and_unbounded_write_authority(self):
        path = self.write("contract.md", "token=secret\nwrite any repository path")
        errors = self.validator.validate_contract(path)
        self.assertTrue(any("secret" in item.lower() for item in errors))
        self.assertTrue(any("allow" in item.lower() or "scope" in item.lower() for item in errors))


if __name__ == "__main__":
    unittest.main()
