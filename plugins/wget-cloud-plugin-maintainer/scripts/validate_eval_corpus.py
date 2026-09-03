#!/usr/bin/env python3
"""Strict validator for the sanitized, explicit-only maintenance eval corpus."""
from __future__ import annotations
import json, sys
from pathlib import Path
from typing import Any, List

PLATFORMS = {"macos", "ubuntu", "windows-contract"}
FORBIDDEN = {"prompt", "raw_prompt", "raw_response", "response", "log", "logs", "token", "cookie", "credential", "credentials", "customer_data", "tool_output"}

def has_forbidden(value: Any) -> bool:
    if isinstance(value, dict): return any(str(key).casefold() in FORBIDDEN or has_forbidden(item) for key, item in value.items())
    return any(has_forbidden(item) for item in value) if isinstance(value, list) else False

def validate_corpus(path: Path) -> List[str]:
    try: corpus = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: return ["cannot read corpus: " + str(error)]
    if not isinstance(corpus, dict) or set(corpus) != {"schema_version", "scenarios"} or corpus.get("schema_version") != 1 or has_forbidden(corpus): return ["corpus root schema or privacy policy is invalid"]
    scenarios = corpus.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios: return ["scenarios must be a non-empty array"]
    errors: List[str] = []; seen = set()
    required = {"id", "intent", "expected_route", "required_invariants", "platforms", "routing"}
    for index, scenario in enumerate(scenarios):
        prefix = "scenarios[" + str(index) + "]"
        if not isinstance(scenario, dict) or set(scenario) != required or has_forbidden(scenario): errors.append(prefix + " schema or privacy policy is invalid"); continue
        identifier = scenario.get("id"); invariants = scenario.get("required_invariants"); platforms = scenario.get("platforms")
        if not isinstance(identifier, str) or not identifier or identifier in seen: errors.append(prefix + ".id must be unique")
        seen.add(identifier)
        if not isinstance(scenario.get("intent"), str) or not scenario["intent"].strip() or len(scenario["intent"]) > 240: errors.append(prefix + ".intent is invalid")
        if scenario.get("expected_route") not in {"wgc-plugin-maintenance", "none"}: errors.append(prefix + ".expected_route is invalid")
        if not isinstance(invariants, list) or not invariants or len(invariants) != len(set(invariants)) or not all(isinstance(item, str) and item for item in invariants): errors.append(prefix + ".required_invariants is invalid")
        if not isinstance(platforms, list) or not platforms or len(platforms) != len(set(platforms)) or any(item not in PLATFORMS for item in platforms): errors.append(prefix + ".platforms is invalid")
        if scenario.get("routing") != {"allow_implicit_invocation": False}: errors.append(prefix + ".routing must remain explicit-only")
    return errors

def main(argv: List[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "skills/wgc-plugin-maintenance/references/evals/corpus.json"
    errors = validate_corpus(path)
    if errors:
        print("\n".join("ERROR: " + item for item in errors), file=sys.stderr); return 1
    print("Validated sanitized maintainer eval corpus."); return 0

if __name__ == "__main__": raise SystemExit(main(sys.argv))
