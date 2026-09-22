#!/usr/bin/env python3
"""Lifecycle hooks for the WGC implementation plugin.

The hook runner intentionally uses only the Python standard library. It is
quiet outside recognized Wget Cloud workspaces and stores transient state only
under PLUGIN_DATA.
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
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple


PROJECTS: Dict[str, Dict[str, Any]] = {
    "frontend": {
        "docs": ["AGENTS.md", "README.md", "BUSINESS_LOGIC.md", "ARCHITECTURE.md"],
        "checks": ["npm test -- --coverage", "npm run type-check", "npm run lint", "npm run build"],
    },
    "backend": {
        "docs": ["AGENTS.md", "README.md", "ARCHITECTURE.md", "BUSINESS_LOGIC.md", "service-local docs"],
        "checks": ["targeted Jest --coverage", "service build", "proto/Prisma checks when applicable"],
    },
    "wget-cloud-front-lib": {
        "docs": ["AGENTS.md", "README.md", "BUSINESS_LOGIC.md", "ARCHITECTURE.md"],
        "checks": ["npm run typecheck", "npm run build", "pack/export and consumer checks"],
    },
    "wget-cloud-site": {
        "docs": ["AGENTS.md", "README.md", "BUSINESS_LOGIC.md", "ARCHITECTURE.md"],
        "checks": ["pnpm test", "pnpm lint", "pnpm type-check", "pnpm build", "guard scripts"],
    },
    "k8s": {
        "docs": ["../AGENTS.md", "README.md", "infrastructure/k8s/docs/ARCHITECTURE.md"],
        "checks": ["make gitops-render", "make validate", "focused GitOps/resource tests"],
    },
}

IMPLEMENTATION_INTENT = re.compile(
    r"(?:\$(?:wgc-implementation)|\bwgc-implementation\b|"
    r"(?:^|[\n.!?]\s*)(?:(?:please|need you to|can you)\s+)?"
    r"(?:implement|fix|refactor|deploy|build|add|change|create)\b|"
    r"(?:^|[\n.!?]\s*)(?:пожалуйста[,\s]+)?(?:сделай|реализуй|исправь|почини|добавь|измени|"
    r"переделай|отрефактори|задеплой|разверни|разработай)\b|"
    r"\b(?:нужно|надо)\s+(?:сделать|реализовать|исправить|починить|добавить|изменить|"
    r"переделать|отрефакторить|задеплоить|развернуть|разработать)\b)",
    re.IGNORECASE,
)
IMPLEMENTATION_EXPLICIT = re.compile(r"(?:\$wgc-implementation|\bwgc-implementation\b)", re.IGNORECASE)
BUGFIX_EXPLICIT = re.compile(r"(?:\$wgc-bugfix|\bwgc-bugfix\b)", re.IGNORECASE)
TASK_CREATION_EXPLICIT = re.compile(r"(?:\$wgc-task-creation|\bwgc-task-creation\b)", re.IGNORECASE)
EPIC_IMPLEMENTATION_EXPLICIT = re.compile(
    r"(?:\$wgc-epic-implementation|\bwgc-epic-implementation\b)", re.IGNORECASE
)
BUGFIX_ACTION = re.compile(
    r"\b(?:fix|repair|resolve|debug|исправ\w*|почин\w*|устран\w*|разобрат\w*|найт\w*\s+причин\w*)\b",
    re.IGNORECASE,
)
BUG_SIGNAL = re.compile(
    r"(?:\b(?:bug|defect|regression|crash|exception|failure|failed|broken|wrong|incorrect|stale|"
    r"duplicate|missing|timeout|incident|outage|"
    r"not\s+working|doesn['’]?t\s+work|5\d\d|4\d\d)\b|"
    r"\b(?:баг\w*|дефект\w*|регресс\w*|ошиб\w*|исключени\w*|инцидент\w*|таймаут\w*|"
    r"пад\w*|сломал\w*|сбо\w*|неверн\w*|устаревш\w*|дублиру\w*|пропада\w*)\b|"
    r"не\s+(?:работа|сохраня|загружа|открыва|отобража|обновля|созда|удаля|отправля|подключа)\w*)",
    re.IGNORECASE,
)
DEPLOYMENT_FOLLOWUP = re.compile(
    r"\b(?:deploy(?:ment)?|rollout|release|ship|депло\w*|задепло\w*|раскат\w*|релиз\w*|разверн\w*)\b",
    re.IGNORECASE,
)
TASK_CREATION_SIGNAL = re.compile(
    r"(?=.*\b(?:youtrack|epic|backlog|issue|issues|эпик\w*|задач\w*|бэклог\w*)\b)"
    r"(?=.*\b(?:create|add|publish|populate|decompose|prioritize|созда\w*|добав\w*|сформир\w*|"
    r"декомпоз\w*|приоритиз\w*|завест\w*)\b)",
    re.IGNORECASE | re.DOTALL,
)
EPIC_IMPLEMENTATION_SIGNAL = re.compile(
    r"(?=.*\b(?:implement|deliver|execute|реализ\w*|имплемент\w*|выполн\w*)\b)"
    r"(?=.*\b(?:epic|task\s+pool|pool\s+of\s+tasks|эпик\w*|пул\w*\s+задач|"
    r"задач\w*\s+из\s+проект\w*)\b)",
    re.IGNORECASE | re.DOTALL,
)
PROJECT_TARGET_SIGNAL = re.compile(
    r"(?:https://youtrack\.wget-cloud\.ru/|\byoutrack\b|\b(?:PRD|BE|FE|SITE|WGET|FL|K8S)-[1-9]\d*\b)",
    re.IGNORECASE,
)
PROJECT_MUTATION_SIGNAL = re.compile(
    r"\b(?:create|add|publish|populate|update|sync|созда\w*|добав\w*|опубликов\w*|завест\w*|"
    r"обнов\w*|синхрониз\w*)\b",
    re.IGNORECASE,
)
PROJECT_MUTATION_OPT_OUT = re.compile(
    r"(?:\b(?:do\s+not|don't|without)\s+(?:creat|add|publish|updat|sync|mutat|chang)\w*\b|"
    r"\b(?:не|без)\s+(?:созда\w*|добав\w*|публикац\w*|обнов\w*|синхрониз\w*|измен\w*)\b)",
    re.IGNORECASE,
)
TEST_PATH = re.compile(r"(?:^|/)(?:tests?|__tests__|e2e)(?:/|$)|(?:\.(?:test|spec)\.[^.]+$)", re.IGNORECASE)
DOC_PATH = re.compile(r"(?:^|/)(?:docs?|README|AGENTS|ARCHITECTURE|BUSINESS_LOGIC)(?:[./_-]|$)", re.IGNORECASE)
SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".less",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sass",
    ".scss",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}
# Keep the public hook entry point stable, including importlib-based validators.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime.contracts import *
from runtime import teams, evidence, inventory, epic_stages, telemetry
from runtime.state import migrate_state_v4


def bugfix_routes(prompt: str) -> Dict[str, bool]:
    """Return privacy-safe routing flags without persisting the prompt."""
    patterns = {
        "ui": r"\b(?:ui|ux|browser|page|form|modal|pwa|service[ -]?worker|websocket|realtime|"
        r"интерфейс\w*|браузер\w*|страниц\w*|форм\w*|модал\w*)\b",
        "security": r"\b(?:auth|oauth|jwt|session|rbac|permission|acl|tenant|isolation|security|"
        r"авторизац\w*|аутентификац\w*|доступ\w*|разрешени\w*|рол(?:ь|и|ей|ям|ями|ях)|тенант\w*|безопасност\w*)\b",
        "contract": r"\b(?:api|rest|grpc|proto(?:buf)?|schema|contract|openapi|swagger|front-lib|"
        r"контракт\w*|схем\w*|эндпоинт\w*)\b",
        "incident": r"\b(?:prod(?:uction)?|staging|incident|outage|degradation|crash|timeout|5\d\d|"
        r"прод\w*|инцидент\w*|авари\w*|падени\w*|таймаут\w*|деградац\w*)\b",
        "gitops": r"\b(?:k8s|kubernetes|helm|argo(?:\s*cd)?|gitops|manifest|values|ci/?cd|"
        r"кубернетес\w*|манифест\w*)\b",
        "deployment": r"\b(?:deploy(?:ment)?|rollout|release|ship|депло\w*|задепло\w*|раскат\w*|релиз\w*|разверн\w*)\b",
    }
    return {name: bool(re.search(pattern, prompt, re.IGNORECASE)) for name, pattern in patterns.items()}


def project_routes(prompt: str, profile: str) -> Dict[str, bool]:
    targeted = bool(PROJECT_TARGET_SIGNAL.search(prompt) or profile in {"task-creation", "epic-implementation"})
    mutation_opt_out = bool(PROJECT_MUTATION_OPT_OUT.search(prompt))
    mutation_requested = bool(
        targeted
        and not mutation_opt_out
        and (
            PROJECT_MUTATION_SIGNAL.search(prompt)
            or profile == "epic-implementation"
            or (profile in {"implementation", "bugfix"} and (IMPLEMENTATION_INTENT.search(prompt) or BUGFIX_ACTION.search(prompt)))
        )
    )
    return {
        "project_targeted": targeted,
        "mutation_requested": mutation_requested,
    }


def workflow_profile(prompt: str, active_profile: Optional[str] = None) -> Optional[Tuple[str, str]]:
    if BUGFIX_EXPLICIT.search(prompt):
        return "bugfix", "explicit"
    if EPIC_IMPLEMENTATION_EXPLICIT.search(prompt):
        return "epic-implementation", "explicit"
    if TASK_CREATION_EXPLICIT.search(prompt):
        return "task-creation", "explicit"
    if IMPLEMENTATION_EXPLICIT.search(prompt):
        return "implementation", "explicit"
    if active_profile == "bugfix" and (IMPLEMENTATION_INTENT.search(prompt) or DEPLOYMENT_FOLLOWUP.search(prompt)):
        return "bugfix", "followup"
    if active_profile == "epic-implementation" and (
        IMPLEMENTATION_INTENT.search(prompt) or PROJECT_MUTATION_SIGNAL.search(prompt)
    ):
        return "epic-implementation", "followup"
    if active_profile == "task-creation" and PROJECT_MUTATION_SIGNAL.search(prompt):
        return "task-creation", "followup"
    if BUGFIX_ACTION.search(prompt) and BUG_SIGNAL.search(prompt):
        return "bugfix", "inferred"
    if EPIC_IMPLEMENTATION_SIGNAL.search(prompt):
        return "epic-implementation", "inferred"
    if TASK_CREATION_SIGNAL.search(prompt):
        return "task-creation", "inferred"
    if IMPLEMENTATION_INTENT.search(prompt):
        return "implementation", "inferred"
    return None


def read_input() -> Dict[str, Any]:
    try:
        raw = sys.stdin.read()
        value = json.loads(raw) if raw.strip() else {}
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def emit(value: Optional[Dict[str, Any]]) -> None:
    if value:
        sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def run(command: Sequence[str], cwd: Path, timeout: float = 2.0) -> Tuple[int, str]:
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
    current = cwd.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def is_coordinator(path: Path) -> bool:
    modules = path / ".gitmodules"
    if not modules.is_file():
        return False
    try:
        text = modules.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return all(f"path = {name}" in text for name in PROJECTS)


def coordinator_root(start: Path) -> Optional[Path]:
    for candidate in (start, *start.parents):
        if is_coordinator(candidate):
            return candidate.resolve()
    return None


def detect_context(raw_cwd: Any) -> Optional[Dict[str, Any]]:
    try:
        cwd = Path(str(raw_cwd or os.getcwd())).expanduser().resolve()
    except OSError:
        return None
    if not cwd.exists():
        return None

    repo = git_root(cwd)
    if repo is None:
        return None
    coordinator = coordinator_root(repo)

    if is_coordinator(repo):
        project = "coordinator"
        coordinator = repo
    elif repo.name in PROJECTS:
        project = repo.name
    else:
        return None

    return {
        "cwd": str(cwd),
        "repo_root": str(repo),
        "coordinator_root": str(coordinator) if coordinator else None,
        "project": project,
    }


def repo_status(repo: Path) -> str:
    code, output = run(["git", "status", "-sb", "--untracked-files=no"], repo, timeout=3.0)
    if code != 0 or not output:
        return "status unavailable"
    lines = output.splitlines()
    branch = lines[0]
    changed = max(0, len(lines) - 1)
    return f"{branch}; tracked changes: {changed}"


def context_text(context: Dict[str, Any]) -> str:
    project = context["project"]
    repo = Path(context["repo_root"])
    if project == "coordinator":
        docs = "root AGENTS.md, then nested AGENTS.md and required docs for each affected submodule"
        checks = "run checks separately in each affected Git repository"
    else:
        config = PROJECTS[project]
        docs = ", ".join(config["docs"])
        checks = "; ".join(config["checks"])
    return (
        f"WGC workspace detected. Current project: {project}. Git: {repo_status(repo)}. "
        f"Before editing read: {docs}. Expected verification: {checks}. "
        "Treat the coordinator and all submodules as separate repositories; preserve pre-existing changes."
    )


def data_root() -> Path:
    configured = os.environ.get("PLUGIN_DATA")
    root = Path(configured).expanduser() if configured else Path(tempfile.gettempdir()) / "wgc-implementation-plugin-data"
    target = root / "hook-state"
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_session_id(value: Any, cwd: str) -> str:
    raw = str(value or "")
    if raw and re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", raw):
        return raw
    return hashlib.sha256(f"{raw}:{cwd}".encode("utf-8")).hexdigest()[:32]


def state_paths(payload: Dict[str, Any], context: Dict[str, Any]) -> Tuple[Path, Path]:
    session_id = safe_session_id(payload.get("session_id"), context["cwd"])
    state = data_root() / f"{session_id}.json"
    return state, state.with_suffix(".lock")


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    windows_lock = False
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
                windows_lock = True
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
        if os.name == "nt" and windows_lock:
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
        if isinstance(value, dict):
            return value
        return {
            "version": STATE_VERSION,
            "active": True,
            "state_health": "malformed",
            "repository_reaudit_required": True,
        }
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {
            "version": STATE_VERSION,
            "active": True,
            "state_health": "malformed",
            "repository_reaudit_required": True,
        }


# Compatibility name for external callers; migration now establishes v4.
migrate_state_v3 = migrate_state_v4


def update_state(
    payload: Dict[str, Any],
    context: Dict[str, Any],
    updater: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    path, lock = state_paths(payload, context)
    with file_lock(lock):
        existed = path.exists()
        state = read_state(path)
        if existed and state.get("version") is None:
            state = {
                "version": STATE_VERSION,
                "active": True,
                "state_health": "malformed",
                "repository_reaudit_required": True,
            }
        state = migrate_state_v4(state)
        state["version"] = STATE_VERSION
        state.setdefault("active", False)
        state.setdefault("activation", "none")
        state.setdefault("profile", "implementation")
        state.setdefault("bugfix_routes", {})
        state.setdefault("project_routes", {})
        state.setdefault("commands", [])
        state.setdefault("verification", {})
        state.setdefault("touched_paths", [])
        state.setdefault("baseline_dirty", {})
        state.setdefault("stop_turns", [])
        state.setdefault("subagent_results", [])
        state.setdefault("test_assessments", [])
        state.setdefault("selected_items", [])
        state.setdefault("repository_gates", [])
        state.setdefault("state_health", "healthy")
        state.setdefault("repository_reaudit_required", False)
        state["context"] = context
        state["updated_at"] = int(time.time())
        updater(state)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
        return state


def git_status_paths(repo: Path) -> Dict[str, str]:
    code, output = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], repo, timeout=4.0)
    if code != 0 or not output:
        return {}
    result: Dict[str, str] = {}
    entries = output.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry or len(entry) < 4:
            continue
        status = entry[:2]
        paths = [entry[3:]]
        if any(value in {"R", "C"} for value in status) and index < len(entries):
            original = entries[index]
            index += 1
            if original:
                paths.append(original)
        for path in paths:
            candidate = repo / path
            fingerprint = "missing"
            try:
                if candidate.is_file():
                    stat = candidate.stat()
                    if stat.st_size <= 8 * 1024 * 1024:
                        digest = hashlib.sha256()
                        with candidate.open("rb") as handle:
                            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                                digest.update(chunk)
                        fingerprint = digest.hexdigest()
                    else:
                        fingerprint = f"large:{stat.st_size}:{stat.st_mtime_ns}"
                elif candidate.is_dir():
                    fingerprint = "directory"
            except OSError:
                fingerprint = "unreadable"
            result[path] = f"{status}:{fingerprint}"
    return result


def workspace_repositories(context: Dict[str, Any]) -> Dict[str, Path]:
    coordinator = context.get("coordinator_root")
    if not coordinator:
        return {context["project"]: Path(context["repo_root"])}
    root = Path(coordinator)
    repos: Dict[str, Path] = {"coordinator": root}
    for name in PROJECTS:
        candidate = root / name
        if candidate.exists():
            repos[name] = candidate
    return repos


def workspace_snapshot(context: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    return {name: git_status_paths(path) for name, path in workspace_repositories(context).items()}


def workspace_identity(context: Dict[str, Any]) -> str:
    heads: Dict[str, str] = {}
    for name, repo in workspace_repositories(context).items():
        code, output = run(["git", "rev-parse", "HEAD"], repo, timeout=2.0)
        heads[name] = output.splitlines()[-1] if code == 0 and output else "unborn"
    material = {"heads": heads, "dirty": workspace_snapshot(context)}
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def snapshot_since_baseline(
    current: Dict[str, Dict[str, str]], baseline: Any
) -> Dict[str, Dict[str, str]]:
    baseline_map = baseline if isinstance(baseline, dict) else {}
    result: Dict[str, Dict[str, str]] = {}
    for project in set(current) | set(baseline_map):
        paths = current.get(project, {})
        previous = baseline_map.get(project, {})
        previous = previous if isinstance(previous, dict) else {}
        changed = {path: status for path, status in paths.items() if previous.get(path) != status}
        changed.update({path: 'removed' for path in previous if path not in paths})
        if changed:
            result[project] = changed
    return result


def additional_context(event: str, message: str, system_message: Optional[str] = None) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": message,
        }
    }
    if system_message:
        output["systemMessage"] = system_message
    return output


def deny_tool(reason: str) -> Dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def tool_command(payload: Dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    value = tool_input.get("command", tool_input.get("cmd", ""))
    return value if isinstance(value, str) else ""


def resolve_bash_workdir(
    payload: Dict[str, Any], context: Dict[str, Any]
) -> Tuple[Optional[Path], Optional[str]]:
    """Resolve a supplied runner workdir for ordinary policy, or use the event cwd."""
    current = Path(context["cwd"]).resolve()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or "workdir" not in tool_input:
        return current, None

    raw = tool_input.get("workdir")
    if not isinstance(raw, str) or not raw.strip():
        return None, "Bash workdir is invalid or outside the active WGC workspace; the command is blocked."

    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = current / candidate
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None, "Bash workdir is invalid or outside the active WGC workspace; the command is blocked."
    if not resolved.is_dir() or not path_within(resolved, workspace_boundary(context)):
        return None, "Bash workdir is invalid or outside the active WGC workspace; the command is blocked."
    return resolved, None


def command_record(command: str) -> Dict[str, str]:
    known = re.search(
        r"(?:^|[;&|]\s*)(?:[A-Z_][A-Z0-9_]*=[^\s]+\s+)*"
        r"(npm|pnpm|npx|yarn|make|git|kubectl|python3?|node|cargo|go|mvn|gradle|docker|helm|argocd|terraform)\b",
        command,
        re.IGNORECASE,
    )
    return {
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "runner": known.group(1).lower() if known else "shell",
    }


def patch_paths(command: str) -> List[str]:
    paths: List[str] = []
    for match in re.finditer(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$", command, re.MULTILINE):
        value = match.group(1).strip()
        if value and value not in paths:
            paths.append(value)
    return paths


def normalize_patch_path(raw: str, context: Dict[str, Any]) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path(context["cwd"]) / candidate
    return candidate.resolve(strict=False)


def path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def canonical_absolute_file(value: Any) -> Optional[Path]:
    try:
        candidate = Path(value)
    except (TypeError, ValueError):
        return None
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    if not resolved.is_file():
        return None
    return resolved


def workspace_boundary(context: Dict[str, Any]) -> Path:
    coordinator = context.get("coordinator_root")
    return Path(coordinator or context["repo_root"]).resolve()


def canonical_bootstrap_repo(context: Dict[str, Any]) -> Optional[Path]:
    if context.get("coordinator_root"):
        return (Path(context["coordinator_root"]) / "k8s").resolve()
    if context.get("project") == "k8s":
        return Path(context["repo_root"]).resolve()
    return None


def suspicious_secret(command: str) -> bool:
    if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", command):
        return True
    if re.search(r"\bAKIA[0-9A-Z]{16}\b", command):
        return True
    if re.search(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b", command):
        return True
    if re.search(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{16,}\b", command):
        return True
    return False


def consume_known_options(
    args: Sequence[str],
    value_options: Set[str],
    boolean_options: Set[str],
    attached_value: Optional[re.Pattern[str]] = None,
) -> Optional[int]:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            return index + 1
        if attached_value is not None and attached_value.fullmatch(token):
            index += 1
            continue
        option = token.split("=", 1)[0]
        if option in value_options:
            if "=" in token:
                index += 1
            elif index + 1 < len(args):
                index += 2
            else:
                return None
            continue
        if token in boolean_options:
            index += 1
            continue
        if token.startswith("-"):
            return None
        return index
    return index


def short_option_cluster(
    token: str,
    following: Sequence[str],
    boolean_options: Set[str],
    value_options: Set[str],
) -> Optional[Tuple[int, Optional[str], Optional[str]]]:
    if not token.startswith("-") or token.startswith("--") or len(token) < 2 or len(token) > 32:
        return None
    for offset, option in enumerate(token[1:], start=1):
        if option in boolean_options:
            continue
        if option not in value_options:
            return None
        attached_value = token[offset + 1 :]
        if attached_value:
            return 1, option, attached_value
        if following:
            return 2, option, following[0]
        return None
    return 1, None, None


def normalized_env_arguments(args: Sequence[str]) -> Optional[List[str]]:
    current = list(args)
    for _ in range(4):
        index = 0
        expanded = False
        while index < len(current):
            token = current[index]
            if token == "--":
                return current[index + 1 :]
            option = token.split("=", 1)[0]
            if option == "--split-string":
                if "=" in token:
                    value = token.split("=", 1)[1]
                    consumed = 1
                elif index + 1 < len(current):
                    value = current[index + 1]
                    consumed = 2
                else:
                    return None
                try:
                    split_args = shlex.split(value, posix=True)
                except ValueError:
                    return None
                current = current[:index] + split_args + current[index + consumed :]
                expanded = True
                break
            if option in {"--chdir", "--unset"}:
                if "=" in token:
                    index += 1
                elif index + 1 < len(current):
                    index += 2
                else:
                    return None
                continue
            if token in {"-0", "--null", "-i", "--ignore-environment"}:
                index += 1
                continue
            if token.startswith("-") and not token.startswith("--"):
                cluster = short_option_cluster(token, current[index + 1 :], {"0", "i"}, {"C", "S", "u"})
                if cluster is None:
                    return None
                consumed, value_option, value = cluster
                if value_option == "S":
                    try:
                        split_args = shlex.split(value or "", posix=True)
                    except ValueError:
                        return None
                    current = current[:index] + split_args + current[index + consumed :]
                    expanded = True
                    break
                index += consumed
                continue
            if token.startswith("-"):
                return None
            return current[index:]
        if not expanded:
            return []
    return None


def normalized_shell_command(tokens: Sequence[str]) -> Tuple[Optional[str], List[str], bool]:
    current = list(tokens)
    generic_assignment = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.DOTALL)
    approval_assignment = re.compile(r"WGC_[A-Z0-9_]+_APPROVED=1")
    approval_found = False
    for _ in range(6):
        index = 0
        while index < len(current) and generic_assignment.fullmatch(current[index]):
            approval_found = approval_found or bool(approval_assignment.fullmatch(current[index]))
            index += 1
        if index >= len(current):
            return None, [], approval_found
        raw_executable = current[index]
        executable = Path(raw_executable).name.lower()
        args = current[index + 1 :]
        if executable == "env":
            nested = normalized_env_arguments(args)
            if nested is None or not nested:
                return raw_executable, args, approval_found
            current = nested
            continue
        elif executable == "sudo":
            next_index = consume_known_options(
                args,
                {"-C", "-g", "-h", "-p", "-R", "-T", "-u", "--chdir", "--group", "--host", "--prompt", "--role", "--type", "--user"},
                {"-b", "-E", "-e", "-H", "-K", "-k", "-n", "-S", "-v", "--background", "--edit", "--help", "--login", "--non-interactive", "--preserve-env", "--reset-timestamp", "--remove-timestamp", "--stdin", "--validate"},
            )
        elif executable == "command":
            if args[:1] and args[0] in {"-v", "-V"}:
                return raw_executable, args, approval_found
            next_index = consume_known_options(args, set(), {"-p"})
        elif executable == "nohup":
            next_index = consume_known_options(args, set(), set())
        elif executable == "time":
            next_index = consume_known_options(
                args,
                {"-f", "--format", "-o", "--output"},
                {"-a", "--append", "-p", "--portability", "-q", "--quiet", "-v", "--verbose"},
            )
        else:
            return raw_executable, args, approval_found
        if next_index is None or next_index >= len(args):
            return raw_executable, args, approval_found
        current = args[next_index:]
    return None, [], approval_found


def has_wgc_approval_assignment(command: str, depth: int = 0) -> bool:
    if depth > 2:
        return False
    try:
        lexer = shlex.shlex(command.replace("$'1'", "1"), posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return False

    current: List[str] = []
    segments: List[List[str]] = []
    for token in tokens:
        if re.fullmatch(r"[;&|]+", token):
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)

    for segment in segments:
        executable, args, approval_found = normalized_shell_command(segment)
        if approval_found:
            return True
        if executable is not None and Path(executable).name.lower() in {"bash", "sh", "zsh", "dash", "ksh"}:
            for arg_index, arg in enumerate(args[:-1]):
                if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):
                    if has_wgc_approval_assignment(args[arg_index + 1], depth + 1):
                        return True
                    break
    return False


BOOTSTRAP_APPROVAL = "WGC_GITOPS_BOOTSTRAP_APPROVED=1"
BOOTSTRAP_SECRET_NAME = "wget-cloud-k8s-repository"
BOOTSTRAP_REPOSITORY_URL = "ssh://git@github.com/wget-cloud/k8s"

def option_values(args: Sequence[str], names: Set[str]) -> List[str]:
    values: List[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        option = token.split("=", 1)[0]
        if option not in names:
            index += 1
            continue
        if "=" in token:
            values.append(token.split("=", 1)[1])
            index += 1
        elif index + 1 < len(args):
            values.append(args[index + 1])
            index += 2
        else:
            values.append("")
            index += 1
    return values


def exact_option(args: Sequence[str], names: Set[str], expected: str) -> bool:
    return option_values(args, names) == [expected]


def command_positionals(
    args: Sequence[str], value_options: Set[str], boolean_options: Set[str]
) -> Optional[List[str]]:
    positionals: List[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        option = token.split("=", 1)[0]
        if option in value_options:
            if "=" not in token:
                index += 1
                if index >= len(args):
                    return None
            index += 1
            continue
        if option in boolean_options and "=" not in token:
            index += 1
            continue
        if token.startswith("-"):
            return None
        positionals.append(token)
        index += 1
    return positionals


def bootstrap_make_contract(repo: Path) -> Optional[Dict[str, str]]:
    argocd = repo / "infrastructure" / "k8s" / "bootstrap" / "argocd"
    makefile = canonical_absolute_file(argocd / "makefile")
    values_path = canonical_absolute_file(argocd / "values.yaml")
    if repo.name != "k8s" or makefile is None or values_path is None:
        return None
    try:
        text = makefile.read_text(encoding="utf-8")
    except OSError:
        return None
    contract: Dict[str, str] = {}
    for name in ("NAMESPACE", "RELEASE", "CHART", "CHART_VERSION", "VALUES", "TIMEOUT"):
        match = re.search(rf"(?m)^{name}\s*\?=\s*([^\s#]+)\s*$", text)
        if not match:
            return None
        contract[name.lower()] = match.group(1)
    if contract["values"] != "values.yaml":
        return None
    contract["values_path"] = str(values_path.resolve())
    return contract


def simple_yaml_scalars(text: str) -> Optional[Dict[Tuple[str, ...], str]]:
    scalars: Dict[Tuple[str, ...], str] = {}
    seen: Set[Tuple[str, ...]] = set()
    stack: List[Tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            return None
        match = re.match(r"^( *)([A-Za-z0-9_./-]+):(?:\s*(.*))?$", raw_line)
        if not match:
            if raw_line.lstrip().startswith("-"):
                continue
            return None
        indent = len(match.group(1))
        key = match.group(2)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        path = tuple(item[1] for item in stack) + (key,)
        if path in seen:
            return None
        seen.add(path)
        value = (match.group(3) or "").strip()
        if value:
            scalars[path] = value.strip("\"'")
        else:
            stack.append((indent, key))
    scalars[("__seen__",)] = "\n".join(".".join(path) for path in sorted(seen))
    return scalars


def immutable_bootstrap_root(repo: Path, context: str) -> Optional[Path]:
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", context):
        return None
    root = canonical_absolute_file(
        repo / "infrastructure" / "k8s" / "bootstrap" / "roots" / f"{context}.yaml"
    )
    if root is None:
        return None
    try:
        text = root.read_text(encoding="utf-8")
    except OSError:
        return None
    if re.search(r"(?m)^\s*---(?:\s|#|$)", text):
        return None
    scalars = simple_yaml_scalars(text)
    if not scalars:
        return None
    expected = {
        ("apiVersion",): "argoproj.io/v1alpha1",
        ("kind",): "Application",
        ("metadata", "name"): f"{context}-cluster",
        ("metadata", "namespace"): "argocd",
        ("spec", "project"): "default",
        ("spec", "source", "repoURL"): BOOTSTRAP_REPOSITORY_URL,
        ("spec", "source", "path"): f"infrastructure/k8s/gitops/clusters/{context}/root",
    }
    if any(scalars.get(path) != value for path, value in expected.items()):
        return None
    seen = set(scalars.pop(("__seen__",), "").splitlines())
    if not {"apiVersion", "kind", "metadata", "spec"}.issubset(seen):
        return None
    top_level = {path for path in seen if "." not in path}
    if top_level != {"apiVersion", "kind", "metadata", "spec"} or "spec.sources" in seen:
        return None
    source_paths = {path for path in seen if path == "spec.source" or path.startswith("spec.source.")}
    allowed_source_paths = {
        "spec.source", "spec.source.repoURL", "spec.source.targetRevision", "spec.source.path", "spec.source.directory"
    }
    if not source_paths.issubset(allowed_source_paths):
        return None
    directory = scalars.get(("spec", "source", "directory"))
    if directory is not None and not re.fullmatch(r"\{recurse:\s*true\}", directory):
        return None
    destination_flow = scalars.get(("spec", "destination"))
    destination_mapping = (
        scalars.get(("spec", "destination", "namespace")) == "argocd"
        and scalars.get(("spec", "destination", "server")) == "https://kubernetes.default.svc"
    )
    if destination_flow is not None:
        normalized_destination = re.sub(r"\s+", " ", destination_flow)
        destination_mapping = bool(
            re.fullmatch(
                r"\{namespace:\s*argocd,\s*server:\s*['\"]?https://kubernetes\.default\.svc['\"]?\}",
                normalized_destination,
            )
        )
    sync_paths = {path for path in seen if path == "spec.syncPolicy" or path.startswith("spec.syncPolicy.")}
    if sync_paths:
        if scalars.get(("spec", "syncPolicy")) is not None:
            return None
        if sync_paths != {"spec.syncPolicy", "spec.syncPolicy.syncOptions"}:
            return None
        if scalars.get(("spec", "syncPolicy", "syncOptions")) != "[CreateNamespace=true]":
            return None
    if not destination_mapping:
        return None
    target = scalars.get(("spec", "source", "targetRevision"), "")
    if target.lower() in {"head", "main", "master", "latest", "develop", "dev"}:
        return None
    immutable_sha = bool(re.fullmatch(r"[0-9a-f]{40,64}", target, re.IGNORECASE))
    dated_tag = bool(re.search(r"(?:^|[-_.])\d{4}-\d{2}-\d{2}(?:[.-]\d+)?$", target))
    if dated_tag:
        code, _ = run(["git", "show-ref", "--verify", "--quiet", f"refs/tags/{target}"], repo, timeout=2.0)
        dated_tag = code == 0
    if not (immutable_sha or dated_tag):
        return None
    revision = target if immutable_sha else f"refs/tags/{target}"
    bootstrap_inputs = tuple(
        canonical_absolute_file(path)
        for path in (
            root,
            repo / "infrastructure" / "k8s" / "bootstrap" / "argocd" / "makefile",
            repo / "infrastructure" / "k8s" / "bootstrap" / "argocd" / "values.yaml",
        )
    )
    if any(path is None for path in bootstrap_inputs):
        return None
    for path in bootstrap_inputs:
        assert path is not None
        relative = path.relative_to(repo).as_posix()
        work_code, working_blob = run(["git", "hash-object", "--", str(path)], repo, timeout=2.0)
        ref_code, published_blob = run(["git", "rev-parse", f"{revision}:{relative}"], repo, timeout=2.0)
        if work_code != 0 or ref_code != 0 or working_blob != published_blob:
            return None
    return root.resolve()


def bootstrap_kube_scope(args: Sequence[str], context: str, kubeconfig: str) -> bool:
    kubeconfig_path = canonical_absolute_file(kubeconfig)
    if kubeconfig_path is None:
        return False
    return (
        exact_option(args, {"--kubeconfig"}, kubeconfig)
        and exact_option(args, {"--context", "--kube-context"}, context)
        and exact_option(args, {"-n", "--namespace"}, "argocd")
    )


def approved_helm_bootstrap(args: Sequence[str], repo: Path, contract: Dict[str, str]) -> bool:
    value_options = {
        "--kubeconfig", "--kube-context", "-n", "--namespace", "-f", "--values",
        "--timeout", "--version",
    }
    boolean_options = {"--install", "--create-namespace", "--wait"}
    if command_positionals(args, value_options, boolean_options) != [
        "upgrade", contract["release"], contract["chart"]
    ]:
        return False
    context_values = option_values(args, {"--kube-context"})
    kubeconfigs = option_values(args, {"--kubeconfig"})
    if len(context_values) != 1 or len(kubeconfigs) != 1:
        return False
    context = context_values[0]
    if not immutable_bootstrap_root(repo, context):
        return False
    values = option_values(args, {"-f", "--values"})
    if len(values) != 1:
        return False
    values_path = canonical_absolute_file(values[0])
    return (
        values_path is not None
        and bootstrap_kube_scope(args, context, kubeconfigs[0])
        and values_path == Path(contract["values_path"]).resolve()
        and exact_option(args, {"--version"}, contract["chart_version"])
        and exact_option(args, {"--timeout"}, contract["timeout"])
        and "--install" in args
        and "--create-namespace" in args
        and "--wait" in args
    )


def approved_repository_bootstrap(commands: Sequence[Tuple[str, List[str]]], repo: Path) -> bool:
    if len(commands) != 3 or any(executable != "kubectl" for executable, _ in commands):
        return False
    create, label, apply = (args for _, args in commands)
    common_values = {"--kubeconfig", "--context", "-n", "--namespace"}
    contexts = option_values(create, {"--context"})
    kubeconfigs = option_values(create, {"--kubeconfig"})
    if len(contexts) != 1 or len(kubeconfigs) != 1 or not immutable_bootstrap_root(repo, contexts[0]):
        return False
    for args in (create, label, apply):
        if not bootstrap_kube_scope(args, contexts[0], kubeconfigs[0]):
            return False

    create_values = common_values | {"--from-literal", "--from-file", "--dry-run", "-o", "--output"}
    if command_positionals(create, create_values, set()) != [
        "create", "secret", "generic", BOOTSTRAP_SECRET_NAME
    ]:
        return False
    literals = option_values(create, {"--from-literal"})
    key_files = option_values(create, {"--from-file"})
    if sorted(literals) != ["type=git", f"url={BOOTSTRAP_REPOSITORY_URL}"] or len(key_files) != 1:
        return False
    key_match = re.fullmatch(r"sshPrivateKey=(.+)", key_files[0])
    if not key_match:
        return False
    key_path = canonical_absolute_file(key_match.group(1))
    if key_path is None:
        return False
    if not exact_option(create, {"--dry-run"}, "client") or not exact_option(create, {"-o", "--output"}, "yaml"):
        return False

    label_values = common_values | {"-f", "--filename", "-o", "--output"}
    if command_positionals(label, label_values, {"--local"}) != [
        "label", "argocd.argoproj.io/secret-type=repository"
    ]:
        return False
    if "--local" not in label or not exact_option(label, {"-f", "--filename"}, "-"):
        return False
    if not exact_option(label, {"-o", "--output"}, "yaml"):
        return False

    apply_values = common_values | {"-f", "--filename"}
    return (
        command_positionals(apply, apply_values, set()) == ["apply"]
        and exact_option(apply, {"-f", "--filename"}, "-")
    )


def approved_root_bootstrap(args: Sequence[str], repo: Path) -> bool:
    value_options = {"--kubeconfig", "--context", "-n", "--namespace", "-f", "--filename"}
    if command_positionals(args, value_options, set()) != ["apply"]:
        return False
    contexts = option_values(args, {"--context"})
    kubeconfigs = option_values(args, {"--kubeconfig"})
    filenames = option_values(args, {"-f", "--filename"})
    if len(contexts) != 1 or len(kubeconfigs) != 1 or len(filenames) != 1:
        return False
    root = immutable_bootstrap_root(repo, contexts[0])
    if not root or not bootstrap_kube_scope(args, contexts[0], kubeconfigs[0]):
        return False
    supplied = canonical_absolute_file(filenames[0])
    return supplied is not None and supplied == root.resolve()


def approved_gitops_bootstrap(command: str, cwd: Path, expected_repo: Optional[Path]) -> bool:
    marker = re.match(rf"^\s*{re.escape(BOOTSTRAP_APPROVAL)}\s+", command)
    if not marker:
        return False
    if expected_repo is None:
        return False
    try:
        repo = expected_repo.resolve(strict=True)
        event_cwd = cwd.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return False
    allowed_event_roots = {repo}
    coordinator = repo.parent
    if repo == coordinator / "k8s" and is_coordinator(coordinator):
        allowed_event_roots.add(coordinator.resolve())
    if repo.name != "k8s" or not repo.is_dir() or event_cwd not in allowed_event_roots:
        return False
    repo_git_root = git_root(repo)
    if repo_git_root is None or repo_git_root.resolve() != repo:
        return False
    contract = bootstrap_make_contract(repo)
    if not contract:
        return False
    commands = shell_commands(command)
    body = command[marker.end() :].strip()
    if re.search(r"[$`\n\r<>*?\[\]{}#]", body):
        return False
    if len(commands) == 1:
        executable, args = commands[0]
        if executable == "helm" and re.match(r"^helm(?:\s|$)", body):
            return approved_helm_bootstrap(args, repo, contract)
        if executable == "kubectl" and re.match(r"^kubectl(?:\s|$)", body):
            return approved_root_bootstrap(args, repo)
        return False
    if ";" in body or "&" in body:
        return False
    raw_segments = re.split(r"\s*\|\s*", body)
    if len(raw_segments) != 3 or any(not re.match(r"^kubectl(?:\s|$)", segment) for segment in raw_segments):
        return False
    return approved_repository_bootstrap(commands, repo)


def shell_commands(command: str, depth: int = 0) -> List[Tuple[str, List[str]]]:
    if depth > 2:
        return []
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return []

    segments: List[List[str]] = []
    current: List[str] = []
    for token in tokens:
        if re.fullmatch(r"[;&|]+", token):
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)

    commands: List[Tuple[str, List[str]]] = []
    for segment in segments:
        executable, args, _ = normalized_shell_command(segment)
        if executable is None:
            continue
        executable_name = Path(executable).name.lower()
        commands.append((executable, args))
        if executable_name == "xargs":
            nested = xargs_literal_command(args)
            if nested:
                commands.append(nested)
        if executable_name in {"bash", "sh", "zsh", "dash", "ksh"}:
            for arg_index, arg in enumerate(args[:-1]):
                if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):
                    commands.extend(shell_commands(args[arg_index + 1], depth + 1))
                    break
    return commands


def xargs_literal_command(args: Sequence[str]) -> Optional[Tuple[str, List[str]]]:
    value_options = {
        "-a", "--arg-file", "-d", "--delimiter", "-E", "--eof", "-I", "--replace",
        "-J", "-L", "--max-lines", "-n", "--max-args", "-P", "--max-procs", "-R", "-s", "--max-chars", "-S",
    }
    boolean_options = {
        "-0", "--null", "-o", "--open-tty", "-p", "--interactive", "-r", "--no-run-if-empty",
        "-t", "--verbose", "-x", "--exit",
    }
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            index += 1
            break
        option = token.split("=", 1)[0]
        if token.startswith("-") and not token.startswith("--"):
            cluster = short_option_cluster(
                token,
                args[index + 1 :],
                {"0", "o", "p", "r", "t", "x"},
                {"a", "d", "E", "I", "J", "L", "n", "P", "R", "s", "S"},
            )
            if cluster is None:
                return None
            index += cluster[0]
            continue
        if option in value_options:
            if "=" in token:
                index += 1
            else:
                index += 2
            continue
        if token in boolean_options:
            index += 1
            continue
        if token.startswith("-"):
            return None
        break
    if index >= len(args) or Path(args[index]).name.lower() != "kubectl":
        return None
    return "kubectl", list(args[index + 1 :])


def retired_wgc_runner_path(value: str) -> bool:
    candidate = Path(os.path.normpath(value))
    return (
        candidate.is_absolute()
        and candidate.name == "runner.py"
        and candidate.parent.parent == Path("/usr/local/libexec")
        and candidate.parent.name.startswith("wget-cloud-")
        and candidate.parent.name != "wget-cloud-"
    )


def python_script_operand(args: Sequence[str]) -> Optional[str]:
    value_options = {"-W", "-X", "--check-hash-based-pycs"}
    attached_value = re.compile(r"^-(?:W|X).+")
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            index += 1
            break
        if token in {"-c", "-m"}:
            return None
        option = token.split("=", 1)[0]
        if attached_value.fullmatch(token):
            index += 1
            continue
        if option in value_options:
            if "=" in token:
                index += 1
            elif index + 1 < len(args):
                index += 2
            else:
                return None
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return args[index] if index < len(args) else None


def retired_wgc_runner_invocation(executable: str, args: Sequence[str]) -> bool:
    if retired_wgc_runner_path(executable):
        return True
    executable_name = Path(executable).name.lower()
    if re.fullmatch(r"python(?:3(?:\.\d+)?)?", executable_name) is None:
        return False
    script = python_script_operand(args)
    return script is not None and retired_wgc_runner_path(script)


def first_positional(args: Sequence[str], options_with_value: Set[str]) -> Tuple[Optional[str], int]:
    index = 0
    while index < len(args):
        token = args[index]
        option = token.split("=", 1)[0]
        if option in options_with_value:
            index += 1 if "=" in token else 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token.lower(), index
    return None, index


def kubectl_violation(args: Sequence[str]) -> Optional[str]:
    options_with_value = {
        "-n",
        "--namespace",
        "--context",
        "--kubeconfig",
        "--cluster",
        "--user",
        "--request-timeout",
        "-o",
        "--output",
    }
    allowed = {"get", "describe", "logs", "events", "top", "wait", "diff", "version", "explain", "cluster-info"}
    verb, index = first_positional(args, options_with_value)
    if not verb:
        return None
    remaining = [token.lower() for token in args[index + 1 :]]
    if verb in allowed:
        return None
    if verb == "rollout" and remaining[:1] == ["status"]:
        return None
    if verb == "auth" and remaining[:1] == ["can-i"]:
        return None
    if verb == "config" and remaining[:1] and remaining[0] in {"current-context", "get-contexts", "view"}:
        return None
    return f"Direct Kubernetes operation 'kubectl {verb}' is blocked. Change desired state in k8s Git and let Argo CD reconcile it."


def git_subcommand(args: Sequence[str]) -> Tuple[Optional[str], int]:
    return first_positional(
        args,
        {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"},
    )


def git_command_cwd(args: Sequence[str], cwd: Path) -> Path:
    target = cwd
    index = 0
    while index < len(args):
        token = args[index]
        if token == "-C" and index + 1 < len(args):
            value = args[index + 1]
            index += 2
        elif token.startswith("-C="):
            value = token.split("=", 1)[1]
            index += 1
        else:
            index += 1
            continue
        candidate = Path(value).expanduser()
        target = candidate.resolve(strict=False) if candidate.is_absolute() else (target / candidate).resolve(strict=False)
    return target


def broad_delete_violation(args: Sequence[str], cwd: Path) -> bool:
    flags = [token for token in args if token.startswith("-")]
    recursive = any("r" in token.lstrip("-") or token == "--recursive" for token in flags)
    forced = any("f" in token.lstrip("-") or token == "--force" for token in flags)
    if not (recursive and forced):
        return False
    targets = [token for token in args if not token.startswith("-")]
    repo = git_root(cwd)
    coordinator = coordinator_root(repo) if repo else None
    protected: Set[Path] = {Path("/"), Path.home().resolve()}
    if repo:
        protected.add(repo.resolve())
    if coordinator:
        protected.add(coordinator.resolve())
        protected.update((coordinator / name).resolve() for name in PROJECTS)
    for target in targets:
        if target in {"~", "$HOME", "${HOME}"}:
            return True
        try:
            resolved = (cwd / Path(target).expanduser()).resolve(strict=False) if not Path(target).is_absolute() else Path(target).expanduser().resolve(strict=False)
        except OSError:
            continue
        if resolved in protected:
            return True
    return False


def command_violation(
    command: str,
    cwd: Path,
    bootstrap_repo: Optional[Path] = None,
    bootstrap_cwd: Optional[Path] = None,
) -> Optional[str]:
    if not command.strip():
        return None
    if suspicious_secret(command):
        return "Possible credential material in a command is blocked. Use an approved environment or secret manager without exposing the value."
    if approved_gitops_bootstrap(command, bootstrap_cwd or cwd, bootstrap_repo):
        return None
    if has_wgc_approval_assignment(command):
        return "Unrecognized WGC approval marker is blocked; only the exact clean-cluster bootstrap contract is supported."

    for executable, args in shell_commands(command):
        if retired_wgc_runner_invocation(executable, args):
            return "Execution of a retired Wget Cloud runner is blocked. Remove the installed runner instead of invoking it."
        executable_name = Path(executable).name.lower()
        if executable_name == "kubectl":
            violation = kubectl_violation(args)
            if violation:
                return violation
        elif executable_name == "helm" and any(token.lower() in {"install", "upgrade", "uninstall", "rollback"} for token in args):
            return "Direct Helm mutation is blocked; use the k8s GitOps repository."
        elif executable_name == "argocd" or executable_name.startswith("argocd-"):
            words = [token.lower() for token in args if not token.startswith("-")]
            if any(words[index : index + 2] in (["app", "sync"], ["app", "set"], ["app", "delete"], ["app", "rollback"], ["app", "terminate-op"]) for index in range(max(0, len(words) - 1))):
                return "Direct Argo CD mutation is blocked; publish reviewed Git desired state instead."
        elif executable_name == "flux" and any(token.lower() in {"reconcile", "suspend", "resume", "delete"} for token in args):
            return "Direct Flux mutation is blocked by the GitOps policy."
        elif executable_name == "docker":
            words = [token.lower() for token in args if not token.startswith("-")]
            if words[:2] in (["system", "prune"], ["volume", "prune"]):
                return "Broad Docker prune is blocked because it can delete unrelated local data."
        elif executable_name == "terraform":
            action, _ = first_positional(args, {"-chdir"})
            if action in {"apply", "destroy"}:
                return "Direct infrastructure mutation is blocked in this GitOps workflow."
        elif executable_name == "rm" and broad_delete_violation(args, cwd):
            return "Broad recursive deletion of a workspace, repository, home directory, or filesystem root is blocked."
        elif executable_name == "git":
            action, index = git_subcommand(args)
            remaining = args[index + 1 :] if action else []
            lowered = [token.lower() for token in remaining]
            if action == "reset" and "--hard" in lowered:
                return "git reset --hard is blocked because it can discard user work."
            if action == "clean" and any(token == "--force" or token.startswith("-") and "f" in token.lstrip("-") for token in remaining):
                return "Forced git clean is blocked because it can delete untracked work."
            if action == "push" and any(token.startswith("--force") or token.startswith("-") and "f" in token.lstrip("-") for token in remaining):
                return "Force-push is blocked by the WGC delivery policy."
            if action == "checkout" and "--" in remaining:
                return "git checkout -- is blocked because it can discard local changes."
            if action == "restore" and "--staged" not in remaining:
                return "git restore of worktree files is blocked because it can discard local changes."
            if action == "branch" and "-D" in remaining:
                return "Forced branch deletion is blocked."
            if action == "submodule" and lowered[:1] == ["update"] and "--remote" in lowered:
                return "Mass submodule remote updates are blocked; the coordinator must pin explicit commits."
            if action == "submodule" and lowered[:1] == ["foreach"]:
                return "Mass submodule foreach operations are blocked; inspect and update repositories individually."
            if action == "commit":
                target_cwd = git_command_cwd(args, cwd)
                code, output = run(["git", "diff", "--cached", "--check"], target_cwd, timeout=5.0)
                if code != 0:
                    return f"Commit preflight failed: staged diff check reports problems. {output[:600]}"
                code, output = run(["git", "diff", "--name-only", "--diff-filter=U"], target_cwd, timeout=3.0)
                if code == 0 and output:
                    return "Commit preflight failed: unresolved merge conflicts are present."
    return None


def patch_violation(command: str, context: Dict[str, Any]) -> Optional[str]:
    boundary = workspace_boundary(context)
    for raw in patch_paths(command):
        path = normalize_patch_path(raw, context)
        if not path_within(path, boundary):
            return f"Edit outside the WGC workspace boundary is blocked: {raw}"
        if ".git" in path.parts:
            return f"Direct edits inside Git metadata are blocked: {raw}"
    if suspicious_secret(command):
        return "Possible private key or access token in the patch is blocked. Store only approved secret references in Git."
    return None


def pre_tool_warning(payload: Dict[str, Any], command: str, context: Dict[str, Any]) -> Optional[str]:
    tool = str(payload.get("tool_name", ""))
    notes: List[str] = []
    if tool in {"apply_patch", "Edit", "Write"}:
        paths = patch_paths(command)
        if any(TEST_PATH.search(path.replace("\\", "/")) for path in paths):
            notes.append(
                "Test files are being edited. Only Test-maker may change protected tests; the orchestrator must refresh and verify their SHA-256 hashes."
            )
        if any("/legacy/" in f"/{path.replace('\\', '/')}" for path in paths):
            notes.append("A legacy/archive path is being edited; verify it is not being treated as runtime source of truth.")
        generated = any(path.endswith("profile.generated.yaml") for path in paths)
        source = any("/profiles/" in f"/{path.replace('\\', '/')}" for path in paths)
        if generated and not source:
            notes.append("Generated GitOps profile changed without its profile source in this patch; run the renderer and inspect source/generated consistency.")
    if re.search(r"\bgit\b[^;&|\n]*\b(?:commit|push|merge|rebase|pull|checkout|switch)\b", command, re.IGNORECASE):
        notes.append(
            "Git mutation requires explicit task authorization and separate repository boundaries; verify dirty state, exact branch, diff, and approval."
        )
    if re.search(
        r"(?:\bkubectl\b[^;&|\n]*\blogs\b|\bdocker(?:\s+compose)?\s+logs\b|\bjournalctl\b|\bargocd\b[^;&|\n]*\blogs\b)",
        command,
        re.IGNORECASE,
    ):
        notes.append(
            "Runtime logs may contain credentials or personal data. Use the narrowest service, tenant-safe identifier, time range and line limit; redact output and persist only evidence handles or summaries."
        )
    return " ".join(notes) if notes else None


def nested_exit_code(value: Any) -> Optional[int]:
    if isinstance(value, dict):
        for key in ("exit_code", "exitCode", "status"):
            if isinstance(value.get(key), int):
                return int(value[key])
        for nested in value.values():
            found = nested_exit_code(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = nested_exit_code(nested)
            if found is not None:
                return found
    elif isinstance(value, str):
        match = re.search(r"(?:exit[_ ]code|Process exited with code)\D{0,8}(-?\d+)", value, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def verification_tags(command: str) -> Set[str]:
    lower = command.lower()
    tags: Set[str] = set()
    if re.search(r"\b(test|jest|vitest|playwright|pytest|rspec)\b", lower):
        tags.add("test")
    if re.search(r"\b(playwright|cypress|e2e)\b|test:e2e", lower):
        tags.add("browser")
    if re.search(r"\bsmoke(?:[-_: ]?test)?\b", lower):
        tags.add("smoke")
    if "coverage" in lower or "--cov" in lower:
        tags.add("coverage")
    if "type-check" in lower or "typecheck" in lower or "tsc" in lower:
        tags.add("typecheck")
    if re.search(r"\b(lint|eslint)\b", lower):
        tags.add("lint")
    if re.search(r"\b(build|turbo build)\b", lower):
        tags.add("build")
    if "gitops-render" in lower or "render-profile" in lower:
        tags.add("gitops-render")
    if re.search(r"\bmake\s+validate\b|gitops-validate|resource-validate", lower):
        tags.add("validate")
    if "pack" in lower and ("npm" in lower or "pnpm" in lower):
        tags.add("pack")
    if "consumer" in lower or "frontend" in lower and "wget-cloud-site" in lower:
        tags.add("consumer")
    if "proto:gen" in lower or "buf generate" in lower:
        tags.add("proto-gen")
    if "prisma" in lower and re.search(r"\b(generate|validate|migrate|diff)\b", lower):
        tags.add("prisma")
    return tags


def classify_paths(snapshot: Dict[str, Dict[str, str]], touched: Iterable[str]) -> Dict[str, Any]:
    all_paths: Set[str] = set(touched)
    for project, values in snapshot.items():
        all_paths.update(f"{project}:{path}" for path in values)
    result = {
        "production": False,
        "tests": False,
        "docs": False,
        "k8s": False,
        "projects": set(),
        "paths": sorted(all_paths),
    }
    for value in all_paths:
        project, _, path = value.partition(":")
        normalized = path.replace("\\", "/")
        if project:
            result["projects"].add(project)
        if TEST_PATH.search(normalized):
            result["tests"] = True
            continue
        if DOC_PATH.search(normalized):
            result["docs"] = True
            continue
        suffix = Path(normalized).suffix.lower()
        if project == "k8s" or suffix in {".yaml", ".yml"} and "/k8s/" in f"/{normalized}":
            result["k8s"] = True
        if suffix in SOURCE_SUFFIXES:
            result["production"] = True
    result["projects"] = sorted(result["projects"])
    return result


def relative_touched_paths(command: str, context: Dict[str, Any]) -> List[str]:
    repos = workspace_repositories(context)
    result: List[str] = []
    for raw in patch_paths(command):
        absolute = normalize_patch_path(raw, context)
        owner = None
        owner_root = None
        for name, root in sorted(repos.items(), key=lambda item: len(str(item[1])), reverse=True):
            if path_within(absolute, root.resolve()):
                owner = name
                owner_root = root.resolve()
                break
        if owner and owner_root:
            result.append(f"{owner}:{absolute.relative_to(owner_root).as_posix()}")
    return result


def active_test_assessment(state: Dict[str, Any], item_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    assessments = state.get("test_assessments", [])
    if not isinstance(assessments, list):
        return None
    for assessment in reversed(assessments):
        if not isinstance(assessment, dict):
            continue
        if item_id is None or assessment.get("item_id") == item_id:
            return assessment
    return None


def agent_result_ledger_key(result: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    """Identify one retryable role result without conflating distinct epic items."""
    return (
        str(result.get("role") or ""),
        str(result.get("phase") or ""),
        str(result.get("item_id") or ""),
        str(result.get("item_revision") or ""),
        str(result.get("input_revision") or ""),
    )


def assessment_test_file(path_value: str, context: Dict[str, Any]) -> Optional[Path]:
    repositories = workspace_repositories(context)
    project, separator, relative = path_value.partition(":")
    if separator and project in repositories:
        candidate = repositories[project] / relative
    else:
        candidate = Path(path_value)
        if not candidate.is_absolute():
            candidate = Path(context["repo_root"]) / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_file() or not path_within(resolved, workspace_boundary(context)):
        return None
    return resolved


def file_sha256(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def canonical_scope_path(path_value: str, context: Dict[str, Any]) -> Optional[str]:
    repositories = workspace_repositories(context)
    project, separator, relative = path_value.partition(":")
    if separator and project in repositories:
        owner = project
        root = repositories[project].resolve()
        candidate = root / relative
    else:
        candidate = Path(path_value)
        if not candidate.is_absolute():
            candidate = Path(context["repo_root"]) / candidate
        candidate = candidate.resolve(strict=False)
        owner = ""
        root = Path(context["repo_root"]).resolve()
        for name, repository in sorted(repositories.items(), key=lambda item: len(str(item[1])), reverse=True):
            repository = repository.resolve()
            if path_within(candidate, repository):
                owner = name
                root = repository
                break
        if not owner:
            return None
    try:
        resolved = candidate.resolve(strict=False)
        relative_path = resolved.relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None
    if not relative_path or relative_path == "." or relative_path.startswith("../"):
        return None
    return f"{owner}:{relative_path}"


def assessed_scope_paths(state: Dict[str, Any], context: Dict[str, Any]) -> Set[str]:
    result: Set[str] = set()
    for assessment in state.get("test_assessments", []):
        if not isinstance(assessment, dict):
            continue
        for path in assessment.get("assessed_paths", []):
            if isinstance(path, str):
                canonical = canonical_scope_path(path, context)
                if canonical:
                    result.add(canonical)
    return result


def contract_or_migration_path(value: str) -> bool:
    _, _, path = value.partition(":")
    normalized = "/" + path.lower().replace("\\", "/")
    return bool(
        normalized.endswith(".proto")
        or normalized.endswith("schema.prisma")
        or "/migrations/" in normalized
        or "/domain-types/" in normalized
        or "/site-blocks/" in normalized
        or "/widget-core/" in normalized
        or normalized.endswith("/package.json")
    )


def protected_reuse_change_is_unchanged(
    changed_paths: Set[str],
    state: Dict[str, Any],
    context: Dict[str, Any],
) -> bool:
    test_paths = {path for path in changed_paths if TEST_PATH.search(path.partition(":")[2])}
    if not test_paths:
        return False
    protected: Dict[str, str] = {}
    for assessment in state.get("test_assessments", []):
        if not isinstance(assessment, dict) or assessment.get("test_disposition") != "reuse":
            continue
        proof = assessment.get("reuse_proof")
        if not isinstance(proof, dict):
            continue
        canonical = canonical_scope_path(str(proof.get("test_path") or ""), context)
        digest = str(proof.get("file_sha256") or "").lower()
        scoped = {
            canonical_scope_path(str(path), context)
            for path in assessment.get("assessed_paths", [])
            if isinstance(path, str)
        }
        if canonical and canonical in scoped and re.fullmatch(r"[0-9a-f]{64}", digest):
            protected[canonical] = digest
    if not test_paths.issubset(protected):
        return False
    for path in test_paths:
        file_path = assessment_test_file(path, context)
        if file_path is None or file_sha256(file_path) != protected[path]:
            return False
    return True


def assessment_reuse_path_is_unchanged(
    assessment: Dict[str, Any],
    changed_path: str,
    context: Dict[str, Any],
) -> bool:
    if assessment.get("test_disposition") != "reuse":
        return False
    proof = assessment.get("reuse_proof")
    if not isinstance(proof, dict):
        return False
    canonical = canonical_scope_path(str(proof.get("test_path") or ""), context)
    scoped = {
        canonical_scope_path(str(path), context)
        for path in assessment.get("assessed_paths", [])
        if isinstance(path, str)
    }
    digest = str(proof.get("file_sha256") or "").lower()
    if canonical != changed_path or canonical not in scoped or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    file_path = assessment_test_file(changed_path, context)
    return file_path is not None and file_sha256(file_path) == digest


def assessment_implementor_test_path_is_planned(
    assessment: Dict[str, Any],
    changed_path: str,
    context: Dict[str, Any],
) -> bool:
    """Keep an implementor-owned assessment while its declared ordinary test is authored."""
    if (
        assessment.get("test_ownership") != "implementor"
        or assessment.get("test_disposition") not in {"add", "update"}
    ):
        return False
    plan = assessment.get("test_plan")
    if not isinstance(plan, dict):
        return False
    planned = {
        canonical_scope_path(str(path), context)
        for path in plan.get("tests", [])
        if isinstance(path, str)
    }
    scoped = {
        canonical_scope_path(str(path), context)
        for path in assessment.get("assessed_paths", [])
        if isinstance(path, str)
    }
    return changed_path in planned and changed_path in scoped


def implementor_test_changes_are_planned(
    changed_paths: Set[str],
    state: Dict[str, Any],
    context: Dict[str, Any],
) -> bool:
    test_paths = {path for path in changed_paths if TEST_PATH.search(path.partition(":")[2])}
    if not test_paths:
        return False
    assessments = [value for value in state.get("test_assessments", []) if isinstance(value, dict)]
    return all(
        any(assessment_implementor_test_path_is_planned(assessment, path, context) for assessment in assessments)
        for path in test_paths
    )


def bounded_text(value: Any, field: str, *, limit: int = ADAPTIVE_TEXT_LIMIT) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        return None, f"{field} must be a non-empty string of at most {limit} characters"
    return value.strip(), None


def bounded_text_list(value: Any, field: str, *, required: bool = True) -> Tuple[Optional[List[str]], Optional[str]]:
    if value is None and not required:
        return [], None
    if not isinstance(value, list) or (required and not value) or len(value) > ADAPTIVE_LEDGER_LIMIT:
        qualifier = "non-empty " if required else ""
        return None, f"{field} must be a {qualifier}list of at most {ADAPTIVE_LEDGER_LIMIT} bounded strings"
    normalized: List[str] = []
    for raw in value:
        text, error = bounded_text(raw, field)
        if error:
            return None, error
        assert text is not None
        if text in normalized:
            return None, f"{field} must not contain duplicate values"
        normalized.append(text)
    return normalized, None


def normalize_exact_paths(value: Any, field: str, context: Dict[str, Any]) -> Tuple[Optional[List[str]], Optional[str]]:
    paths, error = bounded_text_list(value, field)
    if error:
        return None, error
    assert paths is not None
    if any(any(token in path for token in ("*", "?", "[", "]")) for path in paths):
        return None, f"{field} accepts exact paths only, not globs"
    canonical = [canonical_scope_path(path, context) for path in paths]
    if any(path is None for path in canonical) or len(set(canonical)) != len(canonical):
        return None, f"{field} must contain unique exact paths inside the active WGC workspace"
    return [str(path) for path in canonical], None


def normalize_test_plan(value: Any, disposition: str, ownership: str, context: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(value, dict):
        return None, f"{disposition} TestAssessment requires a bounded test_plan"
    allowed = {
        "action",
        "tests",
        "commands",
        "expected_baseline",
        "actual_baseline",
        "protected_hashes",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        return None, "test_plan contains unknown fields: " + ", ".join(unknown)
    if value.get("action") != disposition:
        return None, f"test_plan action must match disposition {disposition}"
    tests, error = normalize_exact_paths(value.get("tests"), "test_plan.tests", context)
    if error:
        return None, error
    assert tests is not None
    if any(not TEST_PATH.search(path.partition(":")[2]) for path in tests):
        return None, "test_plan.tests must identify exact test files"
    normalized: Dict[str, Any] = {"action": disposition, "tests": tests}
    hashes = value.get("protected_hashes")
    normalized_hashes: Dict[str, str] = {}
    if ownership == "implementor":
        if hashes not in (None, {}):
            return None, "implementor-owned test_plan must not declare protected_hashes"
        normalized["protected_hashes"] = {}
    elif not isinstance(hashes, dict) or not hashes or len(hashes) > ADAPTIVE_LEDGER_LIMIT:
        return None, f"protected test_plan.protected_hashes must be a non-empty object bounded to {ADAPTIVE_LEDGER_LIMIT} paths"
    if ownership == "implementor":
        hashes = {}
    for raw_path, raw_digest in hashes.items():
        paths, error = normalize_exact_paths([raw_path], "test_plan.protected_hashes", context)
        digest = str(raw_digest or "").lower()
        if error or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None, "test_plan.protected_hashes requires exact workspace paths and SHA-256 values"
        assert paths is not None
        canonical = paths[0]
        if not TEST_PATH.search(canonical.partition(":")[2]):
            return None, "test_plan.protected_hashes may contain test files only"
        if canonical in normalized_hashes:
            return None, "test_plan.protected_hashes must contain unique exact paths"
        protected_file = assessment_test_file(canonical, context)
        actual_digest = file_sha256(protected_file) if protected_file is not None else None
        if actual_digest is None or actual_digest != digest:
            return None, f"test_plan protected hash does not match the existing file: {canonical}"
        normalized_hashes[canonical] = digest
    if ownership == "protected_test_maker" and set(tests) != set(normalized_hashes):
        return None, "test_plan.tests and test_plan.protected_hashes must have the same exact canonical keyset"
    normalized["protected_hashes"] = normalized_hashes
    commands, error = bounded_text_list(value.get("commands"), "test_plan.commands")
    if error:
        return None, "add/update TestPlan requires non-empty bounded exact runnable commands"
    normalized["commands"] = commands
    for field in ("expected_baseline", "actual_baseline"):
        text, error = bounded_text(value.get(field), f"test_plan.{field}")
        if error:
            return None, f"add/update TestPlan requires non-empty bounded {field} evidence"
        normalized[field] = text
    return normalized, None


def normalize_reuse_proof(
    value: Any,
    criticality: str,
    state: Dict[str, Any],
    context: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(value, dict):
        return None, "reuse TestAssessment requires structured reuse_proof"
    allowed = {
        "test_id",
        "test_path",
        "invariant_mapping",
        "successful_run",
        "file_sha256",
        "critical_branch_evidence",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        return None, "reuse_proof contains unknown fields: " + ", ".join(unknown)
    test_id, error = bounded_text(value.get("test_id"), "reuse_proof.test_id")
    if error:
        return None, error
    test_paths, error = normalize_exact_paths([value.get("test_path")], "reuse_proof.test_path", context)
    if error:
        return None, error
    mapping = value.get("invariant_mapping")
    if isinstance(mapping, list):
        normalized_mapping, error = bounded_text_list(mapping, "reuse_proof.invariant_mapping")
    else:
        normalized_mapping, error = bounded_text(mapping, "reuse_proof.invariant_mapping")
    if error:
        return None, error
    digest = str(value.get("file_sha256") or "").lower()
    if value.get("successful_run") is not True or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None, "reuse proof requires successful_run=true and file_sha256"
    assert test_paths is not None
    test_path = test_paths[0]
    if not TEST_PATH.search(test_path.partition(":")[2]):
        return None, "reuse_proof.test_path must identify an exact test file"
    protected = assessment_test_file(test_path, context)
    if protected is None or file_sha256(protected) != digest:
        return None, "reuse proof file_sha256 does not match the protected test file"
    if "test" not in state.get("verification", {}):
        return None, "reuse proof requires a successful test command recorded by the current hook state"
    normalized: Dict[str, Any] = {
        "test_id": test_id,
        "test_path": test_path,
        "invariant_mapping": normalized_mapping,
        "successful_run": True,
        "file_sha256": digest,
    }
    if criticality == "critical":
        branch, error = bounded_text(value.get("critical_branch_evidence"), "reuse_proof.critical_branch_evidence")
        if error or "coverage" not in state.get("verification", {}):
            return None, "critical reuse requires critical_branch_evidence and successful coverage evidence"
        normalized["critical_branch_evidence"] = branch
    elif "critical_branch_evidence" in value:
        branch, error = bounded_text(value.get("critical_branch_evidence"), "reuse_proof.critical_branch_evidence")
        if error:
            return None, error
        normalized["critical_branch_evidence"] = branch
    return normalized, None


def normalize_test_assessment(
    assessment: Any,
    state: Dict[str, Any],
    profile: str,
    context: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(assessment, dict):
        return None, "TestAssessment must be a JSON object"
    unknown = sorted(set(assessment) - TEST_ASSESSMENT_FIELDS)
    if unknown:
        return None, "TestAssessment contains unknown fields: " + ", ".join(unknown)
    if profile != "epic-implementation":
        if (
            not str(state.get("plan_revision") or "").strip()
            or str(state.get("minimum_test_criticality") or "").lower() not in TEST_CRITICALITIES
        ):
            return None, "execution plan_revision and minimum_test_criticality are required before TestAssessment"
        if not str(state.get("acceptance_revision") or "").strip():
            return None, "acceptance owner acceptance_revision is required before TestAssessment"
    normalized: Dict[str, Any] = {}
    for field in ("plan_revision", "acceptance_revision", "scope_fingerprint"):
        text, error = bounded_text(assessment.get(field), field, limit=200)
        if error:
            return None, error
        normalized[field] = text
    criticality = str(assessment.get("test_criticality") or "").lower().strip()
    disposition = str(assessment.get("test_disposition") or "").lower().strip()
    ownership = str(assessment.get("test_ownership") or ("protected_test_maker" if disposition in {"add", "update"} else "n/a")).lower().strip()
    if criticality not in TEST_CRITICALITIES:
        return None, "Unknown or ambiguous test criticality is critical and requires a new critical TestAssessment"
    if disposition not in TEST_DISPOSITIONS:
        return None, f"invalid test disposition: {disposition or '<empty>'}"
    if ownership not in TEST_OWNERSHIPS:
        return None, f"invalid test ownership: {ownership or '<empty>'}"
    if disposition in {"reuse", "none"} and ownership != "n/a":
        return None, "reuse/none TestAssessment requires test_ownership=n/a"
    if disposition in {"add", "update"} and ownership == "n/a":
        return None, "add/update TestAssessment requires implementor or protected_test_maker ownership"
    if criticality == "critical" and disposition in {"add", "update"} and ownership != "protected_test_maker":
        return None, "critical add/update requires protected_test_maker ownership"
    normalized["test_criticality"] = criticality
    normalized["test_disposition"] = disposition
    normalized["test_ownership"] = ownership
    assessed_paths, error = normalize_exact_paths(assessment.get("assessed_paths"), "assessed_paths", context)
    if error:
        return None, error
    normalized["assessed_paths"] = assessed_paths
    for field in ("tested_invariants", "existing_tests", "residual_risks"):
        values, error = bounded_text_list(assessment.get(field), field)
        if error:
            return None, error
        normalized[field] = values
    if "no_relevant_tests" in normalized["existing_tests"] and normalized["existing_tests"] != ["no_relevant_tests"]:
        return None, "existing_tests sentinel no_relevant_tests must be used alone"
    coverage_mode = str(assessment.get("coverage_mode") or "").lower().strip()
    if coverage_mode not in COVERAGE_MODES:
        return None, "coverage_mode must be one of: " + ", ".join(sorted(COVERAGE_MODES))
    normalized["coverage_mode"] = coverage_mode
    for field in ("alternative_evidence", "stronger_alternative_evidence"):
        if field in assessment:
            values, error = bounded_text_list(assessment.get(field), field)
            if error:
                return None, error
            normalized[field] = values
    for field in ("rationale", "follow_up"):
        if field in assessment:
            text, error = bounded_text(assessment.get(field), field)
            if error:
                return None, error
            normalized[field] = text
    if "disproportionate_cost" in assessment:
        if not isinstance(assessment.get("disproportionate_cost"), bool):
            return None, "disproportionate_cost must be a boolean"
        normalized["disproportionate_cost"] = assessment["disproportionate_cost"]
    if criticality == "critical" and disposition == "none":
        return None, "critical + none is forbidden; critical behavior requires add, update, or proven reuse"
    if criticality == "low" or disposition == "none":
        if not normalized.get("alternative_evidence"):
            return None, "low/none TestAssessment requires non-empty visible alternative_evidence"
    if disposition == "none" and not normalized.get("rationale"):
        return None, "none TestAssessment requires a bounded rationale"
    if criticality == "standard" and disposition == "none":
        if (
            normalized.get("disproportionate_cost") is not True
            or not normalized.get("stronger_alternative_evidence")
            or not normalized.get("follow_up")
        ):
            return None, (
                "standard + none requires rationale, disproportionate_cost=true, non-empty "
                "stronger_alternative_evidence and residual_risks lists, and follow_up"
            )
    if disposition in {"add", "update"}:
        plan, error = normalize_test_plan(assessment.get("test_plan"), disposition, ownership, context)
        if error:
            return None, error
        normalized["test_plan"] = plan
        if "reuse_proof" in assessment:
            return None, f"{disposition} TestAssessment must not include reuse_proof"
    elif disposition == "reuse":
        proof, error = normalize_reuse_proof(assessment.get("reuse_proof"), criticality, state, context)
        if error:
            return None, error
        normalized["reuse_proof"] = proof
        if "test_plan" in assessment:
            return None, "reuse TestAssessment must not include test_plan"
    elif "test_plan" in assessment or "reuse_proof" in assessment:
        return None, "none TestAssessment must not include test_plan or reuse_proof"

    rank = {"low": 0, "standard": 1, "critical": 2}
    if profile == "epic-implementation":
        item_id, error = bounded_text(assessment.get("item_id"), "item_id", limit=200)
        item_revision = str(assessment.get("item_revision") or "").lower().strip()
        if error or not re.fullmatch(r"[0-9a-f]{64}", item_revision):
            return None, "epic TestAssessment requires bounded item_id and SHA-256 item_revision"
        match = next(
            (
                item for item in state.get("selected_items", [])
                if isinstance(item, dict)
                and item.get("item_id") == item_id
                and item.get("item_revision") == item_revision
            ),
            None,
        )
        if match is None:
            return None, "epic TestAssessment requires an item_id/item_revision from the frozen selected_items ledger"
        for field in ("plan_revision", "acceptance_revision", "minimum_test_criticality"):
            if not str(match.get(field) or "").strip():
                return None, f"epic item {item_id} is missing per-item {field} before TestAssessment"
        if normalized["plan_revision"] != match["plan_revision"]:
            return None, "epic TestAssessment plan_revision is stale for the selected item"
        if normalized["acceptance_revision"] != match["acceptance_revision"]:
            return None, "epic TestAssessment acceptance_revision is stale for the selected item"
        if match.get("plan_guardian_required"):
            return None, "epic TestAssessment requires a new per-item Architecture Guardian plan approval"
        minimum = str(match["minimum_test_criticality"]).lower()
        normalized["item_id"] = item_id
        normalized["item_revision"] = item_revision
    else:
        expected_plan = str(state.get("plan_revision") or "")
        expected_acceptance = str(state.get("acceptance_revision") or "")
        minimum = str(state.get("minimum_test_criticality") or "").lower()
        if not expected_plan or minimum not in TEST_CRITICALITIES:
            return None, "execution plan_revision and minimum_test_criticality are required before TestAssessment"
        if not expected_acceptance:
            return None, "acceptance owner acceptance_revision is required before TestAssessment"
        if normalized["plan_revision"] != expected_plan:
            return None, "TestAssessment plan_revision is stale"
        if normalized["acceptance_revision"] != expected_acceptance:
            return None, "TestAssessment acceptance_revision is stale"
        if state.get("plan_guardian_required"):
            return None, "TestAssessment requires a new Architecture Guardian plan approval"
    if rank[criticality] < rank[minimum]:
        return None, (
            f"TestAssessment cannot lower architect minimum criticality {minimum}; "
            "new evidence, a new plan revision, and Architecture Guardian approval are required"
        )
    task = teams.active(state, normalized.get('item_id'))
    if task and rank[criticality] < rank[task['risk']]:
        return None, 'TestAssessment cannot lower TaskAssessment risk'
    return normalized, None


def required_checks(classification: Dict[str, Any], assessment: Optional[Dict[str, Any]] = None) -> Set[str]:
    required: Set[str] = set()
    projects = set(classification.get("projects", []))
    disposition = str((assessment or {}).get("test_disposition") or "")
    if classification.get("production") and (
        disposition != "none" or projects.intersection({"frontend", "wget-cloud-site"})
    ):
        required.add("test")
    if "frontend" in projects:
        required.add("typecheck")
    if "backend" in projects and classification.get("production"):
        required.add("coverage")
    if classification.get("production") and (assessment or {}).get("test_criticality") == "critical":
        required.add("coverage")
    if "wget-cloud-front-lib" in projects:
        required.update({"typecheck", "build"})
    if "wget-cloud-site" in projects:
        required.update({"typecheck", "lint", "build"})
    if "k8s" in projects or classification.get("k8s"):
        required.update({"gitops-render", "validate"})
    paths = "\n".join(str(value).lower().replace("\\", "/") for value in classification.get("paths", []))
    if "backend:" in paths and ("/proto/" in paths or ".proto" in paths):
        required.add("proto-gen")
    if "backend:" in paths and ("schema.prisma" in paths or "/prisma/" in paths):
        required.add("prisma")
    public_front_lib = (
        "wget-cloud-front-lib:" in paths
        and any(
            marker in paths
            for marker in (
                "package.json",
                "/domain-types/",
                "/site-blocks/",
                "/widget-core/",
                "/shared-lib/",
                "/index.ts",
            )
        )
    )
    if public_front_lib:
        required.add("consumer")
    return required


def repository_gate_floor(project: str) -> Set[str]:
    if project == "frontend":
        return {"typecheck"}
    if project == "wget-cloud-front-lib":
        return {"typecheck", "build"}
    if project == "wget-cloud-site":
        return {"typecheck", "lint", "build"}
    if project == "k8s":
        return {"gitops-render", "validate"}
    return set()


def required_checks_for_state(classification: Dict[str, Any], state: Dict[str, Any]) -> Set[str]:
    assessments = [
        value
        for value in state.get("test_assessments", [])
        if isinstance(value, dict)
    ]
    task_checks = {check for task in state.get('task_assessments', []) for check in task['checks']}
    if not assessments:
        return required_checks(classification) | task_checks
    if any(value.get("test_disposition") != "none" for value in assessments):
        chosen = next(value for value in assessments if value.get("test_disposition") != "none")
    else:
        chosen = assessments[-1]
    required = required_checks(classification, chosen) | task_checks
    if any(value.get("test_criticality") == "critical" for value in assessments) and classification.get("production"):
        required.add("coverage")
    return required


def parse_agent_result(message: str, profile: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    marker = "WGC_AGENT_RESULT"
    raw = None
    for line in reversed(message.splitlines()):
        candidate = line.strip().strip("`").strip()
        if not candidate.startswith(marker):
            continue
        candidate = candidate[len(marker):].lstrip()
        if candidate.startswith(":"):
            candidate = candidate[1:].lstrip()
        if candidate.startswith("{") and candidate.endswith("}"):
            raw = candidate
            break
    if not raw:
        return None, "missing WGC_AGENT_RESULT marker"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None, "WGC_AGENT_RESULT is not valid one-line JSON"
    if not isinstance(value, dict):
        return None, "WGC_AGENT_RESULT must be a JSON object"
    role = str(value.get("role") or "").lower().strip().replace("_", "-")
    verdict = str(value.get("verdict") or "").lower().strip()
    phase = str(value.get("phase") or "").lower().strip()
    revision = str(value.get("input_revision") or value.get("revision") or "").strip()
    role_verdicts = PROFILE_ROLE_VERDICTS.get(profile, {})
    if role not in role_verdicts:
        return None, f"unknown WGC role for profile {profile}: {role or '<empty>'}"
    if verdict not in role_verdicts[role]:
        if role == "test-maker" and verdict in {"baseline_ready", "tests_ready"}:
            return None, "legacy test-maker verdict cannot satisfy the TestAssessment gate; use assessment_ready"
        return None, f"invalid verdict '{verdict or '<empty>'}' for role {role} in profile {profile}"
    allowed_phases = PROFILE_ROLE_PHASES.get(profile, {}).get(role)
    if allowed_phases is not None and phase not in allowed_phases:
        return None, f"role {role} requires phase one of {sorted(allowed_phases)}"
    if allowed_phases is None and phase:
        return None, f"role {role} requires an empty phase"
    if not revision:
        return None, "WGC_AGENT_RESULT requires input_revision from SubagentStart"
    if role == 'project-manager' and ((phase == 'lifecycle') != (verdict in epic_stages.VERDICTS)):
        return None, 'lifecycle verdicts require Project Manager lifecycle phase'
    stage_plan = value.get('epic_stage_plan')
    if phase == 'lifecycle' or 'epic_stage_plan' in value:
        if role not in {'project-manager', 'youtrack-operator'} or (role == 'project-manager' and phase != 'lifecycle'):
            return None, 'EpicStagePlan belongs to lifecycle Project Manager or YouTrack Operator'
        try:
            stage_plan = epic_stages.normalize(stage_plan)
            gaps = epic_stages.gaps(stage_plan)
        except (ValueError, TypeError, KeyError):
            return None, 'malformed EpicStagePlan'
        if verdict in {'stage_ready', 'synced', 'published', 'no_changes'} and gaps:
            return None, 'EpicStagePlan transition blocked: ' + ', '.join(gaps)
        if verdict == 'awaiting_user' and not any(g == 'questions_open' or g.startswith('approval_required:') for g in gaps):
            return None, 'awaiting_user requires unresolved questions or user approval'
    if role == "test-maker" and verdict == "assessment_ready":
        allowed = {"role", "verdict", "phase", "input_revision", "revision", "assessment", "assessment_revision"} | TEST_ASSESSMENT_FIELDS
        unknown = sorted(set(value) - allowed)
        if unknown:
            return None, "TestAssessment marker contains unknown fields: " + ", ".join(unknown)
    if role == 'task-assessor' and set(value) - {'role', 'verdict', 'phase', 'input_revision', 'task_assessment', 'assessment'}:
        return None, 'Task Assessor marker contains unknown fields'
    inventory_fields = {'epic_inventory', 'epic_reconciliation', 'inventory_change_decision'} & set(value)
    allowed_inventory_fields = (
        {'epic_inventory', 'inventory_change_decision'} if phase == 'scope' and verdict == 'planned'
        else {'epic_reconciliation'} if phase == 'reconcile' and verdict == 'progress_updated'
        else set()
    ) if profile == 'epic-implementation' and role == 'project-manager' else set()
    if inventory_fields - allowed_inventory_fields:
        return None, 'inventory metadata belongs only to the Project Manager scope/reconcile contract'
    result: Dict[str, Any] = {
        "role": role,
        "verdict": verdict,
        "phase": phase,
        "input_revision": revision[:200],
    }
    for key in (
        "task_assessment",
        "assessment_revision",
        "assessment",
        "plan_revision",
        "acceptance_revision",
        "minimum_test_criticality",
        "test_criticality",
        "test_disposition",
        "test_ownership",
        "scope_fingerprint",
        "tested_invariants",
        "existing_tests",
        "coverage_mode",
        "alternative_evidence",
        "residual_risks",
        "disproportionate_cost",
        "stronger_alternative_evidence",
        "rationale",
        "follow_up",
        "reuse_proof",
        "test_plan",
        "assessed_paths",
        "selected_items",
        "epic_inventory",
        "epic_reconciliation",
        "inventory_change_decision",
        "epic_stage_plan",
        "item_id",
        "item_revision",
    ):
        if key in value:
            result[key] = value[key]
    if role == "test-maker" and verdict == "assessment_ready":
        nested = value.get("assessment")
        if nested is not None and not isinstance(nested, dict):
            return None, "nested TestAssessment must be a JSON object"
        assessment_fields = dict(nested or {})
        for key in TEST_ASSESSMENT_FIELDS:
            if key not in value:
                continue
            if key in assessment_fields and assessment_fields[key] != value[key]:
                return None, f"flat and nested TestAssessment disagree on {key}"
            assessment_fields[key] = value[key]
        result["assessment"] = assessment_fields
        for key in ("item_id", "item_revision"):
            if key in assessment_fields:
                result[key] = assessment_fields[key]
    return result, None


def normalize_selected_items(value: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    if not isinstance(value, list) or not value:
        return None, "epic project scope requires a non-empty selected_items ledger"
    if len(value) > ADAPTIVE_LEDGER_LIMIT:
        return None, f"selected_items is bounded to {ADAPTIVE_LEDGER_LIMIT} entries per epic run"
    result: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            return None, "every selected_items entry must be an object"
        allowed = {
            "item_id",
            "item_revision",
            "plan_revision",
            "acceptance_revision",
            "minimum_test_criticality",
        }
        unknown = sorted(set(raw) - allowed)
        if unknown:
            return None, "selected_items entry contains unknown fields: " + ", ".join(unknown)
        item_id = str(raw.get("item_id") or "").strip()
        revision = str(raw.get("item_revision") or "").lower().strip()
        if (
            not item_id
            or len(item_id) > 200
            or not re.fullmatch(r"[0-9a-f]{64}", revision)
            or item_id in seen
        ):
            return None, "selected_items requires unique bounded item_id values and SHA-256 item_revision values"
        seen.add(item_id)
        item: Dict[str, Any] = {"item_id": item_id, "item_revision": revision, "gates": []}
        for field in ("plan_revision", "acceptance_revision"):
            if field in raw:
                text, error = bounded_text(raw.get(field), f"selected_items.{field}", limit=200)
                if error:
                    return None, error
                item[field] = text
        if "minimum_test_criticality" in raw:
            minimum = str(raw.get("minimum_test_criticality") or "").lower().strip()
            if minimum not in TEST_CRITICALITIES:
                return None, "selected_items.minimum_test_criticality must be critical, standard, or low"
            item["minimum_test_criticality"] = minimum
        result.append(item)
    return result, None


def epic_item_gate_for_result(result: Dict[str, Any]) -> Optional[str]:
    role = result.get("role")
    verdict = result.get("verdict")
    phase = result.get("phase")
    if role == "test-maker" and verdict == "assessment_ready":
        return "test-maker"
    if role == "implementor" and verdict == "implemented":
        return "implementor"
    if role == "reviewer" and verdict == "approved":
        return "reviewer"
    if role == "architecture-guardian" and verdict == "approved" and phase == "diff":
        return "architecture"
    if role == "qa" and verdict == "pass":
        return "qa"
    if role == "product-manager" and verdict == "accepted" and phase == "outcome":
        return "product-outcome"
    return None


def update_epic_item_gate(state: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
    gate = epic_item_gate_for_result(result)
    if gate is None:
        return None
    item_id = str(result.get("item_id") or "").strip()
    item_revision = str(result.get("item_revision") or "").strip()
    for item in state.get("selected_items", []):
        if not isinstance(item, dict) or item.get("item_id") != item_id:
            continue
        if item.get("item_revision") != item_revision:
            return "epic item_revision does not match the frozen selected_items ledger"
        gates = set(item.get("gates", []))
        gates.add(gate)
        item["gates"] = sorted(gates)
        return None
    return "epic per-item result requires an item_id from the frozen selected_items ledger"


def epic_item_gaps(state: Dict[str, Any]) -> List[str]:
    gaps: List[str] = []
    selected = state.get("selected_items", [])
    if selected == [] and state.get('epic_inventory'):
        # A fully delivered epic still needs full reconciliation, but no fake
        # implementation assignments solely to populate the execution ledger.
        reports = [r for r in state.get('subagent_results', []) if r.get('role') == 'project-manager' and r.get('phase') == 'reconcile']
        if reports:
            report = reports[-1].get('epic_reconciliation')
            if (inventory.complete(report, state['epic_inventory'])
                    and all(e['disposition'] in {'already-delivered', 'cancelled'} for e in report['items'])):
                return []
    if not isinstance(selected, list) or not selected:
        return ["frozen selected_items ledger"]
    for item in selected:
        if not isinstance(item, dict):
            gaps.append("malformed selected item")
            continue
        task = teams.active(state, item.get('item_id'))
        item_state = {**state, 'profile': 'epic-implementation', 'subagent_results': [r for r in state.get('subagent_results', []) if r.get('item_id') == item['item_id']]}
        required = teams.required_gates('epic-implementation', task)
        if task and active_test_assessment(state, item['item_id']) is None:
            required.add('test-assessment')
        observed = approved_agent_gates(item_state, str(state.get('current_revision', '')))
        missing = sorted(required - observed)
        if missing:
            gaps.append(f"{item.get('item_id', '<unknown>')}@{item.get('item_revision', '<unknown>')}:" + ",".join(missing))
    return gaps


def invalidate_test_assessment(state: Dict[str, Any], *, invalidate_plan_approval: bool = False) -> None:
    state["test_assessments"] = []
    verification = state.setdefault("verification", {})
    verification.pop("test", None)
    verification.pop("coverage", None)
    retained: List[Dict[str, Any]] = []
    for result in state.get("subagent_results", []):
        if not isinstance(result, dict):
            continue
        role = result.get("role")
        phase = result.get("phase")
        if role in TEST_DOWNSTREAM_ROLES:
            continue
        if role == "architecture-guardian" and (phase == "diff" or invalidate_plan_approval):
            continue
        if role == "product-manager" and phase == "outcome":
            continue
        if role == "project-manager" and phase == "reconcile":
            continue
        retained.append(result)
    state["subagent_results"] = retained
    for item in state.get("selected_items", []):
        if isinstance(item, dict):
            item["gates"] = [gate for gate in item.get("gates", []) if gate not in EPIC_ITEM_GATES]


def invalidate_epic_items(
    state: Dict[str, Any],
    item_ids: Set[str],
    *,
    keep_assessment: bool,
    invalidate_integration: bool = True,
    invalidate_plan_approval: bool = False,
) -> None:
    """Invalidate only evidence owned by the affected epic items."""
    if not item_ids:
        return
    if not keep_assessment:
        state["test_assessments"] = [
            assessment
            for assessment in state.get("test_assessments", [])
            if isinstance(assessment, dict) and assessment.get("item_id") not in item_ids
        ]
    verification = state.setdefault("verification", {})
    verification.pop("test", None)
    verification.pop("coverage", None)

    def still_valid(result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        role = result.get("role")
        phase = result.get("phase")
        result_item = result.get("item_id")
        if (
            role == "architecture-guardian"
            and phase == "plan"
            and invalidate_plan_approval
            and (result_item is None or result_item in item_ids)
        ):
            return False
        if result_item in item_ids:
            if role in TEST_DOWNSTREAM_ROLES:
                return keep_assessment and role == "test-maker"
            if role == "architecture-guardian" and phase == "diff":
                return False
            if role == "product-manager" and phase == "outcome":
                return False
        if invalidate_integration:
            if role == "project-manager" and phase == "reconcile":
                return False
            if role == "youtrack-operator":
                return False
        return True

    state["subagent_results"] = [
        result for result in state.get("subagent_results", []) if still_valid(result)
    ]
    for item in state.get("selected_items", []):
        if not isinstance(item, dict) or item.get("item_id") not in item_ids:
            continue
        item["gates"] = ["test-maker"] if keep_assessment and "test-maker" in item.get("gates", []) else []


def invalidate_archived_items(state: Dict[str, Any], changed_paths: Set[str], sensitive: bool) -> None:
    """Later shared/unattributed changes cannot reuse a prior batch's witness."""
    covered = {p for a in state.get('task_assessments', []) for p in a.get('assessed_paths', [])}
    shared = sensitive or bool(changed_paths - covered) or any(
        re.search(r'(?:lock|package\.json|config|AGENTS\.md)', p, re.I) for p in changed_paths)
    state['completed_epic_items'] = [entry for entry in state.get('completed_epic_items', [])
                                    if not shared and entry.get('assessed_paths')
                                    and not changed_paths.intersection(entry['assessed_paths'])]


