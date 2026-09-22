"""Best-effort, metadata-only delivery of WGC lifecycle events."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import request


ENDPOINT = "https://codex-logs.wget-cloud.ru/v1/events"
MAX_PENDING = 5000
BATCH_SIZE = 20
PLUGIN_VERSION = "10.0.0"
MAX_TRANSCRIPT_TAIL = 4 * 1024 * 1024
MAX_TOKEN_COUNT = 1_000_000_000_000


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, request_object, response, code, message, headers, new_url):
        return None


def _data_dir() -> Path:
    configured = os.environ.get("PLUGIN_DATA")
    if configured:
        base = Path(configured).expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "WgetCloud" / "CodexLogs"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "wgc-codex-logs"
    target = base / "telemetry"
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    return target


def _installation_id(root: Path) -> str:
    path = root / "installation-id"
    try:
        return str(uuid.UUID(path.read_text(encoding="ascii").strip()))
    except (FileNotFoundError, ValueError, OSError):
        value = str(uuid.uuid4())
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return str(uuid.UUID(path.read_text(encoding="ascii").strip()))
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(value)
        return value


def _bounded(value: object, limit: int = 160) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    return value if all(character.isprintable() for character in value) else None


def _token_usage(payload: dict) -> dict | None:
    """Read only Codex's numeric usage metadata from the agent's transcript tail."""
    raw_path = payload.get("agent_transcript_path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    try:
        root = (Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions").resolve()
        path = Path(raw_path).resolve(strict=True)
        if not path.is_relative_to(root) or path.suffix != ".jsonl" or not path.is_file():
            return None
        with path.open("rb") as stream:
            size = path.stat().st_size
            start = max(0, size - MAX_TRANSCRIPT_TAIL)
            stream.seek(start)
            if start:
                stream.readline()
            lines = stream.readlines()
        for line in reversed(lines):
            if b'"token_count"' not in line:
                continue
            event = json.loads(line)
            item = event.get("payload")
            if event.get("type") != "event_msg" or not isinstance(item, dict) or item.get("type") != "token_count":
                continue
            info = item.get("info")
            totals = info.get("total_token_usage") if isinstance(info, dict) else None
            if not isinstance(totals, dict):
                continue
            keys = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "total_tokens")
            if any(type(totals.get(key)) is not int or not 0 <= totals[key] <= MAX_TOKEN_COUNT for key in keys):
                continue
            if totals["total_tokens"] != totals["input_tokens"] + totals["output_tokens"]:
                continue
            if totals["cached_input_tokens"] > totals["input_tokens"] or totals["reasoning_output_tokens"] > totals["output_tokens"]:
                continue
            return {**{key: totals[key] for key in keys}, "source": "codex_transcript"}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


def _flush(root: Path) -> None:
    token = os.environ.get("WGC_CODEX_LOGS_TOKEN", "").strip()
    if not token or len(token) > 4096:
        return
    pending = sorted(root.glob("event-*.json"))[:BATCH_SIZE]
    if not pending:
        return
    events = [json.loads(path.read_text(encoding="utf-8")) for path in pending]
    body = json.dumps({"events": events}, separators=(",", ":")).encode("utf-8")
    operation = request.Request(
        ENDPOINT,
        data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    with request.build_opener(_NoRedirect).open(operation, timeout=0.6) as response:
        if not 200 <= response.status < 300:
            return
    for path in pending:
        path.unlink(missing_ok=True)


def flush_pending() -> None:
    if not os.environ.get("WGC_CODEX_LOGS_TOKEN", "").strip():
        return
    try:
        _flush(_data_dir())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return


def record(kind: str, payload: dict, context: dict, profile: str, role: str | None = None, outcome: str | None = None) -> None:
    """Queue only allowlisted metadata; delivery failure never affects a workflow."""
    try:
        root = _data_dir()
        pending = list(root.glob("event-*.json"))
        if len(pending) >= MAX_PENDING:
            sorted(pending)[0].unlink(missing_ok=True)
        event_id = str(uuid.uuid4())
        event = {
            "schema_version": 2,
            "event_id": event_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "plugin_version": PLUGIN_VERSION,
            "installation_id": _installation_id(root),
            "session_id": _bounded(payload.get("session_id")),
            "turn_id": _bounded(payload.get("turn_id")),
            "agent_id": _bounded(payload.get("agent_id")),
            "agent_type": _bounded(payload.get("agent_type"), 80),
            "model": _bounded(payload.get("model"), 100),
            "project": _bounded(context.get("project"), 80),
            "workflow": _bounded(profile, 80),
            "role": _bounded(role, 80),
            "outcome": _bounded(outcome, 80),
            "usage": _token_usage(payload) if kind == "agent_stopped" else None,
        }
        name = root / f"event-{time.time_ns():020d}-{event_id}.json"
        temporary = name.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(event, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, name)
        _flush(root)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return
