import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "validate_eval_corpus.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("maintainer_eval_validator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvalCorpusTest(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "corpus.json"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def valid(self):
        return {
            "schema_version": 1,
            "scenarios": [
                {
                    "id": "approval",
                    "intent": "Audit a plugin defect.",
                    "expected_route": "wgc-plugin-maintenance",
                    "required_invariants": [
                        "audit-before-write",
                        "item-level-change-approval",
                        "no-write-before-approval",
                        "delivery-approval-invalidated",
                        "silent-outside-codex-plugins",
                    ],
                    "platforms": ["macos", "ubuntu", "windows-contract"],
                }
            ],
        }

    def test_valid_corpus_passes(self):
        self.write(self.valid())
        self.assertEqual([], self.validator.validate_corpus(self.path))

    def test_duplicate_ids_fail(self):
        value = self.valid()
        value["scenarios"].append(dict(value["scenarios"][0]))
        self.write(value)
        self.assertTrue(any("unique" in error for error in self.validator.validate_corpus(self.path)))

    def test_missing_safety_invariant_fails(self):
        value = self.valid()
        value["scenarios"][0]["required_invariants"].remove("delivery-approval-invalidated")
        self.write(value)
        self.assertTrue(any("missing safety" in error for error in self.validator.validate_corpus(self.path)))

    def test_raw_prompt_field_fails_schema(self):
        value = self.valid()
        value["scenarios"][0]["raw_prompt"] = "secret"
        self.write(value)
        self.assertTrue(self.validator.validate_corpus(self.path))

    def test_explicit_only_routing_metadata_is_required_and_implicit_routes_are_rejected(self):
        value = self.valid()
        value["scenarios"][0]["routing"] = {"allow_implicit_invocation": False}
        self.write(value)
        self.assertEqual([], self.validator.validate_corpus(self.path))
        value["scenarios"][0]["routing"] = {"allow_implicit_invocation": True}
        self.write(value)
        self.assertTrue(any("explicit-only" in error for error in self.validator.validate_corpus(self.path)))


if __name__ == "__main__":
    unittest.main()
