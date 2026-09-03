#!/usr/bin/env python3
"""Run sanitized baseline/candidate maintenance evaluations in isolated roots."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


FORBIDDEN_RESULT_KEYS = {
    "prompt", "raw_prompt", "raw_response", "response", "log", "logs", "token", "cookie",
    "credential", "credentials", "customer_data", "tool_output",
}
VIOLATIONS = ("approval_violation", "security_violation", "privacy_violation", "path_isolation_violation")


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key).casefold() in FORBIDDEN_RESULT_KEYS or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def sanitized_result(
    scenario: Dict[str, Any], value: Any, label: str
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Validate adapter output and retain metrics only."""
    if not isinstance(value, dict):
        return None, [f"{label} result is malformed"]
    if _contains_forbidden(value):
        return None, [f"{label} result contains a forbidden privacy payload"]
    if not isinstance(value.get("success"), bool):
        return None, [f"{label} result requires boolean success"]
    if value.get("timed_out") is True:
        return None, [f"{label} result timed out"]
    expected_route = scenario.get("expected_route")
    if value.get("actual_route") != expected_route:
        return None, [f"{label} actual_route does not match the expected route"]
    required = scenario.get("required_invariants")
    invariants = value.get("invariants")
    if (
        not isinstance(required, list)
        or not isinstance(invariants, dict)
        or set(invariants) != set(required)
        or any(invariants.get(name) is not True for name in required)
    ):
        return None, [f"{label} invariants do not exactly satisfy the scenario contract"]
    latency = value.get("latency_ms", 0)
    cost = value.get("token_cost_proxy", 0)
    if not isinstance(latency, (int, float)) or isinstance(latency, bool) or latency < 0:
        return None, [f"{label} latency_ms is invalid"]
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
        return None, [f"{label} token_cost_proxy is invalid"]
    metrics = {"success": value["success"], "latency_ms": latency, "token_cost_proxy": cost}
    return metrics, []


def evaluate(scenario: Dict[str, Any], baseline: Any, candidate: Any) -> Dict[str, Any]:
    """Compare two sanitized results and return metrics-only deterministic evidence."""
    failures: List[str] = []
    if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str) or not scenario["id"]:
        failures.append("scenario is malformed")
    if not isinstance(scenario.get("expected_route"), str):
        failures.append("scenario expected_route is malformed")
    if not isinstance(scenario.get("required_invariants"), list) or not all(isinstance(item, str) and item for item in scenario["required_invariants"]):
        failures.append("scenario required_invariants are malformed")
    baseline_metrics, baseline_errors = sanitized_result(scenario, baseline, "baseline")
    candidate_metrics, candidate_errors = sanitized_result(scenario, candidate, "candidate")
    failures.extend(baseline_errors)
    failures.extend(candidate_errors)
    if candidate_metrics is not None:
        for violation in VIOLATIONS:
            if candidate.get(violation) is True:
                failures.append(f"candidate {violation.replace('_', ' ')}")
    if baseline_metrics is not None and candidate_metrics is not None:
        if baseline_metrics["success"] and not candidate_metrics["success"]:
            failures.append("candidate task success regressed from baseline")
    return {
        "scenario_id": scenario.get("id") if isinstance(scenario, dict) else "invalid",
        "passed": not failures,
        "baseline": baseline_metrics or {"success": False, "latency_ms": 0, "token_cost_proxy": 0},
        "candidate": candidate_metrics or {"success": False, "latency_ms": 0, "token_cost_proxy": 0},
        "failures": sorted(set(failures)),
    }


def revision(root: Path) -> Optional[str]:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and len(value) == 40 and all(char in "0123456789abcdef" for char in value) else None


def adapter_result(adapter: Sequence[str], root: Path, scenario: Dict[str, Any], timeout_seconds: float) -> Any:
    payload = json.dumps({"scenario": scenario}, ensure_ascii=False, separators=(",", ":"))
    try:
        result = subprocess.run(list(adapter), cwd=str(root), input=payload, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {"timed_out": True}
    except OSError:
        return {}
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def load_corpus(path: Path) -> List[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scenarios = value.get("scenarios") if isinstance(value, dict) else None
    return scenarios if isinstance(scenarios, list) and all(isinstance(item, dict) for item in scenarios) else []


def run(corpus: Path, baseline_root: Path, candidate_root: Path, baseline_adapter: Sequence[str], candidate_adapter: Sequence[str], timeout_seconds: float) -> Dict[str, Any]:
    scenarios = load_corpus(corpus)
    baseline_revision = revision(baseline_root)
    candidate_revision = revision(candidate_root)
    if not scenarios or baseline_revision is None or candidate_revision is None or baseline_root.resolve() == candidate_root.resolve():
        return {"passed": False, "failures": ["missing or invalid isolated revision-bound evaluation inputs"], "scenarios": []}
    reports = [evaluate(scenario, adapter_result(baseline_adapter, baseline_root, scenario, timeout_seconds), adapter_result(candidate_adapter, candidate_root, scenario, timeout_seconds)) for scenario in scenarios]
    return {
        "passed": all(report["passed"] for report in reports),
        "baseline_revision": baseline_revision,
        "candidate_revision": candidate_revision,
        "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(),
        "scenarios": reports,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare sanitized maintainer baseline/candidate adapters.")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--baseline-adapter", nargs="+", required=True)
    parser.add_argument("--candidate-adapter", nargs="+", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    report = run(args.corpus.resolve(), args.baseline_root.resolve(), args.candidate_root.resolve(), args.baseline_adapter, args.candidate_adapter, args.timeout_seconds)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
