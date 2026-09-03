"""Failing-first contracts for the offline official-validator wrapper (M-008)."""
from __future__ import annotations
import hashlib, importlib.util, json, os, subprocess, tempfile, unittest
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
SCRIPT=Path(os.environ.get("WGC_VALIDATOR_TARGET_ROOT", str(REPO))) / "scripts/run_official_validators.py"
def load():
    spec=importlib.util.spec_from_file_location("official_wrapper", SCRIPT); assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

class OfficialValidatorContracts(unittest.TestCase):
    def setUp(self): self.mod=load(); self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def lock(self):
        content=b"validator\n"; digest=hashlib.sha256(content).hexdigest()
        return {"source":"openai/codex","commit":"a"*40,"license_provenance":"pinned upstream validator provenance","validators":{name:{"url":f"https://raw.githubusercontent.com/openai/codex/{'a'*40}/path/{name}","sha256":digest} for name in self.mod.REQUIRED_VALIDATORS}}, content
    def write_lock(self, value):
        path=self.root/"lock.json"; path.write_text(json.dumps(value)); return path
    def test_lock_requires_exact_allowlist_sha_and_provenance(self):
        valid, _=self.lock()
        for mutate in (lambda x:x.pop("license_provenance"), lambda x:x.update(extra=True), lambda x:x.update(commit="short"), lambda x:x["validators"]["quick_validate.py"].update(sha256="0"*63), lambda x:x["validators"].pop("identifier_validation.py"), lambda x:x["validators"].update(unapproved={"url":"https://example.invalid/x","sha256":"0"*64})):
            value=json.loads(json.dumps(valid)); mutate(value)
            with self.subTest(value=value):
                with self.assertRaises(ValueError): self.mod.load_lock(self.write_lock(value))
    def test_offline_missing_wrong_and_unapproved_cache_never_calls_network(self):
        valid, content=self.lock(); cache=self.root/"cache"; cache.mkdir()
        calls=[]; original=self.mod.urllib.request.urlopen; self.mod.urllib.request.urlopen=lambda *a,**k:calls.append(a) or (_ for _ in ()).throw(AssertionError("network"))
        try:
            for setup in (lambda:None, lambda:(cache/"quick_validate.py").write_bytes(b"wrong"), lambda:(cache/"unapproved.py").write_bytes(content)):
                for path in cache.glob("*"): path.unlink()
                setup(); result=self.mod.ensure_cache(valid, cache, allow_download=False)
                with self.subTest(result=result): self.assertFalse(result["accepted"]); self.assertTrue(result["offline"])
            self.assertEqual([], calls)
        finally: self.mod.urllib.request.urlopen=original
    def test_discovery_includes_every_plugin_and_skill(self):
        for plugin, skill in (("one","alpha"),("two","beta")):
            (self.root/f"plugins/{plugin}/.codex-plugin").mkdir(parents=True); (self.root/f"plugins/{plugin}/.codex-plugin/plugin.json").write_text("{}")
            (self.root/f"plugins/{plugin}/skills/{skill}").mkdir(parents=True); (self.root/f"plugins/{plugin}/skills/{skill}/SKILL.md").write_text("---\n")
        found=self.mod.discover_targets(self.root)
        self.assertEqual(2,len(found["plugins"])); self.assertEqual(2,len(found["skills"]))
    def test_validator_failure_surfaces_sanitized_output_and_target(self):
        cache=self.root/"cache"; cache.mkdir(); repository=self.root/"repo"; repository.mkdir()
        (repository/"plugins/p/.codex-plugin").mkdir(parents=True); (repository/"plugins/p/.codex-plugin/plugin.json").write_text("{}")
        (repository/"plugins/p/skills/s").mkdir(parents=True); (repository/"plugins/p/skills/s/SKILL.md").write_text("---\n")
        original=subprocess.run
        subprocess.run=lambda *a,**k:type("R",(),{"returncode":1,"stdout":"validator diagnostic"})()
        try:
            failures=self.mod.run_validators(cache,repository)
        finally: subprocess.run=original
        self.assertTrue(failures); self.assertIn("validator diagnostic"," ".join(failures)); self.assertIn("plugins/p"," ".join(failures))

    def test_make_validate_downloads_pinned_validators_by_default_with_explicit_offline_override_and_ci_uses_the_same_command(self):
        makefile=(REPO/"Makefile").read_text()
        workflow=(REPO/".github/workflows/validate.yml").read_text()
        self.assertIn("OFFICIAL_VALIDATOR_ARGS ?= --allow-download", makefile)
        self.assertIn("make validate", workflow)
        self.assertNotIn("make validate OFFICIAL_VALIDATOR_ARGS=--allow-download", workflow)

if __name__ == "__main__": unittest.main()