def reconcile_selected_items(state: Dict[str, Any], normalized: List[Dict[str, Any]]) -> None:
    previous = {
        str(item.get("item_id")): item
        for item in state.get("selected_items", [])
        if isinstance(item, dict) and item.get("item_id")
    }
    incoming_ids = {str(item["item_id"]) for item in normalized}
    removed_ids = set(previous) - incoming_ids
    # Archive actual per-item gate completion before the bounded batch is
    # replaced. A final report alone cannot invent execution of earlier batches.
    completed = {e['item_id']: e for e in state.get('completed_epic_items', [])}
    revision = workspace_identity(state['context']) if state.get('context') else str(state.get('current_revision', ''))
    for item_id in removed_ids:
        item_state = {**state, 'selected_items': [previous[item_id]], 'current_revision': revision}
        if not epic_item_gaps(item_state):
            completed[item_id] = {k: previous[item_id][k] for k in ('item_id', 'item_revision')}
            completed[item_id]['evidence_revision'] = revision
            completed[item_id]['assessed_paths'] = sorted({p for a in state.get('task_assessments', []) + state.get('test_assessments', [])
                                                          if a.get('item_id') == item_id for p in a.get('assessed_paths', [])})
    inventory_ids = {(e['item_id'],e['item_revision']) for e in state.get('epic_inventory',{}).get('items',[])}
    state['completed_epic_items'] = [e for e in completed.values() if (e['item_id'],e['item_revision']) in inventory_ids]
    affected_ids: Set[str] = set(removed_ids)
    merged: List[Dict[str, Any]] = []
    revision_fields = {"plan_revision", "acceptance_revision", "minimum_test_criticality"}
    for raw in normalized:
        item = dict(raw)
        old = previous.get(str(item["item_id"]))
        if old and old.get("item_revision") == item.get("item_revision"):
            item["gates"] = list(old.get("gates", []))
            if old.get("plan_guardian_required"):
                item["plan_guardian_required"] = True
            for field in revision_fields:
                if field not in item and field in old:
                    item[field] = old[field]
                elif field in item and field in old and item[field] != old[field]:
                    affected_ids.add(str(item["item_id"]))
            if (
                old.get("plan_revision")
                and item.get("plan_revision")
                and old.get("plan_revision") != item.get("plan_revision")
            ):
                item["plan_guardian_required"] = True
        else:
            affected_ids.add(str(item["item_id"]))
            if old is not None:
                item["plan_guardian_required"] = True
        merged.append(item)
    if affected_ids:
        state['task_assessments'] = [a for a in state.get('task_assessments', []) if a.get('item_id') not in affected_ids]
        invalidate_epic_items(
            state,
            affected_ids,
            keep_assessment=False,
            invalidate_integration=True,
            invalidate_plan_approval=True,
        )
        for item in merged:
            if str(item.get("item_id")) in affected_ids:
                item["gates"] = []
    state["selected_items"] = merged
    if removed_ids:
        state["subagent_results"] = [
            result for result in state.get("subagent_results", [])
            if not isinstance(result, dict) or result.get("item_id") not in removed_ids
        ]


