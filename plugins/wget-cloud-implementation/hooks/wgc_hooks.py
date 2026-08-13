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
EXPLICIT_SKILL = re.compile(r"(?:\$wgc-implementation|\bwgc-implementation\b)", re.IGNORECASE)
TEST_PATH = re.compile(r"(?:^|/)(?:tests?|__tests__|e2e)(?:/|$)|(?:\.(?:test|spec)\.[^.]+$)", re.IGNORECASE)
DOC_PATH = re.compile(r"(?:^|/)(?:docs?|README|AGENTS|ARCHITECTURE|BUSINESS_LOGIC)(?:[./_-]|$)", re.IGNORECASE)
SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
ROLE_VERDICTS: Dict[str, Set[str]] = {
    "explorer": {"mapped", "needs_input"},
    "architect": {"proposed", "needs_input"},
    "architecture-guardian": {"approved", "changes_requested", "needs_input"},
    "test-maker": {"baseline_ready", "changes_requested", "blocked"},
    "implementor": {"implemented", "needs_input", "blocked"},
    "reviewer": {"approved", "changes_requested", "needs_input"},
    "qa": {"pass", "defects_found", "blocked"},
    "devops": {"prepared", "needs_input", "blocked"},
    "infrastructure-reviewer": {"approved", "changes_requested", "needs_input"},
    "deployment-agent": {"deployed_healthy", "failed", "blocked", "approval_invalid"},
}


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
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def update_state(
    payload: Dict[str, Any],
    context: Dict[str, Any],
    updater: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    path, lock = state_paths(payload, context)
    with file_lock(lock):
        state = read_state(path)
        state.setdefault("version", 1)
        state.setdefault("active", False)
        state.setdefault("activation", "none")
        state.setdefault("commands", [])
        state.setdefault("verification", {})
        state.setdefault("touched_paths", [])
        state.setdefault("baseline_dirty", {})
        state.setdefault("stop_turns", [])
        state.setdefault("subagent_results", [])
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
    for project, paths in current.items():
        previous = baseline_map.get(project, {})
        previous = previous if isinstance(previous, dict) else {}
        changed = {path: status for path, status in paths.items() if previous.get(path) != status}
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


def workspace_boundary(context: Dict[str, Any]) -> Path:
    coordinator = context.get("coordinator_root")
    return Path(coordinator or context["repo_root"]).resolve()


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
    assignment = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.DOTALL)
    sudo_value_options = {"-u", "-g", "-h", "-p", "-C", "-R", "-T", "--user", "--group", "--host"}
    for segment in segments:
        index = 0
        while index < len(segment):
            while index < len(segment) and assignment.fullmatch(segment[index]):
                index += 1
            if index >= len(segment):
                break
            executable = Path(segment[index]).name.lower()
            if executable in {"env"}:
                index += 1
                while index < len(segment) and (segment[index].startswith("-") or assignment.fullmatch(segment[index])):
                    index += 1
                continue
            if executable == "sudo":
                index += 1
                while index < len(segment) and segment[index].startswith("-"):
                    option = segment[index].split("=", 1)[0]
                    index += 1
                    if option in sudo_value_options and index < len(segment):
                        index += 1
                continue
            if executable in {"nohup", "time"}:
                index += 1
                while index < len(segment) and segment[index].startswith("-"):
                    index += 1
                continue
            if executable == "command":
                if index + 1 < len(segment) and segment[index + 1] in {"-v", "-V"}:
                    commands.append(("command", segment[index + 1 :]))
                    break
                index += 1
                continue
            args = segment[index + 1 :]
            commands.append((executable, args))
            if executable in {"bash", "sh", "zsh", "dash", "ksh"}:
                for arg_index, arg in enumerate(args[:-1]):
                    if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):
                        commands.extend(shell_commands(args[arg_index + 1], depth + 1))
                        break
            break
    return commands


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


