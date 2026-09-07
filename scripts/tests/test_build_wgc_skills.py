import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('wgc_builder_test', ROOT/'scripts/build_wgc_skills.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for relative in ('plugin-src/wget-cloud-implementation', 'plugins/wget-cloud-implementation/skills'):
            shutil.copytree(ROOT/relative, self.root/relative)
        self.manifest = self.root/'plugin-src/wget-cloud-implementation/composition.json'

    def test_repeatable_build_and_read_only_check_detect_drift(self):
        self.assertGreater(builder.build(self.root, check=True), 100)
        expected = builder.render(self.root)
        target = next(iter(expected))
        target.write_text('drift')
        with self.assertRaisesRegex(ValueError, 'stale'):
            builder.build(self.root, check=True)
        self.assertEqual(target.read_text(), 'drift')
        builder.build(self.root)
        self.assertEqual(builder.render(self.root), expected)
        builder.build(self.root, check=True)

    def test_duplicate_and_escaping_targets_are_rejected_without_write(self):
        original = json.loads(self.manifest.read_text())
        for kind in ('duplicate','escape'):
            value = json.loads(json.dumps(original))
            entries = value['skills']['wgc-implementation']
            if kind == 'duplicate':
                entries.append(entries[0])
            else:
                entries[0]['target'] = '../outside.md'
            self.manifest.write_text(json.dumps(value))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                builder.build(self.root)

    def test_each_skill_works_as_a_standalone_directory(self):
        for skill in (self.root/'plugins/wget-cloud-implementation/skills').iterdir():
            isolated = self.root/'isolated'/skill.name
            shutil.copytree(skill, isolated)
            for path in isolated.rglob('*.md'):
                text = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
                for raw in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
                    target = raw.split('#',1)[0]
                    if not target or '://' in target:
                        continue
                    resolved=(path.parent/target).resolve()
                    self.assertTrue(resolved.is_relative_to(isolated),str(path)+': '+target)
                    self.assertTrue(resolved.exists(),str(path)+': '+target)

    def test_undeclared_output_and_source_are_not_silently_deleted(self):
        extra=self.root/'plugins/wget-cloud-implementation/skills/wgc-implementation/manual.md'
        extra.write_text('unowned')
        with self.assertRaisesRegex(ValueError,'undeclared'):
            builder.build(self.root)
        self.assertEqual(extra.read_text(),'unowned')
