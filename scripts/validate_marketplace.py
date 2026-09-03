#!/usr/bin/env python3
"""Validate repository-local Codex marketplace structure with stdlib only."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


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
REQUIRED_ASSIGNMENT_FIELDS = (
    "TASK_NAME",
    "MODEL_ROUTE",
    "MODEL",
    "REASONING_EFFORT",
    "ROUTING_BASIS",
    "FORK_TURNS",
    "TIME_BUDGET_MIN",
    "CHECKPOINT_INTERVAL_MIN",
    "MAX_EXTENSIONS",
    "PROGRESS_CRITERIA",
)
MODEL_LANES = {"fast", "balanced", "frontier", "main-only"}


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
    for line in markdown_lines_outside_fences(text):
        for raw in MARKDOWN_LINK.findall(line):
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


def assignment_envelope_text(index_text: str) -> str:
    """Return the sole fenced text envelope under the exact registry heading."""
    lines = index_text.splitlines()
    headings = [
        position
        for position, line in enumerate(lines)
        if line.strip() == "## Общий assignment envelope"
    ]
    if len(headings) != 1:
        return ""
    start = headings[0] + 1
    end = next(
        (position for position in range(start, len(lines)) if re.fullmatch(r"##\s+.*", lines[position])),
        len(lines),
    )
    opener = [
        position for position in range(start, end) if lines[position].strip() == "```text"
    ]
    if len(opener) != 1:
        return ""
    closing = next(
        (position for position in range(opener[0] + 1, end) if lines[position].strip() == "```"),
        None,
    )
    if closing is None:
        return ""
    return "\n".join(lines[opener[0] + 1 : closing])


def assignment_routing_fields(index_text: str) -> set[str]:
    """Return required fields declared only in the production assignment envelope."""
    alternatives = "|".join(map(re.escape, REQUIRED_ASSIGNMENT_FIELDS))
    return {
        match.group(1)
        for match in re.finditer(
            rf"^\s*({alternatives})\s*:",
            assignment_envelope_text(index_text),
            re.MULTILINE,
        )
    }


def markdown_lines_outside_fences(text: str) -> Iterable[str]:
    """Yield Markdown lines outside triple-backtick fenced code blocks."""
    fenced = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            yield line


def markdown_table_blocks(index_text: str) -> Iterable[Tuple[Sequence[str], Sequence[Sequence[str]]]]:
    """Yield Markdown tables outside fenced code blocks without filesystem state."""
    lines = list(markdown_lines_outside_fences(index_text))
    position = 0
    while position + 1 < len(lines):
        header_line, divider_line = lines[position : position + 2]
        if "|" not in header_line or "|" not in divider_line:
            position += 1
            continue
        header = [cell.strip() for cell in header_line.strip().strip("|").split("|")]
        divider = [cell.strip() for cell in divider_line.strip().strip("|").split("|")]
        if len(header) != len(divider) or not divider or not all(
            re.fullmatch(r":?-{3,}:?", cell) for cell in divider
        ):
            position += 1
            continue
        position += 2
        rows: List[Sequence[str]] = []
        while position < len(lines) and "|" in lines[position]:
            row = [cell.strip() for cell in lines[position].strip().strip("|").split("|")]
            rows.append(row)
            position += 1
        yield header, rows


def model_routing_entries(index_text: str) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """Extract route links and structural errors from model-lane registry tables."""
    routes: List[Tuple[str, str, str]] = []
    errors: List[str] = []
    for header, rows in markdown_table_blocks(index_text):
        normalized_header = [cell.casefold() for cell in header]
        if "model lane" not in normalized_header:
            continue
        lane_column = normalized_header.index("model lane")
        task_prefix_columns = [
            position for position, cell in enumerate(header) if cell == "Task prefix"
        ]
        if len(task_prefix_columns) != 1:
            errors.append("malformed model routing table row: missing Task prefix column")
            continue
        task_prefix_column = task_prefix_columns[0]
        contract_columns = [
            position
            for position, cell in enumerate(normalized_header)
            if cell in {"contract", "контракт"}
        ]
        if len(contract_columns) != 1:
            errors.append("malformed model routing table row: missing Contract/Контракт column")
            continue
        contract_column = contract_columns[0]
        for row in rows:
            if len(row) != len(header):
                errors.append("malformed model routing table row")
                continue
            links = MARKDOWN_LINK.findall(row[contract_column])
            role_links = [
                raw for raw in links if raw.split("#", 1)[0].strip().strip("<>").endswith(".md")
            ]
            if not role_links:
                errors.append("missing role contract link")
                continue
            if len(role_links) != 1:
                errors.append("exactly one role contract link is required")
                continue
            role_target = role_links[0].split("#", 1)[0].strip().strip("<>")
            routes.append((role_target, row[lane_column].casefold(), row[task_prefix_column]))
    return routes, errors


def model_routes(index_text: str) -> List[Tuple[str, str]]:
    """Return valid-looking ``(role-link, lane)`` pairs for pure parser consumers."""
    routes, _ = model_routing_entries(index_text)
    return [(role_target, lane) for role_target, lane, _ in routes]


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
    declared_fields = assignment_routing_fields(index_text)
    for field in REQUIRED_ASSIGNMENT_FIELDS:
        if field not in declared_fields:
            errors.append(f"{index.relative_to(ROOT)}: missing assignment routing field {field}")
    parsed_routes, routing_errors = model_routing_entries(index_text)
    for error in routing_errors:
        errors.append(f"{index.relative_to(ROOT)}: {error}")
    role_paths = {path.resolve(): path.name for path in role_files}
    routes_by_role: Dict[str, List[str]] = {}
    for role_target, lane, task_prefix in parsed_routes:
        target_path = (role_dir / role_target).resolve(strict=False)
        try:
            target_path.relative_to(role_dir.resolve())
        except ValueError:
            errors.append(
                f"{index.relative_to(ROOT)}: role contract link escapes role directory: {role_target}"
            )
            continue
        role_file = role_paths.get(target_path)
        if role_file is None:
            errors.append(
                f"{index.relative_to(ROOT)}: linked role contract does not exist: {role_target}"
            )
            continue
        routes_by_role.setdefault(role_file, []).append(lane)
        expected_task_prefix = "n/a" if role_file == "orchestrator.md" else role_file.removesuffix(
            ".md"
        ).replace("-", "_")
        if task_prefix != expected_task_prefix:
            if role_file == "orchestrator.md":
                errors.append(
                    f"{index.relative_to(ROOT)}: orchestrator task prefix must be n/a"
                )
            else:
                errors.append(
                    f"{index.relative_to(ROOT)}: task prefix must equal {expected_task_prefix}"
                )
    for role_file, lanes in sorted(routes_by_role.items()):
        if len(lanes) > 1:
            errors.append(f"{index.relative_to(ROOT)}: duplicate model route: {role_file}")
        for lane in lanes:
            if lane not in MODEL_LANES:
                errors.append(f"{index.relative_to(ROOT)}: unknown model lane: {lane}")
            if role_file == "orchestrator.md" and lane != "main-only":
                errors.append(f"{index.relative_to(ROOT)}: orchestrator must use main-only")
            if role_file != "orchestrator.md" and lane == "main-only":
                errors.append(f"{index.relative_to(ROOT)}: only orchestrator may use main-only")
    actual = {path.name for path in role_files}
    for role_file in sorted(actual - set(routes_by_role)):
        errors.append(f"{index.relative_to(ROOT)}: missing model route: {role_file}")
    for role in role_files:
        text = role.read_text(encoding="utf-8")
        for section in REQUIRED_ROLE_SECTIONS:
            if section not in text:
                errors.append(f"{role.relative_to(ROOT)}: missing section {section}")
        if role.name != "orchestrator.md" and "Verdict:" not in text:
            errors.append(f"{role.relative_to(ROOT)}: missing explicit Verdict contract")
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


def validate_workflow_actions(path: Path, errors: List[str]) -> None:
    """Third-party actions require a reviewed full SHA; local/docker uses do not."""
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*-\s*uses:\s*(\S+)(?:\s+(#.*))?\s*$", line)
        if not match:
            continue
        action, comment = match.group(1), match.group(2) or ""
        if action.startswith("./") or action.startswith("docker://"):
            continue
        if "@" not in action:
            errors.append(f"{path.relative_to(ROOT)}: immutable action ref is required")
            continue
        _, revision = action.rsplit("@", 1)
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or not re.search(r"#\s*v\d", comment, re.IGNORECASE):
            errors.append(f"{path.relative_to(ROOT)}: immutable action ref must be a full 40-hex reviewed commit with a human release comment")


def validate_makefile_bytecode(path: Path, errors: List[str]) -> None:
    text = path.read_text(encoding="utf-8")
    reusable_guard = bool(re.search(r"^PYTHON_NO_BYTECODE\s*[?:+]?=\s*PYTHONDONTWRITEBYTECODE=1\s+", text, re.MULTILINE))
    for line in text.splitlines():
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*[?:+]?=", line):
            continue
        if not re.search(r"\b(?:python|python3|\$\(PYTHON(?:_NO_BYTECODE)?\))\b", line):
            continue
        safe = "PYTHONDONTWRITEBYTECODE=1" in line or ("$(PYTHON_NO_BYTECODE)" in line and reusable_guard)
        if not safe:
            errors.append(f"{path.relative_to(ROOT)}: Python validation commands must explicitly disable bytecode artifacts")
        if re.search(r"\bpy_compile\b", line) and "-B" not in line:
            errors.append(f"{path.relative_to(ROOT)}: bytecode artifact creation via py_compile is forbidden")


def validate_tooling_pins(root: Path, errors: List[str]) -> None:
    workflow = root / ".github" / "workflows" / "validate.yml"
    if workflow.is_file():
        validate_workflow_actions(workflow, errors)
    makefile = root / "Makefile"
    if makefile.is_file():
        validate_makefile_bytecode(makefile, errors)


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


def validate_maintainer_contracts(root: Path) -> List[str]:
    """Run the bundle's live semantic validator when the maintainer is present."""
    script = root / "plugins" / "wget-cloud-plugin-maintainer" / "scripts" / "validate_maintainer_contracts.py"
    if not script.is_file():
        return []
    try:
        spec = importlib.util.spec_from_file_location("wgc_maintainer_contracts", script)
        if spec is None or spec.loader is None:
            return ["maintainer semantic validator cannot be loaded"]
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.validate(root)
        return result if isinstance(result, list) and all(isinstance(item, str) for item in result) else ["maintainer semantic validator returned an invalid result"]
    except (ImportError, OSError, AttributeError):
        return ["maintainer semantic validator failed to execute"]