def command_violation(command: str, cwd: Path) -> Optional[str]:
    if not command.strip():
        return None
    if suspicious_secret(command):
        return "Possible credential material in a command is blocked. Use an approved environment or secret manager without exposing the value."

    for executable, args in shell_commands(command):
        if executable == "kubectl":
            violation = kubectl_violation(args)
            if violation:
                return violation
        elif executable == "helm" and any(token.lower() in {"install", "upgrade", "uninstall", "rollback"} for token in args):
            return "Direct Helm mutation is blocked; use the k8s GitOps repository."
        elif executable == "argocd":
            words = [token.lower() for token in args if not token.startswith("-")]
            if any(words[index : index + 2] in (["app", "sync"], ["app", "set"], ["app", "delete"], ["app", "rollback"], ["app", "terminate-op"]) for index in range(max(0, len(words) - 1))):
                return "Direct Argo CD mutation is blocked; publish reviewed Git desired state instead."
        elif executable == "flux" and any(token.lower() in {"reconcile", "suspend", "resume", "delete"} for token in args):
            return "Direct Flux mutation is blocked by the GitOps policy."
        elif executable == "docker":
            words = [token.lower() for token in args if not token.startswith("-")]
            if words[:2] in (["system", "prune"], ["volume", "prune"]):
                return "Broad Docker prune is blocked because it can delete unrelated local data."
        elif executable == "terraform":
            action, _ = first_positional(args, {"-chdir"})
            if action in {"apply", "destroy"}:
                return "Direct infrastructure mutation is blocked in this GitOps workflow."
        elif executable == "rm" and broad_delete_violation(args, cwd):
            return "Broad recursive deletion of a workspace, repository, home directory, or filesystem root is blocked."
        elif executable == "git":
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


def required_checks(classification: Dict[str, Any]) -> Set[str]:
    required: Set[str] = set()
    projects = set(classification.get("projects", []))
    if classification.get("production"):
        required.add("test")
    if "frontend" in projects:
        required.add("typecheck")
    if "backend" in projects and classification.get("production"):
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


def gate_mentions(message: str) -> Set[str]:
    lower = message.lower()
    result: Set[str] = set()
    approval = r"(?:approved|pass(?:ed)?|одобр(?:ен|ено|ил|ила)|принят(?:о|а)?|успешно)"
    if re.search(rf"(?:\breviewer\b|ревью).{{0,80}}{approval}|{approval}.{{0,80}}(?:\breviewer\b|ревью)", lower):
        result.add("reviewer")
    if re.search(
        rf"(?:architecture guardian|architecture-review|архитектур\w*).{{0,80}}{approval}|"
        rf"{approval}.{{0,80}}(?:architecture guardian|architecture-review|архитектур\w*)",
        lower,
    ):
        result.add("architecture")
    if re.search(rf"(?:\bqa\b|тестировщик|exploratory).{{0,80}}{approval}|{approval}.{{0,80}}(?:\bqa\b|тестировщик|exploratory)", lower):
        result.add("qa")
    return result


