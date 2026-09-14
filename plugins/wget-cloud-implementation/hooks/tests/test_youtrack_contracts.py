"""Exercise new roles through the real parser/gates, using synthetic revisions."""
import json
import hashlib
import unittest
from unittest.mock import patch
import test_adaptive_teams as adaptive

hooks = adaptive.hooks


def snapshot(count=123):
    inv={'items':[{'item_id':f'BE-{i+1}','item_revision':'a'*64} for i in range(count)],
         'external_dependencies':[{'item_id':'FL-1','item_revision':'b'*64}]}
    inv['items'].sort(key=lambda x:x['item_id'])
    inv['revision']=hashlib.sha256(json.dumps(inv,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return inv


def report(inv):
    return {'inventory_revision':inv['revision'],
            'items':[{**e,'disposition':'implemented','evidence_refs':['qa-proof'],'decision_ref':''} for e in inv['items']],
            'external_dependencies':[{**e,'disposition':'satisfied','evidence_refs':['release-proof'],'decision_ref':''} for e in inv['external_dependencies']]}


class YouTrackContractsTests(unittest.TestCase):
    def result(self, role, verdict, profile='task-creation', **extra):
        marker = dict(role=role, verdict=verdict, phase='', input_revision='r1')
        marker.update(extra)
        return hooks.parse_agent_result('WGC_AGENT_RESULT: '+json.dumps(marker), profile)

    def test_new_roles_have_identical_phase_and_verdict_contracts_in_all_profiles(self):
        for profile in hooks.PROFILE_ROLE_VERDICTS:
            for role, verdict in [('effort-estimator','estimated'), ('youtrack-operator','synced'), ('youtrack-operator','partially_applied')]:
                with self.subTest(profile=profile,role=role):
                    value, error = self.result(role, verdict, profile)
                    self.assertIsNone(error)
                    self.assertEqual(value['role'], role)
            self.assertIsNotNone(self.result('effort-estimator','estimated',profile,phase='scope')[1])
            self.assertIsNotNone(self.result('github-project-operator','published',profile)[1])

    def test_creation_requires_product_research_and_independent_estimate_even_for_light(self):
        gates = hooks.teams.required_gates('task-creation', adaptive.task())
        self.assertTrue({'product','project','implementation-audit','effort-estimate','backlog-review'} <= gates)

    def test_partial_write_and_unknown_estimate_never_satisfy_completion(self):
        for profile, verdict, gate in [('task-creation','published','project-publish'),('epic-implementation','synced','project-sync')]:
            state = {'profile':profile, 'subagent_results':[]}
            for bad in ('partially_applied','authorization_required','blocked'):
                result,error=self.result('youtrack-operator',bad,profile)
                self.assertIsNone(error)
                state['subagent_results']=[result]
                self.assertNotIn(gate,hooks.approved_agent_gates(state,'r1'))
            result,_=self.result('youtrack-operator',verdict,profile)
            state['subagent_results']=[result]
            self.assertIn(gate,hooks.approved_agent_gates(state,'r1'))
            self.assertNotIn(gate,hooks.approved_agent_gates(state,'r2'))
        for verdict in ('needs_research','needs_input'):
            result,_=self.result('effort-estimator',verdict)
            self.assertNotIn('effort-estimate',hooks.approved_agent_gates({'profile':'task-creation','subagent_results':[result]},'r1'))

    def test_estimate_requires_current_workspace_and_assessment_revision(self):
        task=adaptive.task()
        value,_=self.result('effort-estimator','estimated',assessment_revision=task['assessment_revision'])
        state={'profile':'task-creation','task_assessments':[task],'subagent_results':[value]}
        self.assertIn('effort-estimate',hooks.approved_agent_gates(state,'r1'))
        self.assertNotIn('effort-estimate',hooks.approved_agent_gates(state,'r2'))
        value['assessment_revision']='0'*64
        self.assertNotIn('effort-estimate',hooks.approved_agent_gates(state,'r1'))

    def test_youtrack_creation_and_epic_routing_and_privacy_flags(self):
        for text, profile in [('Создай эпик в YouTrack','task-creation'),('Create YouTrack issue','task-creation'),('Реализуй эпик PRD-4','epic-implementation')]:
            self.assertEqual(hooks.workflow_profile(text)[0],profile)
        self.assertTrue(hooks.PROJECT_TARGET_SIGNAL.search('BE-17'))
        self.assertFalse(hooks.PROJECT_TARGET_SIGNAL.search('https://github.com/orgs/example/projects/1'))
        self.assertFalse(hooks.project_routes('Не создавай задачи в YouTrack','task-creation')['mutation_requested'])

    def test_last_batch_of_123_cannot_complete_the_whole_epic(self):
        inv=hooks.inventory.normalize(snapshot())
        final=report(inv)
        final['items']=final['items'][-23:]
        self.assertFalse(hooks.inventory.complete(final,inv))
        self.assertTrue(hooks.inventory.complete(report(inv),inv))
        self.assertTrue(hooks.inventory.covers_batch(inv,inv['items'][-23:]))
        self.assertFalse(hooks.inventory.covers_batch(inv,[{'item_id':'BE-999','item_revision':'a'*64}]))

    def test_deployed_cancelled_and_external_dependencies_have_explicit_dispositions(self):
        inv=snapshot(2); final=report(inv)
        final['items'][0]['disposition']='already-delivered'
        self.assertTrue(hooks.inventory.complete(final,inv))
        final['external_dependencies'][0]['disposition']='blocking'
        self.assertFalse(hooks.inventory.complete(final,inv))
        final['external_dependencies'][0]['disposition']='satisfied'
        final['items'][1]['disposition']='cancelled'
        self.assertFalse(hooks.inventory.complete(final,inv))
        final['items'][1]['decision_ref']='user-scope-decision'
        self.assertTrue(hooks.inventory.complete(final,inv))
        final['items'][1]['disposition']='deferred'
        self.assertFalse(hooks.inventory.complete(final,inv))

    def test_inventory_rejects_raw_content_duplicates_and_stale_evidence(self):
        inv=snapshot(2)
        for change in ('raw','duplicate','revision'):
            candidate=json.loads(json.dumps(inv))
            if change=='raw': candidate['raw_prompt']='private'
            if change=='duplicate': candidate['items'].append(candidate['items'][0])
            if change=='revision': candidate['revision']='0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):
                hooks.inventory.normalize(candidate)
        final=report(inv);final['items'][0]['item_revision']='c'*64
        self.assertFalse(hooks.inventory.complete(final,inv))

    def test_full_inventory_gate_is_bound_to_current_evidence(self):
        inv=snapshot(2)
        value,_=self.result('project-manager','progress_updated','epic-implementation',phase='reconcile',epic_reconciliation=report(inv))
        state={'profile':'epic-implementation','epic_inventory':inv,'subagent_results':[value],'selected_items':inv['items']}
        self.assertIn('epic-inventory',hooks.approved_agent_gates(state,'r1'))
        self.assertNotIn('epic-inventory',hooks.approved_agent_gates(state,'r2'))

    def test_prior_batches_require_archived_completion_at_matching_item_revision(self):
        inv=snapshot(2)
        value,_=self.result('project-manager','progress_updated','epic-implementation',phase='reconcile',epic_reconciliation=report(inv))
        state={'profile':'epic-implementation','epic_inventory':inv,'subagent_results':[value],
               'selected_items':[inv['items'][1]],'completed_epic_items':[]}
        self.assertNotIn('epic-inventory',hooks.approved_agent_gates(state,'r1'))
        state['completed_epic_items']=[inv['items'][0]]
        self.assertIn('epic-inventory',hooks.approved_agent_gates(state,'r1'))
        state['completed_epic_items']=[{**inv['items'][0],'item_revision':'c'*64}]
        self.assertNotIn('epic-inventory',hooks.approved_agent_gates(state,'r1'))

    def test_batch_rotation_archives_only_items_with_completed_actual_gates(self):
        inv=snapshot(3)
        state={'profile':'epic-implementation','epic_inventory':inv,'selected_items':[dict(e) for e in inv['items'][:2]],
               'subagent_results':[],'current_revision':'r1'}
        with patch.object(hooks,'epic_item_gaps',side_effect=lambda s: [] if s['selected_items'][0]['item_id']=='BE-1' else ['qa']):
            hooks.reconcile_selected_items(state,[inv['items'][2]])
        self.assertEqual(state['completed_epic_items'],[{**inv['items'][0],'evidence_revision':'r1','assessed_paths':[]}])
        self.assertEqual(state['selected_items'][0]['item_id'],'BE-3')

    def test_later_shared_unattributed_or_overlapping_changes_expire_archived_checks(self):
        entry={'item_id':'BE-1','item_revision':'a'*64,'evidence_revision':'r1','assessed_paths':['root:src/one.py']}
        for changed,sensitive,kept in [({'root:src/two.py'},False,True),
                                      ({'root:src/one.py'},False,False),
                                      ({'root:src/unowned.py'},False,False),
                                      ({'root:src/two.py'},True,False)]:
            state={'completed_epic_items':[entry], 'task_assessments':[{'assessed_paths':['root:src/two.py']}]}
            hooks.invalidate_archived_items(state,changed,sensitive)
            self.assertEqual(bool(state['completed_epic_items']),kept)

    def test_delivered_inventory_needs_no_invented_execution_witness(self):
        inv=snapshot(2); final=report(inv)
        for item in final['items']: item['disposition']='already-delivered'
        value,_=self.result('project-manager','progress_updated','epic-implementation',phase='reconcile',epic_reconciliation=final)
        state={'profile':'epic-implementation','epic_inventory':inv,'selected_items':[], 'subagent_results':[value]}
        self.assertIn('epic-inventory',hooks.approved_agent_gates(state,'r1'))
