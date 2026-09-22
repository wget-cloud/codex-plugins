"""Behavioral v7 scenarios; lifecycle fixtures use isolated synthetic repositories."""
import importlib.util
import hashlib
import json
import unittest
from pathlib import Path
import test_wgc_hooks as fixtures

spec = importlib.util.spec_from_file_location('wgc_v7_test_runtime', Path(__file__).resolve().parents[1] / 'wgc_hooks.py')
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)


def task(**changes):
    value = dict(mode='light', complexity='small', risk='low', domains=['backend'], risk_signals=[], checks=[],
                 assessed_paths=['backend:docs/copy.md'], test_disposition='none', rationale='copy-only correction',
                 evidence_refs=['synthetic-visual-check'], plan_revision='p1', acceptance_revision='a1')
    value.update(changes)
    value['assessment_revision'] = hooks.teams.assessment_revision(value)
    return value


def assessment(t):
    return dict(plan_revision=t['plan_revision'], acceptance_revision=t['acceptance_revision'],
                test_criticality=t['risk'], test_disposition=t['test_disposition'], scope_fingerprint='fixture',
                test_ownership='n/a',
                assessed_paths=t['assessed_paths'], tested_invariants=['copy only'], existing_tests=['no_relevant_tests'],
                coverage_mode='none', alternative_evidence=['synthetic-visual-check'], residual_risks=['none-observed'],
                rationale='no behavioral change')


