import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "wget-cloud-implementation"


class EngineeringEfficiencyTests(unittest.TestCase):
    def test_version_and_service_tier_policy(self):
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["version"], "10.0.0")

        hook = (PLUGIN / "hooks" / "wgc_hooks.py").read_text()
        for obsolete_gate in (
            "require_standard_service_tier",
            "WGC_FAST_MODE_FORBIDDEN",
            "WGC_SERVICE_TIER_UNVERIFIABLE",
        ):
            self.assertNotIn(obsolete_gate, hook)

    def test_every_skill_has_bounded_coordination_contract(self):
        for skill in sorted((PLUGIN / "skills").iterdir()):
            coordination = (skill / "references" / "coordination-efficiency.md").read_text()
            registry = (skill / "references" / "agents" / "index.md").read_text()
            routing = (skill / "references" / "model-routing.md").read_text()
            skill_text = (skill / "SKILL.md").read_text()

            for required in (
                "DecisionSnapshot",
                "ResumeCapsule",
                "ASSIGNMENT_KEY",
                "EfficiencyBudget",
                "CheckPlan",
                "HandoffCapsule",
                "EfficiencyCheckpoint",
            ):
                self.assertIn(required, coordination, (skill.name, required))
            self.assertIn("coordination-efficiency.md", skill_text)
            self.assertIn("SPAWN_PREFLIGHT", registry)
            self.assertIn("EFFICIENCY_BUDGET", registry)
            self.assertNotIn("|all>", registry)
            self.assertIn("`all` запрещён", routing)
            self.assertIn("Service tier не является quality gate", routing)

    def test_gpt6_routing_is_bounded_and_astra_is_forbidden(self):
        forbidden_routes = (
            "gpt-6-sol/high",
            "gpt-6-sol/xhigh",
            "gpt-6-sol/max",
            "gpt-6-sol/ultra",
            "gpt-6-astra",
            "gpt-5.6",
            "Terra",
            "Sol/high",
        )

        for skill in sorted((PLUGIN / "skills").iterdir()):
            routing = (skill / "references" / "model-routing.md").read_text()
            registry = (skill / "references" / "agents" / "index.md").read_text()

            self.assertIn("gpt-6-luna/low", routing)
            self.assertIn("gpt-6-luna/medium", routing)
            self.assertIn("gpt-6-sol/low", routing)
            self.assertIn("gpt-6-sol/medium", routing)
            self.assertIn("`high`, `xhigh`, `max` и `ultra`", routing)
            self.assertIn("Astra и Sol выше `medium` запрещены", registry)
            self.assertIn("MEDIUM_ESCALATION_REASON", registry)
            self.assertIn("DECISION_REQUIRED", (skill / "references" / "coordination-efficiency.md").read_text())
            for forbidden in forbidden_routes:
                if forbidden == "gpt-6-astra":
                    self.assertIn("gpt-6-astra` полностью запрещена", routing)
                else:
                    self.assertNotIn(forbidden, routing)
                    self.assertNotIn(forbidden, registry)

    def test_test_ownership_keeps_implementation_lean_and_bugfix_independent(self):
        for name in ("wgc-implementation", "wgc-epic-implementation"):
            skill = PLUGIN / "skills" / name
            policy = (skill / "references" / "test-assessment.md").read_text()
            implementor = (skill / "references" / "agents" / "implementor.md").read_text()
            test_maker = (skill / "references" / "agents" / "test-maker.md").read_text()
            self.assertIn("test_ownership", policy)
            self.assertIn("обычные", implementor.casefold())
            self.assertIn("critical", test_maker.casefold())

        bugfix = (PLUGIN / "skills" / "wgc-bugfix" / "references" / "task-assessment.md").read_text()
        self.assertIn("Обычные `add/update` tests принадлежат Implementor", bugfix)

    def test_compact_coordination_routes_are_explicit(self):
        source = ROOT / "plugin-src" / "wget-cloud-implementation" / "policies"
        policy = (source / "coordination-efficiency.md").read_text()
        assessment = (source / "task-assessment.md").read_text()
        self.assertIn("MAX_UNCHANGED_WAIT_STREAK", policy)
        self.assertIn("ReviewBundle", policy)
        self.assertIn("STOP_AFTER_BOUNDARY", policy)
        self.assertIn("не Full автоматически", assessment)

    def test_startup_defaults_are_enforced_without_a_profile(self):
        source = ROOT / "plugin-src" / "wget-cloud-implementation" / "policies"
        coordination = (source / "coordination-efficiency.md").read_text()
        routing = (source / "model-routing.md").read_text()
        self.assertIn("максимум 3 assignments", coordination)
        self.assertIn("10 coordination decisions", coordination)
        self.assertIn("одним correction batch", coordination)
        self.assertIn("полный pipeline не перезапускается", coordination)
        self.assertIn("Размер задачи, режим Full и длительность работы сами по себе не повышают модель", routing)
        self.assertNotIn("Startup/Fast", coordination)


if __name__ == "__main__":
    unittest.main()
