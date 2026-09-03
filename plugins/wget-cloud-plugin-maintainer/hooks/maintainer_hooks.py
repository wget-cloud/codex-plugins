#!/usr/bin/env python3
"""Privacy-safe approval hooks for the WGC plugin maintainer.

The hook is intentionally stdlib-only. It is silent outside the codex-plugins
repository and stores only hashes plus validated structured gate artifacts.
"""

from __future__ import annotations

import contextlib
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
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple


class ServiceTierPolicyError(RuntimeError):
    """Raised when a maintenance workflow cannot prove that Codex Fast mode is off."""


FORBIDDEN_SERVICE_TIERS = {"fast", "priority", "ultrafast"}


def _codex_policy_values(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[bool]]:
    direct = payload.get("service_tier")
    tier = direct.strip().lower() if isinstance(direct, str) and direct.strip() else None
    fast_mode: Optional[bool] = None
    codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    try:
        lines = (codex_home / "config.toml").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    section = ""
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*=\s*(.+)", line)
        if not match:
            continue
        key, raw_value = match.groups()
        value = raw_value.strip().strip('"\'').lower()
        if tier is None and section == "" and key == "service_tier":
            tier = value
        elif section == "features" and key == "fast_mode" and value in {"true", "false"}:
            fast_mode = value == "true"
    return tier, fast_mode


def require_standard_service_tier(payload: Dict[str, Any]) -> None:
    tier, fast_mode = _codex_policy_values(payload)
    if tier in FORBIDDEN_SERVICE_TIERS or fast_mode is True:
        raise ServiceTierPolicyError(
            "WGC_FAST_MODE_FORBIDDEN: WGC skills cannot run in Codex Fast mode; "
            "use service_tier=default with features.fast_mode=false."
        )
    if tier != "default" or fast_mode is not False:
        raise ServiceTierPolicyError(
            "WGC_SERVICE_TIER_UNVERIFIABLE: refusing to start because service_tier=default "
            "and features.fast_mode=false are not both verifiable."
        )


MAINTENANCE_INTENT = re.compile(
    r"(?:\$wgc-plugin-maintenance|\bwgc-plugin-maintenance\b|"
    r"(?=.*\b(?:plugin|plugins|skill|skills|hook|hooks|subagent|agent|marketplace|плагин\w*|скилл?\w*|хук\w*|субагент\w*)\b)"
    r"(?=.*\b(?:audit|inspect|fix|repair|improve|refactor|extend|release|аудит\w*|провер\w*|исправ\w*|почин\w*|улучш\w*|рефактор\w*|расшир\w*|релиз\w*)\b))",
    re.IGNORECASE | re.DOTALL,
)
CHANGE_APPROVAL = re.compile(
    r"^APPROVE_WGC_PLUGIN_CHANGE=([0-9a-f]{16}):([A-Za-z0-9_.-]+(?:,[A-Za-z0-9_.-]+)*)$"
)
DELIVERY_APPROVAL = re.compile(r"^APPROVE_WGC_PLUGIN_DELIVERY=([0-9a-f]{16})$")
PROPOSAL_MARKER = "WGC_MAINTENANCE_PROPOSAL: "
DELIVERY_MARKER = "WGC_MAINTENANCE_DELIVERY: "
EVIDENCE_MARKER = "WGC_MAINTENANCE_EVIDENCE: "
ROLE_MARKER = "WGC_MAINTAINER_RESULT: "
PROTECTED_TESTS_MARKER = "WGC_MAINTAINER_PROTECTED_TESTS: "
ITEM_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{1,63}$")
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?$"
)
ROLE_VERDICTS: Dict[str, Set[str]] = {
    "auditor": {"audited", "needs_input", "blocked"},
    "architect": {"proposed", "needs_input", "blocked"},
    "test-maker": {"baseline_ready", "needs_input", "blocked"},
    "implementor": {"implemented", "needs_input", "blocked"},
    "reviewer": {"approved", "changes_requested", "needs_input", "blocked"},
    "qa": {"pass", "defects_found", "needs_input", "blocked"},
}
PROPOSAL_SEVERITIES = {"critical", "high", "medium", "low", "info"}
SEMVER_IMPACTS = {"none", "patch", "minor", "major"}
REQUIRED_DELIVERY_VERDICTS = {
    "auditor": "audited",
    "architect": "proposed",
    "test-maker": "baseline_ready",
    "implementor": "implemented",
    "reviewer": "approved",
    "qa": "pass",
}
DELIVERY_RUNNERS = {"git", "gh", "codex"}
READ_ONLY_GIT_ACTIONS = {
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "rev-parse",
    "remote",
    "ls-files",
    "ls-tree",
    "diff-index",
    "check-ignore",
}
READ_ONLY_COMMANDS = {"pwd", "ls", "rg", "find", "head", "tail", "cat", "wc", "shasum", "sha256sum"}
SAFE_ENVIRONMENT_PREFIXES = {"PYTHONDONTWRITEBYTECODE=1"}
UNSAFE_SHELL_SYNTAX = re.compile(r"[\n\r;&|<>`\\]|\$[({]")
SAFE_SED_PRINT_PROGRAM = re.compile(r"^[0-9,$ ]+p$")


def read_input() -> Dict[str, Any]:
    try:
        raw = sys.stdin.read()
        value = json.loads(raw) if raw.strip() else {}
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def emit(value: Optional[Dict[str, Any]]) -> None:
    if value:
        sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def run(command: Sequence[str], cwd: Path, timeout: float = 4.0) -> Tuple[int, str]:
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def git_root(cwd: Path) -> Optional[Path]:
    code, output = run(["git", "rev-parse", "--show-toplevel"], cwd)
    if code == 0 and output:
        return Path(output.splitlines()[-1]).resolve()
    return None


def is_target_repository(root: Path) -> bool:
    marketplace = root / ".agents" / "plugins" / "marketplace.json"
    return (
        root.name == "codex-plugins"
        and marketplace.is_file()
        and (root / "AGENTS.md").is_file()
        and (root / "plugins").is_dir()
    )


def detect_context(raw_cwd: Any) -> Optional[Dict[str, str]]:
    try:
        cwd = Path(str(raw_cwd or os.getcwd())).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    if not cwd.exists():
        return None
    root = git_root(cwd)
    if root is None or not is_target_repository(root):
        return None
    return {"cwd": str(cwd), "repo_root": str(root)}


def git_head(root: Path) -> str:
    code, output = run(["git", "rev-parse", "HEAD"], root)
    return output.splitlines()[-1] if code == 0 and re.fullmatch(r"[0-9a-f]{40}", output.splitlines()[-1]) else "unborn"


def origin_main(root: Path) -> str:
    code, output = run(["git", "rev-parse", "refs/remotes/origin/main"], root)
    return output.splitlines()[-1] if code == 0 and output else "unavailable"


def git_branch(root: Path) -> str:
    code, output = run(["git", "branch", "--show-current"], root)
    return output.strip() if code == 0 else ""


def file_fingerprint(path: Path) -> str:
    try:
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        if path.is_dir():
            return "directory"
        return "missing"
    except OSError:
        return "unreadable"


def dirty_snapshot(root: Path) -> Dict[str, str]:
    code, output = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], root)
    if code != 0 or not output:
        return {}
    result: Dict[str, str] = {}
    entries = output.split("\0")
    position = 0
    while position < len(entries):
        entry = entries[position]
        position += 1
        if not entry or len(entry) < 4:
            continue
        status = entry[:2]
        paths = [entry[3:]]
        if any(marker in {"R", "C"} for marker in status) and position < len(entries):
            original = entries[position]
            position += 1
            if original:
                paths.append(original)
        for raw in paths:
            normalized = raw.replace("\\", "/")
            result[normalized] = f"{status}:{file_fingerprint(root / raw)}"
    return dict(sorted(result.items()))


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dirty_fingerprint(root: Path) -> str:
    return canonical_hash(dirty_snapshot(root))


def worktree_hash(root: Path) -> str:
    return canonical_hash({"head": git_head(root), "dirty": dirty_snapshot(root)})


