#!/usr/bin/env python3
"""Stdlib-only, privacy-safe lifecycle guard for plugin maintenance.

The hook is deliberately fail-closed.  It stores only hashes and the minimum
Gate 1 enforcement data; user prompts, proposal prose, logs, and credentials
never enter the session state.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROLE_MARKER = "WGC_MAINTAINER_RESULT: "
PROTECTED_MARKER = "WGC_MAINTAINER_PROTECTED_TESTS: "
PROPOSAL_MARKER = "WGC_MAINTENANCE_PROPOSAL: "
CHANGE_APPROVAL = re.compile(r"^APPROVE_WGC_PLUGIN_CHANGE=([0-9a-f]{16}):([A-Za-z0-9_.-]+(?:,[A-Za-z0-9_.-]+)*)$")
DELIVERY_APPROVAL = re.compile(r"^APPROVE_WGC_PLUGIN_DELIVERY=([0-9a-f]{16})$")
DELIVERY_MARKER = "WGC_MAINTENANCE_DELIVERY: "
ROLES = ("auditor", "architect", "test-maker", "implementor", "reviewer", "qa")
VERDICTS = {
    "auditor": {"audited", "needs_input", "blocked"},
    "architect": {"proposed", "needs_input", "blocked"},
    "test-maker": {"baseline_ready", "needs_input", "blocked"},
    "implementor": {"implemented", "needs_input", "blocked"},
    "reviewer": {"approved", "changes_requested", "needs_input", "blocked"},
    "qa": {"pass", "defects_found", "needs_input", "blocked"},
}
SUCCESS = {"auditor": "audited", "architect": "proposed", "test-maker": "baseline_ready", "implementor": "implemented", "reviewer": "approved", "qa": "pass"}
READ_GIT = {"status", "diff", "log", "show", "branch", "rev-parse", "remote", "ls-files", "ls-tree", "diff-index", "check-ignore"}
READ_COMMANDS = {"pwd", "ls", "rg", "find", "head", "tail", "cat", "wc", "shasum", "sha256sum"}


def read_input() -> Dict[str, Any]:
    try:
        value = json.loads(sys.stdin.read() or "{}")
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def emit(value: Optional[Dict[str, Any]]) -> None:
    if value:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), end="")


def run(args: List[str], cwd: Path) -> Tuple[int, str]:
    try:
        result = subprocess.run(args, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4, check=False)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def git_root(cwd: Path) -> Optional[Path]:
    code, output = run(["git", "rev-parse", "--show-toplevel"], cwd)
    return Path(output.strip()).resolve() if code == 0 and output.strip() else None


def target_root(raw_cwd: Any) -> Optional[Path]:
    try:
        root = git_root(Path(str(raw_cwd or os.getcwd())).resolve())
    except (OSError, RuntimeError):
        return None
    if not root or not ((root / "AGENTS.md").is_file() and (root / ".agents/plugins/marketplace.json").is_file() and (root / "plugins").is_dir()):
        return None
    return root


def git_head(root: Path) -> str:
    code, output = run(["git", "rev-parse", "HEAD"], root)
    output = output.strip()
    return output if code == 0 and re.fullmatch(r"[0-9a-f]{40}", output) else "unborn"


def file_fingerprint(path: Path) -> str:
    try:
        if not path.is_file():
            return "directory" if path.is_dir() else "missing"
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return "unreadable"


def dirty_snapshot(root: Path) -> Dict[str, str]:
    code, output = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], root)
    if code or not output:
        return {}
    result: Dict[str, str] = {}; entries = output.split("\0"); index = 0
    while index < len(entries):
        entry = entries[index]
        if len(entry) >= 4:
            name = entry[3:].replace("\\", "/")
            result[name] = entry[:2] + ":" + file_fingerprint(root / name)
            # With porcelain v1 -z, rename/copy records carry a second NUL
            # path.  The first path is the current destination we must bind.
            if entry[:1] in {"R", "C"} or entry[1:2] in {"R", "C"}: index += 1
        index += 1
    return dict(sorted(result.items()))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def dirty_fingerprint(root: Path) -> str:
    return canonical_hash(dirty_snapshot(root))


def worktree_hash(root: Path) -> str:
    return canonical_hash({"head": git_head(root), "dirty": dirty_snapshot(root)})


def origin_main(root: Path) -> str:
    code, output = run(["git", "rev-parse", "refs/remotes/origin/main"], root)
    output = output.strip()
    return output if code == 0 and re.fullmatch(r"[0-9a-f]{40}", output) else "unavailable"


def index_fingerprint(root: Path) -> str:
    code, output = run(["git", "ls-files", "-s", "-z"], root)
    return hashlib.sha256(output.encode()).hexdigest() if code == 0 else "unavailable"


def delivery_snapshot(root: Path) -> Dict[str, Any]:
    return {"head": git_head(root), "index_sha256": index_fingerprint(root), "worktree": dirty_snapshot(root), "origin_main": origin_main(root)}


def delivery_chain(snapshot: Dict[str, Any], transitions: List[Dict[str, str]]) -> str:
    return canonical_hash({"snapshot": snapshot, "transitions": transitions})


def staged_paths(root: Path) -> List[str]:
    code, output = run(["git", "diff", "--cached", "--name-only", "-z"], root)
    return sorted(path for path in output.split("\0") if path) if code == 0 else []


def commits_since_origin(root: Path) -> List[str]:
    code, output = run(["git", "log", "--format=%s", "refs/remotes/origin/main..HEAD"], root)
    return list(reversed(output.splitlines())) if code == 0 and output else []


def git_branch(root: Path) -> str:
    code, output = run(["git", "branch", "--show-current"], root)
    return output.strip() if code == 0 else ""


def tag_ref(root: Path, tag: str) -> str:
    if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", tag):
        return "unavailable"
    code, output = run(["git", "rev-parse", "refs/tags/" + tag + "^{}"], root)
    output = output.strip()
    return output if code == 0 and re.fullmatch(r"[0-9a-f]{40}", output) else "unavailable"


def freeze_release(approval: Dict[str, Any], reason: str) -> None:
    approval["release_frozen"] = True
    approval["recovery_reason_sha256"] = hashlib.sha256(reason.encode()).hexdigest()


def manifest_version(root: Path, plugin: str) -> Optional[str]:
    try:
        value = json.loads((root / "plugins" / plugin / ".codex-plugin" / "plugin.json").read_text())
        version = value.get("version") if isinstance(value, dict) else None
        return version if isinstance(version, str) and re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?", version) else None
    except (OSError, json.JSONDecodeError): return None


def validate_delivery(value: Any, state: Dict[str, Any], root: Path) -> Optional[str]:
    required = {"proposal_id","worktree_hash","target","commits","versions","plugins","ci_evidence","runtime_evidence"}
    if not isinstance(value, dict) or set(value) != required: return "delivery marker schema is invalid"
    approval = state.get("change_approval") if isinstance(state.get("change_approval"), dict) else None
    if not approval or value.get("proposal_id") != approval.get("proposal_id"): return "delivery proposal is not bound to Gate 1"
    live = worktree_hash(root)
    if value.get("worktree_hash") != live or value.get("target") != "origin/main": return "delivery worktree hash or target is invalid"
    if not isinstance(value.get("ci_evidence"), bool) or not isinstance(value.get("runtime_evidence"), bool): return "delivery preflight booleans are invalid"
    if not value["ci_evidence"] or not value["runtime_evidence"]: return "delivery preflight evidence attestations are required"
    results=state.get("role_results")
    if not isinstance(results,list) or len(results) < len(ROLES): return "delivery requires all role verdicts"
    latest = successful_role_tail(results)
    if latest is None: return "delivery requires ordered successful role provenance"
    for result in latest[-2:]:
        if result.get("input_revision") != live: return "delivery requires fresh " + result["role"] + " verdict at the exact worktree revision"
    protected = state.get("protected_tests", {})
    if protected:
        error = validate_protected_tests(root, protected)
        if error: return "protected test validation failed: " + error
    commits=value.get("commits")
    if not isinstance(commits,list) or not commits or any(not isinstance(item,dict) or set(item)!={"message","paths"} or not isinstance(item["message"],str) or not item["message"] or not isinstance(item["paths"],list) or not item["paths"] for item in commits): return "delivery commit plan is invalid"
    approved=approval.get("paths",[])
    changed=set(dirty_snapshot(root))
    planned=set()
    for item in commits:
        for path in item["paths"]:
            normalized=normalize_path(path)
            if not normalized or normalized.endswith("/") or not path_allowed(normalized,approved): return "delivery commit path is outside Gate 1"
            planned.add(normalized)
    if changed != planned: return "delivery commit plan must cover exactly the changed paths"
    plugins=value.get("plugins"); versions=value.get("versions")
    if not isinstance(plugins,list) or not plugins or len(plugins)!=len(set(plugins)) or not isinstance(versions,dict) or set(versions)!=set(plugins): return "delivery plugins or versions are invalid"
    for plugin in plugins:
        if not isinstance(plugin,str) or not isinstance(versions.get(plugin),str) or manifest_version(root,plugin) != versions[plugin]: return "delivery plugin version does not match manifest"
    return None


def validate_delivery_command(command: str, state: Dict[str, Any], root: Path) -> Optional[str]:
    approval=state.get("delivery_approval") if isinstance(state.get("delivery_approval"),dict) else None; delivery=state.get("delivery") if isinstance(state.get("delivery"),dict) else None
    if not approval or not delivery or approval.get("delivery_id") != delivery.get("id"): return "Gate 2 approval is required"
    if approval.get("release_frozen"): return "release ledger is frozen for recovery"
    transitions=approval.get("delivery_transitions",[]); snapshot=delivery_snapshot(root)
    if snapshot != approval.get("delivery_snapshot") or approval.get("delivery_chain_sha256") != delivery_chain(snapshot,transitions): return "delivery snapshot or chain changed"
    try: tokens=shlex.split(command)
    except ValueError: return "unparseable delivery command"
    phase=approval.get("release_phase"); expected=[item["message"] for item in delivery["commits"]]
    completed = commits_since_origin(root)
    if tokens[:2]==["git","add"]:
        paths=tokens[3:] if len(tokens)>=4 and tokens[2]=="--" else []
        next_index = len(completed)
        planned = delivery["commits"][next_index]["paths"] if next_index < len(delivery["commits"]) else []
        return None if phase in {"approved","staged","committed"} and paths and paths == planned and all(path_allowed(path, delivery["approved_paths"]) for path in paths) else "git add must use exact next planned paths"
    if tokens[:2]==["git","commit"]:
        next_index = len(completed)
        return None if phase in {"approved","staged","committed"} and len(tokens)==4 and tokens[2]=="-m" and next_index < len(expected) and tokens[3] == expected[next_index] and completed == expected[:next_index] and staged_paths(root) else "git commit must use exactly the next approved -m subject"
    if tokens==["git","push","origin","main"]:
        return None if phase=="committed" and git_branch(root)=="main" and not dirty_snapshot(root) and commits_since_origin(root)==expected else "git push is not at the approved committed phase"
    if len(tokens)==4 and tokens[:3]==["codex","plugin","add"]:
        plugin = tokens[3].removesuffix("@wget-cloud")
        complete = set(approval.get("completed_installs", []))
        return None if phase in {"candidate-ci-verified","installed"} and tokens[3] == plugin+"@wget-cloud" and plugin in delivery["plugins"] and plugin not in complete else "plugin install is not approved"
    if len(tokens)==3 and tokens[:2]==["git","tag"]:
        allowed = {plugin+"-v"+version for plugin,version in delivery["versions"].items()}
        plugins = set(delivery["plugins"])
        return None if phase in {"smoke-passed", "tagged"} and set(approval.get("completed_installs", [])) == plugins and set(approval.get("completed_smokes", [])) == plugins and tokens[2] in allowed and tokens[2] not in set(approval.get("completed_tags", [])) else "tag is not approved"
    if len(tokens)==4 and tokens[:3]==["gh","release","create"]:
        allowed = {plugin+"-v"+version for plugin,version in delivery["versions"].items()}
        return None if phase in {"tagged", "released"} and set(approval.get("completed_tags", [])) == allowed and tokens[3] in allowed and tokens[3] not in set(approval.get("completed_releases", [])) else "release is not approved"
    return "unsupported or nonexact delivery command"


def verify_release_evidence(state: Dict[str, Any], evidence: Any, root: Path) -> Optional[str]:
    approval=state.get("delivery_approval") if isinstance(state.get("delivery_approval"),dict) else None
    if not approval or approval.get("release_frozen"): return "release ledger is unavailable or frozen"
    phase=approval.get("release_phase")
    if phase not in {"push-pending-remote-verification","installed"}: return "external evidence is not valid at this phase"
    if phase=="push-pending-remote-verification" and origin_main(root) != git_head(root): return "remote origin/main does not verify pushed delivery SHA"
    try:
        from importlib.util import spec_from_file_location, module_from_spec
        script=Path(__file__).resolve().parents[1]/"scripts/verify_external_evidence.py"; spec=spec_from_file_location("evidence",script); module=module_from_spec(spec); spec.loader.exec_module(module); verified=module.verify(evidence,commit=git_head(root))
    except (OSError, ImportError, AttributeError): return "external evidence verifier is unavailable"
    if not isinstance(verified,dict) or not verified.get("accepted"): return "external evidence is invalid"
    if phase=="push-pending-remote-verification":
        if not isinstance(evidence,dict) or "runtime" in evidence or "smoke" in evidence: return "candidate CI evidence must not include runtime or smoke evidence"
        approval["release_phase"]="candidate-ci-verified"; step="candidate-ci-verified"
    else:
        delivery=state.get("delivery",{})
        runtime=evidence.get("runtime") if isinstance(evidence,dict) else None
        if not isinstance(runtime,dict) or runtime.get("plugin") not in delivery.get("versions",{}) or runtime.get("version")!=delivery.get("versions",{}).get(runtime.get("plugin")) or not isinstance(evidence.get("smoke"),dict): return "runtime and distinct smoke evidence do not match an approved plugin version"
        approval["release_phase"]="smoke-passed"; step="runtime-and-smoke-verified"
    approval.setdefault("release_transitions",[]).append({"step":step,"evidence_sha256":verified.get("evidence_sha256","")}); return None


def delivery_transition(command: str) -> str:
    try: tokens=shlex.split(command)
    except ValueError: return "unknown"
    if tokens[:2]==["git","add"]: return "git-add"
    if tokens[:2]==["git","commit"]: return "git-commit"
    if tokens==["git","push","origin","main"]: return "git-push"
    if tokens[:3]==["codex","plugin","add"]: return "plugin-install"
    if tokens[:2]==["git","tag"]: return "git-tag"
    if tokens[:3]==["gh","release","create"]: return "release-create"
    return "unknown"


def transition_postcondition(transition: str, before: Dict[str, Any], after: Dict[str, Any], root: Path, requested: List[str], command: str) -> Optional[str]:
    if transition=="git-add":
        staged=staged_paths(root)
        if before["head"]!=after["head"] or before["origin_main"]!=after["origin_main"] or before["index_sha256"]==after["index_sha256"] or not staged or set(staged)!=set(requested) or any(not path_allowed(path,requested) for path in staged): return "git add postcondition failed"
        return None
    if transition=="git-commit":
        try: subject=shlex.split(command)[3]
        except (ValueError,IndexError): return "git commit postcondition is unparseable"
        if before["head"]==after["head"] or commits_since_origin(root)[-1:]!=[subject]: return "git commit postcondition failed"
        return None
    if transition=="git-push":
        if before["head"] != after["head"] or before["index_sha256"] != after["index_sha256"] or before["worktree"] != after["worktree"] or after["origin_main"] != before["head"]: return "git push readback did not bind origin/main to unchanged HEAD"
        return None
    if transition=="git-tag":
        try: tag=shlex.split(command)[2]
        except (ValueError, IndexError): return "git tag postcondition is unparseable"
        if before!=after or tag_ref(root, tag) != after["head"]: return "git tag postcondition failed"
        return None
    if transition in {"plugin-install","release-create"}:
        if before!=after: return transition+" changed repository snapshot"
        return None
    return "unknown delivery transition"


def record_pending_delivery(payload: Dict[str, Any], root: Path, state: Dict[str, Any], command: str) -> None:
    approval=state["delivery_approval"]; snapshot=delivery_snapshot(root); transition=delivery_transition(command)
    tokens=shlex.split(command); requested=tokens[3:] if transition=="git-add" else []
    argument = tokens[3] if transition in {"git-commit","plugin-install","release-create"} else (tokens[2] if transition=="git-tag" else None)
    if transition == "plugin-install" and isinstance(argument, str): argument = argument.removesuffix("@wget-cloud")
    approval["pending_delivery"]={"transition":transition,"command_sha256":hashlib.sha256(command.encode()).hexdigest(),"snapshot":snapshot,"chain_sha256":approval["delivery_chain_sha256"],"requested_paths":requested,"argument":argument}
    save(payload,root,state)


def advance_delivery(state: Dict[str, Any], root: Path, pending: Dict[str, Any], after: Dict[str, Any]) -> None:
    approval=state["delivery_approval"]; transition=pending["transition"]
    phase={"git-add":"staged","git-commit":"committed","git-push":"push-pending-remote-verification","plugin-install":"installed","git-tag":"tagged","release-create":"released"}[transition]
    transitions=list(approval.get("delivery_transitions",[])); transitions.append({"step":transition,"command_sha256":pending["command_sha256"]})
    approval["delivery_transitions"]=transitions; approval["delivery_snapshot"]=after; approval["delivery_chain_sha256"]=delivery_chain(after,transitions); approval["release_phase"]=phase; approval.pop("pending_delivery",None)
    if transition == "plugin-install": approval.setdefault("completed_installs", []).append(pending["argument"])
    elif transition == "git-tag": approval.setdefault("completed_tags", []).append(pending["argument"])
    elif transition == "release-create": approval.setdefault("completed_releases", []).append(pending["argument"])


def reconcile_pending_delivery(payload: Dict[str, Any], root: Path, state: Dict[str, Any]) -> Optional[str]:
    approval=state.get("delivery_approval") if isinstance(state.get("delivery_approval"),dict) else None; pending=approval.get("pending_delivery") if approval else None
    if not pending: return None
    if pending.get("transition") not in {"git-add","git-commit"}: return "pending delivery transition cannot be reconciled"
    after=delivery_snapshot(root); command="git add -- "+" ".join(pending.get("requested_paths",[])) if pending["transition"]=="git-add" else "git commit -m " + str(pending.get("argument") or "")
    error=transition_postcondition(pending["transition"],pending["snapshot"],after,root,pending.get("requested_paths",[]),command)
    if error: freeze_release(approval,error); save(payload,root,state); return error
    advance_delivery(state,root,pending,after); save(payload,root,state); return None


def handle_post_tool(payload: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    state=state_for(payload,root); approval=state.get("delivery_approval") if isinstance(state.get("delivery_approval"),dict) else None
    if not approval: return None
    raw = payload.get("tool_input")
    pending_evidence = approval.get("pending_evidence")
    if pending_evidence:
        command = raw.get("command", "") if isinstance(raw, dict) else ""
        response = payload.get("tool_response")
        if hashlib.sha256(str(command).encode()).hexdigest() != pending_evidence.get("command_sha256"):
            freeze_release(approval, "evidence command mismatch"); save(payload, root, state); return {"decision":"block","reason":"Delivery frozen: evidence command mismatch."}
        verified = verifier_response(response)
        if verified is None or not verified.get("accepted") or verified["evidence_sha256"] in approval.get("external_evidence_sha256", []):
            freeze_release(approval, "evidence response invalid or replayed"); save(payload, root, state); return {"decision":"block","reason":"External evidence rejected."}
        identifiers = verified["identifiers"]; phase = approval.get("release_phase")
        if phase == "push-pending-remote-verification" and identifiers["ci"] is not None and identifiers["runtime"] is None and identifiers["smoke"] is None:
            approval["release_phase"] = "candidate-ci-verified"
        elif phase == "installed" and identifiers["ci"] is not None and identifiers["runtime"] is not None and identifiers["smoke"] is not None and isinstance(pending_evidence.get("plugin"), str) and pending_evidence["plugin"] in state.get("delivery", {}).get("plugins", []) and pending_evidence["plugin"] in approval.get("completed_installs", []) and pending_evidence["plugin"] not in approval.get("completed_smokes", []):
            approval.setdefault("completed_smokes", []).append(pending_evidence["plugin"])
            if set(approval["completed_smokes"]) == set(state.get("delivery", {}).get("plugins", [])): approval["release_phase"] = "smoke-passed"
        else:
            freeze_release(approval, "evidence phase invalid"); save(payload, root, state); return {"decision":"block","reason":"External evidence phase invalid."}
        approval.setdefault("external_evidence_sha256", []).append(verified["evidence_sha256"])
        approval.setdefault("completed_evidence_commands", []).append(pending_evidence["command_sha256"])
        approval.pop("pending_evidence", None); save(payload, root, state)
        return None
    if not approval.get("pending_delivery"):
        command = raw.get("command", "") if isinstance(raw, dict) else ""
        if hashlib.sha256(str(command).encode()).hexdigest() in approval.get("completed_evidence_commands", []):
            return {"decision":"block","reason":"External evidence replay rejected."}
        return {"decision":"block","reason":"External evidence requires a bound verifier operation."} if isinstance(raw, dict) and "external_evidence" in raw else None
    pending=approval["pending_delivery"]; raw=payload.get("tool_input"); command=raw.get("command","") if isinstance(raw,dict) else ""
    if hashlib.sha256(str(command).encode()).hexdigest()!=pending.get("command_sha256"): freeze_release(approval,"post-tool command mismatch"); save(payload,root,state); return {"decision":"block","reason":"Delivery frozen: post-tool command mismatch."}
    output=payload.get("tool_response")
    failed=not isinstance(output,dict) or output.get("exit_code") not in (None,0) or output.get("isError") is True
    after=delivery_snapshot(root); error="delivery command failed" if failed else transition_postcondition(pending["transition"],pending["snapshot"],after,root,pending.get("requested_paths",[]),str(command))
    if error: freeze_release(approval,error); save(payload,root,state); return {"decision":"block","reason":"Delivery frozen: "+error+"."}
    advance_delivery(state,root,pending,after); save(payload,root,state); return None


def verifier_response(response: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(response, dict) or set(response) != {"exit_code", "output"} or response.get("exit_code") != 0 or not isinstance(response.get("output"), str) or len(response["output"]) > 8192: return None
    try: value = json.loads(response["output"])
    except json.JSONDecodeError: return None
    required = {"accepted", "errors", "evidence_sha256", "identifiers"}
    if not isinstance(value, dict) or set(value) != required or value.get("accepted") is not True or value.get("errors") != [] or not isinstance(value.get("evidence_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["evidence_sha256"]): return None
    identifiers = value.get("identifiers")
    return value if isinstance(identifiers, dict) and set(identifiers) == {"ci", "runtime", "smoke"} and all(item is None or isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in identifiers.values()) else None


def state_path(payload: Dict[str, Any], root: Path) -> Path:
    raw = str(payload.get("session_id") or "")
    session = raw if re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", raw) else hashlib.sha256((raw + str(root)).encode()).hexdigest()[:32]
    base = Path(os.environ.get("PLUGIN_DATA") or tempfile.gettempdir()) / "approval-state"
    base.mkdir(parents=True, exist_ok=True)
    return base / (session + ".json")


def state_for(payload: Dict[str, Any], root: Path) -> Dict[str, Any]:
    path = state_path(payload, root)
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save(payload: Dict[str, Any], root: Path, state: Dict[str, Any]) -> None:
    path = state_path(payload, root)
    state["updated_at"] = int(time.time())
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def context(event: str, message: str, system: Optional[str] = None) -> Dict[str, Any]:
    answer: Dict[str, Any] = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": message}}
    if system:
        answer["systemMessage"] = system
    return answer


def deny(reason: str) -> Dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


def explicit_activation(prompt: str) -> bool:
    """Accept one literal standalone token, never code/quote/substrings/generic intent."""
    match = re.search(r"(?<![A-Za-z0-9_-])\$wgc-plugin-maintenance(?![A-Za-z0-9_-])", prompt)
    if not match:
        return False
    before = prompt[match.start() - 1] if match.start() else ""
    after = prompt[match.end()] if match.end() < len(prompt) else ""
    return (not before or before not in "'\"`") and (not after or after not in "'\"`")


def normalize_path(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or "\0" in raw or any(char in raw for char in "*?[]{}"):
        return None
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return str(path) + ("/" if raw.endswith("/") else "")


def path_allowed(path: str, scopes: Iterable[str]) -> bool:
    candidate = path.rstrip("/")
    for scope in scopes:
        root = scope.rstrip("/")
        if candidate == root or (scope.endswith("/") and candidate.startswith(root + "/")):
            return True
    return False


def dependency_closure(items: Dict[str, Dict[str, Any]], selected: Iterable[str]) -> Optional[set[str]]:
    closure: set[str] = set()
    visiting: set[str] = set()
    def visit(item_id: str) -> bool:
        if item_id in closure:
            return True
        if item_id in visiting or item_id not in items:
            return False
        visiting.add(item_id)
        if not all(isinstance(dep, str) and visit(dep) for dep in items[item_id]["depends_on"]):
            return False
        visiting.remove(item_id); closure.add(item_id)
        return True
    return closure if all(visit(item) for item in selected) else None


def proposal_state(value: Any, root: Path, turn: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(value, dict) or set(value) != {"baseline_head", "dirty_fingerprint", "items"}:
        return None, "proposal schema is invalid"
    if value.get("baseline_head") != git_head(root) or value.get("dirty_fingerprint") != dirty_fingerprint(root):
        return None, "proposal baseline is stale"
    raw_items = value.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return None, "proposal must have items"
    items: Dict[str, Dict[str, Any]] = {}
    required = {"id","summary","severity","benefit","effort","evidence","paths","acceptance","tests","shadow_eval","risks","compatibility","depends_on","semver","self_change"}
    for item in raw_items:
        if not isinstance(item, dict) or set(item) != required or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{1,63}", str(item.get("id"))):
            return None, "proposal item schema is invalid"
        paths = [normalize_path(path) for path in item["paths"]] if isinstance(item["paths"], list) else []
        if not paths or any(path is None for path in paths) or not isinstance(item["depends_on"], list) or not isinstance(item["self_change"], bool):
            return None, "proposal item paths or dependencies are invalid"
        item_id = item["id"]
        if item_id in items:
            return None, "proposal item IDs must be unique"
        items[item_id] = {"id": item_id, "paths": list(paths), "depends_on": list(item["depends_on"]), "self_change": item["self_change"]}
    if dependency_closure(items, items) is None:
        return None, "proposal dependency graph is invalid"
    identifier = canonical_hash({"proposal": canonical_hash(value), "turn": turn, "head": git_head(root)})[:16]
    return {"id": identifier, "baseline_head": value["baseline_head"], "dirty_fingerprint": value["dirty_fingerprint"], "items": items, "proposal_sha256": canonical_hash(value), "registered_turn": turn}, None


def validate_protected_tests(root: Path, paths: Any) -> Optional[str]:
    if not isinstance(paths, dict) or not paths:
        return "protected test paths must be a non-empty exact file/hash map"
    for raw, digest in paths.items():
        path = normalize_path(raw)
        if not path or path.endswith("/") or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return "protected test declaration is invalid"
        if file_fingerprint(root / path) != digest:
            return "protected test fingerprint does not match the live file"
    return None


def parse_role(message: str, root: Path, approved: Iterable[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    lines = message.splitlines()
    markers = [line for line in lines if line.startswith(ROLE_MARKER)]
    if len(markers) != 1 or not lines or lines[-1] != markers[0]:
        return None, "missing exact final role marker"
    try: value = json.loads(markers[0][len(ROLE_MARKER):])
    except json.JSONDecodeError: return None, "invalid role marker JSON"
    if not isinstance(value, dict) or set(value) != {"role", "verdict", "input_revision"}:
        return None, "role marker schema is invalid"
    role, verdict, revision = value["role"], value["verdict"], value["input_revision"]
    if role not in VERDICTS or verdict not in VERDICTS[role] or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
        return None, "role, verdict, or revision is invalid"
    protected = [line for line in lines if line.startswith(PROTECTED_MARKER)]
    if role == "test-maker" and verdict == "baseline_ready" and len(protected) != 1:
        return None, "baseline_ready requires one protected test declaration"
    if protected:
        if role != "test-maker" or verdict != "baseline_ready" or len(protected) != 1:
            return None, "only a ready test-maker can declare protected tests"
        try: paths = json.loads(protected[0][len(PROTECTED_MARKER):]).get("paths")
        except (json.JSONDecodeError, AttributeError): return None, "protected test marker is invalid"
        error = validate_protected_tests(root, paths)
        if error: return None, error
        if any(not path_allowed(name, approved) for name in paths): return None, "protected tests are outside approved paths"
        value["protected_tests"] = paths
    return value, None


def handle_prompt(payload: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    state = state_for(payload, root); prompt = str(payload.get("prompt") or "").strip(); turn = str(payload.get("turn_id") or "unknown")
    gate_two = DELIVERY_APPROVAL.fullmatch(prompt)
    if gate_two:
        delivery=state.get("delivery") if isinstance(state.get("delivery"),dict) else None
        if not delivery or gate_two.group(1)!=delivery.get("id") or turn==delivery.get("registered_turn") or delivery.get("delivery_snapshot")!=delivery_snapshot(root):
            return context("UserPromptSubmit", "No current delivery proposal can grant authority.", "Delivery approval rejected")
        transitions: List[Dict[str,str]]=[]; snapshot=delivery_snapshot(root)
        state["delivery_approval"]={"delivery_id":delivery["id"],"delivery_snapshot":snapshot,"delivery_transitions":transitions,"delivery_chain_sha256":delivery_chain(snapshot,transitions),"release_phase":"approved","release_frozen":False}
        save(payload,root,state)
        return context("UserPromptSubmit", "Gate 2 approved for this exact snapshot and delivery plan.")
    approval = CHANGE_APPROVAL.fullmatch(prompt)
    if approval:
        proposal = state.get("proposal")
        if not state.get("active") or not isinstance(proposal, dict) or approval.group(1) != proposal.get("id") or turn == proposal.get("registered_turn"):
            return context("UserPromptSubmit", "No current proposal can grant authority.", "Maintenance approval rejected")
        requested = approval.group(2).split(","); items = proposal.get("items", {})
        closure = dependency_closure(items, requested) if isinstance(items, dict) and len(requested) == len(set(requested)) else None
        if closure is None or set(requested) != closure or git_head(root) != proposal.get("baseline_head") or dirty_fingerprint(root) != proposal.get("dirty_fingerprint"):
            return context("UserPromptSubmit", "Approval must select the complete current dependency closure.", "Maintenance approval rejected")
        state["change_approval"] = {"proposal_id": proposal["id"], "item_ids": requested, "paths": sorted({path for item in requested for path in items[item]["paths"]}), "approved_turn": turn}
        state["protected_tests"] = {}; save(payload, root, state)
        return context("UserPromptSubmit", "Gate 1 approved only for the selected dependency closure and exact paths.")
    if not state.get("active"):
        if not explicit_activation(prompt): return None
        state = {"active": True, "baseline_head": git_head(root), "baseline_dirty_fingerprint": dirty_fingerprint(root), "baseline_dirty_paths": dirty_snapshot(root), "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "proposal": None, "change_approval": None, "protected_tests": {}, "role_results": [], "subagent_inputs": {}}
        save(payload, root, state)
    return context("UserPromptSubmit", "Explicit WGC plugin-maintenance audit is active; remain read-only until Gate 1.")


def next_role(state: Dict[str, Any]) -> Optional[str]:
    results = state.get("role_results", [])
    last_negative = max((index for index, item in enumerate(results) if item.get("role") in {"reviewer", "qa"} and item.get("verdict") in {"changes_requested", "defects_found"}), default=-1)
    if last_negative >= 0:
        cycle = ("test-maker", "implementor", "reviewer", "qa")
        suffix = results[last_negative + 1:]
        if len(suffix) >= len(cycle): return None
        return cycle[len(suffix)] if all(item.get("role") == cycle[index] and item.get("verdict") == SUCCESS[cycle[index]] for index, item in enumerate(suffix)) else None
    for index, role in enumerate(ROLES):
        if index >= len(results): return role
        if results[index].get("role") != role or results[index].get("verdict") != SUCCESS[role]: return None
    return None


def successful_role_tail(results: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(results, list): return None
    negative = max((index for index, item in enumerate(results) if isinstance(item, dict) and item.get("role") in {"reviewer", "qa"} and item.get("verdict") in {"changes_requested", "defects_found"}), default=-1)
    expected = ROLES if negative < 0 else ("test-maker", "implementor", "reviewer", "qa")
    tail = results[-len(expected):]
    if len(tail) != len(expected) or any(not isinstance(item, dict) or item.get("role") != role or item.get("verdict") != SUCCESS[role] for role, item in zip(expected, tail)): return None
    if negative >= 0 and negative >= len(results) - len(expected): return None
    return tail


def handle_start(payload: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    state = state_for(payload, root)
    if not state.get("active"): return None
    agent, role, task = str(payload.get("agent_id") or ""), str(payload.get("assigned_role") or ""), str(payload.get("task_name") or "")
    expected = next_role(state); prefix = role.replace("-", "_")
    if not agent or role != expected or not re.fullmatch(re.escape(prefix) + r"(?:_[a-z0-9]+)*", task):
        return context("SubagentStart", "Maintainer assignment rejected: explicit role, order, agent identity, and exact task-name prefix are required.")
    inputs = state.setdefault("subagent_inputs", {})
    if agent in inputs or any(entry.get("agent_id") == agent for entry in state.get("role_results", [])):
        return context("SubagentStart", "Maintainer assignment rejected: agent identity cannot be replayed across roles.")
    revision = worktree_hash(root); inputs[agent] = {"role": role, "task_name": task, "revision": revision, "at": int(time.time())}; save(payload, root, state)
    return context("SubagentStart", f'Role {role} is bound to this revision. End exactly: WGC_MAINTAINER_RESULT: {{"role":"{role}","verdict":"<allowed-verdict>","input_revision":"{revision}"}}')


def handle_stop_agent(payload: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    state = state_for(payload, root)
    if not state.get("active"): return None
    agent = str(payload.get("agent_id") or ""); binding = state.get("subagent_inputs", {}).get(agent)
    approved = state.get("change_approval", {}).get("paths", []) if isinstance(state.get("change_approval"), dict) else []
    result, error = parse_role(str(payload.get("last_assistant_message") or ""), root, approved)
    if not binding: error = error or "missing SubagentStart provenance"
    elif result and (result["role"] != binding["role"] or result["input_revision"] != binding["revision"] or result["role"] != next_role(state)): error = "role result does not match bound identity, role order, or revision"
    elif result and result.get("role") == "test-maker" and "protected_tests" in result:
        previous = state.get("protected_tests", {})
        if isinstance(previous, dict) and not set(previous).issubset(result["protected_tests"]): error = "remediation protected tests may not omit prior paths"
    if error: return {"decision": "block", "reason": "Maintainer role artifact rejected: " + error}
    state["subagent_inputs"].pop(agent, None)
    if "protected_tests" in result: state["protected_tests"] = result.pop("protected_tests")
    state.setdefault("role_results", []).append({**result, "agent_id": agent, "at": int(time.time())}); save(payload, root, state)
    return None


def pre_tool(payload: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    state = state_for(payload, root)
    if not state.get("active"): return None
    approval = state.get("delivery_approval") if isinstance(state.get("delivery_approval"), dict) else None
    if approval and approval.get("pending_delivery"):
        error = reconcile_pending_delivery(payload, root, state)
        if error:
            return deny("Delivery frozen: " + error)
        state = state_for(payload, root)
    tool = str(payload.get("tool_name") or "")
    change = state.get("change_approval") if isinstance(state.get("change_approval"), dict) else None
    if tool in {"apply_patch", "Edit", "Write"}:
        if approval:
            freeze_release(approval, "direct write attempted after Gate 2")
            save(payload, root, state)
            return deny("Direct writes freeze delivery after Gate 2.")
        if not change: return deny("Direct writers are blocked until Gate 1 approval.")
        paths = direct_write_paths(tool, payload.get("tool_input"))
        if not paths or any(not path_allowed(path, change.get("paths", [])) for path in paths): return deny("Direct writer paths must be explicit and within Gate 1 scope.")
        return None
    if tool != "Bash": return None
    raw = payload.get("tool_input"); command = raw.get("command", "") if isinstance(raw, dict) else ""
    if not isinstance(command, str) or not command.strip(): return deny("Empty Bash command is blocked.")
    if re.search(r"[\n\r;&|<>`]|\$[({]", command) or command.lstrip().startswith(("env ", "command ", "alias ", "./", "/")) or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", command): return deny("Shell wrappers, composition, path overrides, and aliases are blocked.")
    try: tokens = shlex.split(command)
    except ValueError: return deny("Unparseable Bash command is blocked.")
    if not tokens: return deny("Unparseable Bash command is blocked.")
    if approval and evidence_command(tokens, approval):
        pending = {"command_sha256": hashlib.sha256(command.encode()).hexdigest(), "head": approval.get("delivery_snapshot", {}).get("head")}
        plugin = encoded_evidence_plugin(tokens)
        if plugin is not None:
            delivery = state.get("delivery", {})
            if approval.get("release_phase") != "installed" or plugin not in delivery.get("plugins", []) or plugin not in approval.get("completed_installs", []) or plugin in approval.get("completed_smokes", []): return deny("Evidence plugin is not an approved installed unsmoked plugin.")
            pending["plugin"] = plugin
        approval["pending_evidence"] = pending
        save(payload, root, state)
        return None
    if isinstance(state.get("delivery_approval"),dict):
        error=validate_delivery_command(command,state,root)
        if error is None:
            record_pending_delivery(payload,root,state,command)
            return None
    if change and validation_command(tokens, change.get("paths", [])):
        return None
    executable, args = tokens[0], tokens[1:]
    if executable == "git":
        action = next((arg for arg in args if not arg.startswith("-")), "")
        if action in READ_GIT and not any(arg.startswith(("-C", "-c", "--git-dir", "--work-tree", "--config-env")) or arg == "-C" or arg == "-c" for arg in args): return None
        return deny("Git mutation and wrappers are blocked; only direct read-only Git audit commands are allowed.")
    if executable in READ_COMMANDS:
        if executable == "find" and any(arg in {"-delete","-exec","-execdir","-ok","-okdir"} for arg in args): return deny("Writing find actions are blocked.")
        return None
    if executable == "sed" and args and "-n" in args and any(re.fullmatch(r"[0-9,$ ]+p", arg) for arg in args): return None
    return deny("Bash is fail-closed: no make, unittest, repository scripts, interpreters, or writes are allowed by this hook profile.")


def direct_write_paths(tool: str, raw: Any) -> List[str]:
    if not isinstance(raw, dict): return []
    if tool in {"Edit", "Write"}:
        path = normalize_path(raw.get("file_path")); return [path] if path and not path.endswith("/") else []
    patch = raw.get("patch") if isinstance(raw.get("patch"), str) else raw.get("command")
    if not isinstance(patch, str) or len(patch) > 200000: return []
    paths: List[str] = []
    for line in patch.splitlines():
        match = re.fullmatch(r"\*\*\* (?:Update|Add|Delete) File: (.+)", line) or re.fullmatch(r"\*\*\* Move to(?: File)?: (.+)", line)
        if match:
            path = normalize_path(match.group(1))
            if not path or path.endswith("/"): return []
            paths.append(path)
    return paths


def validation_command(tokens: List[str], scopes: Iterable[str]) -> bool:
    exact = {
        ("make", "validate"),
        ("python3", "-B", "plugins/wget-cloud-plugin-maintainer/scripts/validate_eval_corpus.py"),
        ("python3", "-B", "plugins/wget-cloud-plugin-maintainer/scripts/validate_maintainer_contracts.py"),
        ("python3", "-B", "plugins/wget-cloud-plugin-maintainer/scripts/run_shadow_eval.py", "--help"),
        ("python3", "-B", "scripts/run_official_validators.py"),
        ("python3", "-B", "-m", "unittest", "plugins.wget-cloud-plugin-maintainer.hooks.tests.test_maintainer_hooks"),
    }
    if tuple(tokens) in exact: return True
    if len(tokens) < 4 or tokens[0] not in {"python", "python3"} or tokens[1:3] != ["-m", "unittest"]: return False
    return all((target.startswith("tests.") or ".tests." in target) and (path := normalize_path(target.replace(".", "/"))) and path_allowed(path, scopes) for target in tokens[3:])


def evidence_command(tokens: List[str], approval: Dict[str, Any]) -> bool:
    prefix = ["python3", "-B", "plugins/wget-cloud-plugin-maintainer/scripts/verify_external_evidence.py"]
    if tokens[:3] != prefix: return False
    if len(tokens) == 5:
        evidence_file, commit = tokens[3:]
        return normalize_path(evidence_file) == evidence_file and "/" not in evidence_file and re.fullmatch(r"[0-9a-f]{40}", commit) is not None and commit == approval.get("delivery_snapshot", {}).get("head")
    if len(tokens) != 6 or tokens[3] != "--encoded": return False
    encoded, commit = tokens[4:]
    if not isinstance(encoded, str) or not 1 <= len(encoded) <= 8192 or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded): return False
    try: parsed = json.loads(base64.urlsafe_b64decode((encoded + "=" * (-len(encoded) % 4)).encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError): return False
    return isinstance(parsed, dict) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None and commit == approval.get("delivery_snapshot", {}).get("head")


def encoded_evidence_plugin(tokens: List[str]) -> Optional[str]:
    if len(tokens) != 6 or tokens[3] != "--encoded": return None
    try: value = json.loads(base64.urlsafe_b64decode((tokens[4] + "=" * (-len(tokens[4]) % 4)).encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError): return None
    runtime = value.get("runtime") if isinstance(value, dict) else None
    if not isinstance(runtime, dict) or set(runtime) != {"plugin", "version", "status", "enabled"} or runtime.get("status") != "installed" or runtime.get("enabled") is not True:
        return None
    plugin = runtime.get("plugin")
    return plugin if isinstance(plugin, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,160}", plugin) else None


def handle_stop(payload: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    state = state_for(payload, root)
    if not state.get("active"): return None
    message = str(payload.get("last_assistant_message") or "")
    delivery_lines=[line for line in message.splitlines() if line.startswith(DELIVERY_MARKER)]
    if delivery_lines:
        if len(delivery_lines)!=1 or message.rstrip().splitlines()[-1]!=delivery_lines[0]: return {"decision":"block","reason":"Delivery marker must be exactly final."}
        try: delivery=json.loads(delivery_lines[0][len(DELIVERY_MARKER):])
        except json.JSONDecodeError: return {"decision":"block","reason":"Delivery marker JSON is invalid."}
        error=validate_delivery(delivery,state,root)
        if error: return {"decision":"block","reason":error}
        snapshot=delivery_snapshot(root); identifier=canonical_hash({"delivery":canonical_hash(delivery),"snapshot":snapshot})[:16]
        state["delivery"]={**delivery,"id":identifier,"approved_paths":state["change_approval"]["paths"],"delivery_snapshot":snapshot,"origin_main":snapshot["origin_main"],"registered_turn":str(payload.get("turn_id") or "unknown")}; state["delivery_approval"]=None; save(payload,root,state)
        return {"decision":"block","reason":"Maintenance delivery registered as "+identifier+". Await a later exact Gate 2 approval."}
    lines = [line for line in message.splitlines() if line.startswith(PROPOSAL_MARKER)]
    if not lines: return None
    if len(lines) != 1 or message.rstrip().splitlines()[-1] != lines[0]: return {"decision": "block", "reason": "Maintenance proposal marker must be exactly final."}
    try: proposal = json.loads(lines[0][len(PROPOSAL_MARKER):])
    except json.JSONDecodeError: return {"decision": "block", "reason": "Maintenance proposal JSON is invalid."}
    results = state.get("role_results", [])
    if len(results) < 2 or [item.get("role") for item in results[:2]] != ["auditor", "architect"] or [item.get("verdict") for item in results[:2]] != ["audited", "proposed"]:
        return {"decision": "block", "reason": "Auditor and Architect evidence is required before Gate 1."}
    registered, error = proposal_state(proposal, root, str(payload.get("turn_id") or "unknown"))
    if error: return {"decision": "block", "reason": error}
    baseline_dirty = state.get("baseline_dirty_paths", {})
    if not isinstance(baseline_dirty, dict): return {"decision": "block", "reason": "baseline dirty state is invalid"}
    if any(path_allowed(dirty, item["paths"]) for dirty in baseline_dirty for item in registered["items"].values()):
        return {"decision": "block", "reason": "proposal scope overlaps a baseline dirty path"}
    state["proposal"] = registered; state["change_approval"] = None; save(payload, root, state)
    return {"decision": "block", "reason": "Maintenance proposal registered as " + registered["id"] + ". Await a later exact Gate 1 approval."}


def main() -> None:
    action = sys.argv[1] if len(sys.argv) == 2 else ""; payload = read_input(); root = target_root(payload.get("cwd"))
    if root is None: return
    result: Optional[Dict[str, Any]] = None
    if action == "prompt-submit": result = handle_prompt(payload, root)
    elif action == "subagent-start": result = handle_start(payload, root)
    elif action == "subagent-stop": result = handle_stop_agent(payload, root)
    elif action == "pre-tool": result = pre_tool(payload, root)
    elif action == "post-tool": result = handle_post_tool(payload, root)
    elif action == "stop": result = handle_stop(payload, root)
    elif action == "session-start": result = context("SessionStart", "WGC plugin maintainer boundaries loaded.")
    elif action == "session-end": result = context("SessionEnd", "WGC plugin maintainer session closed.")
    emit(result)


if __name__ == "__main__": main()
