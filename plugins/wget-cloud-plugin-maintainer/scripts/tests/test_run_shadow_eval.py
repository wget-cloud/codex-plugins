"""Failing-first contracts for the sanitized shadow-evaluation runner."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run_shadow_eval.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("shadow_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShadowEvalContractTest(unittest.TestCase):
    def setUp(self):
        self.runner = load_runner()
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def scenario(self, **overrides):
        value = {"id": "safe", "expected_route": "wgc-plugin-maintenance", "required_invariants": ["no-write-before-approval"]}
        value.update(overrides)
        return value

    def result(self, **overrides):
        value = {
            "success": True,
            "actual_route": "wgc-plugin-maintenance",
            "invariants": {"no-write-before-approval": True},
        }
        value.update(overrides)
        return value

    def test_pass_records_sanitized_baseline_and_candidate_metrics(self):
        report = self.runner.evaluate(self.scenario(), baseline=self.result(latency_ms=3), candidate=self.result(latency_ms=2))
        self.assertTrue(report["passed"])
        self.assertEqual({"success", "latency_ms", "token_cost_proxy"}, set(report["baseline"]))

    def test_regression_and_safety_violations_fail_even_when_candidate_succeeds(self):
        report = self.runner.evaluate(self.scenario(), baseline=self.result(), candidate=self.result(success=False, approval_violation=True))
        self.assertFalse(report["passed"])
        self.assertIn("approval", " ".join(report["failures"]).lower())

    def test_malformed_results_timeout_and_privacy_payloads_fail_closed(self):
        for candidate in ({}, {"timed_out": True}, {"success": True, "raw_prompt": "customer secret"}):
            with self.subTest(candidate=candidate):
                report = self.runner.evaluate(self.scenario(), baseline=self.result(), candidate=candidate)
                self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