def index_fingerprint(root: Path) -> str:
    """Hash the complete Git index without persisting its contents in hook state."""
    code, output = run(["git", "ls-files", "-s", "-z"], root)
    return hashlib.sha256(output.encode("utf-8")).hexdigest() if code == 0 else "unavailable"


def delivery_snapshot(root: Path) -> Dict[str, Any]:
    """The full repository state that delivery commands are allowed to advance."""
    return {
        "head": git_head(root),
        "index_sha256": index_fingerprint(root),
        "worktree": dirty_snapshot(root),
        "origin_main": origin_main(root),
    }


def delivery_chain(snapshot: Dict[str, Any], transitions: Sequence[Dict[str, str]]) -> str:
    return canonical_hash({"snapshot": snapshot, "transitions": list(transitions)})


def minimal_proposal_state(value: Dict[str, Any], proposal_id: str, turn_id: str) -> Dict[str, Any]:
    """Keep only Gate 1 enforcement data; bind discarded prose by its hash."""
    return {
        "id": proposal_id,
        "proposal_sha256": canonical_hash(value),
        "baseline_head": value["baseline_head"],
        "dirty_fingerprint": value["dirty_fingerprint"],
        "items": [
            {
                "id": item["id"],
                "paths": list(item["paths"]),
                "depends_on": list(item["depends_on"]),
                "self_change": item["self_change"],
            }
            for item in value["items"]
        ],
        "registered_turn": turn_id,
        "registered_at": int(time.time()),
    }


def secret_sentinels(proposal: Dict[str, Any], item_ids: Sequence[str]) -> List[str]:
    """Store non-reversible binding sentinels, never raw prompt or proposal text."""
    seed = str(proposal.get("proposal_sha256") or proposal.get("id") or "")
    return [hashlib.sha256(f"{seed}:{item_id}".encode("utf-8")).hexdigest() for item_id in sorted(item_ids)]


def external_evidence_binding(root: Path, ci_evidence: bool, runtime_evidence: bool) -> Dict[str, str]:
    """Persist only subject-bound evidence identifiers, never external records."""
    subject = {"commit": git_head(root), "origin_main": origin_main(root), "ci": ci_evidence, "runtime": runtime_evidence}
    digest = canonical_hash(subject)
    return {"subject_sha256": digest, "ci_identifier": hashlib.sha256(f"ci:{digest}".encode("utf-8")).hexdigest(), "runtime_identifier": hashlib.sha256(f"runtime:{digest}".encode("utf-8")).hexdigest()}


def release_phase(state: Dict[str, Any]) -> str:
    approval = state.get("delivery_approval") if isinstance(state.get("delivery_approval"), dict) else {}
    return str(approval.get("release_phase") or "")


def freeze_release(approval: Dict[str, Any], reason: str) -> None:
    approval["release_frozen"] = True
    approval["recovery_reason_sha256"] = hashlib.sha256(reason.encode("utf-8")).hexdigest()


def verify_release_evidence(state: Dict[str, Any], evidence: Any, root: Path) -> Optional[str]:
    """Advance only the evidence-bound phases; persist no raw external record."""
    approval = state.get("delivery_approval") if isinstance(state.get("delivery_approval"), dict) else None
    if not approval or approval.get("release_frozen"):
        return "release ledger is unavailable or frozen for recovery"
    phase = release_phase(state)
    if phase not in {"push-pending-remote-verification", "installed"}:
        return "external evidence is not valid at the current release phase"
    if phase == "push-pending-remote-verification" and origin_main(root) != git_head(root):
        return "remote origin/main does not verify the pushed delivery SHA"
    try:
        import importlib.util
        verifier_path = Path(__file__).resolve().parents[1] / "scripts" / "verify_external_evidence.py"
        spec = importlib.util.spec_from_file_location("wgc_external_evidence", verifier_path)
        if spec is None or spec.loader is None:
            return "external evidence verifier is unavailable"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        verified = module.verify(evidence, commit=git_head(root))
    except (ImportError, OSError, AttributeError):
        return "external evidence verifier is unavailable"
    if not isinstance(verified, dict) or verified.get("accepted") is not True:
        return "external evidence is stale, mismatched, incomplete, or unsafe"
    if phase == "push-pending-remote-verification":
        if not isinstance(evidence, dict) or evidence.get("runtime") is not None or evidence.get("smoke") is not None:
            return "candidate CI verification must contain only the exact post-push CI evidence"
        approval["release_phase"] = "candidate-ci-verified"
        step = "candidate-ci-verified"
    else:
        if not isinstance(evidence, dict) or not isinstance(evidence.get("runtime"), dict) or not isinstance(evidence.get("smoke"), dict):
            return "installed runtime and distinct-task smoke evidence are both required before tagging"
        runtime = evidence["runtime"]
        delivery = state.get("delivery") if isinstance(state.get("delivery"), dict) else {}
        versions = delivery.get("versions") if isinstance(delivery.get("versions"), dict) else {}
        if runtime.get("plugin") not in versions or runtime.get("version") != versions.get(runtime.get("plugin")):
            return "runtime inventory does not match an exact approved plugin version"
        approval["release_phase"] = "smoke-passed"
        step = "runtime-installed-and-smoke-passed"
    transitions = approval.setdefault("release_transitions", [])
    transitions.append({"step": step, "evidence_sha256": str(verified.get("evidence_sha256") or "")})
    approval["external_evidence_identifiers"] = verified.get("identifiers", {})
    return None


def data_root() -> Path:
    configured = os.environ.get("PLUGIN_DATA")
    base = Path(configured).expanduser() if configured else Path(tempfile.gettempdir()) / "wgc-plugin-maintainer-data"
    target = base / "approval-state"
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_session_id(value: Any, root: str) -> str:
    raw = str(value or "")
    if raw and re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", raw):
        return raw
    return hashlib.sha256(f"{raw}:{root}".encode("utf-8")).hexdigest()[:32]


def state_paths(payload: Dict[str, Any], context: Dict[str, str]) -> Tuple[Path, Path]:
    session = safe_session_id(payload.get("session_id"), context["repo_root"])
    path = data_root() / f"{session}.json"
    return path, path.with_suffix(".lock")


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    locked_windows = False
    try:
        if os.name == "nt":
            try:
                import msvcrt  # type: ignore

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                locked_windows = True
            except (ImportError, OSError):
                pass
        else:
            try:
                import fcntl  # type: ignore

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
        yield
    finally:
        if os.name == "nt" and locked_windows:
            try:
                import msvcrt  # type: ignore

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except (ImportError, OSError):
                pass
        elif os.name != "nt":
            try:
                import fcntl  # type: ignore

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
        handle.close()


