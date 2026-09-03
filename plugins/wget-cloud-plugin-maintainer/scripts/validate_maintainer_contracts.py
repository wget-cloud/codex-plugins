#!/usr/bin/env python3
"""Semantic, stdlib-only validation for the maintainer approval contract."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PLUGIN_ROOT / "skills" / "wgc-plugin-maintenance"
REQUIRED_EVENTS = {
    "SessionStart": "session-start", "UserPromptSubmit": "prompt-submit", "SubagentStart": "subagent-start",
    "SubagentStop": "subagent-stop", "PreToolUse": "pre-tool", "PostToolUse": "post-tool",
    "Stop": "stop", "SessionEnd": "session-end",
}
ROLE_ORDER = ("auditor", "architect", "test-maker", "implementor", "reviewer", "qa")


def validate_contract(path: Path) -> List[str]:
    """Validate a role/approval contract without accepting prose-only safety claims."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"cannot read contract: {error}"]
    lower = text.casefold()
    errors: List[str] = []
    if "gate 1" not in lower or "gate 2" not in lower:
        errors.append("contract must define both Gate 1 and Gate 2")
    if "protected" not in lower or "test" not in lower:
        errors.append("contract must preserve protected tests")
    positions = [lower.find(role) for role in ROLE_ORDER]
    present = [position for position in positions if position >= 0]
    if present and (len(present) != len(ROLE_ORDER) or positions != sorted(positions)):
        errors.append("role order must be auditor, architect, test-maker, implementor, reviewer, qa before delivery")
    delivery = lower.find("delivery")
    if delivery >= 0 and (lower.find("reviewer") < 0 or lower.find("qa") < 0 or delivery < lower.find("reviewer") or delivery < lower.find("qa")):
        errors.append("delivery order requires reviewer and qa first")
    if re.search(r"(?:token|secret|password|credential)\s*=", lower):
        errors.append("contract contains raw secret-like material")
    if re.search(r"(?:write|edit|modify)\s+(?:any|all|arbitrary)\s+(?:repository\s+)?path", lower):
        errors.append("write authority must be limited to an explicit approved scope")
    return errors


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise OSError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_repository(root: Path = PLUGIN_ROOT) -> List[str]:
    errors: List[str] = []
    try:
        hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8")).get("hooks")
    except (OSError, json.JSONDecodeError):
        return ["hooks.json is unreadable"]
    if not isinstance(hooks, dict) or set(hooks) != set(REQUIRED_EVENTS):
        errors.append("hooks.json must link every required lifecycle event")
    else:
        for event, action in REQUIRED_EVENTS.items():
            groups = hooks.get(event)
            handlers = groups[0].get("hooks", []) if isinstance(groups, list) and groups and isinstance(groups[0], dict) else []
            if len(handlers) != 1 or not isinstance(handlers[0], dict):
                errors.append(f"{event} must have one synchronous handler")
                continue
            handler = handlers[0]
            if handler.get("type") != "command" or "async" in handler or action not in str(handler.get("command", "")) or action not in str(handler.get("commandWindows", "")):
                errors.append(f"{event} hook linkage is invalid")
        for event in ("PreToolUse", "PostToolUse"):
            matcher = str(hooks[event][0].get("matcher", ""))
            if not all(tool in matcher for tool in ("Bash", "apply_patch", "Edit", "Write")):
                errors.append(f"{event} matcher does not cover all scoped mutation tools")
    try:
        hook_module = load_module(root / "hooks" / "maintainer_hooks.py", "maintainer_hook_contract")
        if set(getattr(hook_module, "HANDLERS", {})) != set(REQUIRED_EVENTS.values()):
            errors.append("hook handler map is not synchronized with hooks.json")
        roles = getattr(hook_module, "ROLE_VERDICTS", {})
        for role, verdicts in roles.items():
            role_text = (root / "skills" / "wgc-plugin-maintenance" / "references" / "agents" / f"{role}.md").read_text(encoding="utf-8")
            if not all(verdict in role_text for verdict in verdicts):
                errors.append(f"role/verdict contract mismatch for {role}")
        if not all(hasattr(hook_module, name) for name in ("PROPOSAL_MARKER", "DELIVERY_MARKER", "EVIDENCE_MARKER", "verify_release_evidence")):
            errors.append("hook marker/evidence contract is incomplete")
    except (OSError, ImportError, AttributeError):
        errors.append("maintainer hook contract is unreadable")
    metadata = root / "skills" / "wgc-plugin-maintenance" / "agents" / "openai.yaml"
    try:
        if "allow_implicit_invocation: false" not in metadata.read_text(encoding="utf-8"):
            errors.append("maintainer activation must remain explicit-only")
    except OSError:
        errors.append("skill activation metadata is unreadable")
    approval = root / "skills" / "wgc-plugin-maintenance" / "references" / "approval-and-delivery.md"
    evaluation = root / "skills" / "wgc-plugin-maintenance" / "references" / "evaluation-and-release.md"
    contract_text = "\n".join(path.read_text(encoding="utf-8") for path in (approval, evaluation))
    if "candidate-ci-verified" not in contract_text or "smoke-passed" not in contract_text or "GitHub Release" not in contract_text:
        errors.append("release evidence order is undocumented")
    if "evidence.schema.json" not in contract_text:
        errors.append("external evidence schema is not linked")
    try:
        schema = json.loads((root / "skills" / "wgc-plugin-maintenance" / "references" / "evidence.schema.json").read_text(encoding="utf-8"))
        if schema.get("type") != "object" or "commit" not in schema.get("required", []):
            errors.append("external evidence schema is invalid")
    except (OSError, json.JSONDecodeError):
        errors.append("external evidence schema is unreadable")
    try:
        corpus_validator = load_module(root / "scripts" / "validate_eval_corpus.py", "maintainer_corpus_validator")
        if corpus_validator.validate_corpus(SKILL_ROOT / "references" / "evals" / "corpus.json"):
            errors.append("sanitized evaluation corpus is invalid")
    except (OSError, ImportError, AttributeError):
        errors.append("sanitized evaluation corpus linkage is invalid")
    makefile = root.parents[1] / "Makefile"
    try:
        make_text = makefile.read_text(encoding="utf-8")
        if "validate_maintainer_contracts.py" not in make_text or "verify_external_evidence.py" not in make_text:
            errors.append("Makefile does not integrate maintainer semantic validation")
    except OSError:
        errors.append("Makefile is unreadable")
    return errors


def validate(repository_root: Path) -> List[str]:
    """Adapter used by the marketplace validator for an arbitrary repository root."""
    return validate_repository(repository_root / "plugins" / "wget-cloud-plugin-maintainer")


def main(argv: List[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) == 2 else PLUGIN_ROOT
    errors = validate_repository(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Validated maintainer semantic contracts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
