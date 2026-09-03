import importlib.util
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "wgc_hooks.py"
HOOKS_JSON = SCRIPT.parent / "hooks.json"
PLUGIN_JSON = SCRIPT.parent.parent / ".codex-plugin" / "plugin.json"
ADAPTIVE_POLICY_FIXTURE = SCRIPT.parent / "tests" / "fixtures" / "adaptive_test_policy_cases.json"
WORKDIR_ABSENT = object()

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

    def test_all_handlers_are_synchronous(self):
        config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        for event, groups in config.items():
            for group in groups:
                for handler in group["hooks"]:
                    self.assertNotIn("async", handler, f"{event} hook must run synchronously")

    def test_manifest_uses_plain_semver_without_build_metadata(self):
        manifest = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
        plain_semver = re.compile(
            r"^(0|[1-9]\d*)\."
            r"(0|[1-9]\d*)\."
            r"(0|[1-9]\d*)"
            r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
            r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?$"
        )
        version = manifest["version"]
        self.assertEqual(version, "6.1.0")
        self.assertNotIn("+", version, "plugin version must not contain build metadata")
        self.assertIsNotNone(plain_semver.fullmatch(version), f"invalid plain SemVer: {version}")

    def test_profile_contracts_match_separate_role_files(self):
        spec = importlib.util.spec_from_file_location("wgc_hooks_contracts", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        skills = SCRIPT.parent.parent / "skills"
        for profile, role_verdicts in module.PROFILE_ROLE_VERDICTS.items():
            role_dir = skills / f"wgc-{profile}" / "references" / "agents"
            documented = {path.stem for path in role_dir.glob("*.md") if path.name != "index.md"}
            self.assertEqual(documented, set(role_verdicts) | {"orchestrator"})
            for role, verdicts in role_verdicts.items():
                text = (role_dir / f"{role}.md").read_text(encoding="utf-8")
                for verdict in verdicts:
                    self.assertIn(verdict, text, f"{profile}/{role} does not document {verdict}")


class WgcHooksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "wgetcloud"
        self.root.mkdir()
        self.data = Path(self.temp.name) / "plugin-data"
        self.codex_home = Path(self.temp.name) / "codex-home"
        self.codex_home.mkdir()
        (self.codex_home / "config.toml").write_text(
            'service_tier = "default"\n\n[features]\nfast_mode = false\n',
            encoding="utf-8",
        )
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

    def raw_call(self, action, payload, cwd=None):
        payload = {"session_id": "session-test", "cwd": str(cwd or self.root), **payload}
        env = dict(os.environ)
        env["PLUGIN_DATA"] = str(self.data)
        env["CODEX_HOME"] = str(self.codex_home)
        return subprocess.run(
            [sys.executable, str(SCRIPT), action],
            input=json.dumps(payload),
            cwd=str(cwd or self.root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def call(self, action, payload, cwd=None):
        result = self.raw_call(action, payload, cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def test_fast_and_unverifiable_service_tiers_refuse_skill_activation(self):
        prompt = {"hook_event_name": "UserPromptSubmit", "turn_id": "tier-test", "prompt": "$wgc-implementation do it"}
        for tier in ("fast", "priority", "ultrafast"):
            with self.subTest(tier=tier):
                result = self.raw_call("prompt-submit", {**prompt, "service_tier": tier})
                self.assertEqual(2, result.returncode)
                self.assertIn("WGC_FAST_MODE_FORBIDDEN", result.stderr)

        for config in (
            '[features]\nfast_mode = false\n',
            'service_tier = "auto"\n\n[features]\nfast_mode = false\n',
            'service_tier = "default"\n',
            'not valid toml',
        ):
            with self.subTest(config=config):
                (self.codex_home / "config.toml").write_text(config, encoding="utf-8")
                result = self.raw_call("prompt-submit", prompt)
                self.assertEqual(2, result.returncode)
                self.assertIn("WGC_SERVICE_TIER_UNVERIFIABLE", result.stderr)
        (self.codex_home / "config.toml").write_text(
            'service_tier = "default"\n\n[features]\nfast_mode = false\n', encoding="utf-8"
        )

    def _bootstrap_fixture(self):
        k8s = self.projects["k8s"]
        argocd = k8s / "infrastructure" / "k8s" / "bootstrap" / "argocd"
        roots = k8s / "infrastructure" / "k8s" / "bootstrap" / "roots"
        argocd.mkdir(parents=True)
        roots.mkdir(parents=True)
        (argocd / "makefile").write_text(
            """NAMESPACE ?= argocd
RELEASE ?= argo-cd
CHART ?= argo/argo-cd
CHART_VERSION ?= 8.0.0
VALUES ?= values.yaml
WAIT ?= true
TIMEOUT ?= 10m
""",
            encoding="utf-8",
        )
        (argocd / "values.yaml").write_text("crds:\n  install: true\n", encoding="utf-8")
        root = roots / "clean-bootstrap.yaml"
        root.write_text(
            """apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: clean-bootstrap-cluster
  namespace: argocd
  labels:
    wget-cloud.io/profile: clean-bootstrap
spec:
  project: default
  source:
    repoURL: ssh://git@github.com/wget-cloud/k8s
    targetRevision: clean-bootstrap-2026-08-15.1
    path: infrastructure/k8s/gitops/clusters/clean-bootstrap/root
  destination:
    namespace: argocd
    server: https://kubernetes.default.svc
  syncPolicy:
    syncOptions: [CreateNamespace=true]
""",
            encoding="utf-8",
        )
        self._git_commit(
            k8s,
            [
                "infrastructure/k8s/bootstrap/argocd/makefile",
                "infrastructure/k8s/bootstrap/argocd/values.yaml",
                "infrastructure/k8s/bootstrap/roots/clean-bootstrap.yaml",
            ],
        )
        self._run(["git", "tag", "clean-bootstrap-2026-08-15.1"], k8s)

        kubeconfig = Path(self.temp.name) / "clean-bootstrap.kubeconfig"
        kubeconfig.write_text(
            """apiVersion: v1
kind: Config
current-context: clean-bootstrap
contexts:
- name: clean-bootstrap
  context:
    cluster: clean-bootstrap
    user: bootstrap
""",
            encoding="utf-8",
        )
        key = Path(self.temp.name) / "wget-cloud-k8s-repository.key"
        key.write_text("synthetic-test-key-file\n", encoding="utf-8")
        return {
            "k8s": k8s,
            "kubeconfig": kubeconfig,
            "key": key,
            "root": root,
            "makefile": argocd / "makefile",
            "values_file": argocd / "values.yaml",
            "values": "infrastructure/k8s/bootstrap/argocd/values.yaml",
            "root_path": "infrastructure/k8s/bootstrap/roots/clean-bootstrap.yaml",
        }

    def _bootstrap_command(self, command, cwd=None):
        return self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
            cwd or self.projects["k8s"],
        )

    def _bootstrap_command_with_workdir(self, command, payload_cwd, workdir=WORKDIR_ABSENT):
        tool_input = {"command": command}
        if workdir is not WORKDIR_ABSENT:
            tool_input["workdir"] = workdir
        return self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": tool_input,
            },
            payload_cwd,
        )

    def _assert_bootstrap_denied(self, command, cwd=None):
        output = self._bootstrap_command(command, cwd)
        self.assertIsNotNone(output, f"unsafe bootstrap command was allowed: {command}")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def _approved_helm_bootstrap(self, fixture):
        return (
            f"WGC_GITOPS_BOOTSTRAP_APPROVED=1 helm --kubeconfig {fixture['kubeconfig']} "
            "--kube-context clean-bootstrap upgrade --install argo-cd argo/argo-cd "
            f"--namespace argocd --create-namespace --values {fixture['values_file']} "
            "--wait --timeout 10m --version 8.0.0"
        )

    def _relative_helm_bootstrap(self, fixture):
        return self._approved_helm_bootstrap(fixture).replace(
            str(fixture["values_file"]),
            fixture["values"],
            1,
        )

    def _approved_repository_bootstrap(self, fixture):
        common = f"--kubeconfig {fixture['kubeconfig']} --context clean-bootstrap"
        return (
            f"WGC_GITOPS_BOOTSTRAP_APPROVED=1 kubectl {common} --namespace argocd create secret generic "
            "wget-cloud-k8s-repository --from-literal=type=git "
            "--from-literal=url=ssh://git@github.com/wget-cloud/k8s "
            f"--from-file=sshPrivateKey={fixture['key']} --dry-run=client --output=yaml | "
            f"kubectl {common} --namespace argocd label --local --filename=- "
            "argocd.argoproj.io/secret-type=repository --output=yaml | "
            f"kubectl {common} --namespace argocd apply --filename=-"
        )

    def _approved_root_bootstrap(self, fixture):
        return (
            f"WGC_GITOPS_BOOTSTRAP_APPROVED=1 kubectl --kubeconfig {fixture['kubeconfig']} "
            f"--context clean-bootstrap --namespace argocd apply --filename={fixture['root']}"
        )

    def _relative_root_bootstrap(self, fixture):
        return self._approved_root_bootstrap(fixture).replace(
            str(fixture["root"]),
            fixture["root_path"],
            1,
        )

    def _tag_bootstrap_root(self, fixture, content, tag):
        fixture["root"].write_text(content, encoding="utf-8")
        self._git_commit(fixture["k8s"], [fixture["root_path"]])
        self._run(["git", "tag", tag], fixture["k8s"])

    def activate(self, project="backend"):
        cwd = self.projects[project]
        return self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": "turn-1", "prompt": "Use $wgc-implementation to fix it"},
            cwd,
        )

    def activate_bugfix(self, project="backend", prompt="Исправь баг: расчёт суммы возвращает неверное значение"):
        cwd = self.projects[project]
        return self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": "turn-bugfix", "prompt": prompt},
            cwd,
        )

    def activate_profile(self, profile, project="backend", prompt=None):
        cwd = self.projects[project]
        prompt = prompt or f"Use $wgc-{profile} for this request"
        return self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "turn_id": f"turn-{profile}", "prompt": prompt},
            cwd,
        )

    def record_agent(self, cwd, role, verdict, phase="", auto_defaults=True, **extra):
        if role == "test-maker" and verdict == "assessment_ready" and auto_defaults and "assessment" not in extra:
            test_file = cwd / "tests" / "app.test.ts"
            test_file.parent.mkdir(exist_ok=True)
            test_file.write_text("it('app', () => {});\n", encoding="utf-8")
            self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: tests/app.test.ts\n+x\n*** End Patch"}, "tool_response": {"ok": True}}, cwd)
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
        marker_value = {"role": role, "verdict": verdict, "phase": phase, "input_revision": revision, **extra}
        if auto_defaults and role == "architect" and verdict in {"proposed", "planned"}:
            marker_value.setdefault("plan_revision", "test-plan-r1")
            marker_value.setdefault("minimum_test_criticality", "low")
            marker_value.setdefault("acceptance_revision", "test-ac-r1")
        if auto_defaults and role == "reproducer" and verdict in {"reproduced", "characterized"}:
            marker_value.setdefault("acceptance_revision", "test-ac-r1")
        state = self.adaptive_state()
        if auto_defaults and state.get("profile") == "epic-implementation" and role == "architecture-guardian" and phase == "plan":
            marker_value.setdefault("item_id", "EPIC-1")
            marker_value.setdefault("item_revision", "a" * 64)
        if auto_defaults and role == "architecture-guardian" and verdict == "approved" and phase == "plan":
            item_id = marker_value.get("item_id")
            item_revision = marker_value.get("item_revision")
            matched = next((item for item in state.get("selected_items", []) if isinstance(item, dict) and item.get("item_id") == item_id and item.get("item_revision") == item_revision), None)
            marker_value.setdefault("plan_revision", (matched or state).get("plan_revision", "test-plan-r1"))
        if auto_defaults and state.get("profile") == "epic-implementation":
            if role == "project-manager" and verdict == "planned" and phase == "scope":
                marker_value.setdefault("selected_items", [{"item_id": "EPIC-1", "item_revision": "a" * 64, "plan_revision": "test-plan-r1", "acceptance_revision": "test-ac-r1", "minimum_test_criticality": "low"}])
            if role in {"test-maker", "implementor", "reviewer", "qa"} or (role == "architecture-guardian" and phase == "diff") or (role == "product-manager" and phase == "outcome"):
                marker_value.setdefault("item_id", "EPIC-1")
                marker_value.setdefault("item_revision", "a" * 64)
        if role == "test-maker" and verdict == "assessment_ready" and "assessment" not in marker_value:
            test_file = cwd / "tests" / "app.test.ts"
            test_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()
            marker_value.update(
                {
                    "plan_revision": "test-plan-r1",
                    "acceptance_revision": "test-ac-r1",
                    "test_criticality": "standard",
                    "test_disposition": "add",
                    "scope_fingerprint": "test-scope-r1",
                    "assessed_paths": ["src/app.ts"],
                    "tested_invariants": ["app behavior remains observable"],
                    "existing_tests": ["no_relevant_tests"],
                    "coverage_mode": "targeted",
                    "residual_risks": ["integration regression"],
                    "test_plan": {"action": "add", "tests": ["tests/app.test.ts"], "protected_hashes": {"tests/app.test.ts": test_hash}, "commands": ["npm test -- tests/app.test.ts"], "expected_baseline": "red", "actual_baseline": "red"},
                }
            )
        marker = json.dumps(marker_value, separators=(",", ":"))
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

    def record_test_assessment(self, cwd, assessment, verdict="assessment_ready", prepare=True, complete=True):
        assessment = dict(assessment)
        if complete:
            assessment.setdefault("assessed_paths", ["src/app.ts"])
            assessment.setdefault("tested_invariants", ["observable invariant"])
            assessment.setdefault("existing_tests", ["no_relevant_tests"])
            assessment.setdefault("coverage_mode", "targeted")
            assessment.setdefault("residual_risks", ["integration risk"])
            if assessment.get("test_disposition") in {"add", "update"}:
                assessment.setdefault("test_plan", {"action": assessment["test_disposition"], "tests": ["tests/app.test.ts"], "protected_hashes": {"tests/app.test.ts": "0" * 64}, "commands": ["npm test -- tests/app.test.ts"], "expected_baseline": "red", "actual_baseline": "red"})
        if prepare and self.adaptive_state().get("profile") != "epic-implementation":
            state = self.adaptive_state()
            if not state.get("plan_revision") or not state.get("acceptance_revision"):
                self.record_agent(cwd, "architect", "proposed", plan_revision=assessment.get("plan_revision", "test-plan-r1"), acceptance_revision=assessment.get("acceptance_revision", "test-ac-r1"), minimum_test_criticality=assessment.get("test_criticality", "low"))
        self.agent_counter += 1
        agent_id = f"assessment-agent-{self.agent_counter}"
        started = self.call(
            "subagent-start",
            {
                "hook_event_name": "SubagentStart",
                "turn_id": "turn-assessment",
                "agent_id": agent_id,
                "agent_type": "test-maker",
            },
            cwd,
        )
        revision = re.search(
            r"revision is ([0-9a-f]{64})",
            started["hookSpecificOutput"]["additionalContext"],
        ).group(1)
        marker = {
            "role": "test-maker",
            "verdict": verdict,
            "phase": "",
            "input_revision": revision,
            **assessment,
        }
        return self.call(
            "subagent-stop",
            {
                "hook_event_name": "SubagentStop",
                "turn_id": "turn-assessment",
                "agent_id": agent_id,
                "agent_type": "test-maker",
                "stop_hook_active": False,
                "last_assistant_message": "WGC_AGENT_RESULT: " + json.dumps(marker, separators=(",", ":")),
            },
            cwd,
        )

    def record_epic_agent(self, cwd, role, verdict, phase="", item_id="EPIC-1", item_revision=None, **extra):
        return self.record_agent(
            cwd,
            role,
            verdict,
            phase,
            item_id=item_id,
            item_revision=item_revision or "a" * 64,
            **extra,
        )

    def freeze_epic_items(self, cwd, items=None):
        return self.record_agent(
            cwd,
            "project-manager",
            "planned",
            "scope",
            selected_items=items or [{"item_id": "EPIC-1", "item_revision": "a" * 64}],
        )

    def adaptive_state(self):
        state_path = next((self.data / "hook-state").glob("*.json"))
        return json.loads(state_path.read_text(encoding="utf-8"))

    def test_adaptive_policy_fixture_covers_twenty_sanitized_cases(self):
        cases = json.loads(ADAPTIVE_POLICY_FIXTURE.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 20)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        required = {"css-token-5px", "tsx-cosmetic-5px", "a11y-focus-order", "critical-none-invalid", "state-v2-legacy", "malformed-assessment", "epic-mixed-ledger"}
        self.assertTrue(required.issubset({case["id"] for case in cases}))
        self.assertEqual(
            {case["test_disposition"] for case in cases},
            {"add", "update", "reuse", "none"},
        )
        reuse = next(case for case in cases if case["id"] == "reuse-proof")["reuse_proof"]
        self.assertEqual(reuse["file_sha256"], hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

    def test_state_v3_requires_empty_adaptive_assessment_ledger(self):
        self.activate()
        state = self.adaptive_state()
        self.assertEqual(state["version"], 3)
        self.assertEqual(state["test_assessments"], [])
        self.assertEqual(state["selected_items"], [])

    def test_v2_migration_preserves_verification_and_resets_legacy_downstream_gates(self):
        cwd = self.projects["backend"]
        self.activate()
        path = next((self.data / "hook-state").glob("*.json"))
        path.write_text(json.dumps({"version": 2, "active": True, "verification": {"test": {"at": 1}, "coverage": {"at": 1}, "typecheck": {"at": 1}}, "subagent_results": [{"role": "architect", "verdict": "proposed", "phase": ""}, {"role": "test-maker", "verdict": "baseline_ready", "phase": ""}, {"role": "qa", "verdict": "pass", "phase": ""}]}), encoding="utf-8")
        self.call("session-start", {"hook_event_name": "SessionStart", "source": "resume"}, cwd)
        state = self.adaptive_state()
        self.assertEqual(state["version"], 3)
        self.assertNotIn("test", state["verification"])
        self.assertNotIn("coverage", state["verification"])
        self.assertIn("typecheck", state["verification"])
        self.assertEqual([result["role"] for result in state["subagent_results"]], ["architect"])
        self.assertEqual(state["test_assessments"], [])

    def test_malformed_state_blocks_completion_fail_closed(self):
        cwd = self.projects["backend"]
        self.activate()
        path = next((self.data / "hook-state").glob("*.json"))
        path.write_text("{broken", encoding="utf-8")
        blocked = self.call("stop", {"hook_event_name": "Stop", "turn_id": "malformed", "stop_hook_active": False, "last_assistant_message": "done"}, cwd)
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("malformed", blocked["reason"])

    def test_every_disposition_requires_bounded_assessment_evidence_and_allowlisted_shape(self):
        cwd = self.projects["backend"]
        self.activate()
        for disposition in ("add", "update", "reuse", "none"):
            assessment = {"plan_revision": "plan-r1", "acceptance_revision": "accept-r1", "test_criticality": "low", "test_disposition": disposition, "scope_fingerprint": "scope-r1"}
            blocked = self.record_test_assessment(cwd, assessment)
            self.assertIsNotNone(blocked, f"{disposition} must require assessment evidence")
            self.assertEqual(blocked["decision"], "block")
        raw_blob = {"plan_revision": "plan-r1", "acceptance_revision": "accept-r1", "test_criticality": "low", "test_disposition": "add", "scope_fingerprint": "scope-r1", "assessed_paths": ["src/a.ts"], "tested_invariants": ["invariant"], "existing_tests": ["no_relevant_tests"], "coverage_mode": "targeted", "residual_risks": ["risk"], "untrusted_raw_blob": {"prompt": "must not persist"}}
        blocked = self.record_test_assessment(cwd, raw_blob)
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("unknown", blocked["reason"].lower())

    def test_execution_plan_and_acceptance_revisions_are_required_before_assessment(self):
        cwd = self.projects["backend"]
        self.activate()
        architect = self.record_agent(cwd, "architect", "proposed", auto_defaults=False)
        self.assertIsNotNone(architect, "execution architect marker must include plan revision and criticality floor")
        self.assertEqual(architect["decision"], "block")
        self.assertIn("plan_revision", architect["reason"])
        assessment = {"plan_revision": "plan-r1", "acceptance_revision": "accept-r1", "test_criticality": "standard", "test_disposition": "add", "scope_fingerprint": "scope-r1"}
        blocked = self.record_test_assessment(cwd, assessment, prepare=False)
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("plan", blocked["reason"].lower())

    def test_v2_migration_clears_test_and_coverage_verification_and_epic_capacity_is_bounded(self):
        cwd = self.projects["backend"]
        self.activate()
        path = next((self.data / "hook-state").glob("*.json"))
        path.write_text(json.dumps({"version": 2, "active": True, "verification": {"test": {"at": 1}, "coverage": {"at": 1}, "typecheck": {"at": 1}}}), encoding="utf-8")
        self.call("session-start", {"hook_event_name": "SessionStart", "source": "resume"}, cwd)
        verification = self.adaptive_state()["verification"]
        self.assertNotIn("test", verification)
        self.assertNotIn("coverage", verification)
        self.assertIn("typecheck", verification)

    def test_unknown_or_unbounded_assessment_data_is_rejected_and_never_persisted(self):
        cwd = self.projects["backend"]
        self.activate()
        assessment = {"plan_revision": "plan-r1", "acceptance_revision": "accept-r1", "test_criticality": "low", "test_disposition": "add", "scope_fingerprint": "scope-r1", "assessed_paths": ["src/a.ts"] * 201, "tested_invariants": ["i"], "existing_tests": ["no_relevant_tests"], "coverage_mode": "targeted", "residual_risks": ["r"], "test_plan": {"action": "add", "tests": ["a.test.ts"], "protected_hashes": {"a.test.ts": "0" * 64}}, "nested_raw": {"secret": "never-persist"}}
        blocked = self.record_test_assessment(cwd, assessment)
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked["decision"], "block")
        self.assertNotIn("never-persist", json.dumps(self.adaptive_state()))

    def test_none_preserves_frontend_and_site_repository_test_gates(self):
        for project, expected in (("frontend", {"test", "typecheck"}), ("wget-cloud-site", {"test", "typecheck", "lint", "build"})):
            cwd = self.projects[project]
            self.activate(project)
            source = cwd / "src" / "card.tsx"
            source.parent.mkdir(exist_ok=True)
            source.write_text("export const Card = () => null;\n", encoding="utf-8")
            self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: src/card.tsx\n+x\n*** End Patch"}, "tool_response": {"ok": True}}, cwd)
            assessment = {"plan_revision": "plan-r1", "acceptance_revision": "accept-r1", "test_criticality": "low", "test_disposition": "none", "scope_fingerprint": "scope-r1", "assessed_paths": ["src/card.tsx"], "tested_invariants": ["visual spacing"], "existing_tests": ["no_relevant_tests"], "coverage_mode": "none", "residual_risks": ["visual drift"], "alternative_evidence": ["screenshot"], "rationale": "cosmetic"}
            self.assertIsNone(self.record_test_assessment(cwd, assessment))
            self.assertTrue(expected.issubset(set(self.adaptive_state()["repository_gates"])))

    def test_epic_item_scoped_assessments_preserve_sibling_and_reject_stale_revision(self):
        cwd = self.projects["backend"]
        self.activate_profile("epic-implementation")
        items = [
            {"item_id": "A", "item_revision": "a" * 64, "plan_revision": "p-a", "acceptance_revision": "ac-a", "minimum_test_criticality": "critical"},
            {"item_id": "B", "item_revision": "b" * 64, "plan_revision": "p-b", "acceptance_revision": "ac-b", "minimum_test_criticality": "standard"},
        ]
        self.assertIsNone(self.freeze_epic_items(cwd, items))
        prepared = []
        for item, path in zip(items, ("src/a.ts", "src/b.ts")):
            test_path = f"tests/{item['item_id'].lower()}.test.ts"
            test_file = cwd / test_path; test_file.parent.mkdir(exist_ok=True); test_file.write_text(f"it('{item['item_id']}', () => {{}});\n", encoding="utf-8")
            test_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()
            self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": {"command": f"*** Begin Patch\n*** Add File: {test_path}\n+x\n*** End Patch"}, "tool_response": {"ok": True}}, cwd)
            prepared.append((item, path, test_path, test_hash))
        for item, path, test_path, test_hash in prepared:
            assessment = {"plan_revision": item["plan_revision"], "acceptance_revision": item["acceptance_revision"], "test_criticality": item["minimum_test_criticality"], "test_disposition": "add", "scope_fingerprint": path, "item_id": item["item_id"], "item_revision": item["item_revision"], "assessed_paths": [path], "tested_invariants": [item["item_id"]], "existing_tests": ["no_relevant_tests"], "coverage_mode": "targeted", "residual_risks": ["risk"], "test_plan": {"action": "add", "tests": [test_path], "protected_hashes": {test_path: test_hash}, "commands": [f"npm test -- {test_path}"], "expected_baseline": "red", "actual_baseline": "red"}}
            self.assertIsNone(self.record_test_assessment(cwd, assessment))
        (cwd / "src").mkdir(exist_ok=True)
        (cwd / "src" / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
        self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: src/a.ts\n+x\n*** End Patch"}, "tool_response": {"ok": True}}, cwd)
        remaining = self.adaptive_state()["test_assessments"]
        self.assertEqual([value["item_id"] for value in remaining], ["A", "B"])
        stale = {**next(value for value in remaining if value["item_id"] == "A"), "item_revision": "z" * 64}
        self.assertEqual(self.record_test_assessment(cwd, stale)["decision"], "block")

    def test_epic_assessment_capacity_fails_closed_without_eviction(self):
        cwd = self.projects["backend"]
        self.activate_profile("epic-implementation")
        state = self.adaptive_state()
        capacity = 100
        items = [{"item_id": f"I{i}", "item_revision": f"{i:064x}", "plan_revision": "p", "acceptance_revision": "ac", "minimum_test_criticality": "critical" if i == 0 else "low"} for i in range(capacity)]
        self.assertIsNone(self.freeze_epic_items(cwd, items))
        state = self.adaptive_state(); state["test_assessments"] = [{"item_id": item["item_id"], "item_revision": item["item_revision"], "test_criticality": item["minimum_test_criticality"]} for item in items]; path = next((self.data / "hook-state").glob("*.json")); path.write_text(json.dumps(state), encoding="utf-8")
        oversized = items + [{"item_id": "I100", "item_revision": "f" * 64, "plan_revision": "p", "acceptance_revision": "ac", "minimum_test_criticality": "low"}]
        blocked = self.record_agent(cwd, "project-manager", "planned", "scope", auto_defaults=False, selected_items=oversized)
        self.assertEqual(blocked["decision"], "block")
        self.assertRegex(blocked["reason"], r"(?i)(100|bound|capacity)")
        self.assertEqual(self.adaptive_state()["test_assessments"][0]["item_id"], "I0")

    def test_malformed_reactivation_resets_snapshots_and_untrusted_gates(self):
        cwd = self.projects["backend"]
        self.activate(); path = next((self.data / "hook-state").glob("*.json"))
        state = self.adaptive_state(); state.update({"baseline_dirty": {"bad": {"x": "1"}}, "current_dirty": {"bad": {"x": "2"}}, "verification": {"test": {"at": 1}, "coverage": {"at": 1}}, "subagent_results": [{"role": "reviewer"}, {"role": "qa"}], "test_assessments": [{"item_id": "bad"}]}); path.write_text(json.dumps(state), encoding="utf-8")
        path.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.call("stop", {"hook_event_name": "Stop", "turn_id": "bad", "stop_hook_active": False}, cwd)["decision"], "block")
        self.activate()
        state = self.adaptive_state()
        self.assertEqual(state["state_health"], "healthy")
        self.assertEqual(state["test_assessments"], [])
        self.assertEqual(state["subagent_results"], [])
        self.assertNotEqual(state["baseline_dirty"], {"bad": {"x": "1"}})
        self.assertNotIn("test", state["verification"])
        self.assertNotIn("coverage", state["verification"])

    def test_same_plan_floor_downgrade_requires_new_plan_and_guardian_reapproval(self):
        cwd = self.projects["backend"]
        self.activate()
        self.assertIsNone(self.record_agent(cwd, "architect", "proposed", plan_revision="p1", minimum_test_criticality="critical", acceptance_revision="ac1"))
        self.record_agent(cwd, "architect", "planned")
        self.record_agent(cwd, "architecture-guardian", "approved", "plan")
        lowered = self.record_agent(cwd, "architect", "proposed", plan_revision="p1", minimum_test_criticality="low", acceptance_revision="ac1")
        self.assertIsNotNone(lowered, "same-plan criticality downgrade must fail closed")
        self.assertEqual(lowered["decision"], "block")
        self.assertIn("criticality", lowered["reason"].lower())
        self.assertIsNone(self.record_agent(cwd, "architect", "proposed", plan_revision="p2", minimum_test_criticality="low", acceptance_revision="ac2"))
        p2_test = cwd / "tests" / "p2.test.ts"; p2_test.parent.mkdir(exist_ok=True); p2_test.write_text("it('p2', () => {});\n", encoding="utf-8")
        p2_hash = hashlib.sha256(p2_test.read_bytes()).hexdigest()
        assessment = {"plan_revision": "p2", "acceptance_revision": "ac2", "test_criticality": "low", "test_disposition": "add", "scope_fingerprint": "p2", "assessed_paths": ["src/p2.ts"], "tested_invariants": ["p2"], "existing_tests": ["no_relevant_tests"], "coverage_mode": "targeted", "residual_risks": ["r"], "alternative_evidence": ["focused review"], "test_plan": {"action": "add", "tests": ["tests/p2.test.ts"], "protected_hashes": {"tests/p2.test.ts": p2_hash}, "commands": ["npm test -- tests/p2.test.ts"], "expected_baseline": "red", "actual_baseline": "red"}}
        self.assertIsNotNone(self.record_test_assessment(cwd, assessment), "new plan requires new guardian plan approval")
        self.assertIsNone(self.record_agent(cwd, "architecture-guardian", "approved", "plan"))
        self.assertIsNone(self.record_test_assessment(cwd, assessment))

    def test_guardian_plan_marker_must_match_current_plan_revision(self):
        cwd = self.projects["backend"]; self.activate()
        self.assertIsNone(self.record_agent(cwd, "architect", "proposed", plan_revision="p1", minimum_test_criticality="standard", acceptance_revision="ac1"))
        missing = self.record_agent(cwd, "architecture-guardian", "approved", "plan", auto_defaults=False)
        self.assertIsNotNone(missing)
        self.assertIsNone(self.record_agent(cwd, "architect", "proposed", plan_revision="p2", minimum_test_criticality="standard", acceptance_revision="ac2"))
        stale = self.record_agent(cwd, "architecture-guardian", "approved", "plan", plan_revision="p1")
        self.assertIsNotNone(stale, "stale guardian p1 must not approve current p2 plan")
        self.assertIsNone(self.record_agent(cwd, "architecture-guardian", "approved", "plan", plan_revision="p2"))

    def test_epic_guardian_plan_marker_binds_item_revision_and_current_plan(self):
        cwd = self.projects["backend"]; self.activate_profile("epic-implementation")
        item = {"item_id": "I1", "item_revision": "e" * 64, "plan_revision": "p1", "acceptance_revision": "ac", "minimum_test_criticality": "standard"}
        self.assertIsNone(self.freeze_epic_items(cwd, [item]))
        self.assertIsNone(self.record_agent(cwd, "architect", "proposed", item_id="I1", item_revision=item["item_revision"], plan_revision="p2", minimum_test_criticality="standard", acceptance_revision="ac"))
        missing = self.record_agent(cwd, "architecture-guardian", "approved", "plan", item_id="I1", item_revision=item["item_revision"], auto_defaults=False)
        self.assertIsNotNone(missing)
        stale = self.record_agent(cwd, "architecture-guardian", "approved", "plan", item_id="I1", item_revision=item["item_revision"], plan_revision="p1")
        self.assertIsNotNone(stale)
        self.assertIsNone(self.record_agent(cwd, "architecture-guardian", "approved", "plan", item_id="I1", item_revision=item["item_revision"], plan_revision="p2"))

    def test_result_ledger_accepts_exact_capacity_without_eviction(self):
        cwd = self.projects["backend"]
        self.activate()
        state = self.adaptive_state()
        state["subagent_results"] = [
            {"role": "explorer", "verdict": "mapped", "phase": "", "input_revision": f"seed-{index:04d}"}
            for index in range(999)
        ]
        path = next((self.data / "hook-state").glob("*.json"))
        path.write_text(json.dumps(state), encoding="utf-8")

        self.assertIsNone(self.record_agent(cwd, "explorer", "mapped", auto_defaults=False))
        results = self.adaptive_state()["subagent_results"]
        self.assertEqual(len(results), 1000)
        self.assertEqual(results[0]["input_revision"], "seed-0000")
        self.assertEqual(results[998]["input_revision"], "seed-0998")

    def test_result_ledger_rejects_1001st_unique_without_eviction(self):
        cwd = self.projects["backend"]
        self.activate()
        seeded = [
            {"role": "explorer", "verdict": "mapped", "phase": "", "input_revision": f"seed-{index:04d}"}
            for index in range(1000)
        ]
        state = self.adaptive_state()
        state["subagent_results"] = seeded
        path = next((self.data / "hook-state").glob("*.json"))
        path.write_text(json.dumps(state), encoding="utf-8")

        blocked = self.record_agent(cwd, "reviewer", "approved", auto_defaults=False)
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("bounded capacity of 1000", blocked["reason"])
        self.assertEqual(self.adaptive_state()["subagent_results"], seeded)

    def test_result_ledger_retry_at_capacity_replaces_in_place(self):
        cwd = self.projects["backend"]
        self.activate()
        state = self.adaptive_state()
        state["subagent_results"] = [
            {"role": "explorer", "verdict": "mapped", "phase": "", "input_revision": f"seed-{index:04d}"}
            for index in range(999)
        ]
        path = next((self.data / "hook-state").glob("*.json"))
        path.write_text(json.dumps(state), encoding="utf-8")
        self.assertIsNone(self.record_agent(cwd, "explorer", "mapped", auto_defaults=False))
        first_results = self.adaptive_state()["subagent_results"]
        first_record = first_results[-1]
        self.assertEqual(len(first_results), 1000)

        self.assertIsNone(self.record_agent(cwd, "explorer", "mapped", auto_defaults=False))
        retried_results = self.adaptive_state()["subagent_results"]
        self.assertEqual(len(retried_results), 1000)
        self.assertEqual(retried_results[0]["input_revision"], "seed-0000")
        self.assertEqual(retried_results[-1]["input_revision"], first_record["input_revision"])
        self.assertNotEqual(retried_results[-1]["agent_id"], first_record["agent_id"])

    def test_add_update_test_plan_requires_real_matching_file_hash_and_evidence(self):
        cwd = self.projects["backend"]
        self.activate()
        base = {"plan_revision": "p", "acceptance_revision": "ac", "test_criticality": "standard", "test_disposition": "add", "scope_fingerprint": "s", "assessed_paths": ["src/a.ts"], "tested_invariants": ["a"], "existing_tests": ["no_relevant_tests"], "coverage_mode": "targeted", "residual_risks": ["r"]}
        fake = {**base, "test_plan": {"action": "add", "tests": ["tests/a.test.ts"], "protected_hashes": {"tests/a.test.ts": "0" * 64}, "commands": ["npm test -- tests/a.test.ts"], "expected_baseline": "red", "actual_baseline": "red"}}
        blocked = self.record_test_assessment(cwd, fake)
        self.assertIsNotNone(blocked, "fake protected hash must fail closed")
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("hash", blocked["reason"].lower())
        test_file = cwd / "tests" / "a.test.ts"; test_file.parent.mkdir(); test_file.write_text("it('a', () => {});\n", encoding="utf-8")
        digest = hashlib.sha256(test_file.read_bytes()).hexdigest()
        valid = {**base, "test_plan": {"action": "add", "tests": ["tests/a.test.ts"], "protected_hashes": {"tests/a.test.ts": digest}, "commands": ["npm test -- tests/a.test.ts"], "expected_baseline": "red", "actual_baseline": "red"}}
        self.assertIsNone(self.record_test_assessment(cwd, valid))

    def test_epic_same_plan_floor_downgrade_requires_new_plan_guardian_approval(self):
        cwd = self.projects["backend"]; self.activate_profile("epic-implementation")
        item = {"item_id": "E1", "item_revision": "e" * 64, "plan_revision": "p1", "acceptance_revision": "ac1", "minimum_test_criticality": "critical"}
        self.assertIsNone(self.freeze_epic_items(cwd, [item]))
        lowered = {**item, "minimum_test_criticality": "low"}
        blocked = self.record_agent(cwd, "architect", "proposed", item_id="E1", item_revision=item["item_revision"], plan_revision="p1", minimum_test_criticality="low", acceptance_revision="ac1")
        self.assertIsNotNone(blocked, "same item plan floor downgrade must block")

    def test_test_plan_keyset_and_update_path_integrity_fail_closed(self):
        cwd = self.projects["backend"]; self.activate()
        common = {"plan_revision": "p", "acceptance_revision": "ac", "test_criticality": "standard", "scope_fingerprint": "s", "assessed_paths": ["src/a.ts"], "tested_invariants": ["a"], "existing_tests": ["no_relevant_tests"], "coverage_mode": "targeted", "residual_risks": ["r"]}
        mismatch = {**common, "test_disposition": "add", "test_plan": {"action": "add", "tests": ["tests/a.test.ts"], "protected_hashes": {"tests/b.test.ts": "0" * 64}}}
        self.assertIsNotNone(self.record_test_assessment(cwd, mismatch), "test and hash keysets must match")
        missing = {**common, "test_disposition": "update", "test_plan": {"action": "update", "tests": ["tests/missing.test.ts"], "protected_hashes": {"tests/missing.test.ts": "0" * 64}, "protected_test_handshake": True}}
        self.assertIsNotNone(self.record_test_assessment(cwd, missing), "update must require an existing test file")

    def test_epic_docs_or_yaml_write_clears_all_stale_item_gates(self):
        cwd = self.projects["backend"]; self.activate_profile("epic-implementation")
        items = [{"item_id": "A", "item_revision": "a" * 64, "plan_revision": "p", "acceptance_revision": "ac", "minimum_test_criticality": "low"}, {"item_id": "B", "item_revision": "b" * 64, "plan_revision": "p", "acceptance_revision": "ac", "minimum_test_criticality": "low"}]
        self.assertIsNone(self.freeze_epic_items(cwd, items)); state = self.adaptive_state(); state["selected_items"][0]["gates"] = ["reviewer", "qa"]; state["selected_items"][1]["gates"] = ["reviewer", "qa"]; path = next((self.data / "hook-state").glob("*.json")); path.write_text(json.dumps(state), encoding="utf-8")
        (cwd / "docs").mkdir(); (cwd / "docs" / "note.md").write_text("x\n", encoding="utf-8")
        self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: docs/note.md\n+x\n*** End Patch"}, "tool_response": {"ok": True}}, cwd)
        self.assertEqual([item["gates"] for item in self.adaptive_state()["selected_items"]], [[], []])

    def test_test_maker_requires_assessment_ready_with_mandatory_fields(self):
        cwd = self.projects["backend"]
        self.activate()
        output = self.record_agent(cwd, "test-maker", "baseline_ready")
        self.assertIsNotNone(output, "legacy baseline_ready must not satisfy TestAssessment gate")
        self.assertEqual(output["decision"], "block")
        self.assertIn("TestAssessment", output["reason"])

    def test_critical_none_and_unknown_semantics_fail_closed(self):
        cwd = self.projects["backend"]
        self.activate()
        invalid = self.record_test_assessment(
            cwd,
            {
                "plan_revision": "plan-r1",
                "acceptance_revision": "accept-r1",
                "test_criticality": "critical",
                "test_disposition": "none",
                "scope_fingerprint": "scope-r1",
            },
        )
        self.assertIsNotNone(invalid, "critical + none TestAssessment must fail closed")
        self.assertEqual(invalid["decision"], "block")
        self.assertIn("critical", invalid["reason"])
        unknown = self.record_test_assessment(
            cwd,
            {
                "plan_revision": "plan-r2",
                "acceptance_revision": "accept-r2",
                "test_criticality": "unknown",
                "test_disposition": "reuse",
                "scope_fingerprint": "scope-r2",
                "reuse_proof": {"test_path": "tests/existing.test.ts", "covered_branch": "unknown semantic branch"},
            },
        )
        self.assertIsNotNone(unknown, "unknown semantics must be normalized to critical")
        self.assertEqual(unknown["decision"], "block")
        self.assertIn("critical", unknown["reason"])

    def test_standard_none_requires_complete_exception_evidence(self):
        cwd = self.projects["backend"]
        self.activate()
        assessment = {
            "plan_revision": "plan-r1", "acceptance_revision": "accept-r1",
            "test_criticality": "standard", "test_disposition": "none", "scope_fingerprint": "scope-r1",
            "disproportionate_cost": True, "stronger_alternative_evidence": ["manual trace"], "alternative_evidence": ["manual trace"],
        }
        missing = self.record_test_assessment(cwd, assessment)
        self.assertIsNotNone(missing, "standard + none must reject incomplete exception evidence")
        self.assertEqual(missing["decision"], "block")
        self.assertIn("rationale", missing["reason"])
        complete = {**assessment, "rationale": "isolated non-observable rendering detail", "residual_risks": ["visual drift"], "follow_up": "verify in release smoke"}
        self.assertIsNone(self.record_test_assessment(cwd, complete))

    def test_reuse_proof_requires_exact_protected_file_and_critical_branch_evidence(self):
        cwd = self.projects["backend"]
        self.activate()
        protected = cwd / "tests" / "price.test.ts"
        protected.parent.mkdir()
        protected.write_text("it('rounding boundary', () => {});\n", encoding="utf-8")
        self.call(
            "post-tool",
            {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "npm test -- --coverage"}, "tool_response": {"exit_code": 0}},
            cwd,
        )
        incomplete = {
            "plan_revision": "plan-r1",
            "acceptance_revision": "accept-r1",
            "test_criticality": "critical",
            "test_disposition": "reuse",
            "scope_fingerprint": "scope-r1",
            "reuse_proof": {"test_id": "rounding-boundary", "test_path": "tests/price.test.ts", "invariant_mapping": "rounding", "successful_run": True, "file_sha256": "0" * 64},
        }
        rejected = self.record_test_assessment(cwd, incomplete)
        self.assertEqual(rejected["decision"], "block")
        self.assertIn("file_sha256", rejected["reason"])
        valid = dict(incomplete)
        valid["reuse_proof"] = {**incomplete["reuse_proof"], "file_sha256": __import__("hashlib").sha256(protected.read_bytes()).hexdigest(), "critical_branch_evidence": "rounding boundary branch"}
        self.assertIsNone(self.record_test_assessment(cwd, valid))

    def test_assessment_retains_in_scope_write_and_invalidates_out_of_scope_write(self):
        cwd = self.projects["backend"]
        self.activate()
        protected = cwd / "tests" / "price.test.ts"; protected.parent.mkdir(exist_ok=True); protected.write_text("it('price', () => {});\n", encoding="utf-8")
        digest = hashlib.sha256(protected.read_bytes()).hexdigest()
        self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: tests/price.test.ts\n+x\n*** End Patch"}, "tool_response": {"ok": True}}, cwd)
        assessment = {"plan_revision": "plan-r1", "acceptance_revision": "accept-r1", "test_criticality": "standard", "test_disposition": "add", "scope_fingerprint": "scope-r1", "assessed_paths": ["src/price.ts"], "tested_invariants": ["price boundary"], "existing_tests": ["no_relevant_tests"], "coverage_mode": "targeted", "residual_risks": ["integration"], "test_plan": {"action": "add", "tests": ["tests/price.test.ts"], "protected_hashes": {"tests/price.test.ts": digest}, "commands": ["npm test -- tests/price.test.ts"], "expected_baseline": "red", "actual_baseline": "red"}}
        self.assertIsNone(self.record_test_assessment(cwd, assessment))
        source = cwd / "src" / "price.ts"
        source.parent.mkdir()
        source.write_text("export const total = 1;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/price.ts\n+x\n*** End Patch"},
                "tool_response": {"ok": True},
            },
            cwd,
        )
        self.assertEqual(self.adaptive_state()["test_assessments"][-1]["scope_fingerprint"], "scope-r1")
        outside = cwd / "src" / "tax.ts"
        outside.write_text("export const tax = 1;\n", encoding="utf-8")
        self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Add File: src/tax.ts\n+x\n*** End Patch"}, "tool_response": {"ok": True}}, cwd)
        self.assertEqual(self.adaptive_state()["test_assessments"], [])

    def test_epic_assessment_requires_item_revision_ledger_and_preserves_repository_gates(self):
        cwd = self.projects["frontend"]
        self.activate_profile("epic-implementation")
        item = {"item_id": "CRM-42", "item_revision": "b" * 64, "plan_revision": "plan-r1", "acceptance_revision": "accept-r1", "minimum_test_criticality": "low"}
        self.assertIsNone(self.freeze_epic_items(cwd, [item]))
        self.assertIsNone(self.record_test_assessment(
            cwd,
            {
                "plan_revision": "plan-r1",
                "acceptance_revision": "accept-r1",
                "test_criticality": "low",
                "test_disposition": "none",
                "scope_fingerprint": "scope-r1",
                "alternative_evidence": ["visual review"], "rationale": "cosmetic adjustment",
                "item_id": item["item_id"],
                "item_revision": item["item_revision"],
            },
        ), "assessment_ready must be accepted before the epic ledger can be evaluated")
        state = self.adaptive_state()
        self.assertEqual(state["selected_items"], [{**item, "gates": ["test-maker"]}])

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

    def test_subagent_verdicts_are_scoped_to_active_profile(self):
        cwd = self.projects["backend"]
        self.activate()
        agent_id = "wrong-profile-architect"
        started = self.call(
            "subagent-start",
            {
                "hook_event_name": "SubagentStart",
                "agent_id": agent_id,
                "agent_type": "architect",
            },
            cwd,
        )
        revision = re.search(
            r"revision is ([0-9a-f]{64})",
            started["hookSpecificOutput"]["additionalContext"],
        ).group(1)
        marker = json.dumps(
            {
                "role": "architect",
                "verdict": "planned",
                "phase": "",
                "input_revision": revision,
            },
            separators=(",", ":"),
        )
        output = self.call(
            "subagent-stop",
            {
                "hook_event_name": "SubagentStop",
                "agent_id": agent_id,
                "agent_type": "architect",
                "stop_hook_active": False,
                "last_assistant_message": f"WGC_AGENT_RESULT: {marker}",
            },
            cwd,
        )
        self.assertEqual(output["decision"], "block")
        self.assertIn("profile implementation", output["reason"])

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

    def test_prompt_submit_selects_bugfix_profile_and_privacy_safe_routes(self):
        output = self.activate_bugfix(
            prompt="Use $wgc-bugfix: production API/UI regression in PWA exposes another tenant after WebSocket reconnect; deploy through Argo after approval",
        )
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("bugfix workflow activated", context)
        self.assertIn("reproduce before patching", context)
        state_path = next((self.data / "hook-state").glob("*.json"))
        raw = state_path.read_text(encoding="utf-8")
        state = json.loads(raw)
        self.assertEqual(state["version"], 3)
        self.assertEqual(state["profile"], "bugfix")
        self.assertTrue(state["bugfix_routes"]["ui"])
        self.assertTrue(state["bugfix_routes"]["security"])
        self.assertTrue(state["bugfix_routes"]["contract"])
        self.assertTrue(state["bugfix_routes"]["incident"])
        self.assertTrue(state["bugfix_routes"]["gitops"])
        self.assertTrue(state["bugfix_routes"]["deployment"])
        self.assertNotIn("another tenant", raw)

    def test_prompt_submit_routes_task_creation_and_epic_profiles(self):
        task = self.activate_profile(
            "task-creation",
            prompt="Use $wgc-task-creation to create an ordered backlog in GitHub Project #42",
        )
        self.assertIn("task-creation workflow activated", task["hookSpecificOutput"]["additionalContext"])
        task_state_path = next((self.data / "hook-state").glob("*.json"))
        task_state = json.loads(task_state_path.read_text(encoding="utf-8"))
        self.assertEqual(task_state["profile"], "task-creation")
        self.assertTrue(task_state["project_routes"]["project_targeted"])
        self.assertTrue(task_state["project_routes"]["mutation_requested"])

        epic = self.call(
            "prompt-submit",
            {
                "session_id": "session-epic-profile",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Use $wgc-epic-implementation to implement epic CRM-EP01 from GitHub Project #1",
            },
            self.projects["backend"],
        )
        self.assertIn("epic-implementation workflow activated", epic["hookSpecificOutput"]["additionalContext"])
        states = [json.loads(path.read_text(encoding="utf-8")) for path in (self.data / "hook-state").glob("*.json")]
        epic_state = next(state for state in states if state["profile"] == "epic-implementation")
        self.assertTrue(epic_state["project_routes"]["mutation_requested"])

    def test_routing_precedence_and_generic_create_do_not_select_task_creation(self):
        explicit_bug = self.call(
            "prompt-submit",
            {
                "session_id": "session-explicit-bug",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Use $wgc-bugfix while reviewing this epic backlog bug",
            },
            self.projects["backend"],
        )
        self.assertIn("bugfix workflow", explicit_bug["hookSpecificOutput"]["additionalContext"])
        generic = self.call(
            "prompt-submit",
            {
                "session_id": "session-generic-create",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Create a helper function in the backend",
            },
            self.projects["backend"],
        )
        self.assertIn("implementation workflow", generic["hookSpecificOutput"]["additionalContext"])

    def test_project_profiles_do_not_persist_raw_prompt_or_project_url(self):
        secret_title = "Confidential Customer Migration"
        project_url = "https://github.com/orgs/wget-cloud/projects/987"
        self.activate_profile(
            "task-creation",
            prompt=f"Use $wgc-task-creation to create {secret_title} in {project_url}",
        )
        state_path = next((self.data / "hook-state").glob("*.json"))
        raw = state_path.read_text(encoding="utf-8")
        self.assertNotIn(secret_title, raw)
        self.assertNotIn(project_url, raw)
        state = json.loads(raw)
        self.assertIn("last_prompt_sha256", state)
        self.assertEqual(set(state["project_routes"]), {"project_targeted", "mutation_requested"})

    def test_project_mutation_opt_out_overrides_epic_default(self):
        cwd = self.projects["backend"]
        self.activate_profile(
            "epic-implementation",
            prompt="Use $wgc-epic-implementation for CRM-EP01 without updating GitHub Project",
        )
        state_path = next((self.data / "hook-state").glob("*.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertFalse(state["project_routes"]["mutation_requested"])
        for role, verdict, phase in (
            ("product-manager", "accepted", "scope"),
            ("project-manager", "planned", "scope"),
            ("architect", "proposed", ""),
            ("architecture-guardian", "approved", "plan"),
            ("test-maker", "assessment_ready", ""),
            ("implementor", "implemented", ""),
            ("reviewer", "approved", ""),
            ("architecture-guardian", "approved", "diff"),
            ("qa", "pass", ""),
            ("product-manager", "accepted", "outcome"),
            ("project-manager", "progress_updated", "reconcile"),
        ):
            self.record_agent(cwd, role, verdict, phase)
        completed = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-epic-no-project-write",
                "stop_hook_active": False,
                "last_assistant_message": "Implemented without Project mutation",
            },
            cwd,
        )
        self.assertIsNone(completed)

    def test_late_project_mutation_opt_out_revokes_prior_epic_sync(self):
        cwd = self.projects["backend"]
        self.activate_profile(
            "epic-implementation",
            prompt="Use $wgc-epic-implementation and sync GitHub Project statuses",
        )
        state_path = next((self.data / "hook-state").glob("*.json"))
        before = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertTrue(before["project_routes"]["mutation_requested"])
        self.call(
            "prompt-submit",
            {
                "hook_event_name": "UserPromptSubmit",
                "turn_id": "turn-epic-opt-out-followup",
                "prompt": "Do not update GitHub Project; continue implementation read-only for statuses",
            },
            cwd,
        )
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertFalse(after["project_routes"]["mutation_requested"])

    def test_epic_rework_invalidates_product_outcome_but_preserves_scope(self):
        cwd = self.projects["backend"]
        self.activate_profile(
            "epic-implementation",
            prompt="Use $wgc-epic-implementation for CRM-EP01 from GitHub Project #1",
        )
        self.record_agent(cwd, "product-manager", "accepted", "scope")
        self.record_agent(cwd, "product-manager", "accepted", "outcome")
        source = cwd / "src" / "epic.ts"
        source.parent.mkdir()
        source.write_text("export const epic = true;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/epic.ts\n+x\n*** End Patch"},
                "tool_response": {"ok": True},
            },
            cwd,
        )
        state_path = next((self.data / "hook-state").glob("*.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        product_phases = {
            result["phase"]
            for result in state["subagent_results"]
            if result["role"] == "product-manager"
        }
        self.assertEqual(product_phases, {"scope"})

    def test_bugfix_inference_does_not_capture_generic_implementation(self):
        bugfix = self.activate_bugfix(prompt="Почини ошибку: расчёт иногда падает")
        self.assertIn("bugfix workflow", bugfix["hookSpecificOutput"]["additionalContext"])
        implementation = self.call(
            "prompt-submit",
            {
                "session_id": "session-generic-implementation",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Исправь документацию архитектуры",
            },
            self.projects["backend"],
        )
        self.assertIn("implementation workflow", implementation["hookSpecificOutput"]["additionalContext"])
        states = [json.loads(path.read_text(encoding="utf-8")) for path in (self.data / "hook-state").glob("*.json")]
        self.assertIn("implementation", {state["profile"] for state in states})

    def test_deployment_followup_stays_in_active_bugfix_profile(self):
        self.activate_bugfix()
        output = self.call(
            "prompt-submit",
            {"hook_event_name": "UserPromptSubmit", "prompt": "Одобряю деплой исправления после показа revision"},
            self.projects["backend"],
        )
        self.assertIn("bugfix workflow", output["hookSpecificOutput"]["additionalContext"])
        state_path = next((self.data / "hook-state").glob("*.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["profile"], "bugfix")
        self.assertTrue(state["bugfix_routes"]["deployment"])

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

    def test_allows_only_exact_human_approved_clean_bootstrap(self):
        fixture = self._bootstrap_fixture()
        self.assertIsNone(self._bootstrap_command(self._approved_helm_bootstrap(fixture)))

    def test_unknown_provider_recovery_marker_never_bypasses_mutation_policy(self):
        marker = "WGC_PROVIDER_RECOVERY_APPROVED=1"
        commands = {
            "env-python": f"{marker} /usr/bin/env -i /usr/bin/python3 /tmp/provider-runner.py",
            "kubectl": f"{marker} kubectl -n backend apply -f deployment.yaml",
            "helm": f"{marker} helm upgrade gateway ./chart",
            "argocd": f"{marker} argocd app sync clean-bootstrap-cluster",
            "argocd-prefixed": f"{marker} argocd-custom app sync clean-bootstrap-cluster",
        }
        for case, command in commands.items():
            with self.subTest(case=case):
                output = self._bootstrap_command(command)
                self.assertIsNotNone(output, f"provider marker bypassed policy: {command}")
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_provider_marker_before_direct_python_runner(self):
        output = self._bootstrap_command(
            "WGC_PROVIDER_RECOVERY_APPROVED=1 /usr/bin/python3 /tmp/provider-runner.py"
        )
        self.assertIsNotNone(output, "provider marker must not authorize a direct runner")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_quoted_provider_marker_before_direct_python_runner(self):
        output = self._bootstrap_command(
            'WGC_PROVIDER_RECOVERY_APPROVED="1" /usr/bin/python3 /tmp/provider-runner.py'
        )
        self.assertIsNotNone(output, "quoted provider marker must not authorize a direct runner")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_provider_marker_through_command_wrappers(self):
        marker = "WGC_PROVIDER_RECOVERY_APPROVED=1"
        commands = {
            "env-unset": f"env -u FOO {marker} /usr/bin/python3 /tmp/provider-runner.py",
            "command-env": f"command env {marker} /usr/bin/python3 /tmp/provider-runner.py",
            "nohup-env": f"nohup env {marker} /usr/bin/python3 /tmp/provider-runner.py",
            "sudo-env": f"sudo env {marker} /usr/bin/python3 /tmp/provider-runner.py",
            "env-split-string": "/usr/bin/env -S 'WGC_PROVIDER_RECOVERY_APPROVED=1 /usr/bin/true'",
            "env-long-split-string": (
                "env --split-string='WGC_PROVIDER_RECOVERY_APPROVED=1 /usr/bin/true'"
            ),
            "env-combined-clean-split-string": (
                "env -iS 'WGC_PROVIDER_RECOVERY_APPROVED=1 /usr/bin/true'"
            ),
        }
        for case, command in commands.items():
            with self.subTest(case=case):
                output = self._bootstrap_command(command)
                self.assertIsNotNone(output, f"provider marker bypassed through wrapper: {command}")
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_shell_escaped_provider_marker_value_one(self):
        # In POSIX shell assignment context, the backslash is removed: the value is `1`.
        output = self._bootstrap_command(
            "WGC_PROVIDER_RECOVERY_APPROVED=\\1 /usr/bin/python3 /tmp/provider-runner.py"
        )
        self.assertIsNotNone(output, "escaped provider marker must not authorize a runner")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_ansi_quoted_provider_marker_value_one(self):
        output = self._bootstrap_command(
            "WGC_PROVIDER_RECOVERY_APPROVED=$'1' /usr/bin/true"
        )
        self.assertIsNotNone(output, "ANSI-quoted provider marker must not authorize a runner")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_kubectl_mutations_hidden_behind_xargs(self):
        commands = {
            "direct-xargs": "xargs kubectl delete pod gateway-0",
            "piped-xargs": "printf pod/gateway-0 | xargs kubectl delete -n backend",
        }
        for case, command in commands.items():
            with self.subTest(case=case):
                output = self._bootstrap_command(command)
                self.assertIsNotNone(output, f"xargs bypassed Kubernetes policy: {command}")
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_kubectl_mutations_hidden_behind_xargs_options(self):
        commands = {
            "max-args": "xargs -n 1 kubectl delete pod",
            "replacement": "xargs -I{} kubectl delete pod {}",
            "end-of-options": "xargs -- kubectl delete pod",
        }
        for case, command in commands.items():
            with self.subTest(case=case):
                output = self._bootstrap_command(command)
                self.assertIsNotNone(output, f"xargs option bypassed Kubernetes policy: {command}")
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_kubectl_mutations_hidden_behind_bsd_xargs_options(self):
        commands = {
            "bsd-replacement": "xargs -J{} kubectl delete pod {}",
            "bsd-replacements": "xargs -R 1 kubectl delete pod",
            "bsd-replacement-size": "xargs -S 1024 kubectl delete pod",
            "combined-short-options": "xargs -0t kubectl delete pod",
            "null-delimited-max-args": "xargs -0n1 kubectl delete pod",
            "trace-max-args": "xargs -tn1 kubectl delete pod",
            "null-trace-max-args": "xargs -0tn1 kubectl delete pod",
        }
        for case, command in commands.items():
            with self.subTest(case=case):
                output = self._bootstrap_command(command)
                self.assertIsNotNone(output, f"BSD xargs option bypassed Kubernetes policy: {command}")
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_allows_read_only_kubectl_hidden_behind_xargs_options(self):
        commands = (
            "xargs -n 1 kubectl get pod",
            "xargs -J{} kubectl get pod {}",
            "xargs -R 1 kubectl get pod",
            "xargs -S 1024 kubectl get pod",
            "xargs -0t kubectl get pod",
            "xargs -0n1 kubectl get pod",
            "xargs -tn1 kubectl get pod",
            "xargs -0tn1 kubectl get pod",
        )
        for command in commands:
            with self.subTest(command=command):
                output = self._bootstrap_command(command)
                self.assertIsNone(output, "read-only xargs kubectl command must remain allowed")

    def test_allows_prose_marker_that_is_not_shell_assignment(self):
        output = self._bootstrap_command("echo WGC_PROVIDER_RECOVERY_APPROVED=1")
        self.assertIsNone(output, "marker text passed to echo is not an authorization assignment")

    def test_blocks_markerless_retired_recovery_runner_paths(self):
        commands = {
            "via-clean-env": (
                "/usr/bin/env -i HOME=/var/empty PATH=/usr/bin:/bin /usr/bin/python3 "
                "/usr/local/libexec/wget-cloud-retired-recovery/runner.py --stage 1"
            ),
            "direct": (
                "/usr/bin/python3 /usr/local/libexec/wget-cloud-retired-recovery/runner.py"
            ),
            "direct-executable": (
                "/usr/local/libexec/wget-cloud-retired-recovery/runner.py --stage 1"
            ),
            "direct-executable-via-clean-env": (
                "/usr/bin/env -i HOME=/var/empty "
                "/usr/local/libexec/wget-cloud-retired-recovery/runner.py --stage 1"
            ),
            "python-bytecode-option": (
                "/usr/bin/python3 -B /usr/local/libexec/wget-cloud-retired-recovery/runner.py"
            ),
            "python-unbuffered-option": (
                "/usr/bin/python3 -u /usr/local/libexec/wget-cloud-retired-recovery/runner.py"
            ),
            "python-isolated-option": (
                "/usr/bin/python3 -I /usr/local/libexec/wget-cloud-retired-recovery/runner.py"
            ),
            "python-end-of-options": (
                "/usr/bin/python3 -- /usr/local/libexec/wget-cloud-retired-recovery/runner.py"
            ),
            "python-hash-pyc-option": (
                "/usr/bin/python3 --check-hash-based-pycs=always "
                "/usr/local/libexec/wget-cloud-retired-recovery/runner.py"
            ),
            "lexical-path": (
                "/usr/bin/python3 /usr/local/libexec/wget-cloud-retired-recovery/sub/../runner.py"
            ),
            "env-split-string": (
                "/usr/bin/env -S 'python3 "
                "/usr/local/libexec/wget-cloud-retired-recovery/runner.py'"
            ),
        }
        for case, command in commands.items():
            with self.subTest(case=case):
                output = self._bootstrap_command(command)
                self.assertIsNotNone(output, f"retired recovery runner bypassed policy: {command}")
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_allows_unrelated_python_runner(self):
        for command in (
            "/usr/bin/python3 /tmp/safe-tool.py",
            "/tmp/safe-tool.py",
            "/usr/bin/env -S '/tmp/safe-tool.py'",
            "/usr/bin/env -iS '/tmp/safe-tool.py'",
        ):
            with self.subTest(command=command):
                output = self._bootstrap_command(command)
                self.assertIsNone(output, "unrelated runner must not be blocked by retired-runner policy")

    def test_claimed_devops_actor_cannot_bypass_kubernetes_policy(self):
        common = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "agent_id": "claimed-devops",
            "agent_type": "devops",
        }
        blocked = self.call(
            "pre-tool",
            {**common, "tool_input": {"command": "kubectl -n backend apply -f deployment.yaml"}},
            self.projects["k8s"],
        )
        self.assertEqual(blocked["hookSpecificOutput"]["permissionDecision"], "deny")
        allowed = self.call(
            "pre-tool",
            {**common, "tool_input": {"command": "kubectl -n backend get pods -o wide"}},
            self.projects["k8s"],
        )
        self.assertIsNone(allowed)

    def test_allows_exact_repository_credential_and_immutable_root_bootstrap(self):
        fixture = self._bootstrap_fixture()
        for command in (
            self._approved_repository_bootstrap(fixture),
            self._approved_root_bootstrap(fixture),
        ):
            with self.subTest(command=command):
                self.assertIsNone(self._bootstrap_command(command))

    def test_gitops_bootstrap_exact_absolute_inputs_ignore_absolute_tool_workdir(self):
        fixture = self._bootstrap_fixture()
        for command in (
            self._approved_helm_bootstrap(fixture),
            self._approved_repository_bootstrap(fixture),
            self._approved_root_bootstrap(fixture),
        ):
            with self.subTest(command=command):
                self.assertIsNone(
                    self._bootstrap_command_with_workdir(
                        command,
                        self.root,
                        str(fixture["k8s"]),
                    )
                )

    def test_gitops_bootstrap_exact_absolute_inputs_ignore_relative_tool_workdir(self):
        fixture = self._bootstrap_fixture()
        for command in (
            self._approved_helm_bootstrap(fixture),
            self._approved_repository_bootstrap(fixture),
            self._approved_root_bootstrap(fixture),
        ):
            with self.subTest(command=command):
                self.assertIsNone(
                    self._bootstrap_command_with_workdir(
                        command,
                        self.root,
                        "k8s",
                    )
                )

    def test_gitops_bootstrap_without_tool_workdir_allows_only_canonical_absolute_repo_inputs(self):
        fixture = self._bootstrap_fixture()
        for command in (
            self._approved_helm_bootstrap(fixture),
            self._approved_repository_bootstrap(fixture),
            self._approved_root_bootstrap(fixture),
        ):
            with self.subTest(command=command):
                output = self._bootstrap_command_with_workdir(command, self.root)
                self.assertIsNone(output)

    def test_gitops_bootstrap_without_tool_workdir_denies_relative_repo_inputs(self):
        fixture = self._bootstrap_fixture()
        nested = fixture["k8s"] / "nested-relative-workdir"
        nested.mkdir()
        relative_key = os.path.relpath(fixture["key"], self.root)
        relative_kubeconfig = os.path.relpath(fixture["kubeconfig"], self.root)
        repository = self._approved_repository_bootstrap(fixture)
        denied = {
            "relative-helm-values": self._relative_helm_bootstrap(fixture),
            "relative-root-filename": self._relative_root_bootstrap(fixture),
            "relative-repository-key": repository.replace(str(fixture["key"]), relative_key, 1),
            "relative-repository-kubeconfig": repository.replace(
                str(fixture["kubeconfig"]),
                relative_kubeconfig,
            ),
        }
        ignored_workdirs = {
            "absent": WORKDIR_ABSENT,
            "canonical-k8s": str(fixture["k8s"]),
            "mismatched-project": str(self.projects["backend"]),
            "nested-k8s": str(nested),
        }
        for case, command in denied.items():
            for workdir_case, workdir in ignored_workdirs.items():
                with self.subTest(case=case, workdir_case=workdir_case, command=command):
                    output = self._bootstrap_command_with_workdir(command, self.root, workdir)
                    self.assertIsNotNone(output)
                    self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_gitops_bootstrap_without_tool_workdir_preserves_shadow_and_near_miss_denials(self):
        fixture = self._bootstrap_fixture()
        absolute_helm = self._approved_helm_bootstrap(fixture)
        absolute_root = self._approved_root_bootstrap(fixture)
        shadow = self.root / "shadow" / "k8s"
        shadow.mkdir(parents=True)
        self._git_init(shadow)
        denied = {
            "shadow-event-cwd": self._bootstrap_command_with_workdir(absolute_helm, shadow),
            "missing-approval-marker": self._bootstrap_command_with_workdir(
                absolute_helm.replace("WGC_GITOPS_BOOTSTRAP_APPROVED=1 ", "", 1),
                self.root,
            ),
            "wrong-chart": self._bootstrap_command_with_workdir(
                absolute_helm.replace("argo/argo-cd", "bitnami/argo-cd", 1),
                self.root,
            ),
            "extra-mutation": self._bootstrap_command_with_workdir(
                absolute_root + " ; kubectl --context clean-bootstrap delete namespace backend",
                self.root,
            ),
        }
        for case, output in denied.items():
            with self.subTest(case=case):
                self.assertIsNotNone(output)
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_gitops_bootstrap_exact_absolute_inputs_ignore_valid_tool_workdir_values(self):
        fixture = self._bootstrap_fixture()
        nested = fixture["k8s"] / "nested"
        nested.mkdir()
        commands = (
            self._approved_helm_bootstrap(fixture),
            self._approved_repository_bootstrap(fixture),
            self._approved_root_bootstrap(fixture),
        )
        ignored_workdirs = {
            "coordinator": str(self.root),
            "backend": str(self.projects["backend"]),
            "other-project": str(self.projects["frontend"]),
            "canonical-k8s": str(fixture["k8s"]),
            "nested-k8s": str(nested),
        }
        for command in commands:
            for case, workdir in ignored_workdirs.items():
                with self.subTest(case=case, workdir=workdir, command=command):
                    output = self._bootstrap_command_with_workdir(command, self.root, workdir)
                    self.assertIsNone(output)

    def test_gitops_bootstrap_malformed_or_outside_tool_workdir_stays_fail_closed(self):
        fixture = self._bootstrap_fixture()
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        nonexistent = Path(self.temp.name) / "nonexistent"
        commands = (
            self._approved_helm_bootstrap(fixture),
            self._approved_repository_bootstrap(fixture),
            self._approved_root_bootstrap(fixture),
        )
        denied_workdirs = {
            "outside-coordinator": str(outside),
            "nonexistent": str(nonexistent),
            "file": str(fixture["kubeconfig"]),
            "non-string-number": 7,
            "non-string-list": [str(fixture["k8s"])],
            "blank": "",
            "whitespace": "   ",
        }
        for command in commands:
            for case, workdir in denied_workdirs.items():
                with self.subTest(case=case, workdir=workdir, command=command):
                    output = self._bootstrap_command_with_workdir(command, self.root, workdir)
                    self.assertIsNotNone(output)
                    self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_gitops_bootstrap_tool_workdir_preserves_near_miss_denials(self):
        fixture = self._bootstrap_fixture()
        helm = self._approved_helm_bootstrap(fixture)
        repository = self._approved_repository_bootstrap(fixture)
        root = self._approved_root_bootstrap(fixture)
        denied = (
            helm.replace("WGC_GITOPS_BOOTSTRAP_APPROVED=1 ", "", 1),
            helm.replace("argo/argo-cd", "bitnami/argo-cd", 1),
            repository.replace("wget-cloud-k8s-repository", "other-repository", 1),
            repository.replace(" | ", " ; "),
            root.replace(str(fixture["root"]), "infrastructure/k8s/bootstrap/roots/dev.yaml", 1),
            root + " ; kubectl --context clean-bootstrap delete namespace backend",
        )
        for command in denied:
            with self.subTest(command=command):
                output = self._bootstrap_command_with_workdir(
                    command,
                    self.root,
                    str(fixture["k8s"]),
                )
                self.assertIsNotNone(output)
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_gitops_bootstrap_rejects_nested_shadow_k8s_repository(self):
        fixture = self._bootstrap_fixture()
        canonical_command = self._approved_helm_bootstrap(fixture)
        self.assertIsNone(
            self._bootstrap_command_with_workdir(
                canonical_command,
                self.root,
                str(fixture["k8s"]),
            )
        )

        shadow = self.root / "shadow" / "k8s"
        shadow.mkdir(parents=True)
        self._git_init(shadow)
        argocd = shadow / "infrastructure" / "k8s" / "bootstrap" / "argocd"
        roots = shadow / "infrastructure" / "k8s" / "bootstrap" / "roots"
        argocd.mkdir(parents=True)
        roots.mkdir(parents=True)
        (argocd / "makefile").write_text(
            """NAMESPACE ?= argocd
RELEASE ?= argo-cd
CHART ?= attacker/argo-cd
CHART_VERSION ?= 9.9.9
VALUES ?= values.yaml
WAIT ?= true
TIMEOUT ?= 10m
""",
            encoding="utf-8",
        )
        (argocd / "values.yaml").write_text("crds:\n  install: true\n", encoding="utf-8")
        shadow_tag = "clean-bootstrap-shadow-2026-08-20.1"
        (roots / "clean-bootstrap.yaml").write_text(
            f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: clean-bootstrap-cluster
  namespace: argocd
  labels:
    wget-cloud.io/profile: clean-bootstrap
spec:
  project: default
  source:
    repoURL: ssh://git@github.com/wget-cloud/k8s
    targetRevision: {shadow_tag}
    path: infrastructure/k8s/gitops/clusters/clean-bootstrap/root
  destination:
    namespace: argocd
    server: https://kubernetes.default.svc
  syncPolicy:
    syncOptions: [CreateNamespace=true]
""",
            encoding="utf-8",
        )
        self._git_commit(
            shadow,
            [
                "infrastructure/k8s/bootstrap/argocd/makefile",
                "infrastructure/k8s/bootstrap/argocd/values.yaml",
                "infrastructure/k8s/bootstrap/roots/clean-bootstrap.yaml",
            ],
        )
        self._run(["git", "tag", shadow_tag], shadow)

        attacker_command = (
            canonical_command.replace(str(fixture["values_file"]), str(argocd / "values.yaml"), 1)
            .replace("argo/argo-cd", "attacker/argo-cd", 1)
            .replace(
                "--version 8.0.0",
                "--version 9.9.9",
                1,
            )
        )
        shadow_attempts = {
            "coordinator-event-with-shadow-workdir": self._bootstrap_command_with_workdir(
                attacker_command,
                self.root,
                str(shadow),
            ),
            "shadow-event-without-workdir": self._bootstrap_command_with_workdir(
                attacker_command,
                shadow,
            ),
        }
        for case, output in shadow_attempts.items():
            with self.subTest(case=case):
                self.assertIsNotNone(output)
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_gitops_bootstrap_requires_canonical_k8s_path_to_be_exact_git_root(self):
        fixture = self._bootstrap_fixture()
        shutil.rmtree(fixture["k8s"] / ".git")

        duplicate_argocd = self.root / "infrastructure" / "k8s" / "bootstrap" / "argocd"
        duplicate_roots = self.root / "infrastructure" / "k8s" / "bootstrap" / "roots"
        duplicate_argocd.mkdir(parents=True)
        duplicate_roots.mkdir(parents=True)
        duplicate_makefile = duplicate_argocd / "makefile"
        duplicate_values = duplicate_argocd / "values.yaml"
        duplicate_root = duplicate_roots / "clean-bootstrap.yaml"
        shutil.copyfile(fixture["makefile"], duplicate_makefile)
        shutil.copyfile(fixture["values_file"], duplicate_values)
        shutil.copyfile(fixture["root"], duplicate_root)

        coordinator_owned = (
            "k8s/infrastructure/k8s/bootstrap/argocd/makefile",
            "k8s/infrastructure/k8s/bootstrap/argocd/values.yaml",
            "k8s/infrastructure/k8s/bootstrap/roots/clean-bootstrap.yaml",
            "infrastructure/k8s/bootstrap/argocd/makefile",
            "infrastructure/k8s/bootstrap/argocd/values.yaml",
            "infrastructure/k8s/bootstrap/roots/clean-bootstrap.yaml",
        )
        self._git_commit(self.root, coordinator_owned)
        self._run(["git", "tag", "clean-bootstrap-2026-08-15.1"], self.root)

        for command in (
            self._approved_helm_bootstrap(fixture),
            self._approved_repository_bootstrap(fixture),
            self._approved_root_bootstrap(fixture),
        ):
            with self.subTest(command=command):
                output = self._bootstrap_command_with_workdir(command, self.root)
                self.assertIsNotNone(output)
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_denies_dirty_repo_owned_helm_contract_after_tag(self):
        fixture = self._bootstrap_fixture()
        helm = self._approved_helm_bootstrap(fixture)
        tagged_values = fixture["values_file"].read_text(encoding="utf-8")
        tagged_makefile = fixture["makefile"].read_text(encoding="utf-8")

        fixture["values_file"].write_text(
            tagged_values + "server:\n  extraArgs: [--insecure]\n",
            encoding="utf-8",
        )
        with self.subTest(input="dirty values.yaml"):
            self._assert_bootstrap_denied(helm)
        fixture["values_file"].write_text(tagged_values, encoding="utf-8")

        fixture["makefile"].write_text(
            tagged_makefile.replace("CHART ?= argo/argo-cd", "CHART ?= attacker/argo-cd").replace(
                "CHART_VERSION ?= 8.0.0",
                "CHART_VERSION ?= 9.9.9",
            ),
            encoding="utf-8",
        )
        dirty_contract_command = helm.replace("argo/argo-cd", "attacker/argo-cd", 1).replace(
            "--version 8.0.0",
            "--version 9.9.9",
            1,
        )
        with self.subTest(input="dirty makefile contract"):
            self._assert_bootstrap_denied(dirty_contract_command)

    def test_denies_tagged_roots_with_yaml_document_or_field_smuggling(self):
        fixture = self._bootstrap_fixture()
        root = self._approved_root_bootstrap(fixture)
        tagged_root = fixture["root"].read_text(encoding="utf-8")

        document_tag = "clean-bootstrap-2026-08-17.1"
        second_document = tagged_root.replace(
            "targetRevision: clean-bootstrap-2026-08-15.1",
            f"targetRevision: {document_tag}",
        ) + """--- # second document
{apiVersion: v1, kind: ConfigMap, metadata: {name: smuggled, namespace: argocd}}
"""
        self._tag_bootstrap_root(fixture, second_document, document_tag)
        with self.subTest(input="commented separator and flow ConfigMap"):
            self._assert_bootstrap_denied(root)

        annotations_tag = "clean-bootstrap-2026-08-18.1"
        annotation_smuggling = f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: clean-bootstrap-cluster
  namespace: argocd
  annotations:
    repoURL: ssh://git@github.com/wget-cloud/k8s
    targetRevision: {annotations_tag}
    path: infrastructure/k8s/gitops/clusters/clean-bootstrap/root
spec:
  project: default
  source:
    repoURL: ssh://git@github.com/attacker/k8s
    targetRevision: main
    path: infrastructure/k8s/gitops/clusters/clean-bootstrap/attacker
  destination:
    namespace: argocd
    server: https://kubernetes.default.svc
"""
        self._tag_bootstrap_root(fixture, annotation_smuggling, annotations_tag)
        with self.subTest(input="expected source fields only in metadata annotations"):
            self._assert_bootstrap_denied(root)

    def test_denies_tagged_root_with_automated_sync_policy(self):
        fixture = self._bootstrap_fixture()
        root = self._approved_root_bootstrap(fixture)
        automated_tag = "clean-bootstrap-2026-08-19.1"
        automated_root = fixture["root"].read_text(encoding="utf-8").replace(
            "targetRevision: clean-bootstrap-2026-08-15.1",
            f"targetRevision: {automated_tag}",
        ).replace(
            "  syncPolicy:\n    syncOptions: [CreateNamespace=true]\n",
            "  syncPolicy: {automated: {prune: true, selfHeal: true}}\n",
        )
        self._tag_bootstrap_root(fixture, automated_root, automated_tag)
        self._assert_bootstrap_denied(root)

    def test_relative_bootstrap_paths_are_bound_to_invocation_cwd(self):
        fixture = self._bootstrap_fixture()
        nested = fixture["k8s"] / "nested"
        nested_values = nested / fixture["values"]
        nested_root = nested / fixture["root_path"]
        nested_values.parent.mkdir(parents=True)
        nested_root.parent.mkdir(parents=True)
        nested_values.write_text("server:\n  extraArgs: [--insecure]\n", encoding="utf-8")
        nested_root.write_text(
            """apiVersion: v1
kind: ConfigMap
metadata:
  name: nested-path-shadow
  namespace: argocd
""",
            encoding="utf-8",
        )

        for command in (
            self._relative_helm_bootstrap(fixture),
            self._relative_root_bootstrap(fixture),
        ):
            with self.subTest(command=command):
                self._assert_bootstrap_denied(command, nested)

    def test_gitops_bootstrap_exception_denies_every_near_miss_and_extra_mutation(self):
        fixture = self._bootstrap_fixture()
        helm = self._approved_helm_bootstrap(fixture)
        repository = self._approved_repository_bootstrap(fixture)
        root = self._approved_root_bootstrap(fixture)
        tagged_root = fixture["root"].read_text(encoding="utf-8")
        denied = (
            helm.replace("WGC_GITOPS_BOOTSTRAP_APPROVED=1 ", "", 1),
            helm.replace("WGC_GITOPS_BOOTSTRAP_APPROVED=1", "WGC_GITOPS_BOOTSTRAP_APPROVED=0", 1),
            helm.replace("argo/argo-cd", "bitnami/argo-cd", 1),
            helm.replace("--version 8.0.0", "--version 8.1.0", 1),
            helm.replace("--namespace argocd", "--namespace kube-system", 1),
            helm.replace("--kube-context clean-bootstrap", "--kube-context dev", 1),
            helm.replace(f"--kubeconfig {fixture['kubeconfig']} ", "", 1),
            helm.replace(
                str(fixture["kubeconfig"]),
                f"$(printf %s {fixture['kubeconfig']})",
                1,
            ),
            helm.replace(str(fixture["values_file"]), "infrastructure/k8s/bootstrap/argocd/other-values.yaml", 1),
            helm.replace(" helm ", " /tmp/helm ", 1),
            repository.replace("wget-cloud-k8s-repository", "other-repository", 1),
            repository.replace(
                "argocd.argoproj.io/secret-type=repository",
                "argocd.argoproj.io/secret-type=repo-creds",
                1,
            ),
            repository.replace(
                "url=ssh://git@github.com/wget-cloud/k8s",
                "url=ssh://git@github.com/other/k8s",
                1,
            ),
            repository.replace("--namespace argocd", "--namespace default", 1),
            repository.replace("--context clean-bootstrap", "--context dev", 1),
            repository.replace(
                f"--from-file=sshPrivateKey={fixture['key']}",
                "--from-literal=sshPrivateKey=inline-key-material",
                1,
            ),
            repository.replace(
                str(fixture["key"]),
                f"`printf %s {fixture['key']}`",
                1,
            ),
            repository.replace(" | ", " ; "),
            repository.replace(" | ", " & "),
            repository.replace(" kubectl ", " ./kubectl "),
            root.replace(str(fixture["root"]), "infrastructure/k8s/bootstrap/roots/dev.yaml", 1),
            root + " > /tmp/wgc-bootstrap-output.yaml",
            root + "\nkubectl --context clean-bootstrap delete namespace backend",
            root + " ; kubectl --context clean-bootstrap delete namespace backend",
            "WGC_GITOPS_BOOTSTRAP_APPROVED=1 argocd app sync clean-bootstrap-cluster",
            "WGC_GITOPS_BOOTSTRAP_APPROVED=1 kubectl --context clean-bootstrap delete pod gateway-0",
        )
        for command in denied:
            with self.subTest(command=command):
                self._assert_bootstrap_denied(command)

        self._assert_bootstrap_denied(helm, self.projects["backend"])
        fixture["root"].write_text(
            fixture["root"].read_text(encoding="utf-8").replace(
                "targetRevision: clean-bootstrap-2026-08-15.1",
                "targetRevision: clean-bootstrap-2026-08-16.1",
            ),
            encoding="utf-8",
        )
        self._assert_bootstrap_denied(root)
        fixture["root"].write_text(
            tagged_root.replace(
                "targetRevision: clean-bootstrap-2026-08-15.1",
                "targetRevision: main",
            ),
            encoding="utf-8",
        )
        self._assert_bootstrap_denied(root)
        fixture["root"].write_text(
            tagged_root
            + """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: smuggled-bootstrap-mutation
  namespace: argocd
""",
            encoding="utf-8",
        )
        self._assert_bootstrap_denied(root)
        fixture["root"].write_text(
            tagged_root.replace(
                "repoURL: ssh://git@github.com/wget-cloud/k8s",
                "repoURL: ssh://git@github.com/attacker/k8s\n"
                "    # expected repoURL: ssh://git@github.com/wget-cloud/k8s",
            ),
            encoding="utf-8",
        )
        self._assert_bootstrap_denied(root)

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
        self.assertIn("permissionDecision", output["hookSpecificOutput"])
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("staged diff", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_git_commit_preflight_uses_valid_supplied_workdir_for_non_bootstrap_policy(self):
        target = self.projects["backend"]
        bad = target / "bad-workdir.txt"
        bad.write_text("trailing whitespace   \n", encoding="utf-8")
        self._run(["git", "add", "bad-workdir.txt"], target)
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "git commit -m test",
                    "workdir": str(target),
                },
            },
            self.root,
        )
        self.assertIn("permissionDecision", output["hookSpecificOutput"])
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

    def test_runtime_log_collection_warns_about_scope_and_redaction(self):
        output = self.call(
            "pre-tool",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "kubectl -n backend logs deploy/gateway --since=10m --tail=200"},
            },
            self.projects["backend"],
        )
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("personal data", context)
        self.assertIn("redact", context)

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
        self.record_agent(cwd, "test-maker", "assessment_ready")
        self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "npm test -- --coverage"}, "tool_response": {"exit_code": 0}}, cwd)
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

    def test_positive_final_prose_cannot_replace_structured_review_gates(self):
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
        self.assertIsNone(self.record_agent(cwd, "architect", "proposed"))
        self.assertIsNone(self.record_agent(cwd, "test-maker", "assessment_ready"))
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

        blocked = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-prose-gates",
                "stop_hook_active": False,
                "last_assistant_message": "Reviewer approved; Architecture Guardian approved; QA pass.",
            },
            cwd,
        )
        self.assertIsNotNone(blocked, "positive prose must not deactivate a workflow without structured review artifacts")
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("reviewer", blocked["reason"])
        self.assertIn("architecture", blocked["reason"])
        self.assertIn("qa", blocked["reason"])

    def test_task_creation_requires_structured_gates_without_local_diff(self):
        cwd = self.projects["backend"]
        self.activate_profile(
            "task-creation",
            prompt="Use $wgc-task-creation to analyze and create tasks in GitHub Project #1",
        )
        blocked = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-task-creation-gaps",
                "stop_hook_active": False,
                "last_assistant_message": "Backlog ready",
            },
            cwd,
        )
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("product", blocked["reason"])
        self.assertIn("project-publish", blocked["reason"])
        for role, verdict in (
            ("product-manager", "specified"),
            ("project-manager", "project_ready"),
            ("implementation-auditor", "audited"),
            ("architect", "proposed"),
            ("backlog-reviewer", "approved"),
            ("github-project-operator", "published"),
        ):
            self.record_agent(cwd, role, verdict)
        completed = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-task-creation-complete",
                "stop_hook_active": False,
                "last_assistant_message": "Published and verified",
            },
            cwd,
        )
        self.assertIsNone(completed)

    def test_task_creation_planning_only_does_not_require_publish_gate(self):
        cwd = self.projects["backend"]
        self.activate_profile(
            "task-creation",
            prompt="Use $wgc-task-creation to analyze the backlog without publishing anything",
        )
        for role, verdict in (
            ("product-manager", "specified"),
            ("project-manager", "project_ready"),
            ("implementation-auditor", "audited"),
            ("architect", "proposed"),
            ("backlog-reviewer", "approved"),
        ):
            self.record_agent(cwd, role, verdict)
        completed = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-task-plan-only",
                "stop_hook_active": False,
                "last_assistant_message": "Planning complete",
            },
            cwd,
        )
        self.assertIsNone(completed)

    def test_epic_implementation_requires_scope_reconcile_and_project_sync(self):
        cwd = self.projects["backend"]
        self.activate_profile(
            "epic-implementation",
            prompt="Use $wgc-epic-implementation to implement CRM-EP01 from GitHub Project #1",
        )
        invalid_phase = self.record_agent(cwd, "project-manager", "planned")
        self.assertEqual(invalid_phase["decision"], "block")
        self.assertIn("phase", invalid_phase["reason"])
        invalid_product_phase = self.record_agent(cwd, "product-manager", "accepted")
        self.assertEqual(invalid_product_phase["decision"], "block")
        self.assertIn("phase", invalid_product_phase["reason"])
        for role, verdict, phase in (
            ("product-manager", "accepted", "scope"),
            ("project-manager", "planned", "scope"),
            ("architect", "proposed", ""),
            ("architecture-guardian", "approved", "plan"),
            ("test-maker", "assessment_ready", ""),
            ("implementor", "implemented", ""),
            ("reviewer", "approved", ""),
            ("architecture-guardian", "approved", "diff"),
            ("qa", "pass", ""),
            ("product-manager", "accepted", "outcome"),
            ("project-manager", "progress_updated", "reconcile"),
            ("github-project-operator", "synced", ""),
        ):
            self.record_agent(cwd, role, verdict, phase)
        completed = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-epic-complete",
                "stop_hook_active": False,
                "last_assistant_message": "Epic wave reconciled",
            },
            cwd,
        )
        self.assertIsNone(completed)

    def test_successful_bugfix_requires_structured_rca_and_regression_gates(self):
        cwd = self.projects["backend"]
        self.activate_bugfix()
        source = cwd / "src" / "price.ts"
        source.parent.mkdir()
        source.write_text("export const total = 1;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/price.ts\n+x\n*** End Patch"},
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
        for role, verdict, phase in (
            ("bug-triage", "triaged", ""),
            ("bug-investigator", "evidence_ready", "evidence"),
            ("bug-investigator", "root_cause_supported", "rca"),
            ("root-cause-reviewer", "approved", ""),
            ("reproducer", "reproduced", ""),
            ("architect", "planned", ""),
            ("architecture-guardian", "approved", "plan"),
            ("test-maker", "assessment_ready", ""),
            ("implementor", "implemented", ""),
            ("reviewer", "approved", ""),
            ("architecture-guardian", "approved", "diff"),
            ("qa", "pass", ""),
        ):
            self.record_agent(cwd, role, verdict, phase)
        self.call("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "npm test -- --coverage"}, "tool_response": {"exit_code": 0}}, cwd)
        self.record_agent(cwd, "reviewer", "approved")
        self.record_agent(cwd, "architecture-guardian", "approved", "diff")
        self.record_agent(cwd, "qa", "pass")
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-bugfix-success",
                "stop_hook_active": False,
                "last_assistant_message": "Bug fixed.",
            },
            cwd,
        )
        self.assertIsNone(output)

    def test_ui_bugfix_adds_browser_check_and_agent_gate(self):
        cwd = self.projects["frontend"]
        self.activate_bugfix("frontend", "Исправь баг UI: форма не сохраняется после reconnect")
        source = cwd / "src" / "form.tsx"
        source.parent.mkdir()
        source.write_text("export const Form = () => null;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/form.tsx\n+x\n*** End Patch"},
                "tool_response": {"ok": True},
            },
            cwd,
        )
        for command in ("npm test -- --coverage", "npm run type-check"):
            self.call(
                "post-tool",
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "tool_response": {"exit_code": 0},
                },
                cwd,
            )
        output = self.call(
            "stop",
            {
                "hook_event_name": "Stop",
                "turn_id": "turn-ui-bugfix",
                "stop_hook_active": False,
                "last_assistant_message": "Done",
            },
            cwd,
        )
        self.assertIn("browser", output["reason"])

    def test_deployment_bugfix_requires_smoke_and_deployment_gate(self):
        cwd = self.projects["backend"]
        self.activate_bugfix("backend", "Use $wgc-bugfix to fix this production incident and deploy the approved revision")
        source = cwd / "src" / "health.ts"
        source.parent.mkdir()
        source.write_text("export const healthy = true;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/health.ts\n+x\n*** End Patch"},
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
                "turn_id": "turn-deployment-bugfix",
                "stop_hook_active": False,
                "last_assistant_message": "Ready for delivery",
            },
            cwd,
        )
        self.assertIn("smoke", output["reason"])
        self.assertIn("deployment", output["reason"])

    def test_cross_tenant_api_bugfix_requires_security_and_contract_gates(self):
        cwd = self.projects["backend"]
        self.activate_bugfix(
            "backend",
            "Исправь production API баг: роль manager иногда получает данные другого tenant",
        )
        source = cwd / "src" / "client.ts"
        source.parent.mkdir()
        source.write_text("export const client = {};\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/client.ts\n+x\n*** End Patch"},
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
                "turn_id": "turn-security-contract-bugfix",
                "stop_hook_active": False,
                "last_assistant_message": "Fix complete",
            },
            cwd,
        )
        self.assertIn("security", output["reason"])
        self.assertIn("contract", output["reason"])

    def test_bugfix_write_invalidates_diff_gates_but_preserves_plan_and_rca(self):
        cwd = self.projects["backend"]
        self.activate_bugfix()
        source = cwd / "src" / "price.ts"
        source.parent.mkdir()
        source.write_text("export const total = 1;\n", encoding="utf-8")
        self.call(
            "post-tool",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "*** Begin Patch\n*** Add File: src/price.ts\n+x\n*** End Patch"},
                "tool_response": {"ok": True},
            },
            cwd,
        )
        self.record_agent(cwd, "bug-investigator", "root_cause_supported", "rca")
        self.record_agent(cwd, "architect", "planned")
        self.record_agent(cwd, "architecture-guardian", "approved", "plan")
        self.record_agent(cwd, "reviewer", "approved")
        self.record_agent(cwd, "architecture-guardian", "approved", "diff")
        self.record_agent(cwd, "qa", "pass")
        source.write_text("export const total = 2;\n", encoding="utf-8")
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
        state_path = next((self.data / "hook-state").glob("*.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        results = {(item["role"], item.get("phase")) for item in state["subagent_results"]}
        self.assertIn(("bug-investigator", "rca"), results)
        self.assertIn(("architecture-guardian", "plan"), results)
        self.assertNotIn(("architecture-guardian", "diff"), results)
        self.assertFalse(any(role in {"reviewer", "qa"} for role, _ in results))

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
        self.record_agent(cwd, "test-maker", "assessment_ready")
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
