"""Failing-first checks for sanitized external-evidence verification."""

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "verify_external_evidence.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("external_evidence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExternalEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.verifier = load_verifier()

    def evidence(self, **overrides):
        value = {"commit": "a" * 40, "workflow": "validate", "status": "success", "observed_at": 100, "source": "github"}
        value.update(overrides)
        return value

    def test_stale_wrong_commit_and_failed_ci_do_not_satisfy_delivery(self):
        for evidence in (self.evidence(observed_at=1), self.evidence(commit="b" * 40), self.evidence(status="failure")):
            with self.subTest(evidence=evidence):
                result = self.verifier.verify(evidence, commit="a" * 40, now=1000, max_age_seconds=60)
                self.assertFalse(result["accepted"])

    def test_cache_only_evidence_and_smoke_privacy_violations_fail_closed(self):
        for evidence in (self.evidence(source="cache"), self.evidence(smoke={"status": "success", "raw_log": "customer token"})):
            with self.subTest(evidence=evidence):
                result = self.verifier.verify(evidence, commit="a" * 40, now=120, max_age_seconds=60)
                self.assertFalse(result["accepted"])


if __name__ == "__main__":
    unittest.main()