def task_scope_revision(task: Dict[str, Any], context: Dict[str, Any]) -> str:
    files = {}
    for name in task['assessed_paths']:
        path = assessment_test_file(name, context)
        files[name] = file_sha256(path) if path and path.is_file() else 'missing'
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def result_is_current(result: Dict[str, Any], state: Dict[str, Any], revision: str) -> bool:
    task = teams.active(state, result.get('item_id'))
    if result.get('item_id') and task and result.get('scope_revision') and state.get('context'):
        return result['scope_revision'] == task_scope_revision(task, state['context'])
    return result.get('input_revision') == revision


def approved_agent_gates(state: Dict[str, Any], current_revision: str) -> Set[str]:
    gates: Set[str] = set()
    profile = str(state.get("profile") or "implementation")
    results = state.get("subagent_results", [])
    if not isinstance(results, list):
        return gates
    latest: Dict[Tuple[Any, Any, Any], Dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        key = (result.get("role"), result.get("phase"), result.get("item_id") if profile == "epic-implementation" else None)
        latest[key] = result
    for result in latest.values():
        role = result.get("role")
        verdict = result.get("verdict")
        phase = result.get("phase")
        task = teams.active(state, result.get('item_id'))
        if role == 'youtrack-operator':
            if result.get('epic_stage_plan') is not None and not epic_stages.matches_inventory(result['epic_stage_plan'], state):
                continue
            managers = [r for r in latest.values() if r.get('role') == 'project-manager' and r.get('phase') == 'lifecycle']
            if result.get('epic_stage_plan') is not None or any(r.get('verdict') == 'stage_ready' for r in managers):
                if not any(r.get('verdict') == 'stage_ready' and result_is_current(r, state, current_revision)
                           and r.get('assessment_revision') == result.get('assessment_revision')
                           and r.get('epic_stage_plan') == result.get('epic_stage_plan') for r in managers):
                    continue
        if task and role != 'task-assessor' and result.get('assessment_revision') != task['assessment_revision']:
            continue
        if role == 'task-assessor' and verdict == 'assessed' and task and result.get('task_assessment') == task:
            gates.add('task-assessor')
        elif role in {'data-migration-reviewer', 'reliability-reviewer'} and verdict == 'approved' and result_is_current(result, state, current_revision):
            gates.add('data' if role == 'data-migration-reviewer' else 'reliability')
        elif role == "product-manager" and verdict == "specified" and profile == "task-creation":
            gates.add("product")
        elif role == "product-manager" and verdict == "accepted" and profile == "epic-implementation" and phase == "scope":
            gates.add("product-scope")
        elif role == "product-manager" and verdict == "accepted" and profile == "epic-implementation" and phase == "outcome":
            gates.add("product-outcome")
        elif role == "project-manager" and verdict == "project_ready":
            gates.add("project")
        elif role == "project-manager" and verdict == "planned" and phase == "scope":
            gates.add("project-scope")
        elif role == "project-manager" and verdict == "progress_updated" and phase == "reconcile":
            gates.add("project-reconcile")
            report = result.get('epic_reconciliation')
            if result_is_current(result, state, current_revision) and inventory.complete(report, state.get('epic_inventory')):
                executed = {(e['item_id'],e['item_revision']) for e in state.get('completed_epic_items', []) + state.get('selected_items', [])}
                # Selected items are checked separately by epic_item_gaps.
                if all(e['disposition'] != 'implemented' or (e['item_id'],e['item_revision']) in executed for e in report['items']):
                    gates.add("epic-inventory")
        elif role == "implementation-auditor" and verdict == "audited":
            gates.add("implementation-audit")
        elif role == "backlog-reviewer" and verdict == "approved":
            gates.add("backlog-review")
        elif role == "effort-estimator" and verdict == "estimated" and result_is_current(result, state, current_revision):
            gates.add("effort-estimate")
        elif (
            role == "youtrack-operator"
            and verdict in {"published", "no_changes"}
            and profile == "task-creation"
            and result_is_current(result, state, current_revision)
        ):
            gates.add("project-publish")
        elif (
            role == "youtrack-operator"
            and verdict in {"synced", "no_changes"}
            and profile in {"implementation", "bugfix", "epic-implementation"}
            and result_is_current(result, state, current_revision)
        ):
            gates.add("project-sync")
        elif role == "bug-triage" and verdict == "triaged":
            gates.add("bug-triage")
        elif role == "bug-investigator" and verdict == "evidence_ready" and phase == "evidence":
            gates.add("evidence")
        elif role == "bug-investigator" and verdict == "root_cause_supported" and phase == "rca":
            gates.add("root-cause")
        elif role == "reproducer" and verdict in {"reproduced", "characterized"}:
            gates.add("reproducer")
        elif role == "root-cause-reviewer" and verdict == "approved":
            gates.add("root-cause-review")
        elif role == "architect" and verdict in {"proposed", "planned"}:
            gates.add("architect")
        elif role == "architecture-guardian" and verdict == "approved" and phase == "plan":
            guardian_plan = str(result.get("plan_revision") or "")
            if profile == "epic-implementation":
                item = next(
                    (
                        candidate for candidate in state.get("selected_items", [])
                        if isinstance(candidate, dict)
                        and candidate.get("item_id") == result.get("item_id")
                        and candidate.get("item_revision") == result.get("item_revision")
                    ),
                    None,
                )
                if item is not None and guardian_plan == str(item.get("plan_revision") or ""):
                    gates.add("architecture-plan")
            elif guardian_plan and guardian_plan == str(state.get("plan_revision") or ""):
                gates.add("architecture-plan")
        elif role == "test-maker" and verdict == "assessment_ready":
            gates.add("test-maker")
        elif role == "implementor" and verdict == "implemented":
            gates.add("implementor")
        elif role == "reviewer" and verdict == "approved" and result_is_current(result, state, current_revision):
            gates.add("reviewer")
        elif (
            role == "architecture-guardian"
            and verdict == "approved"
            and phase == "diff"
            and result_is_current(result, state, current_revision)
        ):
            gates.add("architecture")
        elif role == "qa" and verdict == "pass" and result_is_current(result, state, current_revision):
            gates.add("qa")
        elif role == "browser-qa" and verdict == "pass" and result_is_current(result, state, current_revision):
            gates.add("browser")
        elif (
            role == "security-reviewer"
            and verdict == "approved"
            and result_is_current(result, state, current_revision)
        ):
            gates.add("security")
        elif role == "contract-qa" and verdict == "pass" and result_is_current(result, state, current_revision):
            gates.add("contract")
        elif role == "devops" and verdict == "prepared":
            gates.add("devops")
        elif (
            role == "infrastructure-reviewer"
            and verdict == "approved"
            and result_is_current(result, state, current_revision)
        ):
            gates.add("infrastructure")
        elif (
            role == "deployment-agent"
            and verdict == "deployed_healthy"
            and result_is_current(result, state, current_revision)
        ):
            gates.add("deployment")
    return gates


def handle_session_start(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    telemetry.flush_pending()
    state_path, _ = state_paths(payload, context)
    prior = read_state(state_path)
    if not prior.get("active"):
        return additional_context("SessionStart", context_text(context))
    def updater(state: Dict[str, Any]) -> None:
        state["last_start_source"] = payload.get("source")
        state.setdefault("started_at", int(time.time()))

    state = update_state(payload, context, updater)
    active = f" Active workflow profile: {state.get('profile', 'implementation')}." if state.get("active") else ""
    return additional_context("SessionStart", context_text(context) + active)


def handle_prompt_submit(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    prompt = str(payload.get("prompt") or "")
    state_path, _ = state_paths(payload, context)
    prior_state = read_state(state_path)
    active_profile = str(prior_state.get("profile")) if prior_state.get("active") else None
    selected = workflow_profile(prompt, active_profile)
    if not selected:
        return None
    profile, activation = selected
    routes = bugfix_routes(prompt) if profile == "bugfix" else {}
    project = project_routes(prompt, profile)

    new_workflow = (
        not prior_state.get("active")
        or prior_state.get("profile") != profile
        or prior_state.get("repository_reaudit_required")
        or prior_state.get("state_health") != "healthy"
    )
    baseline = workspace_snapshot(context) if new_workflow else {}

    def updater(state: Dict[str, Any]) -> None:
        already_active = bool(state.get("active"))
        profile_changed = state.get("profile") != profile
        recovering = bool(
            state.get("repository_reaudit_required")
            or state.get("state_health") != "healthy"
        )
        state["active"] = True
        state["activation"] = activation
        state["profile"] = profile
        state["last_prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if profile == "bugfix":
            previous_routes = state.get("bugfix_routes", {}) if already_active and not profile_changed else {}
            state["bugfix_routes"] = {
                name: bool(enabled or previous_routes.get(name)) for name, enabled in routes.items()
            }
        else:
            state["bugfix_routes"] = {}
        if profile in PROFILE_ROLE_VERDICTS:
            previous_project = state.get("project_routes", {}) if already_active and not profile_changed else {}
            mutation_opt_out = bool(PROJECT_MUTATION_OPT_OUT.search(prompt))
            state["project_routes"] = {
                "project_targeted": bool(project.get("project_targeted") or previous_project.get("project_targeted")),
                "mutation_requested": (
                    False
                    if mutation_opt_out
                    else bool(project.get("mutation_requested") or previous_project.get("mutation_requested"))
                ),
            }
        else:
            state["project_routes"] = {}
        if not already_active or profile_changed or recovering:
            state["task_assessments"] = []
            state["task_reassessment_required"] = True
            state["baseline_dirty"] = baseline
            state["current_dirty"] = baseline
            state["commands"] = []
            state["verification"] = {}
            state["touched_paths"] = []
            state["stop_turns"] = []
            state["subagent_results"] = []
            state["test_assessments"] = []
            state["selected_items"] = []
            state.pop("epic_inventory", None)
            state['completed_epic_items'] = []
            state["repository_gates"] = sorted(repository_gate_floor(context["project"]))
            state["activated_at"] = int(time.time())
        state["state_health"] = "healthy"
        state["repository_reaudit_required"] = False

    update_state(payload, context, updater)
    if not prior_state.get("active") or prior_state.get("profile") != profile:
        telemetry.record("workflow_started", payload, context, profile)
    mode = "explicitly" if activation == "explicit" else "from task intent"
    if profile == "bugfix":
        enabled = ", ".join(name for name, value in routes.items() if value) or "local"
        return additional_context(
            "UserPromptSubmit",
            f"WGC bugfix workflow activated {mode}; routes={enabled}. Build a redacted BugCase, reproduce before patching, support the root cause with scoped evidence, protect regression tests, then use TaskAssessment to select applicable independent gates. Runtime inspection is read-only and deployment still requires explicit human approval.",
        )
    if profile == "task-creation":
        mutation = "publish only through an exact MutationPlan" if project.get("mutation_requested") else "remain read-only until publication is requested"
        return additional_context(
            "UserPromptSubmit",
            f"WGC task-creation workflow activated {mode}. Use YouTrack MCP only, resolve project keys, research code, interview the user, compare alternatives, obtain TaskAssessment, independent story-point estimates and backlog review, and {mutation}. Do not persist raw prompts or guess missing product semantics.",
        )
    if profile == "epic-implementation":
        return additional_context(
            "UserPromptSubmit",
            f"WGC epic-implementation workflow activated {mode}. Research the full YouTrack epic and plan every task before execution; freeze batches of up to 100 issue IDs, build dependency waves, require per-item TaskAssessment and its applicable gates, and synchronize statuses only after evidence.",
        )
    return additional_context(
        "UserPromptSubmit",
        f"WGC implementation workflow activated {mode}. Build a WorkItem, preserve baseline dirty paths, and launch Task Assessor first, then only the selected Light/Standard/Full roles.",
    )


def handle_subagent_start(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state_path, _ = state_paths(payload, context)
    if not read_state(state_path).get("active"):
        return None
    revision = workspace_identity(context)
    agent_id = str(payload.get("agent_id") or "")

    def updater(value: Dict[str, Any]) -> None:
        inputs = value.setdefault("subagent_inputs", {})
        inputs[agent_id] = {"revision": revision, "at": int(time.time())}
        if len(inputs) > 100:
            oldest = sorted(inputs, key=lambda key: inputs[key].get("at", 0))[:-100]
            for key in oldest:
                inputs.pop(key, None)

    state = update_state(payload, context, updater)
    telemetry.record("agent_started", payload, context, str(state.get("profile") or "implementation"))
    active = " Active WGC workflow state is present." if state.get("active") else ""
    profile = str(state.get("profile") or "implementation")
    evidence = (
        " For bugfix work, gather runtime evidence read-only with narrow time/service scope, redact secrets and personal data, and never persist raw logs or the user prompt."
        if profile == "bugfix"
        else (
            " For YouTrack MCP work, use only the assigned Project/item allowlist, never persist raw issue bodies or the user prompt, and do not mutate Project state unless assigned the youtrack-operator role with explicit authority."
            if profile in {"task-creation", "epic-implementation"}
            else ""
        )
    )
    message = (
        f"WGC subagent boundary: project={context['project']}; profile={profile}.{active} Read root and nested AGENTS.md before work. "
        "Stay inside the assigned repository/path scope, preserve existing changes, return evidence and a role verdict, and do not commit, push, deploy, or write to the cluster unless the assignment explicitly authorizes it."
        f"{evidence} Your exact input revision is {revision}."
        ' End the final response with exactly one line: WGC_AGENT_RESULT: {"role":"<role>","verdict":"<allowed-verdict>","phase":"<role-required-phase-or-empty>","input_revision":"<exact-input-revision>"}'
    )
    if profile in {"implementation", "bugfix", "epic-implementation"}:
        message += (
            " Test-maker must use verdict assessment_ready and add flat plan_revision, acceptance_revision, "
            "test_criticality, test_disposition, scope_fingerprint and disposition-specific evidence fields."
            " Execution Architect proposed/planned markers require plan_revision and minimum_test_criticality."
        )
    if profile == "implementation":
        message += " The Architect also records the WorkItem acceptance_revision before TestAssessment."
    if profile == "bugfix":
        message += " The Reproducer records the reproduced/characterized acceptance_revision before TestAssessment."
    if profile == "epic-implementation":
        message += (
            " Project Manager scope must add selected_items[{item_id,item_revision,plan_revision,acceptance_revision,minimum_test_criticality}] or obtain the three revision/floor fields from matching per-item Architect/Product markers; every item-facing "
            "assessment/implementation/diff-review/QA/outcome marker must repeat matching item_id and item_revision."
        )
    if profile in {"implementation", "bugfix", "epic-implementation"}:
        message += (
            " Architecture Guardian phase=plan markers must add plan_revision matching the current plan."
            + (
                " In epic-implementation they must also add the exact frozen item_id and item_revision; a global plan marker is invalid."
                if profile == "epic-implementation"
                else ""
            )
        )
    message += " Use the assignment's explicit model, reasoning effort and fork_turns; never inherit implicitly. Task Assessor returns task_assessment; every assigned downstream result repeats its assessment_revision. Load only assigned role/domain references."
    return additional_context("SubagentStart", message)



def bind_task_plan(state, task):
    target = state
    if task.get('item_id'):
        target = next(i for i in state['selected_items'] if i['item_id'] == task['item_id'])
    for field in ('plan_revision', 'acceptance_revision'):
        target[field] = task[field]
    target['minimum_test_criticality'] = task['risk']
    target['plan_guardian_required'] = False


def valid_orchestrator_result(payload, task, profile, revision):
    message = str(payload.get('last_assistant_message') or '')
    marker = 'WGC_ORCHESTRATOR_RESULT:'
    lines = [line.split(marker, 1)[1].strip() for line in message.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        return False
    try:
        value = json.loads(lines[0])
        fields = {'assessment_revision', 'input_revision', 'acceptance_verified', 'evidence_refs', 'reproduced_before', 'reproduced_after', 'root_cause_reviewed'}
        if not isinstance(value, dict) or set(value) - fields:
            return False
        _, error = bounded_text_list(value.get('evidence_refs'), 'evidence_refs')
        return not error and value.get('assessment_revision') == task['assessment_revision'] and value.get('input_revision') == revision and value.get('acceptance_verified') is True and (profile != 'bugfix' or all(value.get(k) is True for k in ('reproduced_before', 'reproduced_after', 'root_cause_reviewed')))
    except (TypeError, ValueError):
        return False


def handle_subagent_stop(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state_path, _ = state_paths(payload, context)
    if not read_state(state_path).get("active"):
        return None
    state = update_state(payload, context, lambda value: None)
    if not state.get("active"):
        return None
    result, error = parse_agent_result(
        str(payload.get("last_assistant_message") or ""),
        str(state.get("profile") or "implementation"),
    )
    telemetry.record("agent_stopped", payload, context, str(state.get("profile") or "implementation"), result.get("role") if result else None)
    agent_id = str(payload.get("agent_id") or "")
    expected = state.get("subagent_inputs", {}).get(agent_id, {}).get("revision")
    if not error and expected and result and result.get("input_revision") != expected:
        error = "input_revision does not match the revision assigned at SubagentStart"
    profile = str(state.get("profile") or "implementation")
    normalized_task = None
    assessor_test = None
    if not error and result and result['role'] == 'task-assessor' and result['verdict'] == 'assessed':
        try:
            normalized_task = teams.normalize(result.get('task_assessment'))
            if not expected or result['input_revision'] != workspace_identity(context):
                raise ValueError('Task Assessor requires a registered, unchanged input revision')
            paths, path_error = normalize_exact_paths(normalized_task['assessed_paths'], 'assessed_paths', context)
            if path_error:
                raise ValueError(path_error)
            if paths != normalized_task['assessed_paths']:
                raise ValueError('TaskAssessment paths must be canonical')
            for field in ('rationale', 'plan_revision', 'acceptance_revision'):
                _, field_error = bounded_text(normalized_task[field], field)
                if field_error:
                    raise ValueError(field_error)
            _, field_error = bounded_text_list(normalized_task['evidence_refs'], 'evidence_refs')
            if field_error:
                raise ValueError(field_error)
            if profile == 'epic-implementation':
                item = next((i for i in state.get('selected_items', []) if i['item_id'] == normalized_task.get('item_id') and i['item_revision'] == normalized_task.get('item_revision')), None)
                if item is None:
                    raise ValueError('TaskAssessment requires a frozen epic item')
                for field in ('plan_revision', 'acceptance_revision'):
                    if item.get(field) and item[field] != normalized_task[field]:
                        raise ValueError('TaskAssessment disagrees with frozen ' + field)
            elif normalized_task.get('item_id'):
                raise ValueError('item identity is only valid for epic work')
            # The assessor may plan ordinary implementation tests but never author them.
            # Bugfix add/update remains independently owned by Test-maker.
            assessor_owns_test_plan = (
                profile != 'task-creation'
                and normalized_task['mode'] != 'full'
                and not (
                    profile == 'bugfix'
                    and normalized_task['test_disposition'] in {'add', 'update'}
                )
            )
            if assessor_owns_test_plan:
                test_state = json.loads(json.dumps(state))
                bind_task_plan(test_state, normalized_task)
                assessor_test, test_error = normalize_test_assessment(result.get('assessment'), test_state, profile, context)
                if test_error:
                    raise ValueError(test_error)
                if assessor_test['test_disposition'] != normalized_task['test_disposition'] or assessor_test['test_criticality'] != normalized_task['risk'] or assessor_test['assessed_paths'] != normalized_task['assessed_paths']:
                    raise ValueError('TaskAssessment and TestAssessment disagree')
                if normalized_task['test_disposition'] in {'add', 'update'} and assessor_test['test_ownership'] != 'implementor':
                    raise ValueError('standard add/update TaskAssessment requires implementor-owned tests')
            elif result.get('assessment') is not None:
                raise ValueError('this route requires a separate Test-maker or no execution tests')
            result = {k: result[k] for k in ('role', 'verdict', 'phase', 'input_revision')}
            result['task_assessment'] = normalized_task
            if normalized_task.get('item_id'):
                result.update(item_id=normalized_task['item_id'], item_revision=normalized_task['item_revision'])
        except (ValueError, TypeError, KeyError) as problem:
            error = str(problem)
    if not error and result and result['role'] != 'task-assessor':
        task = teams.active(state, result.get('item_id'))
        if task and result.get('assessment_revision') != task['assessment_revision']:
            error = 'role result requires the current assessment_revision'
        if task and any(result.get(field) is not None and result[field] != task[field] for field in ('plan_revision', 'acceptance_revision')):
            error = 'changed plan/acceptance requires a new TaskAssessment'
        independent = {'reviewer', 'architecture-guardian', 'qa', 'browser-qa', 'security-reviewer', 'contract-qa', 'data-migration-reviewer', 'reliability-reviewer', 'test-maker', 'infrastructure-reviewer'}
        if task and result['role'] in independent and any(r.get('agent_id') == agent_id and r.get('role') in {'implementor', 'devops'} for r in state.get('subagent_results', [])):
            error = 'independent review/test roles cannot reuse the implementation agent'
    normalized_items: Optional[List[Dict[str, Any]]] = None
    normalized_assessment: Optional[Dict[str, Any]] = None
    if (
        not error
        and result
        and profile in {"implementation", "bugfix", "epic-implementation"}
        and result.get("role") == "architect"
        and result.get("verdict") in {"proposed", "planned"}
    ):
        plan_revision = str(result.get("plan_revision") or "").strip()
        minimum = str(result.get("minimum_test_criticality") or "").lower().strip()
        if not plan_revision or len(plan_revision) > 200:
            error = "execution architect result requires a bounded plan_revision"
        elif minimum not in TEST_CRITICALITIES:
            error = "execution architect result requires minimum_test_criticality=critical|standard|low"
        elif profile == "implementation":
            acceptance = str(result.get("acceptance_revision") or "").strip()
            if not acceptance or len(acceptance) > 200:
                error = "implementation acceptance owner result requires a bounded acceptance_revision"
        if not error:
            previous_plan: Optional[str] = None
            previous_minimum: Optional[str] = None
            if profile == "epic-implementation" and result.get("item_id"):
                prior_item = next(
                    (
                        item for item in state.get("selected_items", [])
                        if isinstance(item, dict)
                        and item.get("item_id") == result.get("item_id")
                        and item.get("item_revision") == str(result.get("item_revision") or "").lower()
                    ),
                    None,
                )
                if prior_item is not None:
                    previous_plan = str(prior_item.get("plan_revision") or "") or None
                    previous_minimum = str(prior_item.get("minimum_test_criticality") or "").lower() or None
            elif profile != "epic-implementation":
                previous_plan = str(state.get("plan_revision") or "") or None
                previous_minimum = str(state.get("minimum_test_criticality") or "").lower() or None
            if (
                previous_plan == plan_revision
                and previous_minimum in TEST_CRITICALITY_RANK
                and TEST_CRITICALITY_RANK[minimum] < TEST_CRITICALITY_RANK[previous_minimum]
            ):
                error = (
                    "minimum test criticality cannot be lowered within the same plan_revision; "
                    "issue a new plan_revision and obtain a new Architecture Guardian plan approval"
                )
    if (
        not error
        and result
        and profile == "bugfix"
        and result.get("role") == "reproducer"
        and result.get("verdict") in {"reproduced", "characterized"}
    ):
        acceptance = str(result.get("acceptance_revision") or "").strip()
        if not acceptance or len(acceptance) > 200:
            error = "bugfix acceptance owner result requires a bounded acceptance_revision"
    if (
        not error
        and result
        and profile == "epic-implementation"
        and result.get("role") == "product-manager"
        and result.get("verdict") == "accepted"
        and result.get("phase") == "scope"
        and (result.get("item_id") or result.get("item_revision"))
    ):
        acceptance = str(result.get("acceptance_revision") or "").strip()
        if not acceptance or len(acceptance) > 200:
            error = "epic per-item acceptance owner result requires a bounded acceptance_revision"
    if (
        not error
        and result
        and profile in {"implementation", "bugfix", "epic-implementation"}
        and result.get("role") == "architecture-guardian"
        and result.get("phase") == "plan"
    ):
        guardian_plan = str(result.get("plan_revision") or "").strip()
        if not guardian_plan or len(guardian_plan) > 200:
            error = "Architecture Guardian phase=plan result requires a bounded plan_revision"
        elif profile == "epic-implementation":
            item_id = str(result.get("item_id") or "").strip()
            item_revision = str(result.get("item_revision") or "").lower().strip()
            matched_item = next(
                (
                    item for item in state.get("selected_items", [])
                    if isinstance(item, dict)
                    and item.get("item_id") == item_id
                    and item.get("item_revision") == item_revision
                ),
                None,
            )
            if matched_item is None:
                error = (
                    "epic Architecture Guardian phase=plan result requires exact item_id/item_revision "
                    "from the frozen selected_items ledger"
                )
            elif guardian_plan != str(matched_item.get("plan_revision") or ""):
                error = "epic Architecture Guardian plan_revision is stale for the selected item"
        elif guardian_plan != str(state.get("plan_revision") or ""):
            error = "Architecture Guardian plan_revision is stale for the current execution plan"
    if not error and result and result.get("role") == "test-maker" and result.get("verdict") == "assessment_ready":
        normalized_assessment, error = normalize_test_assessment(result.get("assessment"), state, profile, context)
        if not error and normalized_assessment is not None:
            result = {
                "role": result["role"],
                "verdict": result["verdict"],
                "phase": result["phase"],
                "input_revision": result["input_revision"],
                "assessment": normalized_assessment,
                **({"assessment_revision": result["assessment_revision"]} if result.get("assessment_revision") else {}),
                **(
                    {
                        "item_id": normalized_assessment["item_id"],
                        "item_revision": normalized_assessment["item_revision"],
                    }
                    if profile == "epic-implementation"
                    else {}
                ),
            }
    if (
        not error
        and result
        and profile == "epic-implementation"
        and result.get("role") == "project-manager"
        and result.get("verdict") == "planned"
        and result.get("phase") == "scope"
    ):
        if result.get('selected_items') == [] and result.get('epic_inventory'):
            normalized_items, error = [], None
        else:
            normalized_items, error = normalize_selected_items(result.get("selected_items"))
        if not error:
            try:
                snapshot = inventory.normalize(result.get('epic_inventory') or state.get('epic_inventory'))
                prior_inventory = state.get('epic_inventory')
                if prior_inventory and prior_inventory['revision'] != snapshot['revision']:
                    if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}', str(result.get('inventory_change_decision') or '')):
                        raise ValueError('changed epic inventory requires an explicit user decision reference')
                if not inventory.covers_batch(snapshot, normalized_items):
                    raise ValueError('execution batch must be a subset of the complete epic inventory')
                result['epic_inventory'] = snapshot
            except (ValueError, TypeError, KeyError) as problem:
                error = str(problem)
        if not error and normalized_items is not None:
            previous_items = {
                str(item.get("item_id")): item
                for item in state.get("selected_items", [])
                if isinstance(item, dict) and item.get("item_id")
            }
            for candidate in normalized_items:
                previous = previous_items.get(str(candidate["item_id"]))
                if not previous:
                    continue
                previous_plan = str(previous.get("plan_revision") or "")
                next_plan = str(candidate.get("plan_revision") or previous_plan)
                previous_minimum = str(previous.get("minimum_test_criticality") or "").lower()
                next_minimum = str(candidate.get("minimum_test_criticality") or previous_minimum).lower()
                if (
                    previous_plan
                    and next_plan == previous_plan
                    and previous_minimum in TEST_CRITICALITY_RANK
                    and next_minimum in TEST_CRITICALITY_RANK
                    and TEST_CRITICALITY_RANK[next_minimum] < TEST_CRITICALITY_RANK[previous_minimum]
                ):
                    error = (
                        f"epic item {candidate['item_id']} minimum test criticality cannot be lowered within "
                        "the same plan_revision; issue a new per-item plan_revision and obtain a new "
                        "Architecture Guardian plan approval"
                    )
                    break
            result["selected_items"] = normalized_items
    if (not error and result and profile == 'epic-implementation'
            and result.get('role') == 'project-manager' and result.get('verdict') == 'progress_updated'
            and result.get('phase') == 'reconcile'):
        try:
            result['epic_reconciliation'] = inventory.normalize_report(result.get('epic_reconciliation'), state.get('epic_inventory'))
        except (ValueError, TypeError, KeyError) as problem:
            error = str(problem)
    epic_item_bound_result = bool(
        result
        and profile == "epic-implementation"
        and (
            epic_item_gate_for_result(result)
            or result.get("item_id")
            or result.get("item_revision")
        )
    )
    if not error and result and epic_item_bound_result:
        item_id = str(result.get("item_id") or "").strip()
        item_revision = str(result.get("item_revision") or "").lower().strip()
        selected = state.get("selected_items", [])
        matched = next(
            (
                item
                for item in selected
                if isinstance(item, dict)
                and item.get("item_id") == item_id
                and item.get("item_revision") == item_revision
            ),
            None,
        )
        if matched is None:
            error = "epic per-item result requires matching item_id/item_revision from the frozen selected_items ledger"
    if not error and result:
        existing_results = state.get("subagent_results", [])
        if not isinstance(existing_results, list):
            error = "result ledger is malformed; repeat the repository audit before continuing"
        else:
            result_key = agent_result_ledger_key(result)
            replaces_existing = any(
                isinstance(prior, dict) and agent_result_ledger_key(prior) == result_key
                for prior in existing_results
            )
            if len(existing_results) >= RESULT_LEDGER_LIMIT and not replaces_existing:
                error = (
                    f"result ledger reached its bounded capacity of {RESULT_LEDGER_LIMIT}; "
                    "cannot evict active lifecycle evidence"
                )
    if error:
        if payload.get("stop_hook_active"):
            return None
        return {
            "decision": "block",
            "reason": (
                f"Your WGC role artifact is incomplete: {error}. Return the evidence/report, then end with the exact one-line "
                'WGC_AGENT_RESULT JSON required by the SubagentStart instruction.'
            ),
        }

    current_snapshot = workspace_snapshot(context)
    current_classification = classify_paths(
        snapshot_since_baseline(current_snapshot, state.get("baseline_dirty")),
        state.get("touched_paths", []),
    )

    def updater(value: Dict[str, Any]) -> None:
        if normalized_task is not None:
            tasks = value.setdefault('task_assessments', [])
            tasks[:] = [t for t in tasks if t.get('item_id') != normalized_task.get('item_id')]
            tasks.append(normalized_task)
            value['task_reassessment_required'] = False
            # Old approvals cannot transfer into a new assessment, even at the same git revision.
            value['subagent_results'] = [r for r in value.get('subagent_results', []) if r.get('item_id') != normalized_task.get('item_id')]
            if normalized_task['mode'] != 'full':
                bind_task_plan(value, normalized_task)
            if assessor_test is not None:
                assessments = value.setdefault('test_assessments', [])
                assessments[:] = [a for a in assessments if a.get('item_id') != normalized_task.get('item_id')]
                assessments.append({**assessor_test, 'input_revision': result['input_revision']})
        results = value.setdefault("subagent_results", [])
        recorded = {
            **result,
            "agent_id": agent_id[:200],
            "agent_type": str(payload.get("agent_type") or "")[:200],
            "at": int(time.time()),
        }
        recorded_task = teams.active(value, recorded.get('item_id'))
        if recorded_task and recorded.get('item_id'):
            recorded['scope_revision'] = task_scope_revision(recorded_task, context)
        result_key = agent_result_ledger_key(recorded)
        matching = [
            index for index, prior in enumerate(results)
            if isinstance(prior, dict) and agent_result_ledger_key(prior) == result_key
        ]
        if matching:
            results[:] = [
                prior for prior in results
                if not isinstance(prior, dict) or agent_result_ledger_key(prior) != result_key
            ]
            results.append(recorded)
        elif len(results) < RESULT_LEDGER_LIMIT:
            results.append(recorded)
        else:
            value["state_health"] = "malformed"
            value["repository_reaudit_required"] = True
            return
        role = result.get("role")
        verdict = result.get("verdict")
        phase = result.get("phase")
        if role == "architecture-guardian" and verdict == "approved" and phase == "plan":
            if profile == "epic-implementation" and result.get("item_id"):
                approved_item = next(
                    (
                        item for item in value.get("selected_items", [])
                        if isinstance(item, dict)
                        and item.get("item_id") == result.get("item_id")
                        and item.get("item_revision") == str(result.get("item_revision") or "").lower()
                    ),
                    None,
                )
                if approved_item is not None:
                    approved_item["plan_guardian_required"] = False
            elif profile != "epic-implementation":
                value["plan_guardian_required"] = False
        if (
            role == "architect"
            and verdict in {"proposed", "planned"}
            and profile in {"implementation", "bugfix", "epic-implementation"}
        ):
            next_plan = str(result["plan_revision"]).strip()
            minimum = str(result.get("minimum_test_criticality") or "").lower()
            if profile == "epic-implementation" and result.get("item_id"):
                item = next(
                    (
                        candidate for candidate in value.get("selected_items", [])
                        if isinstance(candidate, dict)
                        and candidate.get("item_id") == result.get("item_id")
                        and candidate.get("item_revision") == str(result.get("item_revision") or "").lower()
                    ),
                    None,
                )
                if item is not None:
                    previous_plan = item.get("plan_revision")
                    previous_minimum = item.get("minimum_test_criticality")
                    plan_changed = previous_plan not in (None, next_plan)
                    floor_changed = previous_minimum not in (None, minimum)
                    if plan_changed:
                        invalidate_epic_items(
                            value,
                            {str(item["item_id"])},
                            keep_assessment=False,
                            invalidate_plan_approval=True,
                        )
                        item["plan_guardian_required"] = True
                    elif floor_changed:
                        invalidate_epic_items(
                            value,
                            {str(item["item_id"])},
                            keep_assessment=False,
                            invalidate_plan_approval=False,
                        )
                    item["plan_revision"] = next_plan
                    item["minimum_test_criticality"] = minimum
            elif profile != "epic-implementation":
                previous_plan = value.get("plan_revision")
                previous_minimum = value.get("minimum_test_criticality")
                if previous_plan and previous_plan != next_plan:
                    invalidate_test_assessment(value, invalidate_plan_approval=True)
                    value["plan_guardian_required"] = True
                elif previous_minimum and previous_minimum != minimum:
                    invalidate_test_assessment(value, invalidate_plan_approval=False)
                value["plan_revision"] = next_plan
                value["minimum_test_criticality"] = minimum
            if profile == "implementation":
                next_acceptance = str(result["acceptance_revision"]).strip()
                if value.get("acceptance_revision") and value.get("acceptance_revision") != next_acceptance:
                    invalidate_test_assessment(value, invalidate_plan_approval=False)
                value["acceptance_revision"] = next_acceptance
        if profile == "bugfix" and role == "reproducer" and verdict in {"reproduced", "characterized"}:
            next_acceptance = str(result["acceptance_revision"]).strip()
            if value.get("acceptance_revision") and value.get("acceptance_revision") != next_acceptance:
                invalidate_test_assessment(value, invalidate_plan_approval=False)
            value["acceptance_revision"] = next_acceptance
        if (
            profile == "epic-implementation"
            and role == "product-manager"
            and verdict == "accepted"
            and phase == "scope"
            and result.get("item_id")
            and result.get("acceptance_revision")
        ):
            item = next(
                (
                    candidate for candidate in value.get("selected_items", [])
                    if isinstance(candidate, dict)
                    and candidate.get("item_id") == result.get("item_id")
                    and candidate.get("item_revision") == str(result.get("item_revision") or "").lower()
                ),
                None,
            )
            if item is not None:
                next_acceptance = str(result["acceptance_revision"]).strip()
                if item.get("acceptance_revision") not in (None, next_acceptance):
                    invalidate_epic_items(value, {str(item["item_id"])}, keep_assessment=False)
                item["acceptance_revision"] = next_acceptance
        if normalized_items is not None:
            value['epic_inventory'] = result['epic_inventory']
            reconcile_selected_items(value, normalized_items)
        if role == "test-maker" and verdict == "assessment_ready":
            assessment = dict(result["assessment"])
            assessment["input_revision"] = result["input_revision"]
            assessment["at"] = int(time.time())
            assessments = value.setdefault("test_assessments", [])
            if profile == "epic-implementation":
                assessments[:] = [
                    prior
                    for prior in assessments
                    if not isinstance(prior, dict) or prior.get("item_id") != assessment.get("item_id")
                ]
            else:
                assessments[:] = []
            assessments.append(assessment)
            if len(assessments) > ADAPTIVE_LEDGER_LIMIT:
                raise ValueError("adaptive assessment ledger exceeded its bounded capacity")
            value["repository_gates"] = sorted(required_checks_for_state(current_classification, value))
        if profile == "epic-implementation":
            update_epic_item_gate(value, recorded)

    update_state(payload, context, updater)
    return None


def handle_pre_tool(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state_path, _ = state_paths(payload, context)
    tool = str(payload.get("tool_name") or "")
    command = tool_command(payload)
    if tool == "Bash":
        event_cwd = Path(context["cwd"]).resolve()
        command_cwd, workdir_violation = resolve_bash_workdir(payload, context)
        violation = workdir_violation or command_violation(
            command,
            command_cwd or event_cwd,
            canonical_bootstrap_repo(context),
            event_cwd,
        )
    elif tool in {"apply_patch", "Edit", "Write"}:
        violation = patch_violation(command, context)
    else:
        violation = None
    if violation:
        def updater(state: Dict[str, Any]) -> None:
            blocks = state.setdefault("guard_blocks", [])
            blocks.append({"at": int(time.time()), "tool": tool, "reason": violation})
            del blocks[:-30]

        update_state(payload, context, updater)
        return deny_tool(violation)

    warning = pre_tool_warning(payload, command, context)
    if warning:
        return additional_context("PreToolUse", warning, "WGC policy check requires attention")
    return None


def handle_post_tool(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state_path, _ = state_paths(payload, context)
    if not read_state(state_path).get("active"):
        return None
    tool = str(payload.get("tool_name") or "")
    command = tool_command(payload)
    touched = relative_touched_paths(command, context) if tool in {"apply_patch", "Edit", "Write"} else []
    snapshot = workspace_snapshot(context)
    exit_code = nested_exit_code(payload.get("tool_response"))
    tags = verification_tags(command) if tool == "Bash" else set()
    current_revision = workspace_identity(context)

    def updater(state: Dict[str, Any]) -> None:
        known = set(state.get("touched_paths", []))
        known.update(touched)
        state["touched_paths"] = sorted(known)[:1000]
        previous = state.get("current_dirty", state.get("baseline_dirty", {}))
        incremental = snapshot_since_baseline(snapshot, previous)
        incremental_classification = classify_paths(incremental, touched)
        if incremental_classification["paths"]:
            changed_paths = set(incremental_classification["paths"])
            teams.invalidate(state, changed_paths)
            evidence.invalidate(state.setdefault('verification', {}), changed_paths)
            all_task_scope = {p for a in state.get('task_assessments', []) for p in a['assessed_paths']}
            if changed_paths - all_task_scope or any(re.search(r'(?:lock|package\.json|config|AGENTS\.md)', p, re.I) for p in changed_paths):
                state['verification'] = {}
            production_paths = {
                path
                for path in changed_paths
                if Path(path.partition(":")[2]).suffix.lower() in SOURCE_SUFFIXES
                and not TEST_PATH.search(path.partition(":")[2])
            }
            test_paths = {
                path for path in changed_paths if TEST_PATH.search(path.partition(":")[2])
            }
            sensitive_paths = {path for path in changed_paths if contract_or_migration_path(path)}
            if sensitive_paths or production_paths or test_paths:
                verification = state.setdefault("verification", {})
                verification.pop("test", None)
                verification.pop("coverage", None)
            profile = str(state.get("profile") or "implementation")
            if profile == 'epic-implementation':
                invalidate_archived_items(state, changed_paths, bool(sensitive_paths))
            if profile == "epic-implementation" and not (production_paths or test_paths or sensitive_paths):
                all_items = {
                    str(item.get("item_id")) for item in state.get("selected_items", [])
                    if isinstance(item, dict) and item.get("item_id")
                }
                task_owners = {a['item_id'] for a in state.get('task_assessments', []) if a.get('item_id') and changed_paths & set(a['assessed_paths'])}
                covered = {p for a in state.get('task_assessments', []) for p in a['assessed_paths']}
                if task_owners and changed_paths <= covered:
                    all_items = task_owners
                # An ordinary docs/YAML/GitOps write has no trustworthy per-item owner.
                # Preserve current assessments, but conservatively clear every item gate
                # downstream of implementation so sibling evidence cannot transfer.
                invalidate_epic_items(state, all_items, keep_assessment=True)
            if profile == "epic-implementation" and (production_paths or test_paths or sensitive_paths):
                assessments = [
                    assessment for assessment in state.get("test_assessments", [])
                    if isinstance(assessment, dict) and assessment.get("item_id")
                ]
                all_items = {
                    str(item.get("item_id")) for item in state.get("selected_items", [])
                    if isinstance(item, dict) and item.get("item_id")
                }
                drop_assessment: Set[str] = set()
                keep_assessment: Set[str] = set()

                def owners_for(path: str) -> Set[str]:
                    owners: Set[str] = set()
                    for assessment in assessments + state.get('task_assessments', []):
                        scoped = set(assessment.get("assessed_paths", []))
                        proof = assessment.get("reuse_proof")
                        proof_path = proof.get("test_path") if isinstance(proof, dict) else None
                        if path in scoped or path == proof_path:
                            owners.add(str(assessment["item_id"]))
                    return owners

                for path in production_paths:
                    owners = owners_for(path)
                    if path in sensitive_paths:
                        drop_assessment.update(owners or all_items)
                    elif owners:
                        keep_assessment.update(owners)
                    else:
                        drop_assessment.update(all_items)
                for path in test_paths:
                    owners = owners_for(path)
                    if not owners:
                        drop_assessment.update(all_items)
                        continue
                    for assessment in assessments:
                        item_id = str(assessment.get("item_id"))
                        if item_id not in owners:
                            continue
                        if assessment_reuse_path_is_unchanged(assessment, path, context):
                            keep_assessment.add(item_id)
                        elif assessment_implementor_test_path_is_planned(assessment, path, context):
                            keep_assessment.add(item_id)
                        else:
                            drop_assessment.add(item_id)
                for path in sensitive_paths - production_paths - test_paths:
                    owners = owners_for(path)
                    drop_assessment.update(owners or all_items)
                if incremental_classification["k8s"] and not (drop_assessment or keep_assessment):
                    drop_assessment.update(all_items)
                keep_assessment.difference_update(drop_assessment)
                invalidate_epic_items(state, drop_assessment, keep_assessment=False)
                invalidate_epic_items(state, keep_assessment, keep_assessment=True)
            elif profile != "epic-implementation":
                scoped_paths = assessed_scope_paths(state, context)
                protected_reuse_unchanged = protected_reuse_change_is_unchanged(
                    changed_paths,
                    state,
                    context,
                )
                planned_implementor_tests = implementor_test_changes_are_planned(
                    changed_paths,
                    state,
                    context,
                )
                production_in_scope = bool(production_paths) and production_paths.issubset(scoped_paths)
                invalidate_assessment = bool(
                    sensitive_paths
                    or (incremental_classification["production"] and not production_in_scope)
                    or (
                        incremental_classification["tests"]
                        and not protected_reuse_unchanged
                        and not planned_implementor_tests
                    )
                )
                invalidate = {
                    "implementor",
                    "reviewer",
                    "qa",
                    "browser-qa",
                    "security-reviewer",
                    "contract-qa",
                    "data-migration-reviewer",
                    "reliability-reviewer",
                    "deployment-agent",
                    "youtrack-operator",
                }
                if invalidate_assessment:
                    invalidate_test_assessment(state)
                    invalidate.add("test-maker")
                if incremental_classification["k8s"]:
                    invalidate.update({"devops", "infrastructure-reviewer"})

                def still_valid(result: Any) -> bool:
                    if not isinstance(result, dict):
                        return False
                    role = result.get("role")
                    if role == "architecture-guardian" and result.get("phase") == "diff":
                        return False
                    if role == "project-manager" and result.get("phase") == "reconcile":
                        return False
                    if role == "product-manager" and result.get("phase") == "outcome":
                        return False
                    return role not in invalidate

                state["subagent_results"] = [
                    result for result in state.get("subagent_results", []) if still_valid(result)
                ]
            if incremental_classification["k8s"]:
                state["subagent_results"] = [
                    result for result in state.get("subagent_results", [])
                    if isinstance(result, dict)
                    and result.get("role") not in {"devops", "infrastructure-reviewer"}
                ]
        state["current_dirty"] = snapshot
        state["current_revision"] = current_revision
        if tool == "Bash" and command.strip():
            commands = state.setdefault("commands", [])
            commands.append(
                {
                    "at": int(time.time()),
                    **command_record(command),
                    "exit_code": exit_code,
                    "tags": sorted(tags),
                }
            )
            del commands[:-80]
            if exit_code == 0:
                verification = state.setdefault("verification", {})
                for tag in tags:
                    scoped = {p for a in state.get('task_assessments', []) for p in a['assessed_paths']}
                    verification[tag] = {'at': int(time.time()), **evidence.record(command_record(command), current_revision, evidence.environment_key(context), scoped, str(payload.get('agent_id') or 'orchestrator'))}
            else:
                for tag in tags:
                    state.setdefault('verification', {}).pop(tag, None)

    state = update_state(payload, context, updater)
    relevant_snapshot = snapshot_since_baseline(snapshot, state.get("baseline_dirty"))
    classification = classify_paths(relevant_snapshot, state.get("touched_paths", []))
    assessment = active_test_assessment(state)
    repository_gates = required_checks_for_state(classification, state)
    if set(state.get("repository_gates", [])) != repository_gates:
        update_state(payload, context, lambda value: value.update(repository_gates=sorted(repository_gates)))
    notes: List[str] = []
    if len(classification["projects"]) > 1:
        notes.append(
            "Changes now span repositories "
            + ", ".join(classification["projects"])
            + "; keep a contract-first DAG, separate checks, commits, and publication order."
        )
    if classification["production"] and assessment is None:
        notes.append("Production code changed; obtain a current TestAssessment before implementation or completion.")
    elif classification["production"] and assessment and assessment.get("test_disposition") != "none" and "test" not in state.get("verification", {}):
        notes.append("The current TestAssessment requires add/update/reuse; run its exact relevant test evidence now.")
    elif classification["production"] and assessment and assessment.get("test_disposition") == "none":
        notes.append("The current TestAssessment selects none; collect its alternative evidence and keep all repository gates.")
    if classification["tests"]:
        notes.append("Test files changed; record protected paths/hashes and reject later Implementor edits to them in the orchestration gate.")
    if classification["k8s"]:
        notes.append("GitOps files changed; run the renderer and validators, then require independent infrastructure review before any deployment approval.")
    if notes:
        digest = hashlib.sha256(' '.join(notes).encode()).hexdigest()
        if state.get('last_advisory_sha256') != digest:
            update_state(payload, context, lambda value: value.update(last_advisory_sha256=digest))
            return additional_context("PostToolUse", " ".join(notes))
    return None


def handle_stop(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state = update_state(payload, context, lambda value: None)
    if not state.get("active"):
        return None
    profile = str(state.get("profile") or "implementation")
    if state.get("repository_reaudit_required") or state.get("state_health") != "healthy":
        if payload.get("stop_hook_active"):
            return None
        return {
            "decision": "block",
            "reason": (
                "WGC hook state is malformed or unsupported. Completion is blocked until a fresh "
                "repository audit and workflow reactivation establish state v4."
            ),
        }

    snapshot = workspace_snapshot(context)
    if snapshot_since_baseline(snapshot, state.get('current_dirty', state.get('baseline_dirty'))):
        # Catch edits performed outside hooked tools before considering old evidence.
        handle_post_tool({**payload, 'tool_name': '', 'tool_input': {}}, context)
        state = update_state(payload, context, lambda value: None)
    relevant_snapshot = snapshot_since_baseline(snapshot, state.get("baseline_dirty"))
    classification = classify_paths(relevant_snapshot, state.get("touched_paths", []))
    if not classification['paths'] and (
            epic_stages.pending_user(state, workspace_identity(context))
            or epic_stages.stage_checkpoint(state, workspace_identity(context))):
        # Keep the workflow active. A user interview/approval pause must neither
        # fabricate a fully decomposed backlog nor be labelled completion.
        return None
    if (
        profile not in {"task-creation", "epic-implementation"}
        and not any((classification["production"], classification["tests"], classification["docs"], classification["k8s"]))
    ):
        def no_changes(value: Dict[str, Any]) -> None:
            value["active"] = False
            value["completed_at"] = int(time.time())
            value["completion"] = "no_tracked_changes"

        update_state(payload, context, no_changes)
        telemetry.record("workflow_ended", payload, context, profile, outcome="no_tracked_changes")
        return None

    routes = state.get("bugfix_routes", {}) if profile == "bugfix" else {}
    routes = routes if isinstance(routes, dict) else {}
    project = state.get("project_routes", {})
    project = project if isinstance(project, dict) else {}
    required = required_checks_for_state(classification, state)
    if profile == "bugfix" and routes.get("ui"):
        required.add("browser")
    if profile == "bugfix" and routes.get("deployment"):
        required.add("smoke")
    completed = set(state.get("verification", {}).keys())
    missing = sorted(required - completed)
    if profile == "bugfix":
        required_gates = {
            "bug-triage",
            "evidence",
            "root-cause",
            "root-cause-review",
            "reproducer",
            "architect",
            "architecture-plan",
            "test-maker",
            "implementor",
            "reviewer",
            "architecture",
            "qa",
        }
        if routes.get("ui"):
            required_gates.add("browser")
        if routes.get("security"):
            required_gates.add("security")
        if routes.get("contract"):
            required_gates.add("contract")
        if routes.get("gitops") or classification["k8s"]:
            required_gates.update({"devops", "infrastructure"})
        if routes.get("deployment"):
            required_gates.add("deployment")
    elif profile == "task-creation":
        required_gates = {"product", "project", "implementation-audit", "architect", "backlog-review", "effort-estimate"}
        if project.get("mutation_requested"):
            required_gates.add("project-publish")
    elif profile == "epic-implementation":
        required_gates = {
            "product-scope",
            "product-outcome",
            "project-scope",
            "architect",
            "architecture-plan",
            "test-maker",
            "implementor",
            "reviewer",
            "architecture",
            "qa",
            "project-reconcile",
        }
        if project.get("mutation_requested"):
            required_gates.add("project-sync")
        if classification["k8s"]:
            required_gates.update({"devops", "infrastructure"})
    else:
        required_gates = {"architect", "test-maker", "reviewer", "architecture", "qa"}
        if classification["k8s"]:
            required_gates.add("infrastructure")
    task = teams.active(state)
    if profile == 'epic-implementation':
        required_gates = {'project-scope', 'project-reconcile', 'epic-inventory'}
        if project.get('mutation_requested'):
            required_gates.add('project-sync')
    elif task:
        required_gates = teams.required_gates(profile, task)
        if profile == 'task-creation' and project.get('mutation_requested'):
            required_gates.add('project-publish')
        if profile == 'bugfix':
            for route, gate in (('security', 'security'), ('contract', 'contract'), ('deployment', 'deployment')):
                if routes.get(route):
                    required_gates.add(gate)
    else:
        required_gates.add('task-assessor')
    if profile in {'implementation', 'bugfix'} and project.get('mutation_requested'):
        required_gates.add('project-sync')
    if task and profile != 'task-creation' and active_test_assessment(state) is None:
        required_gates.add('test-assessment')
    current_revision = workspace_identity(context)
    state['current_revision'] = current_revision
    if task and (task['mode'] == 'light' or profile == 'bugfix' and task['mode'] != 'full'):
        if not valid_orchestrator_result(payload, task, profile, current_revision):
            required_gates.add('orchestrator-verification')
    observed_gates = approved_agent_gates(state, current_revision)
    gate_missing = sorted(required_gates - observed_gates)
    if profile == "epic-implementation":
        gate_missing.extend("item:" + gap for gap in epic_item_gaps(state))
    if state.get("repository_reaudit_required") or state.get("state_health") != "healthy":
        gate_missing.append("repository-reaudit-after-state-recovery")
    if not missing and not gate_missing:
        def complete(value: Dict[str, Any]) -> None:
            value["active"] = False
            value["completed_at"] = int(time.time())

        update_state(payload, context, complete)
        telemetry.record("workflow_ended", payload, context, profile, outcome="completed")
        return None

    turn_id = str(payload.get("turn_id") or "unknown")
    if payload.get("stop_hook_active") or turn_id in state.get("stop_turns", []):
        def incomplete(value: Dict[str, Any]) -> None:
            value["active"] = False
            value["completed_at"] = int(time.time())
            value["completion"] = "incomplete"
            value["remaining_gaps"] = {"verification": missing, "gates": gate_missing}

        update_state(payload, context, incomplete)
        telemetry.record("workflow_ended", payload, context, profile, outcome="incomplete")
        return None

    def updater(value: Dict[str, Any]) -> None:
        turns = value.setdefault("stop_turns", [])
        turns.append(turn_id)
        del turns[:-20]

    update_state(payload, context, updater)

    workflow_name = profile
    parts = [f"Before finishing the WGC {workflow_name}, close the observable completion gaps."]
    if missing:
        parts.append("Missing successful verification evidence: " + ", ".join(missing) + ".")
    if gate_missing:
        parts.append("The structured gate ledger is missing: " + ", ".join(gate_missing) + ".")
    parts.append(
        "Run the applicable checks or state the exact blocker, verify protected-test hashes and repository scope, then produce a factual final report."
    )
    return {"decision": "block", "reason": " ".join(parts)}


def handle_session_end(payload: Dict[str, Any], context: Dict[str, Any]) -> None:
    state_path, _ = state_paths(payload, context)
    prior = read_state(state_path)
    if not prior.get("active"):
        return None
    telemetry.record("workflow_ended", payload, context, str(prior.get("profile") or "implementation"), outcome="session_closed")
    def updater(state: Dict[str, Any]) -> None:
        state["active"] = False
        state["ended_at"] = int(time.time())
        state["commands"] = state.get("commands", [])[-20:]
        state["touched_paths"] = state.get("touched_paths", [])[:500]

    update_state(payload, context, updater)
    return None


HANDLERS: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]]] = {
    "session-start": handle_session_start,
    "prompt-submit": handle_prompt_submit,
    "subagent-start": handle_subagent_start,
    "subagent-stop": handle_subagent_stop,
    "pre-tool": handle_pre_tool,
    "post-tool": handle_post_tool,
    "stop": handle_stop,
    "session-end": handle_session_end,
}


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2 or argv[1] not in HANDLERS:
        sys.stderr.write("usage: wgc_hooks.py <" + "|".join(sorted(HANDLERS)) + ">\n")
        return 2
    payload = read_input()
    try:
        context = detect_context(payload.get("cwd"))
        if context is None:
            return 0
        emit(HANDLERS[argv[1]](payload, context))
        return 0
    except Exception as error:  # Safety fails closed; advisory bookkeeping fails open.
        if argv[1] == "pre-tool":
            emit(deny_tool(f"WGC safety hook failed internally ({type(error).__name__}); the tool call is blocked until the hook is healthy."))
            return 0
        sys.stderr.write(f"wgc hook warning: {type(error).__name__}: {error}\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
