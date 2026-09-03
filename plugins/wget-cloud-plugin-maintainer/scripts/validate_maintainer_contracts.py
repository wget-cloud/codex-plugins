#!/usr/bin/env python3
"""Semantic, stdlib-only validation for the WGC maintainer bundle."""
from __future__ import annotations
import json, sys
from pathlib import Path
from typing import Any, List

EVENTS = {"SessionStart","UserPromptSubmit","SubagentStart","SubagentStop","PreToolUse","PostToolUse","Stop","SessionEnd"}
ROLES = ("auditor","architect","test-maker","implementor","reviewer","qa")
VERDICTS = {"auditor":"audited","architect":"proposed","test-maker":"baseline_ready","implementor":"implemented","reviewer":"approved","qa":"pass"}

def validate(root: Path) -> List[str]:
    plugin = root / "plugins/wget-cloud-plugin-maintainer"; errors: List[str] = []
    hook = plugin / "hooks/maintainer_hooks.py"; config = plugin / "hooks/hooks.json"; skill = plugin / "skills/wgc-plugin-maintenance"; index = skill / "references/agents/index.md"
    for path in (hook, config, skill / "SKILL.md", skill / "agents/openai.yaml", index, skill / "references/evidence.schema.json", plugin / "scripts/validate_eval_corpus.py", plugin / "scripts/run_shadow_eval.py", plugin / "scripts/verify_external_evidence.py"):
        if not path.is_file(): errors.append(str(path.relative_to(root)) + ": required maintainer contract component is missing")
    if errors: return errors
    try: hooks=json.loads(config.read_text(encoding="utf-8")); events=hooks["hooks"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError): return [str(config.relative_to(root)) + ": invalid hook configuration"]
    if not isinstance(events, dict) or set(events) != EVENTS: errors.append("maintainer hooks must declare exactly the synchronous lifecycle event set")
    for event, groups in events.items() if isinstance(events, dict) else ():
        if not isinstance(groups, list) or not groups: errors.append("maintainer hook event has no handler: " + event); continue
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(handlers, list) or not handlers: errors.append("maintainer hook group is malformed: " + event); continue
            for handler in handlers:
                if not isinstance(handler, dict) or handler.get("type") != "command" or not isinstance(handler.get("command"), str) or not isinstance(handler.get("commandWindows"), str) or "maintainer_hooks.py" not in handler.get("command", "") or "maintainer_hooks.py" not in handler.get("commandWindows", "") or "async" in handler: errors.append("maintainer hook handler must be synchronous POSIX and Windows command metadata")
    source=hook.read_text(encoding="utf-8")
    for token in ("def explicit_activation", "$wgc-plugin-maintenance", "def dependency_closure", "def validate_protected_tests", "WGC_MAINTENANCE_PROPOSAL:", "WGC_MAINTAINER_RESULT:"):
        if token not in source: errors.append("maintainer hook lacks required executable contract: " + token)
    metadata=(skill / "agents/openai.yaml").read_text(encoding="utf-8")
    if "allow_implicit_invocation: false" not in metadata or "$wgc-plugin-maintenance" not in metadata: errors.append("maintainer skill must stay explicit-only in UI metadata")
    registry=index.read_text(encoding="utf-8")
    if "auditor → architect → test-maker → implementor → reviewer → QA" not in (skill / "references/workflow.md").read_text(encoding="utf-8"): errors.append("workflow must declare independent maintainer role order")
    for role in ROLES:
        path=skill / "references/agents" / (role + ".md")
        if not path.is_file() or "Verdict:" not in path.read_text(encoding="utf-8") or VERDICTS[role] not in path.read_text(encoding="utf-8"): errors.append("role contract is missing its verdict: " + role)
        if "| " + role.replace("-", "_") + " |" not in registry and "(" + role + ".md)" not in registry: errors.append("role registry is missing prefix/route: " + role)
    approval=(skill / "references/approval-and-delivery.md").read_text(encoding="utf-8")
    if "depends_on" not in approval or "WGC_MAINTAINER_PROTECTED_TESTS" not in registry or "candidate-ci-verified" not in approval: errors.append("approval/delivery references lack dependency, protected-test, or release linkage")
    return errors

def main(argv: List[str]) -> int:
    root=Path(argv[1]).resolve() if len(argv)>1 else Path(__file__).resolve().parents[3]
    errors=validate(root)
    if errors: print("\n".join("ERROR: "+item for item in errors), file=sys.stderr); return 1
    print("Maintainer semantic contracts valid."); return 0
if __name__ == "__main__": raise SystemExit(main(sys.argv))