def read_state(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {"_corrupt": True}
    except OSError:
        return {}


def update_state(
    payload: Dict[str, Any],
    context: Dict[str, str],
    updater: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    path, lock = state_paths(payload, context)
    with file_lock(lock):
        state = read_state(path)
        state.setdefault("version", 1)
        state.setdefault("active", False)
        state.setdefault("proposal", None)
        state.setdefault("change_approval", None)
        state.setdefault("delivery", None)
        state.setdefault("delivery_proposal", None)
        state.setdefault("delivery_approval", None)
        state.setdefault("pending_delivery", None)
        state.setdefault("protected_tests", {})
        state.setdefault("role_results", [])
        state.setdefault("subagent_inputs", {})
        state.setdefault("events", [])
        state["context"] = context
        state["updated_at"] = int(time.time())
        updater(state)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
        return state


def additional_context(event: str, message: str, system_message: Optional[str] = None) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": message}
    }
    if system_message:
        output["systemMessage"] = system_message
    return output


def deny(reason: str) -> Dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def context_message(root: Path) -> str:
    snapshot = dirty_snapshot(root)
    return (
        f"WGC codex-plugins repository detected. HEAD={git_head(root)}; "
        f"origin/main={origin_main(root)}; dirty_paths={len(snapshot)}; "
        f"dirty_fingerprint={canonical_hash(snapshot)}. Automatic maintenance selection is read-only until Gate 1."
    )


def handle_session_start(payload: Dict[str, Any], context: Dict[str, str]) -> Dict[str, Any]:
    root = Path(context["repo_root"])
    state_path, _ = state_paths(payload, context)
    if read_state(state_path).get("active"):
        require_standard_service_tier(payload)
    state = update_state(payload, context, lambda value: None)
    active = " Active maintenance audit is present." if state.get("active") else ""
    return additional_context("SessionStart", context_message(root) + active)


def activation_state(root: Path, prompt: str, turn_id: str) -> Dict[str, Any]:
    snapshot = dirty_snapshot(root)
    return {
        "active": True,
        "activated_at": int(time.time()),
        "activation_turn": turn_id,
        "last_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "baseline_head": git_head(root),
        "baseline_origin_main": origin_main(root),
        "baseline_dirty": snapshot,
        "baseline_dirty_fingerprint": canonical_hash(snapshot),
        "proposal": None,
        "change_approval": None,
        "delivery": None,
        "delivery_approval": None,
        "protected_tests": {},
        "role_results": [],
        "events": [],
    }


def live_matches_proposal(root: Path, proposal: Dict[str, Any]) -> Optional[str]:
    if git_head(root) != proposal.get("baseline_head"):
        return "Repository HEAD changed after the proposal; create a new maintenance proposal."
    if dirty_fingerprint(root) != proposal.get("dirty_fingerprint"):
        return "Repository dirty baseline changed after the proposal; create a new maintenance proposal."
    return None


def handle_prompt_submit(payload: Dict[str, Any], context: Dict[str, str]) -> Optional[Dict[str, Any]]:
    prompt = str(payload.get("prompt") or "").strip()
    turn_id = str(payload.get("turn_id") or "unknown")
    root = Path(context["repo_root"])
    path, _ = state_paths(payload, context)
    prior = read_state(path)

    change_match = CHANGE_APPROVAL.fullmatch(prompt)
    if change_match:
        proposal = prior.get("proposal") if isinstance(prior.get("proposal"), dict) else None
        if not prior.get("active") or not proposal:
            return additional_context("UserPromptSubmit", "No registered maintenance proposal exists; approval grants no write authority.", "Maintenance approval rejected")
        if turn_id == proposal.get("registered_turn"):
            return additional_context("UserPromptSubmit", "Approval must arrive in a later user turn than the proposal.", "Maintenance approval rejected")
        if change_match.group(1) != proposal.get("id"):
            return additional_context("UserPromptSubmit", "The proposal ID is stale or belongs to another proposal.", "Maintenance approval rejected")
        requested = change_match.group(2).split(",")
        items = {item["id"]: item for item in proposal.get("items", []) if isinstance(item, dict)}
        if len(requested) != len(set(requested)) or any(item_id not in items for item_id in requested):
            return additional_context("UserPromptSubmit", "Approval contains duplicate or unknown item IDs.", "Maintenance approval rejected")
        mismatch = live_matches_proposal(root, proposal)
        if mismatch:
            return additional_context("UserPromptSubmit", mismatch, "Maintenance approval rejected")
        approved_paths = sorted({path for item_id in requested for path in items[item_id]["paths"]})

        def approve_change(state: Dict[str, Any]) -> None:
            state["change_approval"] = {
                "proposal_id": proposal["id"],
                "item_ids": requested,
                "paths": approved_paths,
                "approved_turn": turn_id,
                "approval_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "secret_sentinels": secret_sentinels(proposal, requested),
                "at": int(time.time()),
            }
            state["delivery"] = None
            state["delivery_proposal"] = None
            state["delivery_approval"] = None
            state["pending_delivery"] = None
            state["protected_tests"] = {}

        update_state(payload, context, approve_change)
        return additional_context(
            "UserPromptSubmit",
            "Gate 1 approved for items " + ", ".join(requested) + ". Writes remain limited to the registered paths; Git delivery is still blocked.",
        )

    delivery_match = DELIVERY_APPROVAL.fullmatch(prompt)
    if delivery_match:
        delivery = prior.get("delivery") if isinstance(prior.get("delivery"), dict) else None
        if not prior.get("active") or not delivery:
            return additional_context("UserPromptSubmit", "No registered delivery proposal exists; approval grants no delivery authority.", "Delivery approval rejected")
        if turn_id == delivery.get("registered_turn") or delivery_match.group(1) != delivery.get("id"):
            return additional_context("UserPromptSubmit", "Delivery approval is stale or was not provided in a later user turn.", "Delivery approval rejected")
        if worktree_hash(root) != delivery.get("worktree_hash"):
            return additional_context("UserPromptSubmit", "The approved worktree changed; register a new delivery proposal.", "Delivery approval rejected")
        if origin_main(root) != delivery.get("origin_main"):
            return additional_context("UserPromptSubmit", "origin/main changed; re-audit and register a new delivery proposal.", "Delivery approval rejected")
        snapshot = delivery_snapshot(root)
        if snapshot != delivery.get("delivery_snapshot"):
            return additional_context("UserPromptSubmit", "The approved HEAD, index, worktree, or origin/main state changed; register a new delivery proposal.", "Delivery approval rejected")

        def approve_delivery(state: Dict[str, Any]) -> None:
            transitions = [{"step": "gate2-approved"}]
            state["delivery_approval"] = {
                "delivery_id": delivery["id"],
                "approved_turn": turn_id,
                "approval_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "at": int(time.time()),
                "delivery_snapshot": snapshot,
                "delivery_transitions": transitions,
                "delivery_chain_sha256": delivery_chain(snapshot, transitions),
                "release_phase": "approved",
                "release_transitions": [],
                "release_frozen": False,
            }

        update_state(payload, context, approve_delivery)
        return additional_context(
            "UserPromptSubmit",
            "Gate 2 approved for the registered worktree, commit plan, origin/main, versions, install list, smoke task, tags, and releases. Any divergence invalidates delivery.",
        )

    if not MAINTENANCE_INTENT.search(prompt) and not prior.get("active"):
        return None
    require_standard_service_tier(payload)

    if not prior.get("active"):
        fresh = activation_state(root, prompt, turn_id)

        def activate(state: Dict[str, Any]) -> None:
            state.update(fresh)

        update_state(payload, context, activate)
    else:
        update_state(
            payload,
            context,
            lambda state: state.update(
                {"last_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
            ),
        )
    return additional_context(
        "UserPromptSubmit",
        "WGC plugin maintenance read-only audit is active. Perform the complete repository/CI/runtime audit with Auditor and Architect, report all findings and Capability gaps, and do not mutate files before a registered item-level Gate 1 approval.",
    )


def handle_subagent_start(payload: Dict[str, Any], context: Dict[str, str]) -> Optional[Dict[str, Any]]:
    state_path, _ = state_paths(payload, context)
    prior = read_state(state_path)
    if not prior.get("active"):
        return None
    require_standard_service_tier(payload)
    revision = worktree_hash(Path(context["repo_root"]))
    agent_id = str(payload.get("agent_id") or "")

    def record(state: Dict[str, Any]) -> None:
        inputs = state.setdefault("subagent_inputs", {})
        inputs[agent_id] = {"revision": revision, "at": int(time.time())}
        if len(inputs) > 100:
            for key in sorted(inputs, key=lambda item: inputs[item].get("at", 0))[:-100]:
                inputs.pop(key, None)

    update_state(payload, context, record)
    return additional_context(
        "SubagentStart",
        "WGC plugin-maintainer role boundary: read AGENTS.md and your assigned role contract; preserve dirty paths; stay inside ALLOW_PATHS; never commit, push, install, tag, or release. Write roles require Gate 1 evidence. End with exactly: "
        f'WGC_MAINTAINER_RESULT: {{"role":"<role>","verdict":"<allowed-verdict>","input_revision":"{revision}"}}',
    )


def parse_role_result(
    message: str, root: Path, approved_paths: Iterable[str]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    lines = [line for line in message.splitlines() if line.startswith(ROLE_MARKER)]
    if len(lines) != 1 or not message.rstrip().endswith(lines[0]):
        return None, "missing exact final WGC_MAINTAINER_RESULT line"
    try:
        value = json.loads(lines[0][len(ROLE_MARKER) :])
    except json.JSONDecodeError:
        return None, "invalid role result JSON"
    if not isinstance(value, dict) or set(value) != {"role", "verdict", "input_revision"}:
        return None, "role result must contain exactly role, verdict, and input_revision"
    role = str(value.get("role") or "")
    verdict = str(value.get("verdict") or "")
    revision = str(value.get("input_revision") or "")
    if role not in ROLE_VERDICTS or verdict not in ROLE_VERDICTS[role]:
        return None, f"invalid role/verdict contract: {role}/{verdict}"
    if not re.fullmatch(r"[0-9a-f]{64}", revision):
        return None, "input_revision must be the exact 64-hex assigned revision"
    result: Dict[str, Any] = {"role": role, "verdict": verdict, "input_revision": revision}
    protected_lines = [line for line in message.splitlines() if line.startswith(PROTECTED_TESTS_MARKER)]
    if role == "test-maker" and verdict == "baseline_ready":
        if len(protected_lines) != 1:
            return None, "test-maker baseline_ready requires exactly one protected-tests marker"
        try:
            protected_value = json.loads(protected_lines[0][len(PROTECTED_TESTS_MARKER) :])
        except json.JSONDecodeError:
            return None, "protected-tests marker contains invalid JSON"
        paths = protected_value.get("paths") if isinstance(protected_value, dict) else None
        if not isinstance(paths, dict) or not paths:
            return None, "protected-tests marker requires a non-empty paths object"
        protected: Dict[str, str] = {}
        for raw, expected_hash in paths.items():
            normalized = normalize_relative_path(raw) if isinstance(raw, str) else None
            if normalized is None or not path_allowed(normalized, approved_paths):
                return None, "protected test path is invalid or outside Gate 1"
            if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                return None, "protected test hash must be SHA-256"
            if file_fingerprint(root / normalized) != expected_hash:
                return None, "protected test hash does not match the live file"
            protected[normalized] = expected_hash
        result["protected_tests"] = protected
    elif protected_lines:
        return None, "only test-maker baseline_ready may declare protected tests"
    return result, None


def handle_subagent_stop(payload: Dict[str, Any], context: Dict[str, str]) -> Optional[Dict[str, Any]]:
    path, _ = state_paths(payload, context)
    prior = read_state(path)
    if not prior.get("active"):
        return None
    approval = prior.get("change_approval") if isinstance(prior.get("change_approval"), dict) else {}
    result, error = parse_role_result(
        str(payload.get("last_assistant_message") or ""),
        Path(context["repo_root"]),
        approval.get("paths", []),
    )
    agent_id = str(payload.get("agent_id") or "")
    expected = prior.get("subagent_inputs", {}).get(agent_id, {}).get("revision")
    if not error and result and expected and result["input_revision"] != expected:
        error = "input_revision does not match SubagentStart"
    if error:
        if payload.get("stop_hook_active"):
            return None
        return {"decision": "block", "reason": "Maintainer role artifact rejected: " + error + "."}

    def record(state: Dict[str, Any]) -> None:
        protected = result.pop("protected_tests", None)
        if protected is not None:
            state["protected_tests"] = protected
        results = state.setdefault("role_results", [])
        results.append({**result, "agent_id": agent_id[:160], "at": int(time.time())})
        del results[:-100]

    update_state(payload, context, record)
    return None


def normalize_relative_path(raw: str) -> Optional[str]:
    value = raw.strip().replace("\\", "/")
    if not value or value.startswith("/") or "\0" in value:
        return None
    pure = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in pure.parts):
        return None
    if any(character in value for character in "*?[]{}"):
        return None
    normalized = str(pure)
    return normalized + "/" if value.endswith("/") else normalized


def path_allowed(path: str, scopes: Iterable[str]) -> bool:
    candidate = path.rstrip("/")
    for scope in scopes:
        normalized = scope.rstrip("/")
        if scope.endswith("/") and (candidate == normalized or candidate.startswith(normalized + "/")):
            return True
        if candidate == normalized:
            return True
    return False


def paths_overlap(left: str, right: str) -> bool:
    first = left.rstrip("/")
    second = right.rstrip("/")
    return first == second or first.startswith(second + "/") or second.startswith(first + "/")


def patch_paths(text: str) -> List[str]:
    result: List[str] = []
    for match in re.finditer(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$", text, re.MULTILINE):
        normalized = normalize_relative_path(match.group(1))
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def tool_paths(payload: Dict[str, Any], context: Dict[str, str]) -> List[str]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    tool = str(payload.get("tool_name") or "")
    if tool == "apply_patch":
        return patch_paths(str(tool_input.get("command", tool_input.get("patch", ""))))
    raw = tool_input.get("file_path", tool_input.get("path"))
    if not isinstance(raw, str):
        return []
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path(context["cwd"]) / candidate
    try:
        relative = candidate.resolve(strict=False).relative_to(Path(context["repo_root"]).resolve())
    except (OSError, ValueError):
        return []
    normalized = normalize_relative_path(relative.as_posix())
    return [normalized] if normalized else []


def tool_command(payload: Dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    value = tool_input.get("command", tool_input.get("cmd", ""))
    return value if isinstance(value, str) else ""


def shell_tokens(command: str) -> List[str]:
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return []


def destructive_command(command: str) -> Optional[str]:
    lower = command.casefold()
    if re.search(r"\bgit\b[^\n;&|]{0,160}\b(?:reset|clean|rebase|merge)\b", lower):
        return "Destructive or history-rewriting Git operations are forbidden in plugin maintenance."
    if re.search(r"\bgit\b[^\n;&|]{0,160}\bpush\b[^\n]*(?:--force|-f\b|\+[^\s]+)", lower):
        return "Force-push is forbidden in plugin maintenance."
    if re.search(r"\brm\s+(?:-[^\s]*r[^\s]*\s+|--recursive\b)", lower):
        return "Recursive deletion is forbidden by the maintainer hook."
    return None


def delivery_command(command: str) -> bool:
    return bool(
        re.search(r"\bgit\b[^\n;&|]{0,160}\b(?:add|commit|push|tag)\b", command, re.IGNORECASE)
        or re.search(r"\bcodex\s+plugin\s+add\b", command, re.IGNORECASE)
        or re.search(r"\bgh\s+release\s+create\b", command, re.IGNORECASE)
    )


def bash_read_or_validation_error(command: str) -> Optional[str]:
    """Return a fail-closed reason unless *command* is in the Bash read profile.

    Bash has no write authority at Gate 1.  Its deliberately small profile is
    limited to direct audit commands and deterministic validation commands;
    all file changes must use a path-scoped editing tool or an approved Gate 2
    delivery command.
    """
    if not command.strip():
        return "Empty Bash commands are blocked during plugin maintenance."
    if UNSAFE_SHELL_SYNTAX.search(command):
        return "Shell composition syntax (redirects, pipes, substitutions, heredocs, or command chaining) is blocked. Run one direct approved command."
    tokens = shell_tokens(command)
    if not tokens:
        return "Unparseable Bash command is blocked. Run one direct approved audit or validation command."
    if any(token.startswith("$") for token in tokens):
        return "Shell variable expansion is blocked. Run one direct approved command with literal arguments."
    validation_environment = tokens[0] in SAFE_ENVIRONMENT_PREFIXES
    if validation_environment:
        tokens = tokens[1:]
    elif "=" in tokens[0]:
        return "Environment wrappers are blocked. Only PYTHONDONTWRITEBYTECODE=1 is allowed for focused Python validation."
    if not tokens:
        return "Missing command after the validation environment prefix."

    executable = tokens[0].casefold()
    arguments = tokens[1:]
    if executable in READ_ONLY_COMMANDS:
        if executable == "find" and any(argument in {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"} for argument in arguments):
            return "find actions that execute commands or write files are blocked."
        if executable == "rg" and any(argument == "--pre" or argument.startswith("--pre=") for argument in arguments):
            return "rg command-preprocessor options are blocked."
        return None
    if executable == "git":
        if not arguments:
            return "Git requires an explicitly allowed read-only subcommand."
        if any(
            argument == "-C"
            or argument.startswith("-C")
            or argument == "-c"
            or argument.startswith("-c")
            or argument == "--git-dir"
            or argument.startswith("--git-dir=")
            or argument == "--work-tree"
            or argument.startswith("--work-tree=")
            or argument == "--config-env"
            or argument.startswith("--config-env=")
            for argument in arguments
        ):
            return "Git directory/configuration wrappers are blocked; run the audit from the repository working directory."
        action = next((argument.casefold() for argument in arguments if not argument.startswith("-")), "")
        if action in READ_ONLY_GIT_ACTIONS:
            return None
        return "Git is limited to documented read-only audit subcommands until an exact Gate 2 delivery command is approved."
    if executable == "sed":
        if any(argument.startswith("-") and argument not in {"-n", "--quiet", "--silent"} for argument in arguments):
            return "sed options other than -n/--quiet/--silent are blocked."
        non_options = [argument for argument in arguments if not argument.startswith("-")]
        if len(non_options) >= 2 and SAFE_SED_PRINT_PROGRAM.fullmatch(non_options[0]):
            return None
        return "sed is limited to a numeric -n print range (for example, `sed -n '1,120p' file`)."
    if executable == "make" and arguments == ["validate"]:
        return None
    if executable in {"python", "python3"} and len(arguments) >= 2 and arguments[:2] == ["-m", "unittest"]:
        if validation_environment:
            return None
        return "Focused Python validation requires PYTHONDONTWRITEBYTECODE=1 so Bash does not create repository files."
    return "Bash is fail-closed: use a documented read-only audit command, focused validation, a scoped editing tool, or an exact Gate 2 delivery command."


def staged_paths(root: Path) -> List[str]:
    code, output = run(["git", "diff", "--cached", "--name-only", "-z"], root)
    return sorted(path.replace("\\", "/") for path in output.split("\0") if path) if code == 0 else []


def commits_since_origin(root: Path) -> List[str]:
    code, output = run(["git", "log", "--format=%s", "refs/remotes/origin/main..HEAD"], root)
    return list(reversed(output.splitlines())) if code == 0 and output else []


def validate_delivery_command(command: str, state: Dict[str, Any], root: Path) -> Optional[str]:
    approval = state.get("delivery_approval")
    delivery = state.get("delivery") if isinstance(state.get("delivery"), dict) else None
    if not approval or not delivery or approval.get("delivery_id") != delivery.get("id"):
        return "Git delivery, plugin install, tags, and releases require a valid Gate 2 approval."
    if approval.get("release_frozen"):
        return "Release delivery is frozen after a failed verification or transition; create a recovery proposal."
    if state.get("pending_delivery"):
        return "A delivery command is still awaiting its post-tool result; do not start another delivery transition."
    snapshot = delivery_snapshot(root)
    transitions = approval.get("delivery_transitions")
    if not isinstance(transitions, list) or not all(isinstance(item, dict) for item in transitions):
        return "Delivery transition state is invalid; register a new delivery proposal."
    if snapshot != approval.get("delivery_snapshot") or approval.get("delivery_chain_sha256") != delivery_chain(snapshot, transitions):
        return "HEAD, index, worktree, origin/main, or the delivery chain changed; register a new delivery proposal."
    tokens = shell_tokens(command)
    if not tokens:
        return "Unparseable delivery command is blocked."
    lower = [token.casefold() for token in tokens]
    phase = release_phase(state)
    if lower[0] == "git" and len(lower) >= 2:
        action = lower[1]
        if action == "add":
            if phase not in {"approved", "staged"}:
                return "git add is only allowed before the committed delivery phase."
            requested = [normalize_relative_path(token) for token in tokens[2:] if token != "--" and not token.startswith("-")]
            if not requested or any(path is None or not path_allowed(path, delivery["approved_paths"]) for path in requested):
                return "git add is limited to exact Gate 2 paths."
            return None
        if action == "commit":
            if phase not in {"approved", "staged"}:
                return "git commit is only allowed after Gate 2 staging and before push."
            cached = staged_paths(root)
            if not cached or any(not path_allowed(path, delivery["approved_paths"]) for path in cached):
                return "git commit contains no staged files or paths outside Gate 2."
            expected = [entry["message"] for entry in delivery["commits"]]
            existing = commits_since_origin(root)
            if existing != expected[: len(existing)] or len(existing) >= len(expected):
                return "Existing commits do not match the approved atomic commit sequence."
            try:
                message_index = tokens.index("-m") + 1
                message = tokens[message_index]
            except (ValueError, IndexError):
                return "git commit must use the exact approved -m subject."
            if message != expected[len(existing)]:
                return "git commit subject does not match the approved commit plan."
            return None
        if action == "push":
            if phase != "committed":
                return "git push requires a successfully recorded committed phase."
            if lower != ["git", "push", "origin", "main"]:
                return "Only exact non-force `git push origin main` is approved."
            if git_branch(root) != "main" or dirty_snapshot(root):
                return "Push requires branch main and a clean worktree."
            expected = [entry["message"] for entry in delivery["commits"]]
            if commits_since_origin(root) != expected:
                return "Local commits do not match the approved delivery plan."
            return None
        if action == "tag":
            if phase != "smoke-passed":
                return "Release tags require exact installed-runtime and distinct-task smoke evidence after candidate CI verification."
            allowed = {f"{plugin}-v{version}" for plugin, version in delivery["versions"].items()}
            tags = [token for token in tokens[2:] if not token.startswith("-")]
            if len(tags) != 1 or tags[0] not in allowed:
                return "Only the approved per-bundle release tag is allowed."
            return None
    if lower[:3] == ["codex", "plugin", "add"]:
        if phase != "candidate-ci-verified":
            return "Plugin reinstall requires verified candidate CI for the exact remotely verified commit."
        allowed = {f"{plugin}@wget-cloud" for plugin in delivery["plugins"]}
        if len(tokens) != 4 or tokens[3] not in allowed:
            return "Plugin reinstall is limited to the approved plugin@wget-cloud list."
        return None
    if lower[:3] == ["gh", "release", "create"]:
        if phase != "tagged":
            return "GitHub Release creation requires an approved tag after installed runtime and distinct-task smoke evidence."
        allowed = {f"{plugin}-v{version}" for plugin, version in delivery["versions"].items()}
        if len(tokens) < 4 or tokens[3] not in allowed:
            return "GitHub Release is limited to an approved per-bundle tag."
        return None
    return "Unsupported delivery command is blocked."


def delivery_transition(command: str) -> str:
    tokens = shell_tokens(command)
    lower = [token.casefold() for token in tokens]
    if lower[:2] == ["git", "add"]:
        return "git-add"
    if lower[:2] == ["git", "commit"]:
        return "git-commit"
    if lower[:2] == ["git", "push"]:
        return "git-push"
    if lower[:2] == ["git", "tag"]:
        return "git-tag"
    if lower[:3] == ["codex", "plugin", "add"]:
        return "plugin-install"
    if lower[:3] == ["gh", "release", "create"]:
        return "release-create"
    return "unknown"


def delivery_postcondition_error(
    command: str, before: Dict[str, Any], after: Dict[str, Any], root: Path, requested_paths: Sequence[str]
) -> Optional[str]:
    transition = delivery_transition(command)
    if transition == "git-add":
        if after["head"] != before["head"] or after["origin_main"] != before["origin_main"]:
            return "git add changed HEAD or origin/main unexpectedly."
        if after["index_sha256"] == before["index_sha256"]:
            return "git add did not advance the Git index."
        changed_paths = {
            path for path in set(before["worktree"]) | set(after["worktree"])
            if before["worktree"].get(path) != after["worktree"].get(path)
        }
        if not changed_paths or any(not path_allowed(path, requested_paths) for path in changed_paths):
            return "git add changed worktree paths outside its exact approved arguments."
        return None
    if transition == "git-commit":
        if after["head"] == before["head"] or after["origin_main"] != before["origin_main"]:
            return "git commit did not create exactly the expected local commit state."
        if staged_paths(root):
            return "git commit left staged paths behind."
        if after["worktree"]:
            return "git commit left unstaged or untracked repository changes behind."
        return None
    if transition == "git-push":
        if after["head"] != before["head"] or after["index_sha256"] != before["index_sha256"] or after["worktree"] != before["worktree"]:
            return "git push changed local HEAD, index, or worktree unexpectedly."
        return None
    if transition in {"git-tag", "plugin-install", "release-create"}:
        if after != before:
            return f"{transition} changed the repository state unexpectedly."
        return None
    return "The completed delivery command is not an authorized transition."


def reconcile_pending_delivery(
    payload: Dict[str, Any], context: Dict[str, str], state: Dict[str, Any]
) -> Optional[str]:
    """Safely recover an approved add/commit when its PostToolUse event was lost.

    This compatibility path is deliberately limited to actions whose exact
    repository postcondition is observable locally. Pushes and release actions
    still require their normal PostToolUse/evidence transitions.
    """
    pending = state.get("pending_delivery") if isinstance(state.get("pending_delivery"), dict) else None
    if not pending:
        return None
    transition = pending.get("transition")
    if transition not in {"git-add", "git-commit"}:
        return "A delivery command is still awaiting its post-tool result; do not start another delivery transition."
    approval = state.get("delivery_approval") if isinstance(state.get("delivery_approval"), dict) else None
    root = Path(context["repo_root"])
    if not approval or pending.get("snapshot") != approval.get("delivery_snapshot") or pending.get("chain_sha256") != approval.get("delivery_chain_sha256"):
        return "The pending delivery transition no longer matches the approved rolling delivery chain."
    command = "git add" if transition == "git-add" else "git commit"
    after = delivery_snapshot(root)
    error = delivery_postcondition_error(command, pending.get("snapshot", {}), after, root, pending.get("requested_paths", []))
    if error:
        return "Pending delivery transition cannot be reconciled: " + error

    def advance(current: Dict[str, Any]) -> None:
        current_pending = current.get("pending_delivery") if isinstance(current.get("pending_delivery"), dict) else None
        current_approval = current.get("delivery_approval") if isinstance(current.get("delivery_approval"), dict) else None
        if not current_pending or not current_approval:
            return
        if current_pending.get("command_sha256") != pending.get("command_sha256") or current_pending.get("snapshot") != current_approval.get("delivery_snapshot") or current_pending.get("chain_sha256") != current_approval.get("delivery_chain_sha256"):
            return
        transitions = list(current_approval.get("delivery_transitions", []))
        transitions.append({"step": transition, "command_sha256": current_pending["command_sha256"]})
        current_approval["delivery_snapshot"] = after
        current_approval["delivery_transitions"] = transitions
        current_approval["delivery_chain_sha256"] = delivery_chain(after, transitions)
        current_approval["release_phase"] = "staged" if transition == "git-add" else "committed"
        current_approval.setdefault("release_transitions", []).append({"step": current_approval["release_phase"], "command_sha256": current_pending["command_sha256"]})
        current.pop("pending_delivery", None)

    update_state(payload, context, advance)
    return None


def handle_pre_tool(payload: Dict[str, Any], context: Dict[str, str]) -> Optional[Dict[str, Any]]:
    path, _ = state_paths(payload, context)
    state = read_state(path)
    if state.get("_corrupt"):
        return deny("Plugin maintainer approval state is corrupt; repository mutation is blocked until a new audited session.")
    if not state.get("active"):
        return None
    require_standard_service_tier(payload)
    tool = str(payload.get("tool_name") or "")
    command = tool_command(payload)
    destructive = destructive_command(command) if tool == "Bash" else None
    if destructive:
        return deny(destructive)
    if tool in {"apply_patch", "Edit", "Write"}:
        approval = state.get("change_approval")
        if not approval:
            return deny("Repository writes require an item-level Gate 1 approval.")
        paths = tool_paths(payload, context)
        if not paths:
            return deny("The hook could not resolve exact repository paths for this write.")
        if any(not path_allowed(candidate, approval.get("paths", [])) for candidate in paths):
            return deny("Write path is outside the selected Gate 1 items.")
        protected_tests = state.get("protected_tests", {})
        if any(paths_overlap(candidate, protected) for candidate in paths for protected in protected_tests):
            return deny("Write overlaps a test protected by the Test-maker hash contract.")
        baseline_dirty = state.get("baseline_dirty", {})
        if any(paths_overlap(candidate, dirty) for candidate in paths for dirty in baseline_dirty):
            return deny("Write overlaps a pre-existing user change recorded at activation.")
        return None
    if tool == "Bash":
        if UNSAFE_SHELL_SYNTAX.search(command):
            return deny(bash_read_or_validation_error(command) or "Shell composition syntax is blocked.")
        if delivery_command(command):
            reconciliation_error = reconcile_pending_delivery(payload, context, state)
            if reconciliation_error:
                return deny(reconciliation_error)
            state = read_state(path)
            violation = validate_delivery_command(command, state, Path(context["repo_root"]))
            if violation:
                return deny(violation)

            def begin_delivery_transition(current: Dict[str, Any]) -> None:
                approval = current.get("delivery_approval", {})
                tokens = shell_tokens(command)
                requested_paths = [
                    normalized for token in tokens[2:] if token != "--" and not token.startswith("-")
                    for normalized in [normalize_relative_path(token)] if normalized is not None
                ] if delivery_transition(command) == "git-add" else []
                current["pending_delivery"] = {
                    "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                    "transition": delivery_transition(command),
                    "snapshot": approval.get("delivery_snapshot"),
                    "chain_sha256": approval.get("delivery_chain_sha256"),
                    "requested_paths": requested_paths,
                }

            update_state(payload, context, begin_delivery_transition)
            return None
        violation = bash_read_or_validation_error(command)
        return deny(violation) if violation else None
    return None


def nested_exit_code(value: Any) -> Optional[int]:
    if isinstance(value, dict):
        for key in ("exit_code", "exitCode", "code"):
            if isinstance(value.get(key), int):
                return int(value[key])
        for nested in value.values():
            found = nested_exit_code(nested)
            if found is not None:
                return found
    return None


def handle_post_tool(payload: Dict[str, Any], context: Dict[str, str]) -> Optional[Dict[str, Any]]:
    path, _ = state_paths(payload, context)
    prior = read_state(path)
    if not prior.get("active"):
        return None
    command = tool_command(payload)
    event = {
        "at": int(time.time()),
        "tool": str(payload.get("tool_name") or "")[:40],
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest() if command else "",
        "exit_code": nested_exit_code(payload.get("tool_response")),
    }

    pending = prior.get("pending_delivery") if isinstance(prior.get("pending_delivery"), dict) else None
    matches_pending = (
        str(payload.get("tool_name") or "") == "Bash"
        and pending
        and pending.get("command_sha256") == event["command_sha256"]
    )
    post_error: Optional[str] = None
    after_snapshot: Optional[Dict[str, Any]] = None
    if matches_pending and event["exit_code"] == 0:
        approval = prior.get("delivery_approval", {})
        if pending.get("snapshot") != approval.get("delivery_snapshot") or pending.get("chain_sha256") != approval.get("delivery_chain_sha256"):
            post_error = "The pending delivery command no longer matches the approved delivery chain."
        else:
            after_snapshot = delivery_snapshot(Path(context["repo_root"]))
            post_error = delivery_postcondition_error(
                command, pending.get("snapshot", {}), after_snapshot, Path(context["repo_root"]), pending.get("requested_paths", [])
            )

    def record(state: Dict[str, Any]) -> None:
        events = state.setdefault("events", [])
        events.append(event)
        del events[:-100]
        current_pending = state.get("pending_delivery") if isinstance(state.get("pending_delivery"), dict) else None
        if current_pending and current_pending.get("command_sha256") == event["command_sha256"]:
            state.pop("pending_delivery", None)
            if event["exit_code"] == 0 and post_error is None and after_snapshot is not None:
                approval = state.get("delivery_approval", {})
                transitions = list(approval.get("delivery_transitions", []))
                transitions.append({"step": current_pending.get("transition", "unknown"), "command_sha256": event["command_sha256"]})
                approval["delivery_snapshot"] = after_snapshot
                approval["delivery_transitions"] = transitions
                approval["delivery_chain_sha256"] = delivery_chain(after_snapshot, transitions)
                release_steps = {
                    "git-add": "staged",
                    "git-commit": "committed",
                    "git-push": "push-pending-remote-verification",
                    "plugin-install": "installed",
                    "git-tag": "tagged",
                    "release-create": "released",
                }
                release_step = release_steps.get(current_pending.get("transition", ""))
                if release_step:
                    approval["release_phase"] = release_step
                    approval.setdefault("release_transitions", []).append({"step": release_step, "command_sha256": event["command_sha256"]})
                if current_pending.get("transition") == "git-push":
                    state["pushed_head"] = git_head(Path(context["repo_root"]))
            elif event["exit_code"] != 0 or post_error:
                approval = state.get("delivery_approval")
                if isinstance(approval, dict):
                    freeze_release(approval, post_error or "delivery command failed")

    update_state(payload, context, record)
    if matches_pending and post_error:
        return additional_context("PostToolUse", "Delivery transition failed postcondition validation and did not advance: " + post_error)
    approved_delivery_step = matches_pending and event["exit_code"] == 0 and post_error is None
    if not approved_delivery_step and state_changed_since_role(prior, Path(context["repo_root"]), {"reviewer", "qa"}):
        return additional_context("PostToolUse", "Repository revision changed; previous Reviewer and QA verdicts no longer authorize delivery.")
    return None


def state_changed_since_role(state: Dict[str, Any], root: Path, roles: Set[str]) -> bool:
    current = worktree_hash(root)
    return any(
        result.get("role") in roles and result.get("input_revision") != current
        for result in state.get("role_results", [])
        if isinstance(result, dict)
    )


def marker_json(message: str, prefix: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    lines = [line for line in message.splitlines() if line.startswith(prefix)]
    if len(lines) != 1 or not message.rstrip().endswith(lines[0]):
        return None, f"expected exactly one final {prefix.strip()} marker"
    try:
        value = json.loads(lines[0][len(prefix) :])
    except json.JSONDecodeError:
        return None, "marker contains invalid JSON"
    return (value, None) if isinstance(value, dict) else (None, "marker JSON must be an object")


def latest_role_results(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for result in state.get("role_results", []):
        if isinstance(result, dict) and result.get("role") in ROLE_VERDICTS:
            latest[str(result["role"])] = result
    return latest


def validate_proposal(value: Dict[str, Any], state: Dict[str, Any], root: Path) -> Optional[str]:
    if set(value) != {"baseline_head", "dirty_fingerprint", "items"}:
        return "proposal must contain exactly baseline_head, dirty_fingerprint, and items"
    if value.get("baseline_head") != state.get("baseline_head") or value.get("baseline_head") != git_head(root):
        return "proposal baseline_head does not match the active repository"
    if value.get("dirty_fingerprint") != state.get("baseline_dirty_fingerprint") or value.get("dirty_fingerprint") != dirty_fingerprint(root):
        return "proposal dirty_fingerprint does not match the active baseline"
    results = latest_role_results(state)
    if results.get("auditor", {}).get("verdict") != "audited" or results.get("architect", {}).get("verdict") != "proposed":
        return "Auditor=audited and Architect=proposed role artifacts are required"
    items = value.get("items")
    if not isinstance(items, list) or not items:
        return "proposal items must be a non-empty array"
    seen: Set[str] = set()
    dependencies: Dict[str, List[str]] = {}
    baseline_dirty = state.get("baseline_dirty", {})
    for item in items:
        required = {
            "id", "summary", "severity", "benefit", "effort", "evidence", "paths", "acceptance",
            "tests", "shadow_eval", "risks", "compatibility", "depends_on", "semver", "self_change",
        }
        if not isinstance(item, dict) or set(item) != required:
            return "each item must contain exactly the documented approval fields"
        item_id = item.get("id")
        if not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id) or item_id in seen:
            return "item IDs must be unique stable identifiers"
        seen.add(item_id)
        if not isinstance(item.get("summary"), str) or not item["summary"].strip() or len(item["summary"]) > 300:
            return f"item {item_id} has an invalid summary"
        if item.get("severity") not in PROPOSAL_SEVERITIES:
            return f"item {item_id} has an invalid severity"
        for field in ("benefit", "effort", "compatibility"):
            if not isinstance(item.get(field), str) or not item[field].strip() or len(item[field]) > 500:
                return f"item {item_id} has an invalid {field}"
        for field in ("evidence", "acceptance", "tests", "shadow_eval", "risks"):
            entries = item.get(field)
            if not isinstance(entries, list) or not entries or not all(
                isinstance(entry, str) and entry.strip() and len(entry) <= 1000 for entry in entries
            ):
                return f"item {item_id} must contain non-empty {field} entries"
        depends_on = item.get("depends_on")
        if not isinstance(depends_on, list) or not all(
            isinstance(dependency, str) and ITEM_ID.fullmatch(dependency) for dependency in depends_on
        ) or len(depends_on) != len(set(depends_on)):
            return f"item {item_id} has invalid dependencies"
        if item_id in depends_on:
            return f"item {item_id} cannot depend on itself"
        dependencies[item_id] = depends_on
        if item.get("semver") not in SEMVER_IMPACTS:
            return f"item {item_id} has an invalid SemVer impact"
        if not isinstance(item.get("self_change"), bool):
            return f"item {item_id} must declare self_change as a boolean"
        if not isinstance(item.get("paths"), list) or not item["paths"]:
            return f"item {item_id} must contain paths"
        normalized = [normalize_relative_path(path) if isinstance(path, str) else None for path in item["paths"]]
        if any(path is None for path in normalized) or len(normalized) != len(set(normalized)):
            return f"item {item_id} contains invalid or duplicate paths"
        if any(paths_overlap(path or "", dirty) for path in normalized for dirty in baseline_dirty):
            return f"item {item_id} overlaps a pre-existing dirty path"
        self_path = any((path or "").startswith("plugins/wget-cloud-plugin-maintainer/") for path in normalized)
        if self_path and item.get("self_change") is not True:
            return f"item {item_id} changes the maintainer but self_change is not true"
        item["paths"] = normalized
    for item_id, item_dependencies in dependencies.items():
        unknown = set(item_dependencies) - seen
        if unknown:
            return f"item {item_id} depends on unknown items"
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def has_cycle(item_id: str) -> bool:
        if item_id in visiting:
            return True
        if item_id in visited:
            return False
        visiting.add(item_id)
        if any(has_cycle(dependency) for dependency in dependencies[item_id]):
            return True
        visiting.remove(item_id)
        visited.add(item_id)
        return False

    if any(has_cycle(item_id) for item_id in dependencies):
        return "proposal item dependencies contain a cycle"
    return None


def validate_delivery(value: Dict[str, Any], state: Dict[str, Any], root: Path) -> Optional[str]:
    required = {"proposal_id", "worktree_hash", "target", "commits", "versions", "plugins", "ci_evidence", "runtime_evidence"}
    if set(value) != required:
        return "delivery must contain exactly the documented fields"
    approval = state.get("change_approval")
    if not approval or value.get("proposal_id") != approval.get("proposal_id"):
        return "delivery is not bound to the approved change proposal"
    live_hash = worktree_hash(root)
    if value.get("worktree_hash") != live_hash:
        return "delivery worktree_hash does not match the live repository"
    if value.get("target") != "origin/main":
        return "delivery target must be origin/main"
    if value.get("ci_evidence") is not True or value.get("runtime_evidence") is not True:
        return "GitHub CI and installed-runtime evidence are required before Gate 2"
    results = latest_role_results(state)
    for role, verdict in REQUIRED_DELIVERY_VERDICTS.items():
        if results.get(role, {}).get("verdict") != verdict:
            return f"required role gate missing: {role}={verdict}"
    for role in ("reviewer", "qa"):
        if results[role].get("input_revision") != live_hash:
            return f"{role} verdict is stale for the live worktree"
    for protected_path, expected_hash in state.get("protected_tests", {}).items():
        if file_fingerprint(root / protected_path) != expected_hash:
            return f"protected test changed after the Test-maker gate: {protected_path}"
    commits = value.get("commits")
    if not isinstance(commits, list) or not commits:
        return "delivery commits must be a non-empty array"
    approved_paths = approval.get("paths", [])
    covered: Set[str] = set()
    for entry in commits:
        if not isinstance(entry, dict) or set(entry) != {"message", "paths"}:
            return "each commit must contain exactly message and paths"
        if not isinstance(entry.get("message"), str) or not entry["message"].strip() or len(entry["message"]) > 100:
            return "commit subjects must be non-empty and <= 100 characters"
        paths = entry.get("paths")
        if not isinstance(paths, list) or not paths:
            return "each commit must contain paths"
        for raw in paths:
            normalized = normalize_relative_path(raw) if isinstance(raw, str) else None
            if normalized is None or not path_allowed(normalized, approved_paths):
                return "commit plan contains a path outside Gate 1"
            covered.add(normalized)
        entry["paths"] = [normalize_relative_path(path) for path in paths]
    changed = set(dirty_snapshot(root))
    if any(not path_allowed(path, covered) for path in changed):
        return "commit plan does not cover every changed path"
    versions = value.get("versions")
    plugins = value.get("plugins")
    if not isinstance(versions, dict) or not versions or not isinstance(plugins, list) or not plugins:
        return "versions and plugins must be non-empty"
    if set(plugins) != set(versions) or len(plugins) != len(set(plugins)):
        return "plugins and versions must contain the same unique names"
    for plugin, version in versions.items():
        if not isinstance(plugin, str) or not ITEM_ID.fullmatch(plugin) or not isinstance(version, str) or not SEMVER.fullmatch(version):
            return "plugin names and versions are invalid"
        manifest = root / "plugins" / plugin / ".codex-plugin" / "plugin.json"
        try:
            actual = json.loads(manifest.read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError, AttributeError):
            return f"cannot read manifest for {plugin}"
        if actual != version:
            return f"delivery version does not match manifest for {plugin}"
    value["approved_paths"] = approved_paths
    value["origin_main"] = origin_main(root)
    value["external_evidence"] = external_evidence_binding(root, value["ci_evidence"], value["runtime_evidence"])
    snapshot = delivery_snapshot(root)
    value["delivery_snapshot"] = snapshot
    value["delivery_transitions"] = []
    value["delivery_chain_sha256"] = delivery_chain(snapshot, [])
    return None


def handle_stop(payload: Dict[str, Any], context: Dict[str, str]) -> Optional[Dict[str, Any]]:
    path, _ = state_paths(payload, context)
    state = read_state(path)
    if not state.get("active"):
        return None
    message = str(payload.get("last_assistant_message") or "")
    turn_id = str(payload.get("turn_id") or "unknown")
    root = Path(context["repo_root"])
    if EVIDENCE_MARKER in message:
        value, error = marker_json(message, EVIDENCE_MARKER)
        if not error and value:
            error = verify_release_evidence(state, value, root)
        if error:
            def freeze(state_value: Dict[str, Any]) -> None:
                approval = state_value.get("delivery_approval")
                if isinstance(approval, dict):
                    freeze_release(approval, error or "external evidence rejected")

            update_state(payload, context, freeze)
            return {"decision": "block", "reason": "External release evidence rejected: " + error + ". Delivery is frozen; create a recovery proposal."}

        def record_evidence(state_value: Dict[str, Any]) -> None:
            record_error = verify_release_evidence(state_value, value, root)
            if record_error:
                approval = state_value.get("delivery_approval")
                if isinstance(approval, dict):
                    freeze_release(approval, record_error)

        update_state(payload, context, record_evidence)
        return {"decision": "block", "reason": "External evidence recorded for the next release phase. Continue only with the exact approved transition."}
    if PROPOSAL_MARKER in message:
        value, error = marker_json(message, PROPOSAL_MARKER)
        if not error and value:
            error = validate_proposal(value, state, root)
        if error:
            return {"decision": "block", "reason": "Maintenance proposal rejected: " + error + "."}
        proposal_id = canonical_hash(
            {"session": safe_session_id(payload.get("session_id"), context["repo_root"]), "turn": turn_id, "proposal": value}
        )[:16]

        def register(proposal_state: Dict[str, Any]) -> None:
            proposal_state["proposal"] = minimal_proposal_state(value, proposal_id, turn_id)
            proposal_state["change_approval"] = None
            proposal_state["delivery"] = None
            proposal_state["delivery_proposal"] = None
            proposal_state["delivery_approval"] = None
            proposal_state["pending_delivery"] = None

        update_state(payload, context, register)
        return {
            "decision": "block",
            "reason": (
                f"Proposal registered as {proposal_id}. Remove the machine marker, repeat the brief item summary, and ask the user to reply "
                f"APPROVE_WGC_PLUGIN_CHANGE={proposal_id}:<comma-separated-item-ids>. Do not mutate files yet."
            ),
        }
    if DELIVERY_MARKER in message:
        value, error = marker_json(message, DELIVERY_MARKER)
        if not error and value:
            error = validate_delivery(value, state, root)
        if error:
            return {"decision": "block", "reason": "Maintenance delivery rejected: " + error + "."}
        delivery_id = canonical_hash(
            {"session": safe_session_id(payload.get("session_id"), context["repo_root"]), "turn": turn_id, "delivery": value}
        )[:16]

        def register_delivery(delivery_state: Dict[str, Any]) -> None:
            proposal = {**value, "id": delivery_id, "registered_turn": turn_id, "registered_at": int(time.time())}
            delivery_state["delivery"] = proposal
            delivery_state["delivery_proposal"] = proposal
            delivery_state["delivery_approval"] = None
            delivery_state["pending_delivery"] = None

        update_state(payload, context, register_delivery)
        return {
            "decision": "block",
            "reason": (
                f"Delivery registered as {delivery_id}. Remove the machine marker, repeat the exact commits, versions, target, CI/runtime, reinstall, smoke, tag, and release plan, then ask the user to reply "
                f"APPROVE_WGC_PLUGIN_DELIVERY={delivery_id}. Do not deliver yet."
            ),
        }
    return None


def handle_session_end(payload: Dict[str, Any], context: Dict[str, str]) -> None:
    def close(state: Dict[str, Any]) -> None:
        state["active"] = False
        state["change_approval"] = None
        state["delivery_approval"] = None
        state["closed_at"] = int(time.time())

    update_state(payload, context, close)
    return None


HANDLERS: Dict[str, Callable[[Dict[str, Any], Dict[str, str]], Optional[Dict[str, Any]]]] = {
    "session-start": handle_session_start,
    "prompt-submit": handle_prompt_submit,
    "subagent-start": handle_subagent_start,
    "subagent-stop": handle_subagent_stop,
    "pre-tool": handle_pre_tool,
    "post-tool": handle_post_tool,
    "stop": handle_stop,
    "session-end": handle_session_end,
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in HANDLERS:
        sys.stderr.write("usage: maintainer_hooks.py <" + "|".join(sorted(HANDLERS)) + ">\n")
        return 2
    payload = read_input()
    context = detect_context(payload.get("cwd"))
    if context is None:
        return 0
    try:
        emit(HANDLERS[sys.argv[1]](payload, context))
        return 0
    except ServiceTierPolicyError as error:
        sys.stderr.write(f"{type(error).__name__}: {error}\n")
        return 2
    except Exception as error:  # fail closed for active maintenance tool use
        if sys.argv[1] == "pre-tool":
            emit(deny(f"Plugin maintainer approval check failed internally: {type(error).__name__}."))
            return 0
        sys.stderr.write(f"plugin maintainer hook warning: {type(error).__name__}: {error}\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
