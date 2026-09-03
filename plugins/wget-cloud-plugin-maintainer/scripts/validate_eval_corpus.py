#!/usr/bin/env python3
"""Validate the maintainer's sanitized behavioral-evaluation corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = (
    PLUGIN_ROOT
    / "skills"
    / "wgc-plugin-maintenance"
    / "references"
    / "evals"
    / "corpus.json"
)
PLATFORMS = {"macos", "ubuntu", "windows-contract"}
REQUIRED_INVARIANTS = {
    "audit-before-write",
    "item-level-change-approval",
    "no-write-before-approval",
    "delivery-approval-invalidated",
    "silent-outside-codex-plugins",
}
FORBIDDEN_KEYS = {"prompt", "raw_prompt", "logs", "token", "cookie", "credentials", "customer_data"}


def validate_corpus(path: Path) -> List[str]:
    errors: List[str] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"cannot read corpus: {error}"]
    if not isinstance(value, dict) or set(value) != {"schema_version", "scenarios"}:
        return ["corpus must contain exactly schema_version and scenarios"]
    if value.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return errors + ["scenarios must be a non-empty array"]
    seen = set()
    observed_invariants = set()
    for index, scenario in enumerate(scenarios):
        prefix = f"scenarios[{index}]"
        if not isinstance(scenario, dict):
            errors.append(f"{prefix} must be an object")
            continue
        required_fields = {"id", "intent", "expected_route", "required_invariants", "platforms"}
        allowed_fields = required_fields | {"routing"}
        if not required_fields.issubset(scenario) or set(scenario) - allowed_fields:
            errors.append(f"{prefix} has unexpected or missing fields")
            continue
        if any(key.casefold() in FORBIDDEN_KEYS for key in scenario):
            errors.append(f"{prefix} contains a forbidden raw-data field")
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in seen:
            errors.append(f"{prefix}.id must be a unique string")
        else:
            seen.add(scenario_id)
        intent = scenario.get("intent")
        if not isinstance(intent, str) or not intent.strip() or len(intent) > 240:
            errors.append(f"{prefix}.intent must be a concise sanitized description")
        if scenario.get("expected_route") not in {"wgc-plugin-maintenance", "none"}:
            errors.append(f"{prefix}.expected_route is invalid")
        routing = scenario.get("routing")
        if routing is not None:
            if not isinstance(routing, dict) or set(routing) != {"allow_implicit_invocation"}:
                errors.append(f"{prefix}.routing must contain only allow_implicit_invocation")
            elif routing.get("allow_implicit_invocation") is not False:
                errors.append(f"{prefix}.routing must be explicit-only")
        invariants = scenario.get("required_invariants")
        if not isinstance(invariants, list) or not invariants or not all(isinstance(item, str) and item for item in invariants):
            errors.append(f"{prefix}.required_invariants must be non-empty strings")
        else:
            observed_invariants.update(invariants)
        platforms = scenario.get("platforms")
        if not isinstance(platforms, list) or not platforms or any(platform not in PLATFORMS for platform in platforms):
            errors.append(f"{prefix}.platforms contains unsupported values")
    missing = sorted(REQUIRED_INVARIANTS - observed_invariants)
    if missing:
        errors.append("corpus is missing safety invariants: " + ", ".join(missing))
    return errors


def main(argv: List[str]) -> int:
    path = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_CORPUS
    errors = validate_corpus(path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    print(f"Validated {len(data['scenarios'])} sanitized maintainer eval scenario(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
