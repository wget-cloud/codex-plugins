#!/usr/bin/env python3
"""Fail-closed verification for sanitized CI, runtime, and smoke evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


HEX40 = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_KEYS = {
    "prompt", "raw_prompt", "raw_log", "log", "logs", "output", "tool_output", "token", "cookie",
    "credential", "credentials", "customer_data", "secret",
}
RUNTIME_FAILURES = {"cache-only", "absent", "version-mismatch"}
EVIDENCE_KEYS = {"commit", "workflow", "status", "observed_at", "source", "subject_task_id", "runtime", "smoke"}
RUNTIME_KEYS = {"plugin", "version", "status", "enabled"}
SMOKE_KEYS = {"task_id", "commit", "status", "source", "observed_at"}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def has_forbidden_data(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key).casefold() in FORBIDDEN_KEYS or has_forbidden_data(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_forbidden_data(item) for item in value)
    return False


def verify(evidence: Any, *, commit: str, now: Optional[int] = None, max_age_seconds: int = 3600) -> Dict[str, Any]:
    """Validate a sanitized evidence object and return identifiers, never raw evidence."""
    failures: List[str] = []
    now = int(time.time()) if now is None else now
    if not isinstance(evidence, dict) or has_forbidden_data(evidence):
        return {"accepted": False, "failures": ["evidence is malformed or contains forbidden privacy data"]}
    if set(evidence) - EVIDENCE_KEYS:
        failures.append("evidence contains fields outside the strict schema")
    if not isinstance(commit, str) or not HEX40.fullmatch(commit):
        failures.append("delivery commit is invalid")
    if not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
        failures.append("maximum evidence age is invalid")
    required = {"commit", "workflow", "status", "observed_at", "source"}
    if not required.issubset(evidence):
        failures.append("CI evidence is missing required fields")
    if evidence.get("commit") != commit:
        failures.append("CI evidence commit does not match delivery subject")
    if evidence.get("workflow") != "validate" or evidence.get("status") != "success" or evidence.get("source") != "github":
        failures.append("CI evidence is not a successful GitHub validate run")
    observed_at = evidence.get("observed_at")
    if not isinstance(observed_at, int) or isinstance(observed_at, bool) or observed_at > now or now - observed_at > max_age_seconds:
        failures.append("CI evidence is stale or has an invalid timestamp")
    runtime = evidence.get("runtime")
    if runtime is not None:
        if not isinstance(runtime, dict):
            failures.append("runtime inventory is malformed")
        elif set(runtime) != RUNTIME_KEYS:
            failures.append("runtime inventory does not match the strict schema")
        elif runtime.get("status") in RUNTIME_FAILURES:
            failures.append("runtime inventory is cache-only, absent, or version-mismatched")
        elif runtime.get("status") != "installed" or runtime.get("enabled") is not True:
            failures.append("runtime inventory is not installed and enabled")
        elif not isinstance(runtime.get("plugin"), str) or not isinstance(runtime.get("version"), str):
            failures.append("runtime inventory lacks plugin/version identity")
    smoke = evidence.get("smoke")
    if smoke is not None:
        if not isinstance(smoke, dict):
            failures.append("smoke evidence is malformed")
        elif set(smoke) != SMOKE_KEYS:
            failures.append("smoke evidence does not match the strict schema")
        elif smoke.get("status") != "success" or smoke.get("source") != "codex":
            failures.append("smoke evidence is not a successful Codex task")
        elif not isinstance(smoke.get("task_id"), str) or not smoke["task_id"]:
            failures.append("smoke evidence lacks a task identifier")
        elif not isinstance(evidence.get("subject_task_id"), str) or not evidence["subject_task_id"]:
            failures.append("smoke evidence lacks the originating task identifier")
        elif smoke.get("task_id") == evidence.get("subject_task_id"):
            failures.append("smoke must run in a distinct Codex task")
        elif smoke.get("commit") != commit:
            failures.append("smoke evidence commit does not match delivery subject")
        elif not isinstance(smoke.get("observed_at"), int) or smoke["observed_at"] > now or now - smoke["observed_at"] > max_age_seconds:
            failures.append("smoke evidence is stale or has an invalid timestamp")
    accepted = not failures
    if not accepted:
        return {"accepted": False, "failures": sorted(set(failures))}
    identifiers = {
        "ci": canonical_hash({key: evidence[key] for key in sorted(required)}),
        "runtime": canonical_hash(runtime) if runtime is not None else None,
        "smoke": canonical_hash(smoke) if smoke is not None else None,
    }
    return {"accepted": True, "evidence_sha256": canonical_hash(identifiers), "identifiers": identifiers, "failures": []}


def main(argv: List[str]) -> int:
    if len(argv) not in {3, 4}:
        print("usage: verify_external_evidence.py <evidence.json> <commit> [max-age-seconds]", file=sys.stderr)
        return 2
    try:
        evidence = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        max_age = int(argv[3]) if len(argv) == 4 else 3600
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: cannot read sanitized evidence: {error}", file=sys.stderr)
        return 2
    result = verify(evidence, commit=argv[2], max_age_seconds=max_age)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