def validate_repository(root: Path | None = None) -> Tuple[List[str], Dict[str, int]]:
    root = ROOT if root is None else root
    marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
    errors: List[str] = []
    counts = {"plugins": 0, "skills": 0, "roles": 0}
    for required in (root / "README.md", root / "AGENTS.md", marketplace_path):
        if not required.is_file():
            errors.append(f"missing required file: {required.relative_to(ROOT)}")
    if not marketplace_path.is_file():
        return errors, counts
    try:
        marketplace = load_json(marketplace_path)
    except ValidationError as error:
        errors.append(str(error))
        return errors, counts
    entries = marketplace.get("plugins")
    if not isinstance(entries, list):
        errors.append(f"{marketplace_path.relative_to(ROOT)}: plugins must be an array")
        return errors, counts
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{marketplace_path.relative_to(ROOT)}: each plugin entry must be an object")
            continue
        name = str(entry.get("name") or "")
        if not name or name in seen:
            errors.append(f"{marketplace_path.relative_to(ROOT)}: plugin names must be unique and non-empty")
            continue
        seen.add(name)
        source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        expected_path = f"./plugins/{name}"
        if source.get("source") != "local" or source.get("path") != expected_path:
            errors.append(f"{marketplace_path.relative_to(ROOT)}: {name} source must be {expected_path}")
        policy = entry.get("policy") if isinstance(entry.get("policy"), dict) else {}
        if policy.get("installation") not in {"NOT_AVAILABLE", "AVAILABLE", "INSTALLED_BY_DEFAULT"}:
            errors.append(f"{marketplace_path.relative_to(ROOT)}: {name} has invalid installation policy")
        if policy.get("authentication") not in {"ON_INSTALL", "ON_USE"}:
            errors.append(f"{marketplace_path.relative_to(ROOT)}: {name} has invalid authentication policy")
        if not entry.get("category"):
            errors.append(f"{marketplace_path.relative_to(ROOT)}: {name} category is required")
        plugin = root / "plugins" / name
        skills, roles = validate_plugin(plugin, errors)
        counts["plugins"] += 1
        counts["skills"] += skills
        counts["roles"] += roles
    plugin_dirs = {path.name for path in (root / "plugins").iterdir() if path.is_dir()}
    for orphan in sorted(plugin_dirs - seen):
        errors.append(f"plugins/{orphan}: plugin is not registered in marketplace")
    validate_links([root / "README.md", root / "AGENTS.md"], errors)
    validate_tooling_pins(root, errors)
    errors.extend(validate_maintainer_contracts(root))
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
