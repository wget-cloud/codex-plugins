"""Protected failing-first lifecycle, gate, and delivery attack corpus (M-001..M-011)."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[2]
SCRIPT = Path(os.environ.get("WGC_MAINTAINER_TARGET_ROOT", str(PLUGIN))) / "hooks" / "maintainer_hooks.py"


def load_hooks():
    spec = importlib.util.spec_from_file_location("maintainer_hooks", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HookAttackContract(unittest.TestCase):
    """Every test is an executable security invariant, never prose matching."""

    def setUp(self):
        self.hooks = load_hooks()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "codex-plugins"
        self.root.mkdir()
        self.data = Path(self.temp.name) / "state"
        self.execute(["git", "init", "-q", "-b", "main"])
        self.execute(["git", "config", "user.name", "Test"])
        self.execute(["git", "config", "user.email", "test@example.invalid"])
        (self.root / ".agents/plugins").mkdir(parents=True)
        (self.root / "plugins/sample/.codex-plugin").mkdir(parents=True)
        (self.root / "AGENTS.md").write_text("fixture\n")
        (self.root / ".agents/plugins/marketplace.json").write_text('{"plugins":[]}')
        (self.root / "plugins/sample/.codex-plugin/plugin.json").write_text('{"name":"sample","version":"1.0.0"}')
        (self.root / "tests").mkdir()
        (self.root / "tests/protected.py").write_text("baseline\n")
        self.execute(["git", "add", "."]); self.execute(["git", "commit", "-qm", "fixture"])
        self.execute(["git", "remote", "add", "origin", "https://example.invalid/repo.git"])
        self.execute(["git", "update-ref", "refs/remotes/origin/main", self.out(["git", "rev-parse", "HEAD"])])
        self.agent = 0

    def tearDown(self): self.temp.cleanup()
    def execute(self, argv): return subprocess.run(argv, cwd=self.root, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    def out(self, argv): return self.execute(argv).stdout.strip()
    def call(self, action, **payload):
        env = dict(os.environ, PLUGIN_DATA=str(self.data))
        request = {"session_id":"s", "cwd":str(self.root), **payload}
        result = subprocess.run([sys.executable, str(SCRIPT), action], input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else None
    def denied(self, command):
        value = self.call("pre-tool", hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command":command})
        self.assertIsNotNone(value, command)
        self.assertEqual("deny", value["hookSpecificOutput"]["permissionDecision"], command)
    def activate(self, prompt="$wgc-plugin-maintenance audit plugin hooks"):
        return self.call("prompt-submit", hook_event_name="UserPromptSubmit", turn_id="t", prompt=prompt)
    def start(self, agent="a", role="auditor"):
        return self.call("subagent-start", hook_event_name="SubagentStart", agent_id=agent, assigned_role=role, task_name=role.replace("-", "_"))
    def record(self, agent, role, verdict):
        self.start(agent, role)
        revision = self.hooks.worktree_hash(self.root)
        return self.call("subagent-stop", hook_event_name="SubagentStop", agent_id=agent, last_assistant_message="WGC_MAINTAINER_RESULT: " + json.dumps({"role":role,"verdict":verdict,"input_revision":revision}))
    def item(self, item_id, depends_on):
        return {"id":item_id,"summary":"safe change","severity":"low","benefit":"test","effort":"small","evidence":["sanitized fixture"],"paths":["docs/"],"acceptance":["test"],"tests":["test"],"shadow_eval":["test"],"risks":["none"],"compatibility":"compatible","depends_on":depends_on,"semver":"patch","self_change":False}

    def test_m001_explicit_activation_rejects_generic_quoted_and_substring_mentions(self):
        for prompt in ("fix this", "quoted '$wgc-plugin-maintenance' only", "mywgc-plugin-maintenancex", "plugin maintenance is nice"):
            with self.subTest(prompt=prompt): self.assertIsNone(self.activate(prompt))
        self.assertIsNotNone(self.activate("$wgc-plugin-maintenance audit the plugin"))

    def test_m002_unknown_or_missing_subagent_start_never_creates_role_evidence(self):
        self.activate()
        marker = "WGC_MAINTAINER_RESULT: " + json.dumps({"role":"auditor","verdict":"audited","input_revision":self.hooks.worktree_hash(self.root)})
        for agent in (None, "unknown"):
            payload = {"hook_event_name":"SubagentStop", "last_assistant_message":marker}
            if agent is not None: payload["agent_id"] = agent
            result = self.call("subagent-stop", **payload)
            self.assertTrue(result and "reason" in result)

    def test_m003_lifecycle_provenance_rejects_spoof_same_agent_bad_order_and_revision(self):
        self.activate(); self.start("same", "auditor")
        revision = self.hooks.worktree_hash(self.root)
        for role, verdict, agent, rev in (("architect","proposed","same",revision), ("auditor","audited","same","0"*64), ("auditor","audited","spoof",revision)):
            marker = "WGC_MAINTAINER_RESULT: " + json.dumps({"role":role,"verdict":verdict,"input_revision":rev})
            result = self.call("subagent-stop", hook_event_name="SubagentStop", agent_id=agent, last_assistant_message=marker)
            self.assertTrue(result and "reason" in result)

    def test_m004_dependency_approval_requires_transitive_closure(self):
        self.activate(); self.record("auditor", "auditor", "audited"); self.record("architect", "architect", "proposed")
        proposal={"baseline_head":self.hooks.git_head(self.root),"dirty_fingerprint":self.hooks.dirty_fingerprint(self.root),"items":[self.item("M-1",["M-2"]),self.item("M-2",["M-3"]),self.item("M-3",[])]}
        response=self.call("stop", hook_event_name="Stop", turn_id="proposal", last_assistant_message="WGC_MAINTENANCE_PROPOSAL: "+json.dumps(proposal))
        proposal_id=re.search(r"registered as ([0-9a-f]{16})", response["reason"]).group(1)
        for selected in ("M-1", "M-1,M-2"):
            with self.subTest(selected=selected):
                result=self.call("prompt-submit", hook_event_name="UserPromptSubmit", turn_id=selected, prompt=f"APPROVE_WGC_PLUGIN_CHANGE={proposal_id}:{selected}")
                self.assertIsNotNone(result)
                self.assertEqual("Maintenance approval rejected", result.get("systemMessage"), "incomplete direct/transitive dependency closure was accepted")

    def test_m005_protected_test_paths_reject_dirty_shared_missing_and_extra_fingerprints(self):
        self.activate()
        self.assertTrue(hasattr(self.hooks, "validate_protected_tests"))
        digest = self.hooks.file_fingerprint(self.root / "tests/protected.py")
        for paths in ({}, {"tests/protected.py":"missing"}, {"tests/protected.py":digest,"tests/extra.py":digest}, {"tests": "directory"}):
            with self.subTest(paths=paths):
                self.assertTrue(self.hooks.validate_protected_tests(self.root, paths))

    def test_m005_remediation_test_maker_cannot_drop_prior_protected_paths_but_may_refresh_a_retained_hash(self):
        extra=self.root/"tests/other.py"; extra.write_text("other baseline\n")
        initial={"tests/protected.py":self.hooks.file_fingerprint(self.root/"tests/protected.py"),"tests/other.py":self.hooks.file_fingerprint(extra)}
        revision=self.hooks.worktree_hash(self.root)
        state={"active":True,"change_approval":{"paths":["tests/"]},"protected_tests":dict(initial),"role_results":[
            {"role":"auditor","verdict":"audited"},{"role":"architect","verdict":"proposed"},{"role":"test-maker","verdict":"baseline_ready"},{"role":"implementor","verdict":"implemented"},{"role":"reviewer","verdict":"changes_requested"},
        ],"subagent_inputs":{"remediation":{"role":"test-maker","revision":revision}}}
        original=(self.hooks.state_for,self.hooks.save)
        self.hooks.state_for=lambda payload, root:state; self.hooks.save=lambda *args:None
        def marker(paths):
            protected="WGC_MAINTAINER_PROTECTED_TESTS: "+json.dumps({"paths":paths})
            result="WGC_MAINTAINER_RESULT: "+json.dumps({"role":"test-maker","verdict":"baseline_ready","input_revision":revision})
            return protected+"\n"+result
        try:
            incomplete={"tests/protected.py":initial["tests/protected.py"]}
            denied=self.hooks.handle_stop_agent({"agent_id":"remediation","last_assistant_message":marker(incomplete)},self.root)
            self.assertEqual("block",denied and denied.get("decision"))
            self.assertEqual(initial,state["protected_tests"],"rejected remediation marker shrank the protected set")
            (self.root/"tests/protected.py").write_text("reworked protected test\n")
            complete={"tests/protected.py":self.hooks.file_fingerprint(self.root/"tests/protected.py"),"tests/other.py":self.hooks.file_fingerprint(extra)}
            self.assertIsNone(self.hooks.handle_stop_agent({"agent_id":"remediation","last_assistant_message":marker(complete)},self.root))
            self.assertEqual(complete,state["protected_tests"])
        finally: (self.hooks.state_for,self.hooks.save)=original

    def test_m006_pre_gate_blocks_writers_and_bypass_wrappers(self):
        self.activate()
        for command in ("make validate", "python -m unittest", "./scripts/run.sh", "PATH=/tmp:$PATH git status", "alias git='true'; git commit -m x", "env git commit -m x"):
            with self.subTest(command=command): self.denied(command)

    def test_m005_m006_pre_tool_blocks_non_bash_writers_before_gate_one_and_outside_approved_paths(self):
        writers = {
            "apply_patch": {"patch":"*** Begin Patch\n*** Update File: outside.py\n@@\n-old\n+new\n*** End Patch"},
            "Edit": {"file_path":"outside.py","old_string":"old","new_string":"new"},
            "Write": {"file_path":"outside.py","content":"new\n"},
        }

        def assert_denied(phase, tool_name, tool_input):
            result = self.call("pre-tool", hook_event_name="PreToolUse", tool_name=tool_name, tool_input=tool_input)
            self.assertIsNotNone(result, f"{phase}: {tool_name} mutation was allowed")
            self.assertEqual("deny", result["hookSpecificOutput"]["permissionDecision"], f"{phase}: {tool_name} mutation was allowed")

        self.activate()
        for tool_name, tool_input in writers.items():
            with self.subTest(phase="before Gate 1", tool=tool_name): assert_denied("before Gate 1", tool_name, tool_input)

        self.record("auditor", "auditor", "audited"); self.record("architect", "architect", "proposed")
        approved_item = self.item("M-5", [])
        approved_item["paths"] = ["tests/"]
        proposal = {"baseline_head":self.hooks.git_head(self.root),"dirty_fingerprint":self.hooks.dirty_fingerprint(self.root),"items":[approved_item]}
        registered = self.call("stop", hook_event_name="Stop", turn_id="proposal", last_assistant_message="WGC_MAINTENANCE_PROPOSAL: "+json.dumps(proposal))
        proposal_id = re.search(r"registered as ([0-9a-f]{16})", registered["reason"]).group(1)
        self.call("prompt-submit", hook_event_name="UserPromptSubmit", turn_id="approval", prompt=f"APPROVE_WGC_PLUGIN_CHANGE={proposal_id}:M-5")
        for tool_name, tool_input in writers.items():
            with self.subTest(phase="after Gate 1 outside scope", tool=tool_name): assert_denied("after Gate 1 outside scope", tool_name, tool_input)

    def test_m003_m006_gate_one_allows_bound_test_maker_validation_but_only_scoped_direct_writes(self):
        self.activate(); self.record("auditor", "auditor", "audited"); self.record("architect", "architect", "proposed")
        approved_item = self.item("M-6", [])
        approved_item["paths"] = ["tests/"]
        proposal = {"baseline_head":self.hooks.git_head(self.root),"dirty_fingerprint":self.hooks.dirty_fingerprint(self.root),"items":[approved_item]}
        registered = self.call("stop", hook_event_name="Stop", turn_id="proposal", last_assistant_message="WGC_MAINTENANCE_PROPOSAL: "+json.dumps(proposal))
        proposal_id = re.search(r"registered as ([0-9a-f]{16})", registered["reason"]).group(1)
        self.call("prompt-submit", hook_event_name="UserPromptSubmit", turn_id="approval", prompt=f"APPROVE_WGC_PLUGIN_CHANGE={proposal_id}:M-6")
        self.start("test-maker", "test-maker")
        validation = self.call("pre-tool", hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command":"python -m unittest tests.protected"})
        self.assertIsNone(validation, "a Gate 1-bound Test-maker cannot run its approved validation command")
        for tool_name, tool_input in (("apply_patch", {"patch":"*** Begin Patch\n*** Update File: tests/protected.py\n@@\n-baseline\n+changed\n*** End Patch"}), ("Edit", {"file_path":"tests/protected.py","old_string":"baseline","new_string":"changed"}), ("Write", {"file_path":"tests/protected.py","content":"changed\n"})):
            with self.subTest(tool=tool_name):
                self.assertIsNone(self.call("pre-tool", hook_event_name="PreToolUse", tool_name=tool_name, tool_input=tool_input), "an approved direct writer must remain limited to the approved file path")

    def test_m005_baseline_ready_test_maker_requires_a_protected_marker(self):
        marker = "WGC_MAINTAINER_RESULT: " + json.dumps({"role":"test-maker","verdict":"baseline_ready","input_revision":self.hooks.worktree_hash(self.root)})
        result, error = self.hooks.parse_role(marker, self.root, ["tests/"])
        self.assertIsNone(result)
        self.assertIn("protected", error or "", "baseline_ready was accepted without an immutable protected-test declaration")

    def test_m004_gate_one_rejects_an_item_scope_overlapping_the_dirty_baseline(self):
        (self.root / "docs").mkdir()
        (self.root / "docs/dirty.md").write_text("pre-existing user work\n")
        self.activate(); self.record("auditor", "auditor", "audited"); self.record("architect", "architect", "proposed")
        proposal = {"baseline_head":self.hooks.git_head(self.root),"dirty_fingerprint":self.hooks.dirty_fingerprint(self.root),"items":[self.item("M-4", [])]}
        result = self.call("stop", hook_event_name="Stop", turn_id="proposal", last_assistant_message="WGC_MAINTENANCE_PROPOSAL: "+json.dumps(proposal))
        self.assertEqual("block", result.get("decision"), "Gate 1 registered an item whose approved scope overlaps the baseline dirty path")
        self.assertIn("dirty", result.get("reason", ""))

    def test_m007_delivery_parser_rejects_mutating_git_and_github_variants(self):
        self.activate()
        for command in ("git commit --amend -m x", "git commit -a -m x", "git commit --no-verify -m x", "git tag -f v1", "gh --repo owner/repo release create v1", "gh release create v1 asset.zip", "command git push origin main", "/usr/bin/git push origin main"):
            with self.subTest(command=command): self.denied(command)

    def test_m008_raw_shell_delivery_argv_is_exact_not_substring_based(self):
        self.activate()
        for command in ("git pushish", "git status; git push origin main", "git -C . push --force origin main", "git --git-dir=.git push origin main"):
            with self.subTest(command=command): self.denied(command)

    def test_m009_outside_repository_is_silent(self):
        outside = Path(self.temp.name) / "outside"; outside.mkdir(); subprocess.run(["git","init","-q"], cwd=outside, check=True)
        self.assertIsNone(self.call("prompt-submit", cwd=str(outside), hook_event_name="UserPromptSubmit", prompt="$wgc-plugin-maintenance audit plugin"))

    def test_m010_declared_hook_events_are_complete_and_synchronous(self):
        config = json.loads((SCRIPT.parent / "hooks.json").read_text())["hooks"]
        self.assertEqual({"SessionStart","UserPromptSubmit","SubagentStart","SubagentStop","PreToolUse","PostToolUse","Stop","SessionEnd"}, set(config))
        self.assertFalse(any("async" in h for groups in config.values() for group in groups for h in group["hooks"]))

    def test_m011_role_result_requires_exact_marker_schema(self):
        self.activate(); self.start("a")
        for marker in ("WGC_MAINTAINER_RESULT: []", 'WGC_MAINTAINER_RESULT: {"role":"auditor","verdict":"audited"}', 'prefix WGC_MAINTAINER_RESULT: {"role":"auditor","verdict":"audited","input_revision":"x"}'):
            with self.subTest(marker=marker):
                result = self.call("subagent-stop", hook_event_name="SubagentStop", agent_id="a", last_assistant_message=marker)
                self.assertTrue(result and "reason" in result)

    def test_m003_target_root_uses_repository_markers_not_checkout_basename(self):
        renamed = Path(self.temp.name) / "renamed-checkout"; renamed.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=renamed, check=True)
        (renamed / "AGENTS.md").write_text("fixture\n"); (renamed / ".agents/plugins").mkdir(parents=True)
        (renamed / ".agents/plugins/marketplace.json").write_text("{}")
        (renamed / "plugins").mkdir()
        self.assertEqual(renamed.resolve(), self.hooks.target_root(renamed))
        (renamed / ".agents/plugins/marketplace.json").unlink()
        self.assertIsNone(self.hooks.target_root(renamed))

    def test_m005_apply_patch_command_and_fallback_cover_all_mutated_and_move_destination_paths(self):
        patch = "\n".join(("*** Begin Patch", "*** Update File: tests/old.py", "*** Move to File: tests/new.py", "*** Add File: tests/add.py", "*** Delete File: tests/delete.py", "*** End Patch"))
        for raw in ({"command":patch}, {"patch":patch}):
            with self.subTest(raw=raw): self.assertEqual(["tests/old.py", "tests/new.py", "tests/add.py", "tests/delete.py"], self.hooks.direct_write_paths("apply_patch", raw))
        for raw in ({"command":""}, {"patch":"*** Begin Patch\n*** End Patch"}, {"patch":"*** Update File: tests/a.py\n*** Update File: ../escape.py"}):
            with self.subTest(raw=raw): self.assertEqual([], self.hooks.direct_write_paths("apply_patch", raw))

    def test_m005_apply_patch_with_any_out_of_scope_mutated_path_is_denied(self):
        state={"active":True,"change_approval":{"paths":["tests/"]}}
        raw={"command":"*** Begin Patch\n*** Update File: tests/inside.py\n*** Move to File: outside.py\n*** End Patch"}
        original=self.hooks.state_for; self.hooks.state_for=lambda payload, root:state
        try:
            result=self.hooks.pre_tool({"tool_name":"apply_patch","tool_input":raw},self.root)
            self.assertEqual("deny", result and result["hookSpecificOutput"].get("permissionDecision"))
        finally: self.hooks.state_for=original

    def test_m006_gate_one_reaches_exact_validation_allowlist_but_not_python_execution_or_wrappers(self):
        state={"active":True,"change_approval":{"paths":["plugins/wget-cloud-plugin-maintainer/"]}}
        original=self.hooks.state_for; self.hooks.state_for=lambda payload, root:state
        try:
            allowed=("make validate", "python3 -B plugins/wget-cloud-plugin-maintainer/scripts/validate_eval_corpus.py", "python3 -B plugins/wget-cloud-plugin-maintainer/scripts/validate_maintainer_contracts.py", "python3 -B plugins/wget-cloud-plugin-maintainer/scripts/run_shadow_eval.py --help", "python3 -B scripts/run_official_validators.py", "python3 -B -m unittest plugins.wget-cloud-plugin-maintainer.hooks.tests.test_maintainer_hooks")
            for command in allowed:
                with self.subTest(command=command): self.assertIsNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":command}},self.root), "required approved validation command was unreachable")
            for command in ("python3 -c 'print(1)'", "python3 -m os", "env python3 -m unittest x", "python3 arbitrary.py"):
                with self.subTest(command=command): self.assertIsNotNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":command}},self.root), "arbitrary execution bypassed the validation allowlist")
        finally: self.hooks.state_for=original

    def test_m005_windows_and_rooted_paths_are_rejected_by_normalization_and_direct_writers(self):
        forbidden=("C:relative.py", "C:/rooted.py", "\\\\server\\share\\file.py", "\\\\?\\C:\\device.py", "/outside.py")
        for path in forbidden:
            with self.subTest(path=path):
                self.assertIsNone(self.hooks.normalize_path(path))
                self.assertEqual([], self.hooks.direct_write_paths("Write", {"file_path":path,"content":"x"}))

    def test_m014_direct_writer_after_gate_two_freezes_before_mutation(self):
        state={"active":True,"change_approval":{"paths":["tests/"]},"delivery_approval":{"release_frozen":False,"release_phase":"approved"}}
        original=self.hooks.state_for; self.hooks.state_for=lambda payload, root:state
        try:
            result=self.hooks.pre_tool({"tool_name":"Write","tool_input":{"file_path":"tests/protected.py","content":"x"}},self.root)
            self.assertEqual("deny", result and result["hookSpecificOutput"].get("permissionDecision"))
            self.assertTrue(state["delivery_approval"]["release_frozen"])
        finally: self.hooks.state_for=original

    def test_m004_dirty_snapshot_preserves_porcelain_statuses_and_nul_rename_copy_records(self):
        original=self.hooks.run
        self.hooks.run=lambda args, root:(0, " M .agents/plugins/marketplace.json\0 D deleted.md\0R  renamed.md\0old.md\0C  copied.md\0source.md\0")
        try:
            snapshot=self.hooks.dirty_snapshot(self.root)
            self.assertTrue(snapshot[".agents/plugins/marketplace.json"].startswith(" M:"))
            self.assertTrue(snapshot["deleted.md"].startswith(" D:"))
            self.assertTrue(snapshot["renamed.md"].startswith("R :"))
            self.assertTrue(snapshot["copied.md"].startswith("C :"))
            self.assertNotIn("old.md",snapshot); self.assertNotIn("source.md",snapshot)
        finally: self.hooks.run=original

    def test_m004_dirty_snapshot_keeps_the_first_real_unstaged_porcelain_status_and_real_rename(self):
        marketplace=self.root/".agents/plugins/marketplace.json"
        marketplace.write_text('{"plugins":["changed"]}')
        self.execute(["git", "mv", "tests/protected.py", "tests/renamed.py"])
        snapshot=self.hooks.dirty_snapshot(self.root)
        self.assertIn(".agents/plugins/marketplace.json",snapshot)
        self.assertTrue(snapshot[".agents/plugins/marketplace.json"].startswith(" M:"), "the first porcelain entry lost its leading unstaged-status space")
        self.assertIn("tests/renamed.py",snapshot)
        self.assertNotIn("tests/protected.py",snapshot)

    def test_m005_apply_patch_move_to_grammar_checks_destination_from_command_and_patch(self):
        patch="*** Begin Patch\n*** Update File: tests/old.py\n*** Move to: outside.py\n*** End Patch"
        for raw in ({"command":patch},{"patch":patch}):
            with self.subTest(raw=raw): self.assertEqual(["tests/old.py","outside.py"],self.hooks.direct_write_paths("apply_patch",raw))

    def test_m006_validation_allowlist_does_not_open_arbitrary_production_unittest_imports(self):
        scopes=["plugins/wget-cloud-plugin-maintainer/"]
        self.assertFalse(self.hooks.validation_command(["python3","-m","unittest","plugins.wget-cloud-plugin-maintainer.hooks.maintainer_hooks"],scopes))
        self.assertFalse(self.hooks.validation_command(["python3","-m","unittest","plugins.wget-cloud-plugin-maintainer.hooks.tests.test_maintainer_hooks","arbitrary"],scopes))


class DeliveryStateMachineContract(unittest.TestCase):
    """M-002/M-004/M-014: exact Gate 2 ledger and ordered release transitions."""

    def setUp(self):
        self.hooks=load_hooks(); self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.snapshot={"head":"a"*40,"index_sha256":"b"*64,"worktree":{"untracked":"??:"+"c"*64},"origin_main":"a"*40}
        self.delivery={"id":"d","approved_paths":["docs/"],"commits":[{"message":"docs: one","paths":["docs/a.md"]}],"versions":{"sample":"1.0.0"},"plugins":["sample"]}
    def tearDown(self): self.temp.cleanup()
    def state(self, phase):
        transitions=[]
        return {"delivery":self.delivery,"delivery_approval":{"delivery_id":"d","release_frozen":False,"delivery_snapshot":self.snapshot,"delivery_transitions":transitions,"delivery_chain_sha256":self.hooks.delivery_chain(self.snapshot,transitions),"release_phase":phase}}
    def with_delivery_mocks(self, callback):
        original=(self.hooks.delivery_snapshot,self.hooks.staged_paths,self.hooks.commits_since_origin,self.hooks.git_branch,self.hooks.dirty_snapshot)
        self.hooks.delivery_snapshot=lambda root:self.snapshot; self.hooks.staged_paths=lambda root:["docs/a.md"]; self.hooks.commits_since_origin=lambda root:[]; self.hooks.git_branch=lambda root:"main"; self.hooks.dirty_snapshot=lambda root:{}
        try: return callback()
        finally: (self.hooks.delivery_snapshot,self.hooks.staged_paths,self.hooks.commits_since_origin,self.hooks.git_branch,self.hooks.dirty_snapshot)=original
    def test_gate_two_rejects_mutating_or_nonexact_delivery_argv(self):
        def check():
            for command, phase in (("git commit --amend -m 'docs: one'","staged"),("git tag -f sample-v1.0.0","smoke-passed"),("gh release create sample-v1.0.0 asset.zip","tagged"),("git push --force origin main","committed")):
                with self.subTest(command=command): self.assertIsNotNone(self.hooks.validate_delivery_command(command,self.state(phase),self.root),"Gate 2 accepted a nonexact mutating argv")
        self.with_delivery_mocks(check)

    def test_m014_git_push_postcondition_allows_only_origin_main_readback_to_the_unchanged_head(self):
        before={"head":"a"*40,"index_sha256":"b"*64,"worktree":{},"origin_main":"c"*40}
        accepted={**before,"origin_main":"a"*40}
        self.assertIsNone(self.hooks.transition_postcondition("git-push",before,accepted,self.root,[],"git push origin main"))
        for altered in ({**accepted,"head":"d"*40},{**accepted,"index_sha256":"e"*64},{**accepted,"worktree":{"docs/a.md":"M"}},{**accepted,"origin_main":"f"*40}):
            with self.subTest(altered=altered): self.assertIsNotNone(self.hooks.transition_postcondition("git-push",before,altered,self.root,[],"git push origin main"))

    def test_m014_pending_delivery_has_no_raw_command_and_plugin_tag_release_advance_without_keyerror(self):
        state=self.state("candidate-ci-verified")
        state["delivery"]["plugins"]=["sample"]; state["delivery"]["versions"]={"sample":"1.0.0"}
        original=(self.hooks.delivery_snapshot,self.hooks.save)
        self.hooks.delivery_snapshot=lambda root:self.snapshot; self.hooks.save=lambda *args:None
        try:
            self.hooks.record_pending_delivery({},self.root,state,"codex plugin add sample@wget-cloud")
            pending=state["delivery_approval"]["pending_delivery"]
            self.assertNotIn("command",pending)
            self.assertEqual("sample",pending.get("argument"))
            self.hooks.advance_delivery(state,self.root,pending,self.snapshot)
            self.assertEqual(["sample"],state["delivery_approval"].get("completed_installs"))
            self.assertFalse(any("codex plugin add" in str(value) for value in state["delivery_approval"].values()))
        finally: (self.hooks.delivery_snapshot,self.hooks.save)=original

    def test_m014_file_free_encoded_evidence_binds_only_hash_and_head_then_advances_from_verifier_output(self):
        import base64
        state=self.state("push-pending-remote-verification"); state["active"]=True
        payload=base64.urlsafe_b64encode(json.dumps({"commit":"a"*40,"workflow":"validate","status":"success","observed_at":1,"source":"github"},separators=(",",":")).encode()).decode().rstrip("=")
        command="python3 -B plugins/wget-cloud-plugin-maintainer/scripts/verify_external_evidence.py --encoded "+payload+" "+"a"*40
        original=(self.hooks.state_for,self.hooks.save)
        self.hooks.state_for=lambda payload, root:state; self.hooks.save=lambda *args:None
        try:
            self.assertIsNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":command}},self.root),"exact bounded encoded verifier command was denied")
            pending=state["delivery_approval"].get("pending_evidence",{})
            self.assertEqual({"command_sha256","head"},set(pending))
            self.assertIsNone(self.hooks.handle_post_tool({"tool_input":{"command":command},"tool_response":{"exit_code":0,"output":json.dumps({"accepted":True,"errors":[],"evidence_sha256":"e"*64,"identifiers":{"ci":"c"*64,"runtime":None,"smoke":None}})}},self.root))
            self.assertEqual("candidate-ci-verified",state["delivery_approval"]["release_phase"])
            self.assertNotIn(payload,json.dumps(state))
            for bad in ("x", "a"*9000, "%%%"):
                with self.subTest(bad=bad): self.assertIsNotNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":"python3 -B plugins/wget-cloud-plugin-maintainer/scripts/verify_external_evidence.py --encoded "+bad+" "+"a"*40}},self.root))
        finally: (self.hooks.state_for,self.hooks.save)=original

    def test_m014_two_plugin_post_smoke_tags_and_releases_complete_exact_sets_once(self):
        self.delivery["plugins"]=["one","two"]; self.delivery["versions"]={"one":"1.0.0","two":"1.0.0"}
        state=self.state("smoke-passed"); approval=state["delivery_approval"]
        approval["completed_installs"]=["one","two"]; approval["completed_smokes"]=["one","two"]
        def check():
            self.assertIsNone(self.hooks.validate_delivery_command("git tag one-v1.0.0",state,self.root))
            approval["completed_tags"]=["one-v1.0.0"]; approval["release_phase"]="tagged"
            self.assertIsNone(self.hooks.validate_delivery_command("git tag two-v1.0.0",state,self.root),"second tag was blocked after the first")
            self.assertIsNotNone(self.hooks.validate_delivery_command("git tag one-v1.0.0",state,self.root),"duplicate tag was allowed")
            self.assertIsNotNone(self.hooks.validate_delivery_command("git tag unknown-v1.0.0",state,self.root),"unknown tag was allowed")
            approval["completed_tags"]=["one-v1.0.0","two-v1.0.0"]
            self.assertIsNone(self.hooks.validate_delivery_command("gh release create one-v1.0.0",state,self.root))
            approval["completed_releases"]=["one-v1.0.0"]; approval["release_phase"]="released"
            self.assertIsNone(self.hooks.validate_delivery_command("gh release create two-v1.0.0",state,self.root),"second release was blocked after the first")
            self.assertIsNotNone(self.hooks.validate_delivery_command("gh release create one-v1.0.0",state,self.root),"duplicate release was allowed")
            self.assertIsNotNone(self.hooks.validate_delivery_command("gh release create unknown-v1.0.0",state,self.root),"unknown release was allowed")
            approval["completed_releases"]=["one-v1.0.0","two-v1.0.0"]
            self.assertEqual({"one-v1.0.0","two-v1.0.0"},set(approval["completed_tags"]))
            self.assertEqual({"one-v1.0.0","two-v1.0.0"},set(approval["completed_releases"]))
        self.with_delivery_mocks(check)

    def test_m014_two_plugin_evidence_requires_ci_then_bound_installed_smokes_before_any_tag(self):
        command="python3 -B plugins/wget-cloud-plugin-maintainer/scripts/verify_external_evidence.py --encoded eyJwbHVnaW4iOiJvbmUifQ " + "a"*40
        response=lambda ci, runtime, smoke: {"exit_code":0,"output":json.dumps({"accepted":True,"errors":[],"evidence_sha256":"e"*64,"identifiers":{"ci":ci,"runtime":runtime,"smoke":smoke}})}
        def state(phase, plugin=None):
            value=self.state(phase); value["active"]=True; value["delivery"]["plugins"]=["one","two"]; value["delivery"]["versions"]={"one":"1.0.0","two":"1.0.0"}
            value["delivery_approval"]["pending_evidence"]={"command_sha256":self.hooks.hashlib.sha256(command.encode()).hexdigest(),"head":"a"*40,"plugin":plugin}
            return value
        original=(self.hooks.state_for,self.hooks.save)
        self.hooks.save=lambda *args:None
        try:
            candidate=state("push-pending-remote-verification")
            self.hooks.state_for=lambda payload, root:candidate
            self.assertIsNone(self.hooks.handle_post_tool({"tool_input":{"command":command},"tool_response":response("c"*64,None,None)},self.root))
            self.assertEqual("candidate-ci-verified",candidate["delivery_approval"]["release_phase"])
            bad_ci=state("push-pending-remote-verification")
            self.hooks.state_for=lambda payload, root:bad_ci
            self.assertEqual("block",(self.hooks.handle_post_tool({"tool_input":{"command":command},"tool_response":response(None,"r"*64,None)},self.root) or {}).get("decision"),"non-CI evidence advanced candidate CI phase")
            installed=state("installed","one")
            self.hooks.state_for=lambda payload, root:installed
            self.assertEqual("block",(self.hooks.handle_post_tool({"tool_input":{"command":command},"tool_response":response("c"*64,None,None)},self.root) or {}).get("decision"),"CI-only evidence advanced installed plugin smoke phase")
            self.assertNotIn("one",installed["delivery_approval"].get("completed_smokes",[]))
        finally: (self.hooks.state_for,self.hooks.save)=original

    def test_m014_two_plugin_tags_require_exact_install_and_smoke_sets(self):
        state=self.state("smoke-passed"); state["delivery"]["plugins"]=["one","two"]; state["delivery"]["versions"]={"one":"1.0.0","two":"1.0.0"}; state["delivery_approval"]["completed_installs"]=[]; state["delivery_approval"]["completed_smokes"]=[]
        def tags():
            self.assertIsNotNone(self.hooks.validate_delivery_command("git tag one-v1.0.0",state,self.root),"tag was allowed before every plugin install and smoke completed")
            state["delivery_approval"]["completed_installs"]=["one","two"]; state["delivery_approval"]["completed_smokes"]=["one","two"]
            self.assertIsNone(self.hooks.validate_delivery_command("git tag one-v1.0.0",state,self.root),"tag remained blocked after exact install/smoke completion")
        self.with_delivery_mocks(tags)

    def test_m014_encoded_runtime_smoke_evidence_binds_nested_plugin_and_advances_installed_smoke(self):
        import base64, time
        commit="a"*40; now=int(time.time())
        def verifier_artifact(plugin):
            evidence={"commit":commit,"workflow":"validate","status":"success","observed_at":now,"source":"github","runtime":{"plugin":plugin,"version":"1.0.0","status":"installed","enabled":True},"smoke":{"task_id":"smoke-"+plugin,"plugin":plugin,"version":"1.0.0","commit":commit,"status":"success","source":"codex","observed_at":now},"subject_task_id":"source-task"}
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/"evidence.json"; path.write_text(json.dumps(evidence))
                verified=subprocess.run([sys.executable,str(PLUGIN/"scripts/verify_external_evidence.py"),str(path),commit],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
            encoded=base64.urlsafe_b64encode(json.dumps(evidence,separators=(",",":")).encode()).decode().rstrip("=")
            return encoded,"python3 -B plugins/wget-cloud-plugin-maintainer/scripts/verify_external_evidence.py --encoded "+encoded+" "+commit,verified.stdout
        encoded_one,command_one,output_one=verifier_artifact("one"); encoded_two,command_two,output_two=verifier_artifact("two")
        state=self.state("installed"); state["active"]=True; state["delivery"]["plugins"]=["one","two"]; state["delivery"]["versions"]={"one":"1.0.0","two":"1.0.0"}; state["delivery_approval"]["completed_installs"]=["one","two"]
        original=(self.hooks.state_for,self.hooks.save)
        self.hooks.state_for=lambda payload, root:state; self.hooks.save=lambda *args:None
        try:
            self.assertIsNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":command_one}},self.root))
            pending=state["delivery_approval"]["pending_evidence"]
            self.assertEqual("one",pending.get("plugin")); self.assertNotIn(encoded_one,json.dumps(pending))
            self.assertIsNone(self.hooks.handle_post_tool({"tool_input":{"command":command_one},"tool_response":{"exit_code":0,"output":output_one}},self.root))
            self.assertEqual("installed",state["delivery_approval"]["release_phase"])
            self.assertEqual(["one"],state["delivery_approval"].get("completed_smokes"))
            self.assertIsNotNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":command_one}},self.root),"duplicate plugin-one smoke was accepted")
            self.assertIsNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":command_two}},self.root))
            self.assertIsNone(self.hooks.handle_post_tool({"tool_input":{"command":command_two},"tool_response":{"exit_code":0,"output":output_two}},self.root))
            self.assertEqual({"one","two"},set(state["delivery_approval"].get("completed_smokes",[])))
            self.assertEqual("smoke-passed",state["delivery_approval"]["release_phase"])
            def tags(): self.assertIsNone(self.hooks.validate_delivery_command("git tag one-v1.0.0",state,self.root))
            self.with_delivery_mocks(tags)
        finally: (self.hooks.state_for,self.hooks.save)=original

    def test_m014_top_level_plugin_encoded_evidence_never_binds_a_smoke_plugin(self):
        import base64
        encoded=base64.urlsafe_b64encode(json.dumps({"plugin":"one"}).encode()).decode().rstrip("=")
        tokens=["python3","-B","plugins/wget-cloud-plugin-maintainer/scripts/verify_external_evidence.py","--encoded",encoded,"a"*40]
        self.assertIsNone(self.hooks.encoded_evidence_plugin(tokens))
    def test_rolling_delivery_chain_binds_head_index_untracked_origin_and_transition_order(self):
        chain=self.hooks.delivery_chain(self.snapshot,[])
        for key, changed in (("head","d"*40),("index_sha256","e"*64),("worktree",{}),("origin_main","f"*40)):
            altered=dict(self.snapshot); altered[key]=changed
            with self.subTest(key=key): self.assertNotEqual(chain,self.hooks.delivery_chain(altered,[]))
        self.assertNotEqual(chain,self.hooks.delivery_chain(self.snapshot,[{"step":"git-add","command_sha256":"1"*64}]))
    def test_release_evidence_cannot_skip_remote_readback_or_replay_after_freeze(self):
        state=self.state("push-pending-remote-verification"); original_origin=self.hooks.origin_main
        self.hooks.origin_main=lambda root:"b"*40
        try: self.assertIn("remote",self.hooks.verify_release_evidence(state,{"commit":"a"*40},self.root))
        finally: self.hooks.origin_main=original_origin
        approval=state["delivery_approval"]; self.hooks.freeze_release(approval,"failed post-tool")
        self.assertIn("frozen",self.hooks.verify_release_evidence(state,{},self.root))
    def test_gate_two_binds_target_plan_versions_and_fresh_reviewer_qa(self):
        (self.root/"plugins/sample/.codex-plugin").mkdir(parents=True); (self.root/"plugins/sample/.codex-plugin/plugin.json").write_text('{"version":"1.0.0"}')
        live="w"*64
        state={"change_approval":{"proposal_id":"p","paths":["docs/"]},"protected_tests":{},"role_results":[{"role":"auditor","verdict":"audited","input_revision":live},{"role":"architect","verdict":"proposed","input_revision":live},{"role":"test-maker","verdict":"baseline_ready","input_revision":live},{"role":"implementor","verdict":"implemented","input_revision":live},{"role":"reviewer","verdict":"approved","input_revision":"stale"},{"role":"qa","verdict":"pass","input_revision":live}]}
        delivery={"proposal_id":"p","worktree_hash":live,"target":"origin/main","commits":[{"message":"docs: one","paths":["docs/a.md"]}],"versions":{"sample":"1.0.0"},"plugins":["sample"],"ci_evidence":True,"runtime_evidence":True}
        original=(self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main)
        self.hooks.worktree_hash=lambda root:live; self.hooks.dirty_snapshot=lambda root:{"docs/a.md":"M"}; self.hooks.origin_main=lambda root:"a"*40
        try:
            self.assertIn("reviewer",self.hooks.validate_delivery(delivery,state,self.root))
            state["role_results"][4]["input_revision"]=live
            delivery["target"]="elsewhere"; self.assertIn("target",self.hooks.validate_delivery(delivery,state,self.root))
            delivery["target"]="origin/main"; delivery["versions"]={"sample":"2.0.0"}; self.assertIn("version",self.hooks.validate_delivery(delivery,state,self.root))
        finally: (self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main)=original

    def test_m003_m014_gate_two_keeps_ordered_provenance_without_requiring_pre_write_roles_at_final_revision(self):
        (self.root/"plugins/sample/.codex-plugin").mkdir(parents=True); (self.root/"plugins/sample/.codex-plugin/plugin.json").write_text('{"version":"1.0.0"}')
        before_tests, after_implementation, final = "a"*64, "b"*64, "c"*64
        state = {"change_approval":{"proposal_id":"p","paths":["docs/"]},"protected_tests":{"tests/protected.py":"d"*64},"role_results":[
            {"role":"auditor","verdict":"audited","input_revision":before_tests,"agent_id":"auditor"},
            {"role":"architect","verdict":"proposed","input_revision":before_tests,"agent_id":"architect"},
            {"role":"test-maker","verdict":"baseline_ready","input_revision":before_tests,"agent_id":"test-maker"},
            {"role":"implementor","verdict":"implemented","input_revision":after_implementation,"agent_id":"implementor"},
            {"role":"reviewer","verdict":"approved","input_revision":final,"agent_id":"reviewer"},
            {"role":"qa","verdict":"pass","input_revision":final,"agent_id":"qa"},
        ]}
        delivery = {"proposal_id":"p","worktree_hash":final,"target":"origin/main","commits":[{"message":"docs: one","paths":["docs/a.md"]}],"versions":{"sample":"1.0.0"},"plugins":["sample"],"ci_evidence":True,"runtime_evidence":True}
        original = (self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main,self.hooks.validate_protected_tests)
        self.hooks.worktree_hash=lambda root:final; self.hooks.dirty_snapshot=lambda root:{"docs/a.md":"M"}; self.hooks.origin_main=lambda root:"a"*40; self.hooks.validate_protected_tests=lambda root, paths:None
        try: self.assertIsNone(self.hooks.validate_delivery(delivery,state,self.root), "Gate 2 made a real Test-maker/Implementor write sequence impossible despite ordered bound provenance")
        finally: (self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main,self.hooks.validate_protected_tests)=original

    def test_m014_gate_two_requires_true_candidate_ci_and_runtime_preflight_flags(self):
        (self.root/"plugins/sample/.codex-plugin").mkdir(parents=True); (self.root/"plugins/sample/.codex-plugin/plugin.json").write_text('{"version":"1.0.0"}')
        live="w"*64
        state={"change_approval":{"proposal_id":"p","paths":["docs/"]},"protected_tests":{},"role_results":[{"role":role,"verdict":self.hooks.SUCCESS[role],"input_revision":live} for role in self.hooks.ROLES]}
        delivery={"proposal_id":"p","worktree_hash":live,"target":"origin/main","commits":[{"message":"docs: one","paths":["docs/a.md"]}],"versions":{"sample":"1.0.0"},"plugins":["sample"],"ci_evidence":False,"runtime_evidence":False}
        original=(self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main)
        self.hooks.worktree_hash=lambda root:live; self.hooks.dirty_snapshot=lambda root:{"docs/a.md":"M"}; self.hooks.origin_main=lambda root:"a"*40
        try: self.assertIn("preflight", self.hooks.validate_delivery(delivery,state,self.root) or "", "Gate 2 accepted false CI/runtime preflight attestations")
        finally: (self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main)=original

    def test_m014_post_tool_uses_tool_response_failure_and_freezes_the_pending_delivery(self):
        state=self.state("approved"); state["delivery_approval"]["pending_delivery"]={"transition":"git-add","command_sha256":self.hooks.hashlib.sha256(b"git add -- docs/a.md").hexdigest(),"snapshot":self.snapshot,"chain_sha256":state["delivery_approval"]["delivery_chain_sha256"],"requested_paths":["docs/a.md"]}
        original=(self.hooks.state_for,self.hooks.save,self.hooks.delivery_snapshot,self.hooks.transition_postcondition)
        self.hooks.state_for=lambda payload, root:state; self.hooks.save=lambda payload, root, state:None; self.hooks.delivery_snapshot=lambda root:self.snapshot; self.hooks.transition_postcondition=lambda *args:None
        try:
            result=self.hooks.handle_post_tool({"tool_input":{"command":"git add -- docs/a.md"},"tool_response":{"exit_code":1}},self.root)
            self.assertEqual("block", result and result.get("decision"), "a failed PostToolUse tool_response advanced the delivery ledger")
            self.assertTrue(state["delivery_approval"]["release_frozen"])
        finally: (self.hooks.state_for,self.hooks.save,self.hooks.delivery_snapshot,self.hooks.transition_postcondition)=original

    def test_m014_post_tool_persists_only_verified_sanitized_external_evidence_phase_progression(self):
        state=self.state("push-pending-remote-verification")
        evidence={"commit":"a"*40,"workflow":"validate","status":"success","observed_at":int(__import__("time").time()),"source":"github"}
        original=(self.hooks.state_for,self.hooks.save,self.hooks.git_head,self.hooks.origin_main)
        self.hooks.state_for=lambda payload, root:state; self.hooks.save=lambda payload, root, state:None; self.hooks.git_head=lambda root:"a"*40; self.hooks.origin_main=lambda root:"a"*40
        try:
            result=self.hooks.handle_post_tool({"tool_name":"Bash","tool_input":{"external_evidence":evidence},"tool_response":{"exit_code":0}},self.root)
            self.assertEqual("block", result and result.get("decision"), "unbound caller tool_input evidence was not rejected")
            self.assertEqual("push-pending-remote-verification", state["delivery_approval"]["release_phase"])
            result=self.hooks.handle_post_tool({"tool_name":"Bash","tool_input":{"external_evidence":{**evidence,"raw_output":"secret"}},"tool_response":{"exit_code":0}},self.root)
            self.assertEqual("block", result and result.get("decision"), "unsanitized unbound evidence was not rejected")
            self.assertEqual([], state["delivery_approval"].get("external_evidence_sha256", []))
        finally: (self.hooks.state_for,self.hooks.save,self.hooks.git_head,self.hooks.origin_main)=original

    def test_m014_external_evidence_uses_declared_post_tool_response_contract_and_rejects_replay(self):
        state=self.state("push-pending-remote-verification")
        evidence={"commit":"a"*40,"workflow":"validate","status":"success","observed_at":int(__import__("time").time()),"source":"github"}
        original=(self.hooks.state_for,self.hooks.save,self.hooks.git_head,self.hooks.origin_main)
        self.hooks.state_for=lambda payload, root:state; self.hooks.save=lambda *args:None; self.hooks.git_head=lambda root:"a"*40; self.hooks.origin_main=lambda root:"a"*40
        try:
            event={"tool_name":"Bash","tool_input":{"command":"python3 -B scripts/verify_external_evidence.py"},"tool_response":{"exit_code":0,"external_evidence":evidence}}
            self.assertIsNone(self.hooks.handle_post_tool(event,self.root), "unbound response evidence should be ignored, not accepted")
            self.assertEqual("push-pending-remote-verification",state["delivery_approval"]["release_phase"])
            self.assertIsNone(self.hooks.handle_post_tool(event,self.root), "replayed unbound response evidence was unexpectedly handled")
            self.assertEqual([],state["delivery_approval"].get("external_evidence_sha256", []))
        finally: (self.hooks.state_for,self.hooks.save,self.hooks.git_head,self.hooks.origin_main)=original

    def test_m007_m008_directory_scope_staging_and_multiple_atomic_commits_are_representable(self):
        self.delivery["approved_paths"]=["docs/"]
        self.delivery["commits"]=[{"message":"docs: first","paths":["docs/a.md"]},{"message":"docs: second","paths":["docs/b.md"]}]
        state=self.state("approved")
        def check():
            self.assertIsNone(self.hooks.validate_delivery_command("git add -- docs/a.md",state,self.root), "directory approval did not authorize staging its file")
            self.hooks.commits_since_origin=lambda root:["docs: first"]
            before={**self.snapshot,"head":"a"*40}; after={**self.snapshot,"head":"b"*40,"worktree":{"docs/b.md":"M"}}
            self.assertIsNone(self.hooks.transition_postcondition("git-commit",before,after,self.root,[],"git commit -m 'docs: first'"), "the first of two ordered atomic commits cannot leave the second planned change")
        self.with_delivery_mocks(check)

    def test_m003_negative_reviewer_verdict_starts_one_new_bound_remediation_cycle_without_replay(self):
        state={"role_results":[
            {"role":"auditor","verdict":"audited","agent_id":"a"}, {"role":"architect","verdict":"proposed","agent_id":"b"}, {"role":"test-maker","verdict":"baseline_ready","agent_id":"c"}, {"role":"implementor","verdict":"implemented","agent_id":"d"}, {"role":"reviewer","verdict":"changes_requested","agent_id":"e"},
        ]}
        self.assertEqual("test-maker", self.hooks.next_role(state), "negative review cannot begin a fresh Test-maker remediation cycle")

    def test_m007_m008_two_commit_delivery_requires_the_next_subject_allows_second_stage_and_blocks_early_push(self):
        self.delivery["commits"]=[{"message":"docs: one","paths":["docs/a.md"]},{"message":"docs: two","paths":["docs/b.md"]}]
        state=self.state("committed"); self.delivery["approved_paths"]=["docs/"]
        def check():
            self.hooks.commits_since_origin=lambda root:["docs: one"]
            self.assertIsNone(self.hooks.validate_delivery_command("git add -- docs/b.md",state,self.root), "second planned file cannot be staged after the first atomic commit")
            self.assertIsNotNone(self.hooks.validate_delivery_command("git push origin main",state,self.root), "push was accepted before all planned commit subjects existed")
            self.hooks.commits_since_origin=lambda root:["docs: one", "docs: two"]
            self.assertIsNone(self.hooks.validate_delivery_command("git push origin main",state,self.root), "push rejected after the exact ordered plan completed")
        self.with_delivery_mocks(check)

    def test_m014_missing_response_freezes_delivery_and_tag_postcondition_checks_exact_ref(self):
        state=self.state("approved"); state["delivery_approval"]["pending_delivery"]={"transition":"git-add","command_sha256":self.hooks.hashlib.sha256(b"git add -- docs/a.md").hexdigest(),"snapshot":self.snapshot,"chain_sha256":state["delivery_approval"]["delivery_chain_sha256"],"requested_paths":["docs/a.md"]}
        original=(self.hooks.state_for,self.hooks.save,self.hooks.delivery_snapshot,self.hooks.transition_postcondition)
        self.hooks.state_for=lambda payload, root:state; self.hooks.save=lambda *args:None; self.hooks.delivery_snapshot=lambda root:self.snapshot; self.hooks.transition_postcondition=lambda *args:None
        try:
            self.assertEqual("block", (self.hooks.handle_post_tool({"tool_input":{"command":"git add -- docs/a.md"}},self.root) or {}).get("decision"))
            self.assertTrue(state["delivery_approval"]["release_frozen"])
        finally: (self.hooks.state_for,self.hooks.save,self.hooks.delivery_snapshot,self.hooks.transition_postcondition)=original

    def test_m014_tag_postcondition_requires_the_exact_tag_ref_at_delivery_head(self):
        self.assertIsNotNone(self.hooks.transition_postcondition("git-tag",self.snapshot,self.snapshot,self.root,[],"git tag sample-v1.0.0"), "tag postcondition accepted without proving the exact tag points at delivery HEAD")

    def test_m003_complete_reviewer_remediation_tail_and_qa_defect_reentry_are_bound_and_consumed(self):
        initial=[("auditor","audited"),("architect","proposed"),("test-maker","baseline_ready"),("implementor","implemented"),("reviewer","changes_requested")]
        remediation=[("test-maker","baseline_ready"),("implementor","implemented"),("reviewer","approved"),("qa","pass")]
        state={"role_results":[{"role":role,"verdict":verdict,"agent_id":f"old-{index}"} for index,(role,verdict) in enumerate(initial)]}
        for index,(role,verdict) in enumerate(remediation):
            self.assertEqual(role,self.hooks.next_role(state))
            state["role_results"].append({"role":role,"verdict":verdict,"agent_id":f"new-{index}"})
        self.assertEqual([role for role,_ in remediation],[item["role"] for item in state["role_results"][-4:]])
        state["role_results"][-1]["verdict"]="defects_found"
        self.assertEqual("test-maker",self.hooks.next_role(state),"QA defects cannot start a fresh bound remediation cycle")

    def test_m014_external_evidence_is_a_reachable_pending_verifier_operation_not_caller_input(self):
        state=self.state("push-pending-remote-verification"); state["active"]=True; state["change_approval"]={"paths":["plugins/wget-cloud-plugin-maintainer/scripts/"]}
        original=self.hooks.state_for; self.hooks.state_for=lambda payload, root:state
        try:
            exact="python3 -B plugins/wget-cloud-plugin-maintainer/scripts/verify_external_evidence.py evidence.json " + "a"*40
            self.assertIsNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":exact}},self.root),"exact verifier command was not reachable through PreToolUse")
            self.assertIn("pending_evidence",state["delivery_approval"],"PreToolUse did not bind a pending verifier operation")
            self.assertIsNotNone(self.hooks.pre_tool({"tool_name":"Bash","tool_input":{"command":"python3 -c 'import os'"}},self.root))
            response={"exit_code":0,"output":json.dumps({"accepted":True,"errors":[],"evidence_sha256":"e"*64,"identifiers":{"ci":"c"*64,"runtime":None,"smoke":None}})}
            self.assertIsNone(self.hooks.handle_post_tool({"tool_input":{"command":exact},"tool_response":response},self.root),"strict successful verifier output did not advance the pending evidence operation")
            self.assertNotIn("pending_evidence",state["delivery_approval"])
            self.assertEqual("candidate-ci-verified",state["delivery_approval"]["release_phase"])
            self.assertEqual(["e"*64],state["delivery_approval"].get("external_evidence_sha256"))
            self.assertEqual("block",(self.hooks.handle_post_tool({"tool_input":{"command":exact},"tool_response":response},self.root) or {}).get("decision"),"verifier evidence replay was accepted")
            self.assertIsNotNone(self.hooks.handle_post_tool({"tool_input":{"external_evidence":{"commit":"a"*40}},"tool_response":{"exit_code":0}},self.root),"caller-invented tool_input evidence was accepted")
        finally: self.hooks.state_for=original

    def test_m014_multi_plugin_delivery_keeps_per_plugin_install_tag_release_sets(self):
        self.delivery["plugins"]=["one","two"]; self.delivery["versions"]={"one":"1.0.0","two":"1.0.0"}
        state=self.state("candidate-ci-verified")
        def check():
            self.assertIsNone(self.hooks.validate_delivery_command("codex plugin add one@wget-cloud",state,self.root))
            state["delivery_approval"]["completed_installs"]=["one"]
            state["delivery_approval"]["release_phase"]="installed"
            self.assertIsNone(self.hooks.validate_delivery_command("codex plugin add two@wget-cloud",state,self.root),"second approved plugin install was collapsed by a global phase")
            self.assertIsNotNone(self.hooks.validate_delivery_command("git tag one-v1.0.0",state,self.root),"tag was allowed before each plugin install/smoke completion")
            self.assertIsNotNone(self.hooks.validate_delivery_command("gh release create one-v1.0.0",state,self.root),"release was allowed before the plugin tag")
        self.with_delivery_mocks(check)

    def test_m003_validate_delivery_consumes_the_latest_complete_successful_remediation_tail(self):
        (self.root/"plugins/sample/.codex-plugin").mkdir(parents=True); (self.root/"plugins/sample/.codex-plugin/plugin.json").write_text('{"version":"1.0.0"}')
        live="f"*64
        history=[("auditor","audited"),("architect","proposed"),("test-maker","baseline_ready"),("implementor","implemented"),("reviewer","changes_requested"),("test-maker","baseline_ready"),("implementor","implemented"),("reviewer","approved"),("qa","pass")]
        state={"change_approval":{"proposal_id":"p","paths":["docs/"]},"protected_tests":{},"role_results":[{"role":role,"verdict":verdict,"input_revision":live,"agent_id":str(index)} for index,(role,verdict) in enumerate(history)]}
        delivery={"proposal_id":"p","worktree_hash":live,"target":"origin/main","commits":[{"message":"docs: one","paths":["docs/a.md"]}],"versions":{"sample":"1.0.0"},"plugins":["sample"],"ci_evidence":True,"runtime_evidence":True}
        original=(self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main)
        self.hooks.worktree_hash=lambda root:live; self.hooks.dirty_snapshot=lambda root:{"docs/a.md":"M"}; self.hooks.origin_main=lambda root:"a"*40
        try: self.assertIsNone(self.hooks.validate_delivery(delivery,state,self.root),"Gate 2 ignored the latest successful remediation tail after a negative review")
        finally: (self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main)=original

    def test_m014_gate_two_rejects_drift_from_test_maker_protected_fingerprint(self):
        protected = self.root / "tests/protected.py"
        protected.parent.mkdir(parents=True)
        protected.write_text("declared baseline\n")
        declared = self.hooks.file_fingerprint(protected)
        protected.write_text("drift after Test-maker declaration\n")
        (self.root/"plugins/sample/.codex-plugin").mkdir(parents=True)
        (self.root/"plugins/sample/.codex-plugin/plugin.json").write_text('{"version":"1.0.0"}')
        live = "w" * 64
        state = {
            "change_approval":{"proposal_id":"p","paths":["docs/","tests/"]},
            "protected_tests":{"tests/protected.py":declared},
            "role_results":[{"role":role,"verdict":self.hooks.SUCCESS[role],"input_revision":live} for role in self.hooks.ROLES],
        }
        delivery = {"proposal_id":"p","worktree_hash":live,"target":"origin/main","commits":[{"message":"docs: one","paths":["docs/a.md"]}],"versions":{"sample":"1.0.0"},"plugins":["sample"],"ci_evidence":True,"runtime_evidence":True}
        original = (self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main)
        self.hooks.worktree_hash=lambda root:live; self.hooks.dirty_snapshot=lambda root:{"docs/a.md":"M"}; self.hooks.origin_main=lambda root:"a"*40
        try:
            self.assertIn("protected test", self.hooks.validate_delivery(delivery,state,self.root) or "", "Gate 2 accepted protected-test fingerprint drift after the Test-maker declaration")
        finally: (self.hooks.worktree_hash,self.hooks.dirty_snapshot,self.hooks.origin_main)=original


if __name__ == "__main__": unittest.main()
