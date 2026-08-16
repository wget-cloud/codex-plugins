import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "wgc_hooks.py"
HOOKS_JSON = SCRIPT.parent / "hooks.json"
PLUGIN_JSON = SCRIPT.parent.parent / ".codex-plugin" / "plugin.json"
WORKDIR_ABSENT = object()
STAGED_SYNC_REVISION = "6c2c3e9dadde2eec3d13fde830bc6db0392b13b8"
STAGED_SYNC_APPS = (
    "twc-wise-finch-cluster",
    "twc-wise-finch-core",
    "twc-wise-finch-local-path-storage",
    "twc-wise-finch-local-path-smoke",
    "local-path-storage-smoke",
)
STAGED_SYNC_RUNNER = "/usr/local/libexec/wget-cloud-staged-sync/runner.py"
STAGED_SYNC_KUBECONFIG = "/usr/local/etc/wget-cloud-staged-sync/twc-wise-finch.kubeconfig"
STAGED_SYNC_ENV_SHA256 = "540f3b55630775d9b2a3aa08cbbe87928ea62c615cd4d13c11f68e2b4571aebc"
STAGED_SYNC_PYTHON_SHA256 = "506cb2ddd061e2992c8ee7c53853340688b53d9fcec94c3aa936524cea5b40cb"
STAGED_SYNC_SYSTEM_ANCESTORS = ("/", "/usr", "/usr/bin")


def staged_sync_runner_command(stage, app):
    return (
        "/usr/bin/env -i WGC_GITOPS_STAGED_SYNC_APPROVED=1 HOME=/var/empty "
        "PATH=/usr/bin:/bin LANG=C LC_ALL=C "
        f"KUBECONFIG={STAGED_SYNC_KUBECONFIG} /usr/bin/python3 {STAGED_SYNC_RUNNER} "
        f"--stage {stage} --app {app} --revision {STAGED_SYNC_REVISION}"
    )


def system_binary_evidence(path, digest, link_count):
    identity = {
        "device": 1,
        "inode": 100 if path == "/usr/bin/env" else 101,
        "uid": 0,
        "gid": 0,
        "mode": "0755",
        "linkCount": link_count,
    }
    return {
        "path": path,
        "canonicalPath": path,
        "kind": "file",
        "symlink": False,
        "owner": "root",
        "group": "wheel",
        "mode": "0755",
        "linkCount": link_count,
        "sha256": digest,
        "pathIdentity": deepcopy(identity),
        "descriptorIdentity": deepcopy(identity),
        "postDescriptorIdentity": deepcopy(identity),
        "descriptorSha256": digest,
        "postDescriptorSha256": digest,
        "descriptorVerified": True,
        "effectiveWritable": False,
    }


