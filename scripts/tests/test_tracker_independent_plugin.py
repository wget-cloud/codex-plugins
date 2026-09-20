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
        self.assertEqual(manifest["version"], "1.0.1")
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


if __name__ == "__main__":
    unittest.main()
