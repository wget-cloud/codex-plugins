import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "wgc_hooks.py"
HOOKS_JSON = SCRIPT.parent / "hooks.json"


class HooksConfigTest(unittest.TestCase):
    def test_all_configured_handlers_resolve_to_runner_actions(self):
        config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        expected_events = {
            "SessionStart",
            "UserPromptSubmit",
            "SubagentStart",
            "SubagentStop",
            "PreToolUse",
            "PostToolUse",
            "Stop",
            "SessionEnd",
        }
        self.assertEqual(set(config["hooks"]), expected_events)
        actions = {
            "session-start",
            "prompt-submit",
            "subagent-start",
            "subagent-stop",
            "pre-tool",
            "post-tool",
            "stop",
            "session-end",
        }
        configured_actions = set()
        for groups in config["hooks"].values():
            for group in groups:
                for handler in group["hooks"]:
                    self.assertEqual(handler["type"], "command")
                    self.assertIn("${PLUGIN_ROOT}/hooks/wgc_hooks.py", handler["command"])
                    configured_actions.add(handler["command"].rsplit(" ", 1)[-1])
        self.assertEqual(configured_actions, actions)

    def test_only_post_tool_runs_async(self):
        config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        async_events = {
            event
            for event, groups in config.items()
            for group in groups
            for handler in group["hooks"]
            if handler.get("async")
        }
        self.assertEqual(async_events, {"PostToolUse"})


class WgcHooksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "wgetcloud"
        self.root.mkdir()
        self.data = Path(self.temp.name) / "plugin-data"
        self.agent_counter = 0
        self._git_init(self.root)
        (self.root / ".gitmodules").write_text(
            "\n".join(
                f'[submodule "{name}"]\n\tpath = {name}\n\turl = https://example.invalid/{name}.git'
                for name in ("frontend", "backend", "wget-cloud-front-lib", "wget-cloud-site", "k8s")
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "AGENTS.md").write_text("# Wget Cloud\n", encoding="utf-8")
        self._git_commit(self.root, [".gitmodules", "AGENTS.md"])
        self.projects = {}
        for name in ("frontend", "backend", "wget-cloud-front-lib", "wget-cloud-site", "k8s"):
            project = self.root / name
            project.mkdir()
            self._git_init(project)
            (project / "AGENTS.md").write_text(f"# {name}\n", encoding="utf-8")
            self._git_commit(project, ["AGENTS.md"])
            self.projects[name] = project

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, command, cwd):
        return subprocess.run(command, cwd=str(cwd), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def _git_init(self, path):
        self._run(["git", "init", "-q"], path)
        self._run(["git", "config", "user.name", "Hook Test"], path)
        self._run(["git", "config", "user.email", "hooks@example.invalid"], path)

    def _git_commit(self, path, files):
        self._run(["git", "add", *files], path)
        self._run(["git", "commit", "-q", "-m", "test fixture"], path)

    def call(self, action, payload, cwd=None):
        payload = {"session_id": "session-test", "cwd": str(cwd or self.root), **payload}
        env = dict(os.environ)
        env["PLUGIN_DATA"] = str(self.data)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), action],
            input=json.dumps(payload),
            cwd=str(cwd or self.root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def activate(self, project="backend"):
        cwd = self.projects[project]
        return self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": "turn-1", "prompt": "Use $wgc-implementation to fix it"},
            cwd,
        )

    def record_agent(self, cwd, role, verdict, phase=""):
        self.agent_counter += 1
        agent_id = f"agent-{self.agent_counter}"
        started = self.call(
            "subagent-start",
            {
                "hook_event_name": "SubagentStart",
                "turn_id": "turn-agent",
                "agent_id": agent_id,
                "agent_type": role,
            },
            cwd,
        )
        context = started["hookSpecificOutput"]["additionalContext"]
        revision = re.search(r"revision is ([0-9a-f]{64})", context).group(1)
        marker = json.dumps(
            {"role": role, "verdict": verdict, "phase": phase, "input_revision": revision},
            separators=(",", ":"),
        )
        return self.call(
            "subagent-stop",
            {
                "hook_event_name": "SubagentStop",
                "turn_id": "turn-agent",
                "agent_id": agent_id,
                "agent_type": role,
                "stop_hook_active": False,
                "last_assistant_message": f"Evidence complete.\nWGC_AGENT_RESULT: {marker}",
            },
            cwd,
        )

    def test_session_start_loads_project_context(self):
        output = self.call(
            "session-start",
            {"hook_event_name": "SessionStart", "source": "startup"},
            self.projects["frontend"],
        )
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Current project: frontend", context)
        self.assertIn("npm run type-check", context)

    def test_subagent_stop_requires_and_records_structured_verdict(self):
        cwd = self.projects["backend"]
        self.activate()
        missing = self.call(
            "subagent-stop",
            {
                "hook_event_name": "SubagentStop",
                "turn_id": "turn-agent-missing",
                "agent_id": "missing-agent",
                "agent_type": "reviewer",
                "stop_hook_active": False,
                "last_assistant_message": "Looks good",
            },
            cwd,
        )
        self.assertEqual(missing["decision"], "block")
        self.assertIn("WGC_AGENT_RESULT", missing["reason"])
        self.assertIsNone(self.record_agent(cwd, "reviewer", "approved"))
        state_path = next((self.data / "hook-state").glob("*.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["subagent_results"][-1]["role"], "reviewer")

    def test_prompt_submit_activates_only_implementation_intent(self):
        output = self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "prompt": "Explain the architecture"},
            self.projects["backend"],
        )
        self.assertIsNone(output)
        output = self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "prompt": "How do I build frontend locally?"},
            self.projects["backend"],
        )
        self.assertIsNone(output)
        output = self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "prompt": "Update me on the current status"},
            self.projects["backend"],
        )
        self.assertIsNone(output)
        output = self.activate()
        self.assertIn("workflow activated", output["hookSpecificOutput"]["additionalContext"])
        states = list((self.data / "hook-state").glob("*.json"))
        state = json.loads(states[0].read_text(encoding="utf-8"))
        self.assertIn("last_prompt_sha256", state)
        self.assertNotIn("last_prompt", state)

    def test_blocks_direct_kubernetes_write_but_allows_read(self):
        blocked = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "kubectl -n backend apply -f deployment.yaml"},
            },
            self.projects["k8s"],
        )
        specific = blocked["hookSpecificOutput"]
        self.assertEqual(specific["permissionDecision"], "deny")
        self.assertIn("Git", specific["permissionDecisionReason"])

        allowed = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "kubectl -n backend get pods -o wide"},
            },
            self.projects["k8s"],
        )
        self.assertIsNone(allowed)
        quoted = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "echo 'kubectl apply is forbidden'"},
            },
            self.projects["k8s"],
        )
        self.assertIsNone(quoted)
        nested = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "zsh -lc 'kubectl apply -f unsafe.yaml'"},
            },
            self.projects["k8s"],
        )
        self.assertEqual(nested["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_pre_tool_fails_closed_when_state_storage_is_broken(self):
        broken_data = Path(self.temp.name) / "not-a-directory"
        broken_data.write_text("file", encoding="utf-8")
        payload = {
            "session_id": "broken-state",
            "cwd": str(self.projects["k8s"]),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "kubectl apply -f unsafe.yaml"},
        }
        env = dict(os.environ)
        env["PLUGIN_DATA"] = str(broken_data)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "pre-tool"],
            input=json.dumps(payload),
            cwd=str(self.projects["k8s"]),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("failed internally", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_blocks_destructive_git_and_force_push(self):
        for command in ("git reset --hard HEAD~1", "git clean -fdx", "git push --force origin main"):
            with self.subTest(command=command):
                output = self.call(
                    "pre-tool",
                    {
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    },
                    self.projects["backend"],
                )
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        quoted = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "rg 'git reset --hard' docs"},
            },
            self.projects["backend"],
        )
        self.assertIsNone(quoted)

    def test_blocks_direct_infrastructure_and_broad_cleanup(self):
        commands = (
            "helm upgrade gateway ./chart",
            "argocd app sync gateway",
            "flux reconcile kustomization apps",
            "terraform apply plan.tfplan",
            "docker system prune -f",
            f"rm -rf {self.root}",
            "sudo kubectl delete pod gateway-0",
        )
        for command in commands:
            with self.subTest(command=command):
                output = self.call(
                    "pre-tool",
                    {
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    },
                    self.projects["k8s"],
                )
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        safe_template = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "helm template gateway ./chart"},
            },
            self.projects["k8s"],
        )
        self.assertIsNone(safe_template)

    def test_git_c_commit_preflight_uses_target_repository(self):
        target = self.projects["backend"]
        bad = target / "bad.txt"
        bad.write_text("trailing whitespace   \n", encoding="utf-8")
        self._run(["git", "add", "bad.txt"], target)
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git -C backend commit -m test"},
            },
            self.root,
        )
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("staged diff", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_blocks_patch_outside_workspace_and_secret_material(self):
        outside = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: /tmp/outside.txt\n+x\n*** End Patch"},
            },
            self.projects["backend"],
        )
        self.assertEqual(outside["hookSpecificOutput"]["permissionDecision"], "deny")

        secret = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Add File: token.txt\n+eyJaaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaaaaaaa.aaaaaaaaaaaaaaaa\n*** End Patch"
                },
            },
            self.projects["backend"],
        )
        self.assertEqual(secret["hookSpecificOutput"]["permissionDecision"], "deny")

        move = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Update File: src.ts\n*** Move to: /tmp/moved.ts\n*** End Patch"
                },
            },
            self.projects["backend"],
        )
        self.assertEqual(move["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_test_edit_is_warned_not_falsely_role_blocked(self):
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Add File: src/example.spec.ts\n+test('x', () => {})\n*** End Patch"
                },
            },
            self.projects["backend"],
        )
        self.assertIn("Test-maker", output["hookSpecificOutput"]["additionalContext"])

    def test_stop_gate_ignores_preexisting_dirty_paths(self):
        source = self.projects["backend"] / "src.ts"
        source.write_text("export const before = true;\n", encoding="utf-8")
        self.activate()
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-preexisting",
                "stop_hook_active": False,
                "last_assistant_message": "Done",
            },
            self.projects["backend"],
        )
        self.assertIsNone(output)

    def test_stop_gate_detects_later_change_to_preexisting_dirty_file(self):
        cwd = self.projects["backend"]
        source = cwd / "src.ts"
        source.write_text("export const before = true;\n", encoding="utf-8")
        self.activate()
        source.write_text("export const after = true;\n", encoding="utf-8")
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-dirty-overlap",
                "stop_hook_active": False,
                "last_assistant_message": "Done",
            },
            cwd,
        )
        self.assertEqual(output["decision"], "block")
        self.assertIn("coverage", output["reason"])

    def test_negative_gate_words_do_not_count_as_approval(self):
        cwd = self.projects["backend"]
        self.activate()
        source = cwd / "src" / "app.ts"
        source.parent.mkdir()
        source.write_text("export const value = 1;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/app.ts\n+x\n*** End Patch"},
                "tool_response": {"ok": True},
            },
            cwd,
        )
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "npm test -- --coverage"},
                "tool_response": {"exit_code": 0},
            },
            cwd,
        )
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-negative-gates",
                "stop_hook_active": False,
                "last_assistant_message": "Reviewer changes_requested; architecture failed; QA defects_found.",
            },
            cwd,
        )
        self.assertIn("architecture", output["reason"])
        self.assertIn("qa", output["reason"])
        self.assertIn("reviewer", output["reason"])

    def test_post_tool_tracks_change_and_stop_continues_once(self):
        cwd = self.projects["backend"]
        self.activate()
        source = cwd / "src" / "app.ts"
        source.parent.mkdir()
        source.write_text("export const value = 1;\n", encoding="utf-8")
        post = self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/app.ts\n+x\n*** End Patch"},
                "tool_response": {"ok": True},
            },
            cwd,
        )
        self.assertIn("Production code changed", post["hookSpecificOutput"]["additionalContext"])

        blocked = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-stop",
                "stop_hook_active": False,
                "last_assistant_message": "Implementation complete",
            },
            cwd,
        )
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("test", blocked["reason"])
        continued = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-stop",
                "stop_hook_active": True,
                "last_assistant_message": "Blocked checks are unavailable and documented",
            },
            cwd,
        )
        self.assertIsNone(continued)
        repeated_without_flag = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-stop",
                "stop_hook_active": False,
                "last_assistant_message": "Still blocked",
            },
            cwd,
        )
        self.assertIsNone(repeated_without_flag)

    def test_post_tool_does_not_persist_command_text(self):
        cwd = self.projects["backend"]
        self.activate()
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "INTERNAL_PASSWORD=supersecret npm test -- --coverage"},
                "tool_response": {"exit_code": 0},
            },
            cwd,
        )
        state_path = next((self.data / "hook-state").glob("*.json"))
        raw = state_path.read_text(encoding="utf-8")
        self.assertNotIn("supersecret", raw)
        state = json.loads(raw)
        self.assertEqual(state["commands"][-1]["runner"], "npm")
        self.assertIn("command_sha256", state["commands"][-1])

    def test_successful_checks_and_gate_ledger_allow_stop(self):
        cwd = self.projects["backend"]
        self.activate()
        source = cwd / "src" / "app.ts"
        source.parent.mkdir()
        source.write_text("export const value = 1;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/app.ts\n+x\n*** End Patch"},
                "tool_response": {"ok": True},
            },
            cwd,
        )
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "npm test -- --coverage"},
                "tool_response": {"exit_code": 0, "output": "passed"},
            },
            cwd,
        )
        self.record_agent(cwd, "architect", "proposed")
        self.record_agent(cwd, "test-maker", "baseline_ready")
        self.record_agent(cwd, "reviewer", "approved")
        self.record_agent(cwd, "architecture-guardian", "approved", "diff")
        self.record_agent(cwd, "qa", "pass")
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-success",
                "stop_hook_active": False,
                "last_assistant_message": "Reviewer approved; Architecture Guardian approved; QA pass.",
            },
            cwd,
        )
        self.assertIsNone(output)

    def test_write_after_review_invalidates_diff_gates(self):
        cwd = self.projects["backend"]
        self.activate()
        source = cwd / "src" / "app.ts"
        source.parent.mkdir()
        source.write_text("export const value = 1;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/app.ts\n+x\n*** End Patch"},
                "tool_response": {"ok": True},
            },
            cwd,
        )
        self.record_agent(cwd, "architect", "proposed")
        self.record_agent(cwd, "test-maker", "baseline_ready")
        self.record_agent(cwd, "reviewer", "approved")
        self.record_agent(cwd, "architecture-guardian", "approved", "diff")
        self.record_agent(cwd, "qa", "pass")
        source.write_text("export const value = 2;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "npm test -- --coverage"},
                "tool_response": {"exit_code": 0},
            },
            cwd,
        )
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-stale-review",
                "stop_hook_active": False,
                "last_assistant_message": "Implementation complete",
            },
            cwd,
        )
        self.assertIn("architecture", output["reason"])
        self.assertIn("qa", output["reason"])
        self.assertIn("reviewer", output["reason"])

    def test_public_front_lib_change_requires_consumer_evidence(self):
        cwd = self.projects["wget-cloud-front-lib"]
        self.activate("wget-cloud-front-lib")
        source = cwd / "src" / "site-blocks" / "index.ts"
        source.parent.mkdir(parents=True)
        source.write_text("export const block = true;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Add File: src/site-blocks/index.ts\n+x\n*** End Patch"
                },
                "tool_response": {"ok": True},
            },
            cwd,
        )
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-front-lib",
                "stop_hook_active": False,
                "last_assistant_message": "Reviewer approved; Architecture Guardian approved; QA pass.",
            },
            cwd,
        )
        self.assertIn("consumer", output["reason"])

    def test_session_end_archives_without_output(self):
        self.activate("frontend")
        output = self.call(
            "session-end",
            {"hook_event_name": "SessionEnd", "reason": "other"},
            self.projects["frontend"],
        )
        self.assertIsNone(output)
        states = list((self.data / "hook-state").glob("*.json"))
        self.assertEqual(len(states), 1)
        state = json.loads(states[0].read_text(encoding="utf-8"))
        self.assertFalse(state["active"])
        self.assertIn("ended_at", state)


if __name__ == "__main__":
    unittest.main()
