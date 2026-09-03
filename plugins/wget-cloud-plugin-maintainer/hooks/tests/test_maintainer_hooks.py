import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "maintainer_hooks.py"
HOOKS_JSON = SCRIPT.parent / "hooks.json"
PLUGIN_JSON = SCRIPT.parent.parent / ".codex-plugin" / "plugin.json"
SKILL_ROOT = SCRIPT.parent.parent / "skills" / "wgc-plugin-maintenance"


def load_hooks():
    spec = importlib.util.spec_from_file_location("maintainer_hooks_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HookConfigurationTest(unittest.TestCase):
    def test_all_handlers_are_synchronous_and_cross_platform(self):
        config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(
            set(config),
            {"SessionStart", "UserPromptSubmit", "SubagentStart", "SubagentStop", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"},
        )
        for groups in config.values():
            for group in groups:
                for handler in group["hooks"]:
                    self.assertEqual("command", handler["type"])
                    self.assertNotIn("async", handler)
                    self.assertIn("${PLUGIN_ROOT}/hooks/maintainer_hooks.py", handler["command"])
                    self.assertIn("%PLUGIN_ROOT%\\hooks\\maintainer_hooks.py", handler["commandWindows"])

    def test_manifest_uses_plain_semver(self):
        manifest = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
        self.assertEqual("0.3.0", manifest["version"])
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
        self.assertNotIn("+", manifest["version"])

    def test_role_contracts_match_hook_verdicts(self):
        module = load_hooks()
        role_dir = SKILL_ROOT / "references" / "agents"
        documented = {path.stem for path in role_dir.glob("*.md") if path.name != "index.md"}
        self.assertEqual(documented, set(module.ROLE_VERDICTS) | {"orchestrator"})
        for role, verdicts in module.ROLE_VERDICTS.items():
            text = (role_dir / f"{role}.md").read_text(encoding="utf-8")
            for verdict in verdicts:
                self.assertIn(verdict, text)


class MaintainerHookTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "codex-plugins"
        self.root.mkdir()
        self.data = Path(self.temp.name) / "plugin-data"
        self.codex_home = Path(self.temp.name) / "codex-home"
        self.codex_home.mkdir()
        (self.codex_home / "config.toml").write_text(
            'service_tier = "default"\n\n[features]\nfast_mode = false\n', encoding="utf-8"
        )
        self.module = load_hooks()
        self._run(["git", "init", "-q", "-b", "main"], self.root)
        self._run(["git", "config", "user.name", "Hook Test"], self.root)
        self._run(["git", "config", "user.email", "hooks@example.invalid"], self.root)
        (self.root / ".agents" / "plugins").mkdir(parents=True)
        (self.root / "plugins" / "sample-plugin" / ".codex-plugin").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        (self.root / ".agents" / "plugins" / "marketplace.json").write_text(
            json.dumps({"name": "wget-cloud", "plugins": []}), encoding="utf-8"
        )
        (self.root / "plugins" / "sample-plugin" / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "sample-plugin", "version": "1.2.3"}), encoding="utf-8"
        )
        (self.root / "tests" / "protected.txt").write_text("immutable baseline\n", encoding="utf-8")
        self._run(["git", "add", "."], self.root)
        self._run(["git", "commit", "-q", "-m", "fixture"], self.root)
        self._run(["git", "remote", "add", "origin", "https://example.invalid/wget-cloud/codex-plugins.git"], self.root)
        head = self._output(["git", "rev-parse", "HEAD"], self.root)
        self._run(["git", "update-ref", "refs/remotes/origin/main", head], self.root)
        self.agent_counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, command, cwd):
        return subprocess.run(command, cwd=str(cwd), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def _output(self, command, cwd):
        return self._run(command, cwd).stdout.strip()

    def raw_call(self, action, payload=None, cwd=None, session="session-test"):
        value = {"session_id": session, "cwd": str(cwd or self.root), **(payload or {})}
        env = dict(os.environ)
        env["PLUGIN_DATA"] = str(self.data)
        env["CODEX_HOME"] = str(self.codex_home)
        return subprocess.run(
            [sys.executable, str(SCRIPT), action],
            input=json.dumps(value),
            cwd=str(cwd or self.root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def call(self, action, payload=None, cwd=None, session="session-test"):
        result = self.raw_call(action, payload, cwd, session)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def test_fast_and_unverifiable_service_tiers_refuse_skill_activation(self):
        prompt = {"hook_event_name": "UserPromptSubmit", "turn_id": "tier-test", "prompt": "$wgc-plugin-maintenance audit"}
        for tier in ("fast", "priority", "ultrafast"):
            with self.subTest(tier=tier):
                result = self.raw_call("prompt-submit", {**prompt, "service_tier": tier})
                self.assertEqual(2, result.returncode)
                self.assertIn("WGC_FAST_MODE_FORBIDDEN", result.stderr)
        (self.codex_home / "config.toml").write_text('[features]\nfast_mode = false\n', encoding="utf-8")
        result = self.raw_call("prompt-submit", prompt)
        self.assertEqual(2, result.returncode)
        self.assertIn("WGC_SERVICE_TIER_UNVERIFIABLE", result.stderr)

    def state(self):
        return json.loads((self.data / "approval-state" / "session-test.json").read_text(encoding="utf-8"))

    def activate(self, prompt="Improve the plugin hooks safely"):
        return self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": "turn-1", "prompt": prompt},
        )

    def proposal_item(self, item_id="M-001", summary="Add maintenance documentation", paths=None, **overrides):
        item = {
            "id": item_id,
            "summary": summary,
            "severity": "medium",
            "benefit": "Keeps the maintenance workflow verifiable",
            "effort": "small",
            "evidence": ["A sanitized fixture reproduces the missing behavior"],
            "paths": paths or ["docs/maintenance.md", "tests/protected.txt"],
            "acceptance": ["The documented behavior is covered by an executable test"],
            "tests": ["make validate"],
            "shadow_eval": ["Compare baseline and candidate against the sanitized corpus"],
            "risks": ["Approval compatibility must remain unchanged"],
            "compatibility": "Backward compatible",
            "depends_on": [],
            "semver": "patch",
            "self_change": False,
        }
        item.update(overrides)
        return item

    def record_role(self, role, verdict):
        self.agent_counter += 1
        agent_id = f"agent-{self.agent_counter}"
        self.call("subagent-start", {"hook_event_name": "SubagentStart", "agent_id": agent_id})
        revision = self.module.worktree_hash(self.root)
        marker = json.dumps({"role": role, "verdict": verdict, "input_revision": revision}, separators=(",", ":"))
        protected = ""
        if role == "test-maker" and verdict == "baseline_ready":
            protected_payload = {
                "paths": {
                    "tests/protected.txt": self.module.file_fingerprint(self.root / "tests" / "protected.txt")
                }
            }
            protected = "WGC_MAINTAINER_PROTECTED_TESTS: " + json.dumps(protected_payload, separators=(",", ":")) + "\n"
        return self.call(
            "subagent-stop",
            {
                "hook_event_name": "SubagentStop",
                "agent_id": agent_id,
                "stop_hook_active": False,
                "last_assistant_message": f"Evidence complete.\n{protected}WGC_MAINTAINER_RESULT: {marker}",
            },
        )

    def register_proposal(self, items=None, turn="turn-2"):
        self.activate()
        self.record_role("auditor", "audited")
        self.record_role("architect", "proposed")
        items = items or [self.proposal_item()]
        proposal = {
            "baseline_head": self.module.git_head(self.root),
            "dirty_fingerprint": self.module.dirty_fingerprint(self.root),
            "items": items,
        }
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": turn,
                "last_assistant_message": "Proposal ready.\nWGC_MAINTENANCE_PROPOSAL: " + json.dumps(proposal, separators=(",", ":")),
            },
        )
        proposal_id = re.search(r"registered as ([0-9a-f]{16})", output["reason"]).group(1)
        return proposal_id, output

    def approve_change(self, proposal_id, items="M-001", turn="turn-3"):
        return self.call(
            "prompt-submit",
            {
                "hook_event_name": "UserPromptSubmit",
                "turn_id": turn,
                "prompt": f"APPROVE_WGC_PLUGIN_CHANGE={proposal_id}:{items}",
            },
        )

    def prepare_delivery(self):
        proposal_id, _ = self.register_proposal()
        self.approve_change(proposal_id)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "maintenance.md").write_text("approved\n", encoding="utf-8")
        for role, verdict in (
            ("test-maker", "baseline_ready"),
            ("implementor", "implemented"),
            ("reviewer", "approved"),
            ("qa", "pass"),
        ):
            self.record_role(role, verdict)
        delivery = {
            "proposal_id": proposal_id,
            "worktree_hash": self.module.worktree_hash(self.root),
            "target": "origin/main",
            "commits": [{"message": "docs(plugin): add maintenance guide", "paths": ["docs/maintenance.md"]}],
            "versions": {"sample-plugin": "1.2.3"},
            "plugins": ["sample-plugin"],
            "ci_evidence": True,
            "runtime_evidence": True,
        }
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-4",
                "last_assistant_message": "Delivery ready.\nWGC_MAINTENANCE_DELIVERY: " + json.dumps(delivery, separators=(",", ":")),
            },
        )
        delivery_id = re.search(r"registered as ([0-9a-f]{16})", output["reason"]).group(1)
        return proposal_id, delivery_id, output

    def test_silent_outside_codex_plugins(self):
        outside = Path(self.temp.name) / "application"
        outside.mkdir()
        self._run(["git", "init", "-q"], outside)
        output = self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "prompt": "Improve plugin hooks"},
            cwd=outside,
            session="outside",
        )
        self.assertIsNone(output)

    def test_activation_is_read_only_and_privacy_safe(self):
        secret = "customer-token-super-secret"
        output = self.activate(f"Audit and improve this plugin; never store {secret}")
        self.assertIn("read-only", output["hookSpecificOutput"]["additionalContext"])
        raw_state = (self.data / "approval-state" / "session-test.json").read_text(encoding="utf-8")
        self.assertNotIn(secret, raw_state)
        self.assertNotIn("last_prompt\"", raw_state)

    def test_write_is_denied_before_gate_one(self):
        self.activate()
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: docs/x.md\n+x\n*** End Patch"},
            },
        )
        self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
        self.assertIn("Gate 1", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_shell_redirection_is_denied_before_gate_one(self):
        self.activate()
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "printf x > docs/x.md"},
            },
        )
        self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])

    def test_bash_write_syntax_and_unresolved_paths_fail_closed_before_gate_one(self):
        self.activate()
        for command in (
            "tee docs/x.md",
            "install -m 600 /dev/null docs/x.md",
            "cp source docs/x.md",
            "mv source docs/x.md",
            "python -c 'open(\"docs/x.md\", \"w\")'",
            "unknown-writer --output docs/x.md",
        ):
            with self.subTest(command=command):
                output = self.call(
                    "pre-tool",
                    {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}},
                )
                self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])

    def test_read_only_command_is_allowed_before_gate_one(self):
        self.activate()
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git status -sb"},
            },
        )
        self.assertIsNone(output)

    def test_proposal_requires_auditor_and_architect(self):
        self.activate()
        proposal = {
            "baseline_head": self.module.git_head(self.root),
            "dirty_fingerprint": self.module.dirty_fingerprint(self.root),
            "items": [self.proposal_item(summary="x", paths=["docs/x.md"])],
        }
        output = self.call(
            "stop",
            {"hook_event_name": "Stop", "turn_id": "turn-2", "last_assistant_message": "WGC_MAINTENANCE_PROPOSAL: " + json.dumps(proposal)},
        )
        self.assertIn("Auditor=audited", output["reason"])

    def test_proposal_binds_full_evidence_and_evaluation_contract(self):
        self.activate()
        self.record_role("auditor", "audited")
        self.record_role("architect", "proposed")
        item = self.proposal_item()
        del item["shadow_eval"]
        proposal = {
            "baseline_head": self.module.git_head(self.root),
            "dirty_fingerprint": self.module.dirty_fingerprint(self.root),
            "items": [item],
        }
        output = self.call(
            "stop",
            {"hook_event_name": "Stop", "turn_id": "turn-2", "last_assistant_message": "WGC_MAINTENANCE_PROPOSAL: " + json.dumps(proposal)},
        )
        self.assertIn("documented approval fields", output["reason"])

    def test_proposal_rejects_unknown_or_cyclic_dependencies(self):
        self.activate()
        self.record_role("auditor", "audited")
        self.record_role("architect", "proposed")

        def submit(items, turn):
            proposal = {
                "baseline_head": self.module.git_head(self.root),
                "dirty_fingerprint": self.module.dirty_fingerprint(self.root),
                "items": items,
            }
            return self.call(
                "stop",
                {"hook_event_name": "Stop", "turn_id": turn, "last_assistant_message": "WGC_MAINTENANCE_PROPOSAL: " + json.dumps(proposal)},
            )

        unknown = [self.proposal_item(depends_on=["M-404"])]
        output = submit(unknown, "turn-unknown")
        self.assertIn("unknown items", output["reason"])
        cyclic = [
            self.proposal_item("M-001", "one", ["docs/one.md"], depends_on=["M-002"]),
            self.proposal_item("M-002", "two", ["docs/two.md"], depends_on=["M-001"]),
        ]
        output = submit(cyclic, "turn-cycle")
        self.assertIn("cycle", output["reason"])

    def test_item_level_approval_limits_paths(self):
        items = [
            self.proposal_item("M-001", "one", ["docs/one.md"]),
            self.proposal_item("M-002", "two", ["docs/two.md"]),
        ]
        proposal_id, _ = self.register_proposal(items)
        self.approve_change(proposal_id, "M-001")
        allowed = self.call(
            "pre-tool",
            {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: docs/one.md\n+x\n*** End Patch"}},
        )
        denied = self.call(
            "pre-tool",
            {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: docs/two.md\n+x\n*** End Patch"}},
        )
        self.assertIsNone(allowed)
        self.assertEqual("deny", denied["hookSpecificOutput"]["permissionDecision"])

    def test_unknown_or_duplicate_item_approval_is_rejected(self):
        proposal_id, _ = self.register_proposal()
        unknown = self.approve_change(proposal_id, "M-999")
        duplicate = self.approve_change(proposal_id, "M-001,M-001", turn="turn-4")
        self.assertEqual("Maintenance approval rejected", unknown["systemMessage"])
        self.assertEqual("Maintenance approval rejected", duplicate["systemMessage"])

    def test_self_change_requires_explicit_flag(self):
        items = [self.proposal_item(
            "M-SELF",
            "change maintainer",
            ["plugins/wget-cloud-plugin-maintainer/SKILL.md"],
            self_change=False,
        )]
        self.activate()
        self.record_role("auditor", "audited")
        self.record_role("architect", "proposed")
        proposal = {"baseline_head": self.module.git_head(self.root), "dirty_fingerprint": self.module.dirty_fingerprint(self.root), "items": items}
        output = self.call(
            "stop",
            {"hook_event_name": "Stop", "turn_id": "turn-2", "last_assistant_message": "WGC_MAINTENANCE_PROPOSAL: " + json.dumps(proposal)},
        )
        self.assertIn("self_change", output["reason"])

    def test_dirty_overlap_rejects_proposal(self):
        dirty = self.root / "docs" / "user.md"
        dirty.parent.mkdir()
        dirty.write_text("user work\n", encoding="utf-8")
        self.activate()
        self.record_role("auditor", "audited")
        self.record_role("architect", "proposed")
        proposal = {
            "baseline_head": self.module.git_head(self.root),
            "dirty_fingerprint": self.module.dirty_fingerprint(self.root),
            "items": [self.proposal_item(summary="overlap", paths=["docs/"])],
        }
        output = self.call(
            "stop",
            {"hook_event_name": "Stop", "turn_id": "turn-2", "last_assistant_message": "WGC_MAINTENANCE_PROPOSAL: " + json.dumps(proposal)},
        )
        self.assertIn("overlaps", output["reason"])

    def test_changed_baseline_invalidates_change_approval(self):
        proposal_id, _ = self.register_proposal()
        (self.root / "outside.md").write_text("changed\n", encoding="utf-8")
        output = self.approve_change(proposal_id)
        self.assertEqual("Maintenance approval rejected", output["systemMessage"])

    def test_delivery_requires_external_evidence_and_all_roles(self):
        proposal_id, _ = self.register_proposal()
        self.approve_change(proposal_id)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "maintenance.md").write_text("approved\n", encoding="utf-8")
        delivery = {
            "proposal_id": proposal_id,
            "worktree_hash": self.module.worktree_hash(self.root),
            "target": "origin/main",
            "commits": [{"message": "docs: add guide", "paths": ["docs/maintenance.md"]}],
            "versions": {"sample-plugin": "1.2.3"},
            "plugins": ["sample-plugin"],
            "ci_evidence": False,
            "runtime_evidence": True,
        }
        output = self.call(
            "stop",
            {"hook_event_name": "Stop", "turn_id": "turn-4", "last_assistant_message": "WGC_MAINTENANCE_DELIVERY: " + json.dumps(delivery)},
        )
        self.assertIn("CI", output["reason"])

    def test_change_and_delivery_approvals_bind_secret_sentinels_without_persisting_them(self):
        secret = "token-forbidden-in-state"
        proposal_id, _ = self.register_proposal()
        self.approve_change(proposal_id)
        state = self.state()
        serialized = json.dumps(state, sort_keys=True)
        self.assertIn("secret_sentinels", state["change_approval"])
        self.assertNotIn(secret, serialized)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in state["change_approval"]["secret_sentinels"]))

    def test_rolling_delivery_hash_invalidates_after_each_delivery_transition(self):
        _, delivery_id, _ = self.prepare_delivery()
        state = self.state()
        self.assertIn("delivery_chain_sha256", state["delivery_proposal"])
        before = state["delivery_proposal"]["delivery_chain_sha256"]
        self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": "turn-5", "prompt": f"APPROVE_WGC_PLUGIN_DELIVERY={delivery_id}"},
        )
        self.assertNotEqual(before, self.state()["delivery_approval"]["delivery_chain_sha256"])

    def test_release_transitions_require_ordered_evidence_and_reject_skips(self):
        _, delivery_id, _ = self.prepare_delivery()
        self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": "turn-5", "prompt": f"APPROVE_WGC_PLUGIN_DELIVERY={delivery_id}"},
        )
        self.assertIn("release_transitions", self.state()["delivery_approval"])
        self.assertEqual([], self.state()["delivery_approval"]["release_transitions"])
        for command in (
            "git tag sample-plugin-v1.2.3",
            "codex plugin add sample-plugin@wget-cloud",
            "gh release create sample-plugin-v1.2.3 --notes ready",
        ):
            with self.subTest(command=command):
                output = self.call(
                    "pre-tool",
                    {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}},
                )
                self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])

    def test_gate_two_controls_commit_push_install_tag_and_release(self):
        _, delivery_id, _ = self.prepare_delivery()
        blocked = self.call(
            "pre-tool",
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git add -- docs/maintenance.md"}},
        )
        self.assertEqual("deny", blocked["hookSpecificOutput"]["permissionDecision"])
        approved = self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": "turn-5", "prompt": f"APPROVE_WGC_PLUGIN_DELIVERY={delivery_id}"},
        )
        self.assertIn("Gate 2 approved", approved["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.call(
            "pre-tool",
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git add -- docs/maintenance.md"}},
        ))
        self._run(["git", "add", "--", "docs/maintenance.md"], self.root)
        self.assertIsNone(self.call(
            "pre-tool",
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git commit -m 'docs(plugin): add maintenance guide'"}},
        ))
        self._run(["git", "commit", "-q", "-m", "docs(plugin): add maintenance guide"], self.root)
        for command in (
            "git tag sample-plugin-v1.2.3",
            "codex plugin add sample-plugin@wget-cloud",
            "gh release create sample-plugin-v1.2.3 --notes ready",
        ):
            with self.subTest(command=f"blocked before push: {command}"):
                output = self.call(
                    "pre-tool",
                    {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}},
                )
                self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
        push = "git push origin main"
        self.assertIsNone(self.call(
            "pre-tool",
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": push}},
        ))
        self.assertIsNone(self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": push},
                "tool_response": {"exit_code": 0},
            },
        ))
        for command, required_evidence in (
            ("codex plugin add sample-plugin@wget-cloud", "candidate CI"),
            ("git tag sample-plugin-v1.2.3", "smoke evidence"),
            ("gh release create sample-plugin-v1.2.3 --notes ready", "smoke evidence"),
        ):
            with self.subTest(command=command):
                output = self.call(
                    "pre-tool",
                    {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}},
                )
                self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
                self.assertIn(required_evidence, output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_implementor_cannot_edit_protected_test(self):
        proposal_id, _ = self.register_proposal()
        self.approve_change(proposal_id)
        self.record_role("test-maker", "baseline_ready")
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Update File: tests/protected.txt\n@@\n-immutable baseline\n+weakened\n*** End Patch"},
            },
        )
        self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
        self.assertIn("protected", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_git_dash_c_delivery_wrapper_cannot_bypass_gate(self):
        self.activate()
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": f"git -C {self.root} push origin main"},
            },
        )
        self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
        self.assertIn("Gate 2", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_force_push_is_always_denied(self):
        self.activate()
        output = self.call(
            "pre-tool",
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}},
        )
        self.assertIn("Force-push", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_changed_worktree_invalidates_delivery_approval(self):
        _, delivery_id, _ = self.prepare_delivery()
        (self.root / "docs" / "other.md").write_text("changed\n", encoding="utf-8")
        output = self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": "turn-5", "prompt": f"APPROVE_WGC_PLUGIN_DELIVERY={delivery_id}"},
        )
        self.assertEqual("Delivery approval rejected", output["systemMessage"])

    def test_corrupt_state_fails_closed_for_write(self):
        self.activate()
        state_path = self.data / "approval-state" / "session-test.json"
        state_path.write_text("{broken", encoding="utf-8")
        output = self.call(
            "pre-tool",
            {"hook_event_name": "PreToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: docs/x.md\n+x\n*** End Patch"}},
        )
        self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
        self.assertIn("corrupt", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_session_end_revokes_approvals(self):
        proposal_id, _ = self.register_proposal()
        self.approve_change(proposal_id)
        self.call("session-end", {"hook_event_name": "SessionEnd"})
        state = self.state()
        self.assertFalse(state["active"])
        self.assertIsNone(state["change_approval"])
        self.assertIsNone(state["delivery_approval"])


if __name__ == "__main__":
    unittest.main()