def parse_agent_result(message: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    marker = "WGC_AGENT_RESULT:"
    raw = None
    for line in reversed(message.splitlines()):
        if marker in line:
            raw = line.split(marker, 1)[1].strip().strip("`")
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
    revision = str(value.get("input_revision") or "").strip()
    if role not in ROLE_VERDICTS:
        return None, f"unknown WGC role: {role or '<empty>'}"
    if verdict not in ROLE_VERDICTS[role]:
        return None, f"invalid verdict '{verdict or '<empty>'}' for role {role}"
    if role == "architecture-guardian" and phase not in {"plan", "diff"}:
        return None, "architecture-guardian result requires phase plan or diff"
    if not revision:
        return None, "WGC_AGENT_RESULT requires input_revision from SubagentStart"
    return {
        "role": role,
        "verdict": verdict,
        "phase": phase,
        "input_revision": revision[:200],
    }, None


def approved_agent_gates(state: Dict[str, Any], current_revision: str) -> Set[str]:
    gates: Set[str] = set()
    results = state.get("subagent_results", [])
    if not isinstance(results, list):
        return gates
    latest: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        latest[(result.get("role"), result.get("phase"))] = result
    for result in latest.values():
        role = result.get("role")
        verdict = result.get("verdict")
        phase = result.get("phase")
        if role == "architect" and verdict == "proposed":
            gates.add("architect")
        elif role == "test-maker" and verdict == "baseline_ready":
            gates.add("test-maker")
        elif role == "reviewer" and verdict == "approved" and result.get("input_revision") == current_revision:
            gates.add("reviewer")
        elif (
            role == "architecture-guardian"
            and verdict == "approved"
            and phase == "diff"
            and result.get("input_revision") == current_revision
        ):
            gates.add("architecture")
        elif role == "qa" and verdict == "pass" and result.get("input_revision") == current_revision:
            gates.add("qa")
        elif (
            role == "infrastructure-reviewer"
            and verdict == "approved"
            and result.get("input_revision") == current_revision
        ):
            gates.add("infrastructure")
    return gates


def handle_session_start(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    def updater(state: Dict[str, Any]) -> None:
        state["last_start_source"] = payload.get("source")
        state.setdefault("started_at", int(time.time()))

    update_state(payload, context, updater)
    return additional_context("SessionStart", context_text(context))


def handle_prompt_submit(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    prompt = str(payload.get("prompt") or "")
    explicit = bool(EXPLICIT_SKILL.search(prompt))
    inferred = bool(IMPLEMENTATION_INTENT.search(prompt))
    if not (explicit or inferred):
        return None

    baseline = workspace_snapshot(context)

    def updater(state: Dict[str, Any]) -> None:
        already_active = bool(state.get("active"))
        state["active"] = True
        state["activation"] = "explicit" if explicit else "inferred"
        state["last_prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if not already_active:
            state["baseline_dirty"] = baseline
            state["current_dirty"] = baseline
            state["commands"] = []
            state["verification"] = {}
            state["touched_paths"] = []
            state["stop_turns"] = []
            state["activated_at"] = int(time.time())

    update_state(payload, context, updater)
    mode = "explicitly" if explicit else "from implementation intent"
    return additional_context(
        "UserPromptSubmit",
        f"WGC implementation workflow activated {mode}. Build a WorkItem, preserve baseline dirty paths, and use the architecture → tests → implementation → independent review → QA gates.",
    )


def handle_subagent_start(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
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
    active = " Active WGC workflow state is present." if state.get("active") else ""
    message = (
        f"WGC subagent boundary: project={context['project']}.{active} Read root and nested AGENTS.md before work. "
        "Stay inside the assigned repository/path scope, preserve existing changes, return evidence and a role verdict, and do not commit, push, deploy, or write to the cluster unless the assignment explicitly authorizes it."
        f" Your exact input revision is {revision}."
        ' End the final response with exactly one line: WGC_AGENT_RESULT: {"role":"<role>","verdict":"<allowed-verdict>","phase":"<plan-or-diff-if-architecture-guardian>","input_revision":"<exact-input-revision>"}'
    )
    return additional_context("SubagentStart", message)


def handle_subagent_stop(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state = update_state(payload, context, lambda value: None)
    if not state.get("active"):
        return None
    result, error = parse_agent_result(str(payload.get("last_assistant_message") or ""))
    agent_id = str(payload.get("agent_id") or "")
    expected = state.get("subagent_inputs", {}).get(agent_id, {}).get("revision")
    if not error and expected and result and result.get("input_revision") != expected:
        error = "input_revision does not match the revision assigned at SubagentStart"
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

    def updater(value: Dict[str, Any]) -> None:
        results = value.setdefault("subagent_results", [])
        recorded = {
            **result,
            "agent_id": agent_id[:200],
            "agent_type": str(payload.get("agent_type") or "")[:200],
            "at": int(time.time()),
        }
        results.append(recorded)
        del results[:-100]

    update_state(payload, context, updater)
    return None


def handle_pre_tool(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tool = str(payload.get("tool_name") or "")
    command = tool_command(payload)
    if tool == "Bash":
        violation = command_violation(command, Path(context["cwd"]))
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
    tool = str(payload.get("tool_name") or "")
    command = tool_command(payload)
    touched = relative_touched_paths(command, context) if tool in {"apply_patch", "Edit", "Write"} else []
    snapshot = workspace_snapshot(context)
    exit_code = nested_exit_code(payload.get("tool_response"))
    tags = verification_tags(command) if tool == "Bash" else set()

    def updater(state: Dict[str, Any]) -> None:
        known = set(state.get("touched_paths", []))
        known.update(touched)
        state["touched_paths"] = sorted(known)[:1000]
        previous = state.get("current_dirty", state.get("baseline_dirty", {}))
        incremental = snapshot_since_baseline(snapshot, previous)
        incremental_classification = classify_paths(incremental, touched)
        if incremental_classification["paths"]:
            invalidate = {"reviewer", "architecture-guardian", "qa"}
            if incremental_classification["tests"]:
                invalidate.add("test-maker")
            if incremental_classification["k8s"]:
                invalidate.add("infrastructure-reviewer")
            state["subagent_results"] = [
                result
                for result in state.get("subagent_results", [])
                if isinstance(result, dict) and result.get("role") not in invalidate
            ]
        state["current_dirty"] = snapshot
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
                    verification[tag] = {"at": int(time.time()), **command_record(command)}

    state = update_state(payload, context, updater)
    relevant_snapshot = snapshot_since_baseline(snapshot, state.get("baseline_dirty"))
    classification = classify_paths(relevant_snapshot, state.get("touched_paths", []))
    notes: List[str] = []
    if len(classification["projects"]) > 1:
        notes.append(
            "Changes now span repositories "
            + ", ".join(classification["projects"])
            + "; keep a contract-first DAG, separate checks, commits, and publication order."
        )
    if classification["production"] and "test" not in state.get("verification", {}):
        notes.append("Production code changed; run the minimal relevant tests with changed-branch coverage now, not only at task end.")
    if classification["tests"]:
        notes.append("Test files changed; record protected paths/hashes and reject later Implementor edits to them in the orchestration gate.")
    if classification["k8s"]:
        notes.append("GitOps files changed; run the renderer and validators, then require independent infrastructure review before any deployment approval.")
    if notes:
        return additional_context("PostToolUse", " ".join(notes))
    return None


def handle_stop(payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state = update_state(payload, context, lambda value: None)
    if not state.get("active"):
        return None

    snapshot = workspace_snapshot(context)
    relevant_snapshot = snapshot_since_baseline(snapshot, state.get("baseline_dirty"))
    classification = classify_paths(relevant_snapshot, state.get("touched_paths", []))
    if not any((classification["production"], classification["tests"], classification["docs"], classification["k8s"])):
        def no_changes(value: Dict[str, Any]) -> None:
            value["active"] = False
            value["completed_at"] = int(time.time())
            value["completion"] = "no_tracked_changes"

        update_state(payload, context, no_changes)
        return None

    required = required_checks(classification)
    completed = set(state.get("verification", {}).keys())
    missing = sorted(required - completed)
    last_message = str(payload.get("last_assistant_message") or "")
    required_gates = {"architect", "test-maker", "reviewer", "architecture", "qa"}
    if classification["k8s"]:
        required_gates.add("infrastructure")
    current_revision = workspace_identity(context)
    observed_gates = approved_agent_gates(state, current_revision) | gate_mentions(last_message)
    gate_missing = sorted(required_gates - observed_gates)
    if not missing and not gate_missing:
        def complete(value: Dict[str, Any]) -> None:
            value["active"] = False
            value["completed_at"] = int(time.time())

        update_state(payload, context, complete)
        return None

    turn_id = str(payload.get("turn_id") or "unknown")
    if payload.get("stop_hook_active") or turn_id in state.get("stop_turns", []):
        def incomplete(value: Dict[str, Any]) -> None:
            value["active"] = False
            value["completed_at"] = int(time.time())
            value["completion"] = "continued_once_with_gaps"
            value["remaining_gaps"] = {"verification": missing, "gates": gate_missing}

        update_state(payload, context, incomplete)
        return None

    def updater(value: Dict[str, Any]) -> None:
        turns = value.setdefault("stop_turns", [])
        turns.append(turn_id)
        del turns[:-20]

    update_state(payload, context, updater)

    parts = ["Before finishing the WGC implementation, close the observable completion gaps."]
    if missing:
        parts.append("Missing successful verification evidence: " + ", ".join(missing) + ".")
    if gate_missing:
        parts.append("The final gate ledger does not mention: " + ", ".join(gate_missing) + ".")
    parts.append(
        "Run the applicable checks or state the exact blocker, verify protected-test hashes and repository scope, then produce a factual final report."
    )
    return {"decision": "block", "reason": " ".join(parts)}


def handle_session_end(payload: Dict[str, Any], context: Dict[str, Any]) -> None:
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
