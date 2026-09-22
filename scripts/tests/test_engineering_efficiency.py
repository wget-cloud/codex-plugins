import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "wget-cloud-implementation"


class EngineeringEfficiencyTests(unittest.TestCase):
    def test_version_and_service_tier_policy(self):
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["version"], "9.1.0")

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
        self.assertIn("Bugfix сохраняет независимый Test-maker", bugfix)


if __name__ == "__main__":
    unittest.main()