class TeamPolicyTests(unittest.TestCase):
    def test_critical_signals_cannot_take_light_and_activate_exact_specialists(self):
        for signal in hooks.teams.CRITICAL_SIGNALS | {'reliability'}:
            with self.subTest(signal=signal):
                with self.assertRaises(ValueError):
                    hooks.teams.normalize(task(risk_signals=[signal]))
                t = task(mode='full', risk='critical', risk_signals=[signal], test_disposition='reuse')
                hooks.teams.normalize(t)
                gates = hooks.teams.required_gates('implementation', t)
                self.assertTrue({'test-maker', 'architect', 'architecture-plan', 'reviewer'} <= gates)
                self.assertEqual('architecture' in gates, signal == 'gitops')
                self.assertEqual('qa' in gates, signal in {'security', 'money', 'contract', 'incident'})
                expected = {'security':'security', 'data':'data', 'migration':'data', 'contract':'contract', 'concurrency':'reliability', 'reliability':'reliability', 'gitops':'infrastructure'}.get(signal)
                if expected:
                    self.assertIn(expected, gates)

    def test_sensitive_path_and_unknown_field_cannot_weaken_assessment(self):
        for changes in ({'assessed_paths':['backend:src/auth.ts']}, {'raw_prompt':'private'}, {'risk':'unknown'}, {'checks':['skip-all']}, {'risk_signals':['invented']}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                hooks.teams.normalize(task(**changes))

    def test_standard_implementation_keeps_ordinary_tests_with_implementor(self):
        t = task(mode='standard', risk='standard', risk_signals=['behavior'], test_disposition='reuse')
        hooks.teams.normalize(t)
        self.assertEqual(hooks.teams.required_gates('implementation', t), {'task-assessor', 'implementor', 'reviewer', 'qa'})
        t['test_disposition'] = 'add'
        self.assertNotIn('test-maker', hooks.teams.required_gates('implementation', t))
        t = task(mode='full', risk='critical', risk_signals=['security'], test_disposition='add')
        self.assertIn('test-maker', hooks.teams.required_gates('implementation', t))
        self.assertIn('test-maker', hooks.teams.required_gates('bugfix', task(mode='standard', risk='standard', risk_signals=['behavior'], test_disposition='add')))

    def test_v3_migration_cannot_reuse_approvals_and_malformed_v4_is_unhealthy(self):
        v = hooks.migrate_state_v4({'version':3, 'baseline_dirty':{'backend':{}}, 'subagent_results':[{'role':'qa','verdict':'pass'}], 'verification':{'test':{}}, 'task_assessments':[]})
        self.assertEqual(v['version'], 4)
        self.assertEqual(v['subagent_results'], [])
        self.assertEqual(v['verification'], {})
        self.assertTrue(v['task_reassessment_required'])
        self.assertEqual(v['baseline_dirty'], {'backend':{}})
        bad = hooks.migrate_state_v4({'version':4,'task_assessments':[{'raw_prompt':'not-allowed'}]})
        self.assertTrue(bad['repository_reaudit_required'])
        self.assertEqual(bad['task_assessments'], [])
        legacy_bad = hooks.migrate_state_v4({'version':3,'selected_items':None})
        self.assertTrue(legacy_bad['repository_reaudit_required'])

    def test_evidence_failure_and_relevant_invalidation(self):
        values = {'lint':{'scope':['backend:a.py']}, 'build':{'scope':['frontend:b.ts']}}
        hooks.evidence.invalidate(values, ['backend:a.py'])
        self.assertEqual(set(values), {'build'})


class TeamLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.WgcHooksTest(methodName='runTest')
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.cwd = self.h.projects['backend']

    def post(self, path, content):
        target = self.cwd / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return self.h.call('post-tool', {'hook_event_name':'PostToolUse', 'tool_name':'apply_patch', 'tool_input':{'command':f'*** Begin Patch\n*** Add File: {path}\n+x\n*** End Patch'}, 'tool_response':{'ok':True}}, self.cwd)

    def finish(self, t, **extra):
        state = self.h.adaptive_state()
        value = dict(assessment_revision=t['assessment_revision'], input_revision=hooks.workspace_identity(state['context']), acceptance_verified=True, evidence_refs=['synthetic-visual-check'])
        value.update(extra)
        return self.h.call('stop', {'hook_event_name':'Stop', 'turn_id':'v7-finish', 'last_assistant_message':'WGC_ORCHESTRATOR_RESULT: '+json.dumps(value)}, self.cwd)

    def test_light_uses_two_agents_and_no_new_test_then_requires_root_evidence(self):
        self.h.activate()
        t = self.h.record_task(self.cwd, task(), assessment(task()))
        self.post('docs/copy.md', 'New copy')
        self.assertIsNone(self.h.record_agent(self.cwd,'implementor','implemented'))
        blocked = self.finish(t, acceptance_verified=False)
        self.assertIn('orchestrator-verification', blocked['reason'])
        # A separate turn is needed after a deliberate failed completion attempt.
        state = self.h.adaptive_state()
        value = dict(assessment_revision=t['assessment_revision'], input_revision=hooks.workspace_identity(state['context']), acceptance_verified=True, evidence_refs=['synthetic-visual-check'])
        self.assertIsNone(self.h.call('stop',{'hook_event_name':'Stop','turn_id':'v7-ok','last_assistant_message':'WGC_ORCHESTRATOR_RESULT: '+json.dumps(value)},self.cwd))
        state = self.h.adaptive_state()
        self.assertEqual({r['role'] for r in state['subagent_results']}, {'task-assessor','implementor'})
        self.assertEqual(len(state['subagent_inputs']), 2)
        self.assertFalse((self.cwd/'tests').exists())

    def test_unhooked_scope_expansion_drops_assessment_at_completion(self):
        self.h.activate()
        t = self.h.record_task(self.cwd, task(), assessment(task()))
        self.post('docs/copy.md', 'New copy')
        self.h.record_agent(self.cwd,'implementor','implemented')
        (self.cwd/'docs/extra.md').write_text('outside assessed scope')
        output = self.finish(t)
        self.assertIn('task-assessor', output['reason'])
        self.assertEqual(self.h.adaptive_state()['task_assessments'], [])

    def test_stale_assessment_revision_cannot_supply_review(self):
        self.h.activate()
        self.h.record_task(self.cwd, task(), assessment(task()))
        output = self.h.record_agent(self.cwd,'reviewer','approved',assessment_revision='0'*64)
        self.assertIn('assessment_revision',output['reason'])

    def test_standard_reuse_completes_without_test_author_and_protects_existing_test(self):
        existing=self.cwd/'tests/existing.test.ts'
        existing.parent.mkdir()
        existing.write_text('existing synthetic invariant')
        self.h.activate()
        self.h.call('post-tool',{'tool_name':'Bash','tool_input':{'command':'npm test -- --coverage'},'tool_response':{'exit_code':0}},self.cwd)
        t=task(mode='standard',risk='standard',risk_signals=['behavior'],test_disposition='reuse',assessed_paths=['backend:src/app.ts','backend:tests/existing.test.ts'])
        a=assessment(t)
        a['reuse_proof']={'test_id':'existing-case','test_path':'backend:tests/existing.test.ts','invariant_mapping':'changed behavior invariant','successful_run':True,'file_sha256':hashlib.sha256(existing.read_bytes()).hexdigest()}
        t=self.h.record_task(self.cwd,t,a)
        self.post('src/app.ts','export const value=1;')
        self.h.record_agent(self.cwd,'implementor','implemented')
        self.h.call('post-tool',{'tool_name':'Bash','tool_input':{'command':'npm test -- --coverage'},'tool_response':{'exit_code':0}},self.cwd)
        self.h.record_agent(self.cwd,'reviewer','approved')
        self.h.record_agent(self.cwd,'qa','pass')
        self.assertIsNone(self.finish(t))
        self.assertNotIn('test-maker',{r['role'] for r in self.h.adaptive_state()['subagent_results']})
        self.assertEqual(list((self.cwd/'tests').iterdir()),[existing])

    def test_standard_implementation_keeps_assessment_while_implementor_authors_planned_test(self):
        self.h.activate()
        t = task(
            mode='standard', risk='standard', risk_signals=['behavior'], test_disposition='add',
            assessed_paths=['backend:src/app.ts', 'backend:tests/app.test.ts'],
        )
        a = assessment(t)
        a.update(
            test_ownership='implementor',
            coverage_mode='targeted',
            test_plan={
                'action':'add', 'tests':['backend:tests/app.test.ts'], 'commands':['npm test -- tests/app.test.ts'],
                'expected_baseline':'missing regression coverage', 'actual_baseline':'missing regression coverage',
            },
        )
        t = self.h.record_task(self.cwd, t, a)
        self.post('tests/app.test.ts', "it('covers the change', () => {});")
        state = self.h.adaptive_state()
        self.assertEqual(len(state['test_assessments']), 1)
        self.assertEqual(state['test_assessments'][0]['test_ownership'], 'implementor')
        self.assertNotIn('test-maker', hooks.teams.required_gates('implementation', t))

    def test_standard_bugfix_add_update_requires_separate_test_maker(self):
        self.h.activate_bugfix()
        t = task(mode='standard', risk='standard', risk_signals=['behavior'], test_disposition='add')
        self.h.record_task(self.cwd, t)
        self.assertEqual(self.h.adaptive_state()['test_assessments'], [])
        self.assertIn('test-maker', hooks.teams.required_gates('bugfix', t))

    def test_compact_bugfix_requires_before_after_and_independent_rca_evidence(self):
        self.h.activate_bugfix(prompt='Use $wgc-bugfix to fix a typo')
        t = self.h.record_task(self.cwd, task(), assessment(task()))
        self.post('docs/copy.md', 'corrected')
        self.h.record_agent(self.cwd,'implementor','implemented')
        self.assertIn('orchestrator-verification', self.finish(t)['reason'])
        state = self.h.adaptive_state()
        value=dict(assessment_revision=t['assessment_revision'],input_revision=hooks.workspace_identity(state['context']),acceptance_verified=True,evidence_refs=['before-after'],reproduced_before=True,reproduced_after=True,root_cause_reviewed=True)
        self.assertIsNone(self.h.call('stop',{'hook_event_name':'Stop','turn_id':'bug-ok','last_assistant_message':'WGC_ORCHESTRATOR_RESULT: '+json.dumps(value)},self.cwd))

    def test_mixed_epic_has_per_item_gates_and_scope_isolation(self):
        self.h.activate_profile('epic-implementation',prompt='Use $wgc-epic-implementation without updating YouTrack')
        self.h.freeze_epic_items(self.cwd,[{'item_id':'L','item_revision':'a'*64},{'item_id':'F','item_revision':'b'*64}])
        light = task(item_id='L',item_revision='a'*64)
        self.h.record_task(self.cwd,light,{**assessment(light),'item_id':'L','item_revision':'a'*64})
        full = task(item_id='F',item_revision='b'*64,mode='full',risk='critical',risk_signals=['security'],test_disposition='add',assessed_paths=['backend:src/auth.ts'])
        self.h.record_task(self.cwd,full)
        self.h.record_agent(self.cwd,'implementor','implemented',item_id='L',item_revision='a'*64)
        self.h.record_agent(self.cwd,'product-manager','accepted','outcome',item_id='L',item_revision='a'*64)
        state=self.h.adaptive_state()
        state['current_revision']=hooks.workspace_identity(state['context'])
        gaps=hooks.epic_item_gaps(state)
        self.assertFalse(any(g.startswith('L@') for g in gaps),gaps)
        self.assertTrue(any(g.startswith('F@') and 'security' in g and 'test-maker' in g for g in gaps),gaps)
        self.post('docs/copy.md','changed light')
        self.assertEqual(len(self.h.adaptive_state()['task_assessments']),2)

    def test_failed_repeat_revokes_check_and_never_persists_output(self):
        self.h.activate()
        for code in (0,1):
            self.h.call('post-tool', {'hook_event_name':'PostToolUse','tool_name':'Bash','tool_input':{'command':'npm run lint'},'tool_response':{'exit_code':code,'output':'RAW_SENTINEL'}},self.cwd)
        state=self.h.adaptive_state()
        self.assertNotIn('lint',state['verification'])
        self.assertNotIn('RAW_SENTINEL',json.dumps(state))


if __name__ == '__main__':
    unittest.main()
