#!/usr/bin/env python3
"""Run privacy-safe, revision-bound baseline/candidate shadow evaluations."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ALLOWED_RESULT = {"success", "actual_route", "latency_ms", "token_cost_proxy", "invariants"}
FORBIDDEN = {"prompt", "raw_prompt", "raw_response", "response", "log", "logs", "token", "cookie", "credential", "credentials", "customer_data", "tool_output"}


def contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key).casefold() in FORBIDDEN or contains_forbidden(item) for key, item in value.items())
    return any(contains_forbidden(item) for item in value) if isinstance(value, list) else False


def sanitized_result(scenario: Dict[str, Any], value: Any, label: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    if not isinstance(value, dict) or contains_forbidden(value):
        return None, [label + " result is malformed or contains raw data"]
    if set(value) != ALLOWED_RESULT:
        return None, [label + " result has missing or extra fields"]
    required = scenario.get("required_invariants")
    invariants = value.get("invariants")
    if not isinstance(required, list) or not isinstance(invariants, dict) or set(invariants) != set(required) or not all(isinstance(key, str) and isinstance(flag, bool) for key, flag in invariants.items()):
        return None, [label + " invariants must exactly match required boolean invariants"]
    if not isinstance(value.get("success"), bool) or not isinstance(value.get("actual_route"), str):
        return None, [label + " success or route is invalid"]
    if value["actual_route"] not in {scenario.get("expected_route"), "none"}:
        return None, [label + " route is not an allowed route"]
    metrics = {"success": value["success"], "actual_route": value["actual_route"], "latency_ms": value.get("latency_ms"), "token_cost_proxy": value.get("token_cost_proxy"), "invariants": dict(sorted(invariants.items()))}
    for name in ("latency_ms", "token_cost_proxy"):
        number = metrics[name]
        if not isinstance(number, (int, float)) or isinstance(number, bool) or number < 0:
            return None, [label + " " + name + " is invalid"]
    return metrics, []


def evaluate(scenario: Dict[str, Any], baseline: Any, candidate: Any) -> Dict[str, Any]:
    failures: List[str] = []
    if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str) or not isinstance(scenario.get("expected_route"), str) or not isinstance(scenario.get("required_invariants"), list):
        failures.append("scenario is malformed")
    base, errors = sanitized_result(scenario, baseline, "baseline") if not failures else (None, failures)
    candidate_metrics, candidate_errors = sanitized_result(scenario, candidate, "candidate") if not failures else (None, [])
    failures.extend(errors); failures.extend(candidate_errors)
    if base and candidate_metrics:
        if candidate_metrics["actual_route"] != scenario["expected_route"]: failures.append("candidate route does not equal expected route")
        if not all(candidate_metrics["invariants"].values()): failures.append("candidate required invariant failed")
        if base["success"] and not candidate_metrics["success"]: failures.append("candidate task success regressed from baseline")
    return {"scenario_id": scenario.get("id", "invalid") if isinstance(scenario, dict) else "invalid", "passed": not failures, "baseline": base or {"success": False}, "candidate": candidate_metrics or {"success": False}, "failures": sorted(set(failures))}


def revision(root: Path) -> Optional[str]:
    try: result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired): return None
    value = result.stdout.strip()
    if result.returncode or not __import__("re").fullmatch(r"[0-9a-f]{40}", value): return None
    try: dirty = subprocess.run(["git", "status", "--porcelain"], cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired): return None
    return value if dirty.returncode == 0 and not dirty.stdout.strip() else None


def adapter_result(adapter: Sequence[str], root: Path, scenario: Dict[str, Any], timeout: float) -> Any:
    try:
        result = subprocess.run(list(adapter), cwd=str(root), input=json.dumps({"scenario": scenario}, ensure_ascii=False, separators=(",", ":")), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired): return None
    if result.returncode != 0 or len(result.stdout) > 65536: return None
    try: return json.loads(result.stdout)
    except json.JSONDecodeError: return None


def load_corpus(path: Path) -> List[Dict[str, Any]]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return []
    scenarios = value.get("scenarios") if isinstance(value, dict) else None
    return scenarios if isinstance(scenarios, list) and all(isinstance(item, dict) for item in scenarios) else []


def run(corpus: Path, baseline_root: Path, candidate_root: Path, baseline_adapter: Sequence[str], candidate_adapter: Sequence[str], timeout_seconds: float) -> Dict[str, Any]:
    scenarios = load_corpus(corpus); baseline_root = baseline_root.resolve(); candidate_root = candidate_root.resolve()
    baseline_revision, candidate_revision = revision(baseline_root), revision(candidate_root)
    if not scenarios or not baseline_revision or not candidate_revision or baseline_root == candidate_root or baseline_revision == candidate_revision:
        return {"passed": False, "failures": ["roots must be distinct, clean, immutable Git worktrees at distinct bound revisions"], "scenarios": []}
    reports = [evaluate(item, adapter_result(baseline_adapter, baseline_root, item, timeout_seconds), adapter_result(candidate_adapter, candidate_root, item, timeout_seconds)) for item in scenarios]
    return {"passed": all(item["passed"] for item in reports), "baseline_revision": baseline_revision, "candidate_revision": candidate_revision, "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(), "scenarios": reports, "uncertainty": "adapter metrics are reported as supplied; no raw adapter payload is retained"}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--corpus", type=Path, required=True); parser.add_argument("--baseline-root", type=Path, required=True); parser.add_argument("--candidate-root", type=Path, required=True); parser.add_argument("--baseline-adapter", nargs="+", required=True); parser.add_argument("--candidate-adapter", nargs="+", required=True); parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0: parser.error("timeout must be positive")
    report = run(args.corpus, args.baseline_root, args.candidate_root, args.baseline_adapter, args.candidate_adapter, args.timeout_seconds); print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))); return 0 if report["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