def system_ancestor_evidence(path):
    identity = {
        "device": 1,
        "inode": {"/": 1, "/usr": 2, "/usr/bin": 3}[path],
        "uid": 0,
        "gid": 0,
        "mode": "0755",
    }
    return {
        "path": path,
        "canonicalPath": path,
        "kind": "directory",
        "symlink": False,
        "owner": "root",
        "group": "wheel",
        "mode": "0755",
        "acl": [],
        "pathIdentity": deepcopy(identity),
        "postPathIdentity": deepcopy(identity),
        "identityVerified": True,
        "effectiveWritable": False,
        "effectiveDeletable": False,
    }
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
        root = roots / "twc-wise-finch.yaml"
        root.write_text(
            """apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: twc-wise-finch-cluster
  namespace: argocd
  labels:
    wget-cloud.io/profile: twc-wise-finch
spec:
  project: default
  source:
    repoURL: ssh://git@github.com/wget-cloud/k8s
    targetRevision: twc-wise-finch-ingress-2026-08-15.1
    path: infrastructure/k8s/gitops/clusters/twc-wise-finch/root
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
                "infrastructure/k8s/bootstrap/roots/twc-wise-finch.yaml",
            ],
        )
        self._run(["git", "tag", "twc-wise-finch-ingress-2026-08-15.1"], k8s)

        kubeconfig = Path(self.temp.name) / "twc-wise-finch.kubeconfig"
        kubeconfig.write_text(
            """apiVersion: v1
kind: Config
current-context: twc-wise-finch
contexts:
- name: twc-wise-finch
  context:
    cluster: twc-wise-finch
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
            "root_path": "infrastructure/k8s/bootstrap/roots/twc-wise-finch.yaml",
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
            "--kube-context twc-wise-finch upgrade --install argo-cd argo/argo-cd "
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
        common = f"--kubeconfig {fixture['kubeconfig']} --context twc-wise-finch"
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
            f"--context twc-wise-finch --namespace argocd apply --filename={fixture['root']}"
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
        self.assertEqual(state["version"], 2)
        self.assertEqual(state["profile"], "bugfix")
        self.assertTrue(state["bugfix_routes"]["ui"])
        self.assertTrue(state["bugfix_routes"]["security"])
        self.assertTrue(state["bugfix_routes"]["contract"])
        self.assertTrue(state["bugfix_routes"]["incident"])
        self.assertTrue(state["bugfix_routes"]["gitops"])
        self.assertTrue(state["bugfix_routes"]["deployment"])
        self.assertNotIn("another tenant", raw)

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

    def test_allows_only_exact_human_approved_argocd_helm_bootstrap(self):
        fixture = self._bootstrap_fixture()
        self.assertIsNone(self._bootstrap_command(self._approved_helm_bootstrap(fixture)))

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
                absolute_root + " ; kubectl --context twc-wise-finch delete namespace backend",
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
            root + " ; kubectl --context twc-wise-finch delete namespace backend",
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
        shadow_tag = "twc-wise-finch-shadow-2026-08-20.1"
        (roots / "twc-wise-finch.yaml").write_text(
            f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: twc-wise-finch-cluster
  namespace: argocd
  labels:
    wget-cloud.io/profile: twc-wise-finch
spec:
  project: default
  source:
    repoURL: ssh://git@github.com/wget-cloud/k8s
    targetRevision: {shadow_tag}
    path: infrastructure/k8s/gitops/clusters/twc-wise-finch/root
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
                "infrastructure/k8s/bootstrap/roots/twc-wise-finch.yaml",
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
        duplicate_root = duplicate_roots / "twc-wise-finch.yaml"
        shutil.copyfile(fixture["makefile"], duplicate_makefile)
        shutil.copyfile(fixture["values_file"], duplicate_values)
        shutil.copyfile(fixture["root"], duplicate_root)

        coordinator_owned = (
            "k8s/infrastructure/k8s/bootstrap/argocd/makefile",
            "k8s/infrastructure/k8s/bootstrap/argocd/values.yaml",
            "k8s/infrastructure/k8s/bootstrap/roots/twc-wise-finch.yaml",
            "infrastructure/k8s/bootstrap/argocd/makefile",
            "infrastructure/k8s/bootstrap/argocd/values.yaml",
            "infrastructure/k8s/bootstrap/roots/twc-wise-finch.yaml",
        )
        self._git_commit(self.root, coordinator_owned)
        self._run(["git", "tag", "twc-wise-finch-ingress-2026-08-15.1"], self.root)

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

        document_tag = "twc-wise-finch-ingress-2026-08-17.1"
        second_document = tagged_root.replace(
            "targetRevision: twc-wise-finch-ingress-2026-08-15.1",
            f"targetRevision: {document_tag}",
        ) + """--- # second document
{apiVersion: v1, kind: ConfigMap, metadata: {name: smuggled, namespace: argocd}}
"""
        self._tag_bootstrap_root(fixture, second_document, document_tag)
        with self.subTest(input="commented separator and flow ConfigMap"):
            self._assert_bootstrap_denied(root)

        annotations_tag = "twc-wise-finch-ingress-2026-08-18.1"
        annotation_smuggling = f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: twc-wise-finch-cluster
  namespace: argocd
  annotations:
    repoURL: ssh://git@github.com/wget-cloud/k8s
    targetRevision: {annotations_tag}
    path: infrastructure/k8s/gitops/clusters/twc-wise-finch/root
spec:
  project: default
  source:
    repoURL: ssh://git@github.com/attacker/k8s
    targetRevision: main
    path: infrastructure/k8s/gitops/clusters/twc-wise-finch/attacker
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
        automated_tag = "twc-wise-finch-ingress-2026-08-19.1"
        automated_root = fixture["root"].read_text(encoding="utf-8").replace(
            "targetRevision: twc-wise-finch-ingress-2026-08-15.1",
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
            helm.replace("--kube-context twc-wise-finch", "--kube-context dev", 1),
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
            repository.replace("--context twc-wise-finch", "--context dev", 1),
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
            root + "\nkubectl --context twc-wise-finch delete namespace backend",
            root + " ; kubectl --context twc-wise-finch delete namespace backend",
            "WGC_GITOPS_BOOTSTRAP_APPROVED=1 argocd app sync twc-wise-finch-cluster",
            "WGC_GITOPS_BOOTSTRAP_APPROVED=1 kubectl --context twc-wise-finch delete pod gateway-0",
        )
        for command in denied:
            with self.subTest(command=command):
                self._assert_bootstrap_denied(command)

        self._assert_bootstrap_denied(helm, self.projects["backend"])
        fixture["root"].write_text(
            fixture["root"].read_text(encoding="utf-8").replace(
                "targetRevision: twc-wise-finch-ingress-2026-08-15.1",
                "targetRevision: twc-wise-finch-ingress-2026-08-16.1",
            ),
            encoding="utf-8",
        )
        self._assert_bootstrap_denied(root)
        fixture["root"].write_text(
            tagged_root.replace(
                "targetRevision: twc-wise-finch-ingress-2026-08-15.1",
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
            ("test-maker", "tests_ready", ""),
            ("implementor", "implemented", ""),
            ("reviewer", "approved", ""),
            ("architecture-guardian", "approved", "diff"),
            ("qa", "pass", ""),
        ):
            self.record_agent(cwd, role, verdict, phase)
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


class StagedSyncRunnerHookContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("wgc_hooks_runner_contract", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_parser_accepts_only_exact_root_owned_stage_commands(self):
        parser = getattr(self.module, "parse_staged_sync_runner_command", None)
        self.assertIsNotNone(parser, "root-owned staged-sync parser contract is missing")
        for stage, app in enumerate(STAGED_SYNC_APPS, start=1):
            with self.subTest(stage=stage, app=app):
                self.assertEqual(
                    parser(staged_sync_runner_command(stage, app)),
                    (stage, app, STAGED_SYNC_REVISION),
                )

    def test_parser_rejects_raw_argocd_ingress_and_command_near_misses(self):
        parser = getattr(self.module, "parse_staged_sync_runner_command", None)
        self.assertIsNotNone(parser, "root-owned staged-sync parser contract is missing")
        exact = staged_sync_runner_command(1, STAGED_SYNC_APPS[0])
        denied = {
            "raw-argocd": (
                "WGC_GITOPS_STAGED_SYNC_APPROVED=1 KUBECONFIG=/tmp/kubeconfig "
                "/tmp/argocd --core app sync twc-wise-finch-cluster"
            ),
            "ingress": staged_sync_runner_command(6, "twc-wise-finch-ingress"),
            "stage-app-mismatch": staged_sync_runner_command(2, STAGED_SYNC_APPS[0]),
            "stage-zero": staged_sync_runner_command(0, STAGED_SYNC_APPS[0]),
            "missing-env-i": exact.replace("/usr/bin/env -i ", "", 1),
            "extra-environment": exact.replace("HOME=/var/empty", "HOME=/var/empty FOO=bar", 1),
            "reordered-environment": exact.replace(
                "PATH=/usr/bin:/bin LANG=C", "LANG=C PATH=/usr/bin:/bin", 1
            ),
            "wrong-home": exact.replace("HOME=/var/empty", "HOME=/tmp"),
            "wrong-path": exact.replace("PATH=/usr/bin:/bin", "PATH=/usr/local/bin:/usr/bin:/bin"),
            "wrong-kubeconfig": exact.replace(STAGED_SYNC_KUBECONFIG, "/tmp/kubeconfig"),
            "wrong-python": exact.replace("/usr/bin/python3", "/usr/local/bin/python3"),
            "wrong-runner": exact.replace(STAGED_SYNC_RUNNER, "/tmp/runner.py"),
            "wrong-revision": exact.replace(STAGED_SYNC_REVISION, "1" * 40),
            "extra-flag": exact + " --timeout 601",
            "semicolon": exact + "; id",
            "and": exact + " && id",
            "or": exact + " || id",
            "pipe": exact + " | id",
            "newline": exact + "\nid",
            "subshell": exact + " $(id)",
        }
        for case, command in denied.items():
            with self.subTest(case=case):
                self.assertIsNone(parser(command))

    def test_system_binary_verifier_requires_fd_identity_hash_and_effective_nonwrite(self):
        verifier = getattr(self.module, "pinned_system_binary", None)
        self.assertIsNotNone(
            verifier,
            "PreToolUse must expose a fail-closed descriptor verifier for env and python3",
        )
        contracts = (
            ("/usr/bin/env", STAGED_SYNC_ENV_SHA256, 1),
            ("/usr/bin/python3", STAGED_SYNC_PYTHON_SHA256, 78),
        )
        for path, digest, link_count in contracts:
            evidence = system_binary_evidence(path, digest, link_count)
            with self.subTest(binary=path, case="valid"):
                self.assertTrue(
                    verifier(
                        path,
                        digest,
                        0o755,
                        link_count,
                        inspect_binary=lambda requested, evidence=evidence: deepcopy(evidence),
                    )
                )

            mutations = {
                "canonical-alias": ("canonicalPath", "/tmp/replaced"),
                "symlink": ("symlink", True),
                "owner": ("owner", "estev"),
                "group": ("group", "staff"),
                "mode": ("mode", "0775"),
                "link-count": ("linkCount", link_count + 1),
                "effective-write": ("effectiveWritable", True),
                "descriptor-unverified": ("descriptorVerified", False),
                "path-fd-identity": (
                    "descriptorIdentity",
                    {**evidence["descriptorIdentity"], "inode": 999999},
                ),
                "descriptor-owner": (
                    "descriptorIdentity",
                    {**evidence["descriptorIdentity"], "uid": 501},
                ),
                "descriptor-group": (
                    "descriptorIdentity",
                    {**evidence["descriptorIdentity"], "gid": 20},
                ),
                "descriptor-mode": (
                    "descriptorIdentity",
                    {**evidence["descriptorIdentity"], "mode": "0775"},
                ),
                "descriptor-link-count": (
                    "descriptorIdentity",
                    {**evidence["descriptorIdentity"], "linkCount": link_count + 1},
                ),
                "post-fstat-identity": (
                    "postDescriptorIdentity",
                    {**evidence["descriptorIdentity"], "inode": 999998},
                ),
                "descriptor-hash": ("descriptorSha256", "0" * 64),
                "post-descriptor-hash": ("postDescriptorSha256", "0" * 64),
                "path-hash": ("sha256", "0" * 64),
            }
            for case, (field, value) in mutations.items():
                broken = deepcopy(evidence)
                broken[field] = value
                with self.subTest(binary=path, case=case):
                    self.assertFalse(
                        verifier(
                            path,
                            digest,
                            0o755,
                            link_count,
                            inspect_binary=lambda requested, broken=broken: deepcopy(broken),
                        )
                    )

    def test_system_ancestor_chain_pins_ls_first_and_accepts_only_the_exact_chain(self):
        verifier = getattr(self.module, "pinned_system_ancestor_chain", None)
        self.assertIsNotNone(
            verifier,
            "system ancestor attestation is required before staged-sync can be allowed",
        )
        for binary in ("/usr/bin/env", "/usr/bin/python3"):
            events = []
            evidence = {
                path: system_ancestor_evidence(path) for path in STAGED_SYNC_SYSTEM_ANCESTORS
            }

            def inspect(path):
                events.append(f"inspect:{path}")
                return deepcopy(evidence[path])

            with self.subTest(binary=binary):
                self.assertTrue(
                    verifier(
                        binary,
                        inspect_ancestor=inspect,
                        attest_ls=lambda: events.append("ls") or True,
                    )
                )
                self.assertEqual(
                    events,
                    ["ls", "inspect:/", "inspect:/usr", "inspect:/usr/bin"],
                )

        self.assertFalse(
            verifier(
                "/usr/bin/ruby",
                inspect_ancestor=lambda path: system_ancestor_evidence(path),
                attest_ls=lambda: True,
            )
        )

    def test_system_ancestor_chain_rejects_unsafe_acl_identity_and_toctou_evidence(self):
        verifier = getattr(self.module, "pinned_system_ancestor_chain", None)
        self.assertIsNotNone(verifier, "system ancestor attestation contract is missing")
        base = {path: system_ancestor_evidence(path) for path in STAGED_SYNC_SYSTEM_ANCESTORS}
        mutations = {}
        for case, field, value in (
            ("symlink", "symlink", True),
            ("canonical-alias", "canonicalPath", "/tmp/usr"),
            ("wrong-owner", "owner", "estev"),
            ("wrong-group", "group", "staff"),
            ("group-write-mode", "mode", "0775"),
            ("world-write-mode", "mode", "0777"),
            ("effective-write", "effectiveWritable", True),
            ("effective-delete", "effectiveDeletable", True),
            ("identity-unverified", "identityVerified", False),
            (
                "post-lstat-toctou",
                "postPathIdentity",
                {**base["/usr"]["pathIdentity"], "inode": 999999},
            ),
            (
                "unexpected-read-acl",
                "acl",
                [
                    {
                        "principal": "user:estev",
                        "type": "allow",
                        "permissions": ["read"],
                    }
                ],
            ),
            (
                "write-acl",
                "acl",
                [
                    {
                        "principal": "user:estev",
                        "type": "allow",
                        "permissions": ["write", "writeattr", "writeextattr"],
                    }
                ],
            ),
            (
                "delete-acl",
                "acl",
                [
                    {
                        "principal": "user:estev",
                        "type": "allow",
                        "permissions": ["delete", "delete_child"],
                    }
                ],
            ),
        ):
            broken = deepcopy(base)
            broken["/usr"][field] = value
            mutations[case] = broken

        wrong_uid = deepcopy(base)
        wrong_uid["/usr"]["pathIdentity"]["uid"] = 501
        wrong_uid["/usr"]["postPathIdentity"]["uid"] = 501
        mutations["wrong-uid"] = wrong_uid
        wrong_gid = deepcopy(base)
        wrong_gid["/usr"]["pathIdentity"]["gid"] = 20
        wrong_gid["/usr"]["postPathIdentity"]["gid"] = 20
        mutations["wrong-gid"] = wrong_gid
        identity_mode = deepcopy(base)
        identity_mode["/usr"]["pathIdentity"]["mode"] = "0775"
        identity_mode["/usr"]["postPathIdentity"]["mode"] = "0775"
        mutations["identity-mode"] = identity_mode
        missing = deepcopy(base)
        missing.pop("/usr")
        mutations["missing-evidence"] = missing

        for case, evidence in mutations.items():
            with self.subTest(case=case):
                self.assertFalse(
                    verifier(
                        "/usr/bin/env",
                        inspect_ancestor=lambda path, evidence=evidence: deepcopy(
                            evidence.get(path, {})
                        ),
                        attest_ls=lambda: True,
                    )
                )

        inspected = []
        self.assertFalse(
            verifier(
                "/usr/bin/env",
                inspect_ancestor=lambda path: inspected.append(path) or system_ancestor_evidence(path),
                attest_ls=lambda: False,
            )
        )
        self.assertEqual(inspected, [], "ancestor evidence was read before /bin/ls attestation")

    def test_system_ancestor_chain_accepts_the_current_safe_host(self):
        verifier = getattr(self.module, "pinned_system_ancestor_chain", None)
        self.assertIsNotNone(verifier, "system ancestor attestation contract is missing")
        self.assertTrue(verifier("/usr/bin/env"))
        self.assertTrue(verifier("/usr/bin/python3"))

    def test_pretooluse_pins_ls_then_both_system_ancestor_chains_before_allow(self):
        command = staged_sync_runner_command(1, STAGED_SYNC_APPS[0])
        events = []
        with mock.patch.object(
            self.module,
            "pinned_ls_before_acl",
            side_effect=lambda: events.append("ls") or True,
        ), mock.patch.object(
            self.module,
            "pinned_system_ancestor_chain",
            side_effect=lambda path: events.append(f"ancestor:{path}") or True,
            create=True,
        ), mock.patch.object(
            self.module,
            "pinned_system_binary",
            side_effect=lambda path, *args: events.append(f"binary:{path}") or True,
        ), mock.patch.object(self.module, "pinned_root_file", return_value=True):
            self.assertTrue(self.module.approved_gitops_staged_sync(command))
        self.assertEqual(
            events[:5],
            [
                "ls",
                "ancestor:/usr/bin/env",
                "ancestor:/usr/bin/python3",
                "binary:/usr/bin/env",
                "binary:/usr/bin/python3",
            ],
        )

        for failed_gate in ("ls", "ancestor:/usr/bin/env", "ancestor:/usr/bin/python3"):
            events = []

            def gate(name):
                events.append(name)
                return name != failed_gate

            with self.subTest(failed_gate=failed_gate), mock.patch.object(
                self.module,
                "pinned_ls_before_acl",
                side_effect=lambda: gate("ls"),
            ), mock.patch.object(
                self.module,
                "pinned_system_ancestor_chain",
                side_effect=lambda path: gate(f"ancestor:{path}"),
                create=True,
            ), mock.patch.object(
                self.module,
                "pinned_system_binary",
                return_value=True,
            ), mock.patch.object(self.module, "pinned_root_file", return_value=True):
                self.assertIsNotNone(
                    self.module.command_violation(
                        command,
                        Path("/tmp"),
                        Path("/tmp"),
                        Path("/tmp"),
                    )
                )

    def test_pretooluse_allows_runner_only_after_both_system_binaries_are_attested(self):
        command = staged_sync_runner_command(1, STAGED_SYNC_APPS[0])
        expected_calls = [
            mock.call("/usr/bin/env", STAGED_SYNC_ENV_SHA256, 0o755, 1),
            mock.call("/usr/bin/python3", STAGED_SYNC_PYTHON_SHA256, 0o755, 78),
        ]
        with mock.patch.object(self.module, "pinned_root_file", return_value=True), mock.patch.object(
            self.module,
            "pinned_ls_before_acl",
            return_value=True,
        ), mock.patch.object(
            self.module,
            "pinned_system_ancestor_chain",
            return_value=True,
            create=True,
        ), mock.patch.object(
            self.module,
            "pinned_system_binary",
            return_value=True,
            create=True,
        ) as verifier:
            self.assertTrue(self.module.approved_gitops_staged_sync(command))
            self.assertEqual(verifier.call_count, 2)
            verifier.assert_has_calls(expected_calls, any_order=True)

        for failed_binary in ("/usr/bin/env", "/usr/bin/python3"):
            with self.subTest(failed_binary=failed_binary), mock.patch.object(
                self.module,
                "pinned_root_file",
                return_value=True,
            ), mock.patch.object(
                self.module,
                "pinned_ls_before_acl",
                return_value=True,
            ), mock.patch.object(
                self.module,
                "pinned_system_ancestor_chain",
                return_value=True,
                create=True,
            ), mock.patch.object(
                self.module,
                "pinned_system_binary",
                side_effect=lambda path, *args: path != failed_binary,
                create=True,
            ):
                violation = self.module.command_violation(
                    command,
                    Path("/tmp"),
                    Path("/tmp"),
                    Path("/tmp"),
                )
                self.assertIsNotNone(
                    violation,
                    f"PreToolUse allowed the runner with unattested {failed_binary}",
                )

    def test_command_policy_delegates_exact_runner_before_argocd_blanket_deny(self):
        command = staged_sync_runner_command(1, STAGED_SYNC_APPS[0])
        with mock.patch.object(
            self.module,
            "approved_gitops_staged_sync",
            return_value=True,
        ) as policy:
            self.assertIsNone(
                self.module.command_violation(command, Path("/tmp"), Path("/tmp"), Path("/tmp"))
            )
            policy.assert_called_once()

    def test_raw_argocd_mutation_remains_denied(self):
        violation = self.module.command_violation(
            "argocd app sync twc-wise-finch-cluster",
            Path("/tmp"),
            Path("/tmp"),
            Path("/tmp"),
        )
        self.assertIsNotNone(violation)


if __name__ == "__main__":
    unittest.main()
