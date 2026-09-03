#!/usr/bin/env python3
"""Fail-closed verifier for bounded, sanitized external delivery evidence."""
from __future__ import annotations
import base64, hashlib, json, re, sys, time
from pathlib import Path
from typing import Any, Dict, List, Optional

HEX40 = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
FORBIDDEN = {"prompt","raw_prompt","raw_response","response","log","logs","output","tool_output","token","cookie","credential","credentials","customer_data","secret","authorization","url","uri"}
ROOT = {"commit","workflow","status","observed_at","source","runtime","smoke","subject_task_id"}
CI = {"commit","workflow","status","observed_at","source"}
RUNTIME = {"plugin","version","status","enabled"}
SMOKE = {"task_id","plugin","version","commit","status","source","observed_at"}

def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def sensitive(value: Any) -> bool:
    if isinstance(value, dict): return any(str(key).casefold() in FORBIDDEN or sensitive(item) for key, item in value.items())
    if isinstance(value, list): return True
    return isinstance(value, str) and (len(value) > 240 or "://" in value or "@" in value)

def timestamp(value: Any, now: int, age: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= now and now - value <= age

def verify(evidence: Any, *, commit: str, now: Optional[int] = None, max_age_seconds: int = 3600) -> Dict[str, Any]:
    errors: List[str] = []; now = int(time.time()) if now is None else now
    if not isinstance(evidence, dict) or sensitive(evidence): return {"accepted": False, "errors": ["evidence contains forbidden or unbounded data"]}
    if not isinstance(commit, str) or not HEX40.fullmatch(commit): errors.append("delivery commit is invalid")
    if not isinstance(now, int) or isinstance(now, bool) or not isinstance(max_age_seconds, int) or isinstance(max_age_seconds, bool) or max_age_seconds <= 0: errors.append("verification clock is invalid")
    if not set(evidence).issubset(ROOT) or not CI.issubset(evidence): errors.append("root evidence schema is invalid")
    if evidence.get("commit") != commit or evidence.get("workflow") != "validate" or evidence.get("status") != "success" or evidence.get("source") != "github" or not timestamp(evidence.get("observed_at"), now, max_age_seconds): errors.append("CI evidence is not a fresh successful bound validate run")
    runtime = evidence.get("runtime")
    if runtime is not None:
        if not isinstance(runtime, dict) or set(runtime) != RUNTIME: errors.append("runtime evidence schema is invalid")
        elif not isinstance(runtime.get("plugin"), str) or not IDENTIFIER.fullmatch(runtime["plugin"]) or not isinstance(runtime.get("version"), str) or not SEMVER.fullmatch(runtime["version"]) or runtime.get("status") != "installed" or runtime.get("enabled") is not True: errors.append("runtime is not an exact installed and enabled plugin")
    smoke = evidence.get("smoke")
    if smoke is not None:
        subject = evidence.get("subject_task_id")
        if runtime is None: errors.append("smoke requires installed runtime evidence")
        if not isinstance(smoke, dict) or set(smoke) != SMOKE: errors.append("smoke evidence schema is invalid")
        elif not isinstance(subject, str) or not IDENTIFIER.fullmatch(subject) or not isinstance(smoke.get("task_id"), str) or not IDENTIFIER.fullmatch(smoke["task_id"]) or smoke["task_id"] == subject or smoke.get("plugin") != runtime.get("plugin") or smoke.get("version") != runtime.get("version") or smoke.get("commit") != commit or smoke.get("status") != "success" or smoke.get("source") != "codex" or not timestamp(smoke.get("observed_at"), now, max_age_seconds): errors.append("smoke is not a fresh distinct task for the exact installed version and commit")
    elif "subject_task_id" in evidence: errors.append("subject task identity is allowed only with smoke evidence")
    if errors: return {"accepted": False, "errors": sorted(set(errors))}
    ci = {key: evidence[key] for key in sorted(CI)}; identifiers = {"ci": canonical_hash(ci), "runtime": canonical_hash(runtime) if runtime else None, "smoke": canonical_hash(smoke) if smoke else None}
    return {"accepted": True, "errors": [], "evidence_sha256": canonical_hash(identifiers), "identifiers": identifiers}

def main(argv: List[str]) -> int:
    if len(argv) == 4 and argv[1] == "--encoded":
        encoded, commit = argv[2:]
        if not 1 <= len(encoded) <= 8192 or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded) or not HEX40.fullmatch(commit): print("usage: verify_external_evidence.py --encoded <bounded-payload> <commit>", file=sys.stderr); return 2
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            evidence = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError): print("ERROR: encoded evidence is invalid", file=sys.stderr); return 2
        result=verify(evidence, commit=commit); print(json.dumps(result, sort_keys=True, separators=(",", ":"))); return 0 if result["accepted"] else 1
    if len(argv) not in {3,4}: print("usage: verify_external_evidence.py <evidence.json> <commit> [max-age-seconds]", file=sys.stderr); return 2
    try: evidence=json.loads(Path(argv[1]).read_text(encoding="utf-8")); age=int(argv[3]) if len(argv)==4 else 3600
    except (OSError, ValueError, json.JSONDecodeError) as error: print("ERROR: " + str(error), file=sys.stderr); return 2
    result=verify(evidence, commit=argv[2], max_age_seconds=age); print(json.dumps(result, sort_keys=True, separators=(",", ":"))); return 0 if result["accepted"] else 1
if __name__ == "__main__": raise SystemExit(main(sys.argv))
