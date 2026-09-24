import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "wget-cloud-development"


class TrackerIndependentPluginTests(unittest.TestCase):
    def test_bundle_contains_only_implementation_and_bugfix(self):
        skill_names = sorted(path.name for path in (PLUGIN / "skills").iterdir())
        self.assertEqual(skill_names, ["wgc-bugfix", "wgc-implementation"])

        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "wget-cloud-development")
        self.assertEqual(manifest["version"], "2.0.1")
        self.assertNotIn("mcpServers", manifest)

    def test_bundle_has_no_tracker_runtime_or_youtrack_knowledge(self):
        for relative in (".mcp.json", "hooks", "scripts"):
            self.assertFalse((PLUGIN / relative).exists(), relative)

        for path in PLUGIN.rglob("*"):
            if path.is_file():
                self.assertNotIn("youtrack", path.read_text(encoding="utf-8").casefold(), path)

    def test_bundle_targets_backend_services_go_contracts(self):
        corpus = "\n".join(
            path.read_text(encoding="utf-8")
            for path in PLUGIN.rglob("*")
            if path.is_file()
        ).casefold()

        for required in (
            "backend-services",
            "services.json",
            "go test -race ./...",
            "go vet ./...",
            "golangci-lint run",
            "go build ./cmd/...",
            "buf breaking",
            "affected-service matrix",
        ):
            self.assertIn(required, corpus)

        for legacy_stack in (
            "nestjs",
            "nest-service",
            "next.js",
            "prisma",
            "jest",
            "front-lib",
            "frontend",
            "browser",
            "pwa",
        ):
            self.assertNotIn(legacy_stack, corpus)

    def test_bundle_does_not_gate_work_by_service_tier(self):
        corpus = "\n".join(
            path.read_text(encoding="utf-8")
            for path in PLUGIN.rglob("*")
            if path.is_file()
        ).casefold()

        for obsolete_gate in (
            "service_tier",
            "service tier",
            "fast_mode",
            "priority-only",
            "wgc_fast_mode_forbidden",
            "wgc_service_tier_unverifiable",
        ):
            self.assertNotIn(obsolete_gate, corpus)

    def test_gpt6_routing_is_bounded_and_astra_is_forbidden(self):
        forbidden_routes = (
            "gpt-6-sol/high",
            "gpt-6-sol/xhigh",
            "gpt-6-sol/max",
            "gpt-6-sol/ultra",
            "gpt-5.6",
            "Terra",
            "Sol/high",
        )

        for skill_name in ("wgc-bugfix", "wgc-implementation"):
            skill = PLUGIN / "skills" / skill_name
            model_routing = (skill / "references" / "model-routing.md").read_text()
            registry = (skill / "references" / "agents" / "index.md").read_text()

            self.assertIn("gpt-6-luna/low", model_routing)
            self.assertIn("gpt-6-luna/medium", model_routing)
            self.assertIn("gpt-6-sol/low", model_routing)
            self.assertIn("gpt-6-sol/medium", model_routing)
            self.assertIn("gpt-6-astra` полностью запрещена", model_routing)
            self.assertIn("`high`, `xhigh`, `max` и `ultra`", model_routing)
            self.assertIn("Astra и Sol выше `medium` запрещены", registry)
            self.assertIn("MEDIUM_ESCALATION_REASON", registry)
            self.assertIn("DECISION_REQUIRED", (skill / "references" / "coordination-efficiency.md").read_text())
            for forbidden in forbidden_routes:
                self.assertNotIn(forbidden, model_routing)
                self.assertNotIn(forbidden, registry)

    def test_coordination_contract_prevents_duplicate_agent_work(self):
        for skill_name in ("wgc-bugfix", "wgc-implementation"):
            skill = PLUGIN / "skills" / skill_name
            coordination = (skill / "references" / "coordination-efficiency.md").read_text()
            registry = (skill / "references" / "agents" / "index.md").read_text()
            model_routing = (skill / "references" / "model-routing.md").read_text()
            skill_text = (skill / "SKILL.md").read_text()

            for required in (
                "DecisionSnapshot",
                "ResumeCapsule",
                "ASSIGNMENT_KEY",
                "RETRY_REASON",
                "DIFF_IDENTITY",
                "FREEZE_STATUS",
                "ContradictionReport",
                "Selective invalidation",
                "T0",
                "T3",
            ):
                self.assertIn(required, coordination, (skill_name, required))

            self.assertIn("coordination-efficiency.md", skill_text)
            self.assertIn("ASSIGNMENT_KEY", registry)
            self.assertIn("RETRY_REASON", registry)
            self.assertIn("DIFF_IDENTITY", registry)
            self.assertNotIn("|all>", registry)
            self.assertIn("`all` запрещён", model_routing)

    def test_long_running_workflow_regression_contracts(self):
        for skill_name in ("wgc-bugfix", "wgc-implementation"):
            skill = PLUGIN / "skills" / skill_name
            coordination = (skill / "references" / "coordination-efficiency.md").read_text()
            registry = (skill / "references" / "agents" / "index.md").read_text()
            orchestrator = (skill / "references" / "agents" / "orchestrator.md").read_text()
            architect = (skill / "references" / "agents" / "architect.md").read_text()
            test_maker = (skill / "references" / "agents" / "test-maker.md").read_text()
            workflow = (skill / "references" / "workflow.md").read_text()

            for required in (
                "ACTIVE_ASSIGNMENTS",
                "COMPLETED_ASSIGNMENTS",
                "BLOCKING_FINDINGS",
                "PROTECTED_TEST_HASHES",
                "VALID_CHECK_CACHE",
                "NEXT_ALLOWED_TRANSITIONS",
                "compaction",
                "same `ASSIGNMENT_KEY`",
                "exponential backoff",
            ):
                self.assertIn(required, coordination, (skill_name, required))

            self.assertIn("RESUME_CAPSULE_REVISION", registry)
            self.assertIn("Test-maker owner", registry)
            self.assertIn("production code или tests", orchestrator)
            self.assertIn("diff-review", architect)
            self.assertIn("TEST_OWNER_ID", test_maker)
            self.assertIn("bounded vertical", workflow)
            self.assertIn("ContradictionReport", workflow)

    def test_lean_tranche_and_cost_controls_are_explicit(self):
        implementation = PLUGIN / "skills" / "wgc-implementation"
        bugfix = PLUGIN / "skills" / "wgc-bugfix"

        implementation_coordination = (implementation / "references" / "coordination-efficiency.md").read_text()
        implementation_registry = (implementation / "references" / "agents" / "index.md").read_text()
        implementation_tests = (implementation / "references" / "test-assessment.md").read_text()
        implementation_workflow = (implementation / "references" / "workflow.md").read_text()
        implementation_model = (implementation / "references" / "model-routing.md").read_text()

        for required in (
            "EfficiencyBudget",
            "MAX_AGENT_ASSIGNMENTS",
                "MAX_UNCHANGED_WAIT_STREAK",
                "MAX_PASSIVE_WAIT_MINUTES",
            "MAX_EXPENSIVE_CHECKS",
            "EfficiencyCheckpoint",
            "ServiceHandoff",
            "5–10",
            "максимум 3 assignments",
            "10 coordination decisions",
            "одним correction batch",
        ):
            self.assertIn(required, implementation_coordination, required)

        self.assertIn("SPAWN_PREFLIGHT", implementation_registry)
        self.assertIn("exact `model`, `reasoning_effort` и `fork_turns`", implementation_model)
        self.assertIn("test_ownership", implementation_tests)
        self.assertIn("обычные `add/update` tests принадлежат Implementor", implementation_tests)
        self.assertIn("T2 gates — один раз", implementation_workflow)

        for skill in (implementation, bugfix):
            coordination = (skill / "references" / "coordination-efficiency.md").read_text()
            orchestrator = (skill / "references" / "agents" / "orchestrator.md").read_text()
            self.assertIn("После одного unchanged wait", coordination)
            self.assertIn("EfficiencyBudget", orchestrator)

    def test_startup_defaults_do_not_require_a_separate_profile(self):
        for skill_name in ("wgc-bugfix", "wgc-implementation"):
            skill = PLUGIN / "skills" / skill_name
            coordination = (skill / "references" / "coordination-efficiency.md").read_text()
            routing = (skill / "references" / "model-routing.md").read_text()
            self.assertIn("максимум 3 assignments", coordination)
            self.assertIn("10 coordination decisions", coordination)
            self.assertIn("полный pipeline не перезапускается", coordination)
            self.assertIn("MEDIUM_ESCALATION_REASON", routing)
            self.assertNotIn("Startup/Fast", coordination)

    def test_plugin_remains_skills_only_after_coordination_hardening(self):
        self.assertFalse((PLUGIN / "hooks").exists())
        self.assertFalse((PLUGIN / ".mcp.json").exists())

    def test_compact_routes_do_not_force_full_pipeline(self):
        for skill_name in ("wgc-bugfix", "wgc-implementation"):
            skill = PLUGIN / "skills" / skill_name
            assessment = (skill / "references" / "task-assessment.md").read_text()
            coordination = (skill / "references" / "coordination-efficiency.md").read_text()
            self.assertIn("Full определяет планирование", assessment)
            self.assertIn("FREEZE_STATUS: n/a", coordination)
            self.assertIn("STOP_AFTER_SERVICE", coordination)

    def test_backend_specific_contracts_follow_service_registry(self):
        corpus = "\n".join(
            path.read_text(encoding="utf-8")
            for path in PLUGIN.rglob("*")
            if path.is_file()
        ).casefold()
        self.assertIn("services.json.coveragemin", corpus)
        for residue in ("responsive/a11y", "service-worker", "state v4", "владелец в v7"):
            self.assertNotIn(residue, corpus)


if __name__ == "__main__":
    unittest.main()
