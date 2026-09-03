"""Protected evaluator, corpus, evidence, and semantic-validator attacks (M-012..M-016)."""
from __future__ import annotations
import importlib.util, json, os, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PLUGIN = Path(os.environ.get("WGC_MAINTAINER_TARGET_ROOT", str(ROOT / "plugins/wget-cloud-plugin-maintainer")))
def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

class EvalSecurityTest(unittest.TestCase):
    def scenario(self, **more):
        value={"id":"x","expected_route":"wgc-plugin-maintenance","required_invariants":["no-write-before-approval"]}; value.update(more); return value
    def test_m012_shadow_adapter_requires_actual_route_and_per_invariant_boolean(self):
        runner=load(PLUGIN/"scripts/run_shadow_eval.py","runner")
        base={"success":True,"actual_route":"wgc-plugin-maintenance","invariants":{"no-write-before-approval":True}}
        for candidate in ({"success":True}, {**base,"actual_route":"none"}, {**base,"invariants":{}}, {**base,"invariants":{"no-write-before-approval":"true"}}, {**base,"invariants":{"no-write-before-approval":True,"extra":True}}):
            with self.subTest(candidate=candidate): self.assertFalse(runner.evaluate(self.scenario(),base,candidate)["passed"])
    def test_m012_shadow_result_rejects_secret_like_or_unexpected_actual_routes_before_reporting(self):
        runner=load(PLUGIN/"scripts/run_shadow_eval.py","runner")
        value={"success":True,"actual_route":"https://token@example.invalid/private","latency_ms":1,"token_cost_proxy":1,"invariants":{"no-write-before-approval":True}}
        metrics, errors=runner.sanitized_result(self.scenario(),value,"candidate")
        self.assertIsNone(metrics, "shadow report retained an arbitrary secret-like actual_route")
        self.assertTrue(errors)
    def test_m013_shadow_eval_rejects_dirty_or_shared_roots_and_unbound_revisions(self):
        runner=load(PLUGIN/"scripts/run_shadow_eval.py","runner")
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/"corpus.json").write_text('{"scenarios":[]}')
            report=runner.run(root/"corpus.json",root,root,["true"],["true"],1)
            self.assertFalse(report["passed"])
    def test_m014_corpus_uses_strict_root_nested_schema_and_no_raw_output(self):
        corpus=load(PLUGIN/"scripts/validate_eval_corpus.py","corpus")
        valid={"schema_version":1,"scenarios":[{"id":"x","intent":"sanitized","expected_route":"none","required_invariants":["silent-outside-codex-plugins"],"platforms":["ubuntu"],"routing":{"allow_implicit_invocation":False}}]}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"c.json"
            for mutate in (lambda x:x.update(extra=True), lambda x:x["scenarios"][0].update(raw_output="secret"), lambda x:x["scenarios"][0]["routing"].update(extra=False), lambda x:x["scenarios"][0].update(platforms=["linux"])):
                value=json.loads(json.dumps(valid)); mutate(value); path.write_text(json.dumps(value));
                with self.subTest(value=value): self.assertTrue(corpus.validate_corpus(path))
    def test_m015_evidence_is_strictly_schema_bound_and_privacy_safe(self):
        evidence=load(PLUGIN/"scripts/verify_external_evidence.py","evidence")
        good={"commit":"a"*40,"workflow":"validate","status":"success","observed_at":100,"source":"github"}
        for bad in ({**good,"extra":1},{**good,"raw_output":"secret"},{**good,"runtime":{"status":"installed","enabled":True,"plugin":"p","version":"1","extra":1}},{**good,"smoke":{"status":"success","source":"codex","task_id":"same","commit":"a"*40,"observed_at":100},"subject_task_id":"same"}):
            with self.subTest(bad=bad): self.assertFalse(evidence.verify(bad,commit="a"*40,now=1000,max_age_seconds=1000)["accepted"])
    def test_m016_validate_repository_invokes_live_maintainer_contract_validator(self):
        validator=load(ROOT/"scripts/validate_marketplace.py","marketplace")
        self.assertTrue(hasattr(validator,"validate_maintainer_contracts"), "repository validation must expose the live semantic validator")
        original_root, original_marketplace=validator.ROOT, validator.MARKETPLACE
        try:
            validator.ROOT=ROOT; validator.MARKETPLACE=ROOT/".agents/plugins/marketplace.json"
            validator.validate_maintainer_contracts=lambda root: ["semantic-sentinel"]
            errors, _=validator.validate_repository(ROOT)
            self.assertIn("semantic-sentinel", errors, "validate_repository must call and propagate live semantic validation")
        finally:
            validator.ROOT, validator.MARKETPLACE=original_root, original_marketplace

if __name__ == "__main__": unittest.main()
