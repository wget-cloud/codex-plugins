#!/usr/bin/env python3
"""Validate repository-local Codex marketplace structure with stdlib only."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?$"
)
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REQUIRED_ROLE_SECTIONS = ("## Назначение", "## Полномочия", "## Запреты", "## Результат")


class ValidationError(Exception):
    pass


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"{path.relative_to(ROOT)}: invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{path.relative_to(ROOT)}: root must be an object")
    return value


def frontmatter(path: Path) -> Dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValidationError(f"{path.relative_to(ROOT)}: cannot read: {error}") from error
    if not lines or lines[0] != "---":
        raise ValidationError(f"{path.relative_to(ROOT)}: missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValidationError(f"{path.relative_to(ROOT)}: unterminated YAML frontmatter") from error
    result: Dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith((" ", "\t")) or ":" not in line:
            raise ValidationError(f"{path.relative_to(ROOT)}: frontmatter must use flat key/value fields")
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"\'')
    return result


def local_links(path: Path) -> Iterable[Tuple[str, Path]]:
    text = path.read_text(encoding="utf-8")
    for raw in MARKDOWN_LINK.findall(text):
        target = raw.split("#", 1)[0].strip().strip("<>")
        if not target or re.match(r"^[a-z][a-z0-9+.-]*://", target, re.IGNORECASE):
            continue
        yield raw, (path.parent / target).resolve(strict=False)


def validate_links(paths: Iterable[Path], errors: List[str]) -> None:
    for path in paths:
        for raw, target in local_links(path):
            try:
                target.relative_to(ROOT)
            except ValueError:
                errors.append(f"{path.relative_to(ROOT)}: link escapes repository: {raw}")
                continue
            if not target.exists():
                errors.append(f"{path.relative_to(ROOT)}: broken local link: {raw}")


def openai_default_prompt(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^\s*default_prompt:\s*["\'](.+)["\']\s*$', text, re.MULTILINE)
    return match.group(1) if match else ""


def validate_agent_registry(skill: Path, errors: List[str]) -> int:
    role_dir = skill / "references" / "agents"
    if not role_dir.exists():
        return 0
    index = role_dir / "index.md"
    if not index.is_file():
        errors.append(f"{role_dir.relative_to(ROOT)}: missing index.md")
        return 0
    index_text = index.read_text(encoding="utf-8")
    role_files = sorted(path for path in role_dir.glob("*.md") if path.name != "index.md")
    if not role_files:
        errors.append(f"{role_dir.relative_to(ROOT)}: no role files")
    if not (role_dir / "orchestrator.md").is_file():
        errors.append(f"{role_dir.relative_to(ROOT)}: orchestrator.md is required")
    for role in role_files:
        if f"({role.name})" not in index_text:
            errors.append(f"{index.relative_to(ROOT)}: role is not registered: {role.name}")
        text = role.read_text(encoding="utf-8")
        for section in REQUIRED_ROLE_SECTIONS:
            if section not in text:
                errors.append(f"{role.relative_to(ROOT)}: missing section {section}")
        if role.name != "orchestrator.md" and "Verdict:" not in text:
            errors.append(f"{role.relative_to(ROOT)}: missing explicit Verdict contract")
    registered = {
        Path(raw.split("#", 1)[0]).name
        for raw, _ in local_links(index)
        if raw.split("#", 1)[0].endswith(".md")
    }
    actual = {path.name for path in role_files}
    for orphan in sorted(registered - actual):
        errors.append(f"{index.relative_to(ROOT)}: registered role file does not exist: {orphan}")
    return len(role_files)


def validate_skill(skill: Path, errors: List[str]) -> int:
    skill_file = skill / "SKILL.md"
    if not skill_file.is_file():
        errors.append(f"{skill.relative_to(ROOT)}: missing SKILL.md")
        return 0
    try:
        metadata = frontmatter(skill_file)
    except ValidationError as error:
        errors.append(str(error))
        return 0
    if set(metadata) != {"name", "description"}:
        errors.append(f"{skill_file.relative_to(ROOT)}: frontmatter must contain only name and description")
    if metadata.get("name") != skill.name or not SKILL_NAME.fullmatch(skill.name):
        errors.append(f"{skill_file.relative_to(ROOT)}: skill name must match folder and kebab-case")
    if not metadata.get("description"):
        errors.append(f"{skill_file.relative_to(ROOT)}: description is required")
    if any(path.name.lower() == "readme.md" for path in skill.rglob("*.md")):
        errors.append(f"{skill.relative_to(ROOT)}: README.md is not allowed inside a skill")
    openai_yaml = skill / "agents" / "openai.yaml"
    if not openai_yaml.is_file():
        errors.append(f"{skill.relative_to(ROOT)}: missing agents/openai.yaml")
    else:
        prompt = openai_default_prompt(openai_yaml)
        if f"${skill.name}" not in prompt:
            errors.append(f"{openai_yaml.relative_to(ROOT)}: default_prompt must mention ${skill.name}")
    for path in skill.rglob("*"):
        if path.is_file() and "[TODO:" in path.read_text(encoding="utf-8", errors="ignore"):
            errors.append(f"{path.relative_to(ROOT)}: TODO placeholder remains")
    markdown = list(skill.rglob("*.md"))
    validate_links(markdown, errors)
    return validate_agent_registry(skill, errors)


def validate_hooks(path: Path, errors: List[str]) -> None:
    try:
        config = load_json(path)
    except ValidationError as error:
        errors.append(str(error))
        return
    events = config.get("hooks")
    if not isinstance(events, dict):
        errors.append(f"{path.relative_to(ROOT)}: hooks must be an object")
        return
    for event, groups in events.items():
        if not isinstance(groups, list):
            errors.append(f"{path.relative_to(ROOT)}: {event} groups must be an array")
            continue
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                errors.append(
                    f"{path.relative_to(ROOT)}: {event}[{group_index}].hooks must be an array"
                )
                continue
            for handler_index, handler in enumerate(group["hooks"]):
                if not isinstance(handler, dict):
                    errors.append(
                        f"{path.relative_to(ROOT)}: "
                        f"{event}[{group_index}].hooks[{handler_index}] must be an object"
                    )
                    continue
                if "async" in handler:
                    errors.append(
                        f"{path.relative_to(ROOT)}: "
                        f"{event}[{group_index}].hooks[{handler_index}] must not declare async"
                    )


def validate_plugin(plugin: Path, errors: List[str]) -> Tuple[int, int]:
    manifest_path = plugin / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        errors.append(f"{plugin.relative_to(ROOT)}: missing .codex-plugin/plugin.json")
        return 0, 0
    try:
        manifest = load_json(manifest_path)
    except ValidationError as error:
        errors.append(str(error))
        return 0, 0
    if manifest.get("name") != plugin.name:
        errors.append(f"{manifest_path.relative_to(ROOT)}: name must match plugin folder")
    if not SEMVER.fullmatch(str(manifest.get("version") or "")):
        errors.append(
            f"{manifest_path.relative_to(ROOT)}: "
            "version must be plain SemVer without build metadata"
        )
    prompts = (manifest.get("interface") or {}).get("defaultPrompt") if isinstance(manifest.get("interface"), dict) else None
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
        errors.append(f"{manifest_path.relative_to(ROOT)}: interface.defaultPrompt must be an array of 1-3 strings")
    elif any(not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 128 for prompt in prompts):
        errors.append(f"{manifest_path.relative_to(ROOT)}: each defaultPrompt must be a non-empty string <= 128 chars")
    skill_root = plugin / str(manifest.get("skills") or "./skills/").removeprefix("./")
    if not skill_root.is_dir():
        errors.append(f"{manifest_path.relative_to(ROOT)}: skills path does not exist")
        return 0, 0
    skills = sorted(path for path in skill_root.iterdir() if path.is_dir())
    roles = sum(validate_skill(skill, errors) for skill in skills)
    hooks = plugin / "hooks" / "hooks.json"
    if hooks.exists():
        validate_hooks(hooks, errors)
    return len(skills), roles


def validate_repository(root: Path = ROOT) -> Tuple[List[str], Dict[str, int]]:
    del root  # The checked layout is intentionally anchored to this script's repository.
    errors: List[str] = []
    counts = {"plugins": 0, "skills": 0, "roles": 0}
    for required in (ROOT / "README.md", ROOT / "AGENTS.md", MARKETPLACE):
        if not required.is_file():
            errors.append(f"missing required file: {required.relative_to(ROOT)}")
    if not MARKETPLACE.is_file():
        return errors, counts
    try:
        marketplace = load_json(MARKETPLACE)
    except ValidationError as error:
        errors.append(str(error))
        return errors, counts
    entries = marketplace.get("plugins")
    if not isinstance(entries, list):
        errors.append(f"{MARKETPLACE.relative_to(ROOT)}: plugins must be an array")
        return errors, counts
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{MARKETPLACE.relative_to(ROOT)}: each plugin entry must be an object")
            continue
        name = str(entry.get("name") or "")
        if not name or name in seen:
            errors.append(f"{MARKETPLACE.relative_to(ROOT)}: plugin names must be unique and non-empty")
            continue
        seen.add(name)
        source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        expected_path = f"./plugins/{name}"
        if source.get("source") != "local" or source.get("path") != expected_path:
            errors.append(f"{MARKETPLACE.relative_to(ROOT)}: {name} source must be {expected_path}")
        policy = entry.get("policy") if isinstance(entry.get("policy"), dict) else {}
        if policy.get("installation") not in {"NOT_AVAILABLE", "AVAILABLE", "INSTALLED_BY_DEFAULT"}:
            errors.append(f"{MARKETPLACE.relative_to(ROOT)}: {name} has invalid installation policy")
        if policy.get("authentication") not in {"ON_INSTALL", "ON_USE"}:
            errors.append(f"{MARKETPLACE.relative_to(ROOT)}: {name} has invalid authentication policy")
        if not entry.get("category"):
            errors.append(f"{MARKETPLACE.relative_to(ROOT)}: {name} category is required")
        plugin = ROOT / "plugins" / name
        skills, roles = validate_plugin(plugin, errors)
        counts["plugins"] += 1
        counts["skills"] += skills
        counts["roles"] += roles
    plugin_dirs = {path.name for path in (ROOT / "plugins").iterdir() if path.is_dir()}
    for orphan in sorted(plugin_dirs - seen):
        errors.append(f"plugins/{orphan}: plugin is not registered in marketplace")
    validate_links([ROOT / "README.md", ROOT / "AGENTS.md"], errors)
    return errors, counts


def main() -> int:
    errors, counts = validate_repository()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Marketplace structure invalid: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(
        "Marketplace structure valid: "
        f"{counts['plugins']} plugin(s), {counts['skills']} skill(s), {counts['roles']} role contract(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
