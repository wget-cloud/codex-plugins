#!/usr/bin/env python3
"""Acceptance tests for agent model-routing validation.

These fixtures intentionally describe the planned registry contract.  They
remain isolated from the marketplace so that they can be introduced before
the production validator and role registries are updated.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPOSITORY_ROOT / "scripts" / "validate_marketplace.py"
ASSIGNMENT_FIELDS = (
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


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_marketplace", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load marketplace validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentModelRoutingValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        self.validator = load_validator()
        self.validator.ROOT = self.root
        self.validator.MARKETPLACE = self.root / ".agents" / "plugins" / "marketplace.json"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def build_fixture(
        self,
        *,
        rows: tuple[tuple[str, str, str], ...] = (
            ("Orchestrator", "main-only", "n/a"),
            ("Implementor", "economy", "implementor"),
        ),
        role_files: tuple[str, ...] = ("orchestrator", "implementor"),
        assignment_fields: tuple[str, ...] = ASSIGNMENT_FIELDS,
        raw_rows: tuple[str, ...] | None = None,
        prose: str = "",
    ) -> None:
        (self.root / ".agents" / "plugins").mkdir(parents=True, exist_ok=True)
        (self.root / "plugins" / "routing-fixture" / ".codex-plugin").mkdir(
            parents=True, exist_ok=True
        )
        role_dir = self.root / "plugins" / "routing-fixture" / "skills" / "routing-skill" / "references" / "agents"
        role_dir.mkdir(parents=True, exist_ok=True)
        (self.root / "README.md").write_text("# fixture\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        (self.root / ".agents" / "plugins" / "marketplace.json").write_text(
            json.dumps(
                {
                    "plugins": [
                        {
                            "name": "routing-fixture",
                            "source": {"source": "local", "path": "./plugins/routing-fixture"},
                            "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
                            "category": "Developer Tools",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (self.root / "plugins" / "routing-fixture" / ".codex-plugin" / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "routing-fixture",
                    "version": "1.0.0",
                    "skills": "./skills/",
                    "interface": {"defaultPrompt": ["Use $routing-skill."]},
                }
            ),
            encoding="utf-8",
        )
        skill = role_dir.parents[1]
        (skill / "agents").mkdir(exist_ok=True)
        (skill / "SKILL.md").write_text(
            "---\nname: routing-skill\ndescription: Fixture skill.\n---\n",
            encoding="utf-8",
        )
        (skill / "agents" / "openai.yaml").write_text(
            'default_prompt: "Use $routing-skill."\n', encoding="utf-8"
        )
        envelope = "\n".join(f"{field}: <value>" for field in assignment_fields)
        table = "\n".join(
            raw_rows
            if raw_rows is not None
            else tuple(
                f"| {role} | {task_prefix} | {lane} | [{role.lower()}]({role.lower()}.md) |"
                for role, lane, task_prefix in rows
            )
        )
        (role_dir / "index.md").write_text(
            "# Agent registry\n\n"
            "## Общий assignment envelope\n\n"
            f"```text\n{envelope}\n```\n\n"
            "## Roles\n\n"
            "| Role | Task prefix | Model lane | Contract |\n"
            "|---|---|---|---|\n"
            f"{table}\n\n{prose}",
            encoding="utf-8",
        )
        for role in role_files:
            body = (
                "## Назначение\n\n"
                "## Полномочия\n\n"
                "## Запреты\n\n"
                "## Результат\n\n"
            )
            if role != "orchestrator":
                body += "Verdict: pass\n"
            (role_dir / f"{role}.md").write_text(body, encoding="utf-8")

    def errors(self) -> list[str]:
        errors, _ = self.validator.validate_repository()
        return errors

    def assert_error(self, meaning: str) -> None:
        rendered = "\n".join(self.errors()).lower()
        self.assertIn(meaning.lower(), rendered)

    def assert_any_error(self, *meanings: str) -> None:
        rendered = "\n".join(self.errors()).lower()
        self.assertTrue(
            any(meaning.lower() in rendered for meaning in meanings),
            f"expected one of {meanings!r}, got: {rendered!r}",
        )

    def test_valid_routing_fixture_passes(self) -> None:
        self.build_fixture()
        self.assertEqual([], self.errors())

    def test_task_name_is_required_in_the_canonical_assignment_envelope(self) -> None:
        self.build_fixture(
            assignment_fields=tuple(field for field in ASSIGNMENT_FIELDS if field != "TASK_NAME")
        )
        self.assert_error("missing assignment routing field TASK_NAME")

    def test_routing_table_requires_an_exact_task_prefix_column(self) -> None:
        self.build_fixture(
            raw_rows=(
                "| Orchestrator | main-only | [orchestrator](orchestrator.md) |",
                "| Implementor | economy | [implementor](implementor.md) |",
            )
        )
        role_dir = (
            self.root
            / "plugins"
            / "routing-fixture"
            / "skills"
            / "routing-skill"
            / "references"
            / "agents"
        )
        index = role_dir / "index.md"
        index.write_text(
            index.read_text(encoding="utf-8")
            .replace("| Role | Task prefix | Model lane | Contract |", "| Role | Model lane | Contract |")
            .replace("|---|---|---|---|", "|---|---|---|"),
            encoding="utf-8",
        )
        self.assert_error("missing Task prefix column")

    def test_spawned_role_task_prefix_must_equal_its_role_file_prefix(self) -> None:
        self.build_fixture(
            rows=(
                ("Orchestrator", "main-only", "n/a"),
                ("Implementor", "economy", "reviewer"),
            )
        )
        self.assert_error("task prefix must equal implementor")

    def test_spawned_role_task_prefix_rejects_a_full_runtime_task_name(self) -> None:
        self.build_fixture(
            rows=(
                ("Orchestrator", "main-only", "n/a"),
                ("Implementor", "economy", "implementor_fixture"),
            )
        )
        self.assert_error("task prefix must equal implementor")

    def test_spawned_role_task_prefix_rejects_orchestrator_na(self) -> None:
        self.build_fixture(
            rows=(
                ("Orchestrator", "main-only", "n/a"),
                ("Implementor", "economy", "n/a"),
            )
        )
        self.assert_error("task prefix must equal implementor")

    def test_role_filename_hyphens_normalize_to_underscores_in_task_prefix(self) -> None:
        self.build_fixture(
            rows=(
                ("Orchestrator", "main-only", "n/a"),
                ("Test-maker", "economy", "test_maker"),
            ),
            role_files=("orchestrator", "test-maker"),
        )
        self.assertEqual([], self.errors())

    def test_orchestrator_task_prefix_must_be_literal_na(self) -> None:
        self.build_fixture(
            rows=(
                ("Orchestrator", "main-only", "orchestrator"),
                ("Implementor", "economy", "implementor"),
            )
        )
        self.assert_error("orchestrator task prefix must be n/a")

    def test_omitted_role_route_fails(self) -> None:
        self.build_fixture(rows=(("Orchestrator", "main-only", "n/a"),))
        self.assert_error("missing model route")

    def test_duplicate_role_route_fails(self) -> None:
        self.build_fixture(
            rows=(
                ("Orchestrator", "main-only", "n/a"),
                ("Implementor", "economy", "implementor"),
                ("Implementor", "balanced", "implementor"),
            )
        )
        self.assert_error("duplicate model route")

    def test_unknown_model_lane_fails(self) -> None:
        self.build_fixture(
            rows=(("Orchestrator", "main-only", "n/a"), ("Implementor", "fast", "implementor"))
        )
        self.assert_error("unknown model lane")

    def test_orchestrator_must_use_main_only_lane(self) -> None:
        self.build_fixture(
            rows=(("Orchestrator", "frontier", "n/a"), ("Implementor", "economy", "implementor"))
        )
        self.assert_error("orchestrator must use main-only")

    def test_subagent_cannot_use_main_only_lane(self) -> None:
        self.build_fixture(
            rows=(("Orchestrator", "main-only", "n/a"), ("Implementor", "main-only", "implementor"))
        )
        self.assert_error("only orchestrator may use main-only")

    def test_each_assignment_routing_field_is_required(self) -> None:
        for missing in ASSIGNMENT_FIELDS:
            with self.subTest(missing=missing):
                fields = tuple(field for field in ASSIGNMENT_FIELDS if field != missing)
                self.build_fixture(assignment_fields=fields)
                self.assert_error(f"missing assignment routing field {missing}")

    def test_envelope_fields_outside_production_envelope_do_not_satisfy_contract(self) -> None:
        for missing in ASSIGNMENT_FIELDS:
            with self.subTest(missing=missing):
                prose = f"## Example assignment\n\n{missing}: example value"
                fields = tuple(field for field in ASSIGNMENT_FIELDS if field != missing)
                self.build_fixture(assignment_fields=fields, prose=prose)
                self.assert_error(f"missing assignment routing field {missing}")

    def test_malformed_routing_table_row_fails(self) -> None:
        self.build_fixture(
            raw_rows=(
                "| Orchestrator | n/a | main-only | [orchestrator](orchestrator.md) |",
                "| Implementor | implementor | economy | [implementor](implementor.md) | unexpected |",
            )
        )
        self.assert_error("malformed model routing table row")

    def test_routing_row_without_contract_link_fails(self) -> None:
        self.build_fixture(
            raw_rows=(
                "| Orchestrator | n/a | main-only | [orchestrator](orchestrator.md) |",
                "| Implementor | implementor | economy | |",
            )
        )
        self.assert_error("missing role contract link")

    def test_routing_row_with_multiple_contract_links_fails(self) -> None:
        self.build_fixture(
            raw_rows=(
                "| Orchestrator | n/a | main-only | [orchestrator](orchestrator.md) |",
                "| Implementor | implementor | economy | [implementor](implementor.md) [duplicate](orchestrator.md) |",
            )
        )
        self.assert_error("exactly one role contract link")

    def test_orphan_linked_role_contract_fails(self) -> None:
        self.build_fixture(
            raw_rows=(
                "| Orchestrator | n/a | main-only | [orchestrator](orchestrator.md) |",
                "| Implementor | implementor | economy | [missing](missing.md) |",
            )
        )
        self.assert_error("linked role contract does not exist")

    def test_fenced_markdown_example_is_not_an_active_registry_or_navigation_link(self) -> None:
        self.build_fixture(
            prose=(
                "## Documentation example\n\n"
                "```markdown\n"
                "| Role | Model lane | Contract |\n"
                "|---|---|---|\n"
                "| Fake | main-only | [fake](missing.md) |\n"
                "```\n"
            )
        )
        self.assertEqual([], self.errors())

    def test_active_contract_link_must_stay_in_role_directory(self) -> None:
        self.build_fixture(
            raw_rows=(
                "| Orchestrator | n/a | main-only | [orchestrator](orchestrator.md) |",
                "| Implementor | implementor | economy | [outside](../../../../outside.md) |",
            )
        )
        outside = self.root / "plugins" / "routing-fixture" / "outside.md"
        outside.write_text("# not a role contract\n", encoding="utf-8")
        self.assert_any_error(
            "role contract link escapes role directory",
            "linked role contract does not exist",
        )


if __name__ == "__main__":
    unittest.main()
