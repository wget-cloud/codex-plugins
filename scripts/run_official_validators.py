#!/usr/bin/env python3
"""Checksum-pinned, offline-first runner for official Codex sample validators."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = REPOSITORY_ROOT / "scripts" / "official_validators.lock.json"
DEFAULT_CACHE = REPOSITORY_ROOT / ".cache" / "official-validators"
REQUIRED_VALIDATORS = {"quick_validate.py", "validate_plugin.py", "identifier_validation.py"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover(root: Path, *, allowlist: Set[str], checksums: Mapping[str, str]) -> Dict[str, Any]:
    """Offline-only cache inspection; never searches beyond the pinned names."""
    errors: List[str] = []
    if not root.is_dir():
        return {"accepted": False, "offline": True, "errors": ["validator cache directory is missing"], "paths": {}}
    unexpected = sorted(path.name for path in root.glob("*.py") if path.name not in allowlist)
    if unexpected:
        errors.append("unapproved validator files present: " + ", ".join(unexpected))
    paths: Dict[str, str] = {}
    for name in sorted(allowlist):
        path = root / name
        if not path.is_file():
            errors.append(f"locked validator is missing: {name}")
            continue
        expected = checksums.get(name)
        if not isinstance(expected, str) or len(expected) != 64 or sha256(path) != expected:
            errors.append(f"checksum mismatch for locked validator: {name}")
            continue
        paths[name] = str(path)
    return {"accepted": not errors, "offline": True, "errors": errors, "paths": paths}


def load_lock(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    validators = value.get("validators") if isinstance(value, dict) else None
    if not isinstance(validators, dict) or set(validators) != REQUIRED_VALIDATORS:
        raise ValueError("lock must contain exactly the approved validator filenames")
    for name, entry in validators.items():
        if not isinstance(entry, dict) or set(entry) != {"url", "sha256"} or not isinstance(entry["url"], str) or not isinstance(entry["sha256"], str):
            raise ValueError(f"lock entry is invalid: {name}")
    return value


def ensure_cache(lock: Mapping[str, Any], cache: Path, *, allow_download: bool) -> Dict[str, Any]:
    validators = lock["validators"]
    checksums = {name: entry["sha256"] for name, entry in validators.items()}
    result = discover(cache, allowlist=set(validators), checksums=checksums)
    if result["accepted"] or not allow_download:
        return result
    cache.mkdir(parents=True, exist_ok=True)
    for name, entry in validators.items():
        target = cache / name
        if target.is_file() and sha256(target) == entry["sha256"]:
            continue
        try:
            with urllib.request.urlopen(entry["url"], timeout=20) as response:
                content = response.read()
        except OSError as error:
            return {"accepted": False, "offline": False, "errors": [f"download failed for {name}: {error}"], "paths": {}}
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry["sha256"]:
            return {"accepted": False, "offline": False, "errors": [f"checksum mismatch for downloaded validator: {name}"], "paths": {}}
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
    return discover(cache, allowlist=set(validators), checksums=checksums)


def discover_targets(repository: Path) -> Dict[str, List[Path]]:
    plugins = sorted(path.parent.parent for path in repository.glob("plugins/*/.codex-plugin/plugin.json"))
    skills = sorted(path.parent for path in repository.glob("plugins/*/skills/*/SKILL.md"))
    return {"plugins": plugins, "skills": skills}


def run_validators(cache: Path, repository: Path) -> List[str]:
    targets = discover_targets(repository)
    failures: List[str] = []
    for skill in targets["skills"]:
        result = subprocess.run([sys.executable, str(cache / "quick_validate.py"), str(skill)], cwd=str(repository), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        if result.returncode:
            failures.append(f"quick_validate failed for {skill.relative_to(repository)}")
    for plugin in targets["plugins"]:
        result = subprocess.run([sys.executable, str(cache / "validate_plugin.py"), str(plugin)], cwd=str(repository), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        if result.returncode:
            failures.append(f"validate_plugin failed for {plugin.relative_to(repository)}")
    return failures


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run lockfile-pinned official Codex validators.")
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--repository", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--allow-download", action="store_true", help="download only the exact lockfile URLs, then verify SHA-256")
    parser.add_argument("--offline", action="store_true", help="require a verified local cache (the default)")
    args = parser.parse_args(argv)
    try:
        lock = load_lock(args.lock.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: invalid official-validator lock: {error}", file=sys.stderr)
        return 2
    result = ensure_cache(lock, args.cache.resolve(), allow_download=args.allow_download and not args.offline)
    if not result["accepted"]:
        for error in result["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        print("Use --allow-download to populate this checksum-verified cache, or provide a verified --cache for offline operation.", file=sys.stderr)
        return 1
    failures = run_validators(args.cache.resolve(), args.repository.resolve())
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    targets = discover_targets(args.repository.resolve())
    print(f"Validated {len(targets['skills'])} skill(s) and {len(targets['plugins'])} plugin(s) with pinned official validators.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
