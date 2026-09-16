"""Epic milestones, explicit human decisions, and stage-scoped turn endings."""
import copy
import json
import unittest
from unittest.mock import patch
import test_adaptive_teams as adaptive

hooks = adaptive.hooks
stages = hooks.epic_stages


def plan(source='Исследование', target='Груминг'):
    return dict(epic_id='PRD-42', scope_revision='a'*64, from_stage=source, to_stage=target,
                inventory_complete=True, epic_described=True, questions_resolved=True,
                grooming_complete=True, decomposition_complete=True, blocking_findings=False,
                evidence_refs=['snapshot-1'], approvals=[], tasks=[])


def approve(p, kind):
    p['approvals'].append(dict(kind=kind, scope_revision=p['scope_revision'], decision_ref='decision-1'))


def task(kind='development', stage='К выполнению', id='BE-42'):
    return dict(id=id, kind=kind, stage=stage, ready=True, completed=True,
                production_verified=True, user_accepted=True, evidence_ref='task-proof',
                exclusion_decision_ref='decision-cancel' if kind=='cancelled' else '')


def marker(p, verdict='stage_ready', role='project-manager', profile='task-creation', phase=None):
    return hooks.parse_agent_result('WGC_AGENT_RESULT: '+json.dumps(dict(role=role,verdict=verdict,
        phase=phase if phase is not None else ('lifecycle' if role=='project-manager' else ''),
        input_revision='r1',epic_stage_plan=p)),profile)


class EpicStagesTests(unittest.TestCase):
    def test_research_needs_closed_questions_completed_research_and_human_approval(self):
        p=plan(); self.assertIn('approval_required:research_to_grooming', stages.gaps(p))
        approve(p,'research_to_grooming'); self.assertEqual(stages.gaps(p),[])
        p['questions_resolved']=False; self.assertIn('questions_open',stages.gaps(p))
        p['questions_resolved']=True; p['tasks']=[task('research')]
        p['tasks'][0]['completed']=False; self.assertIn('research_incomplete',stages.gaps(p))

    def test_each_allowed_edge_and_no_stage_skips(self):
        examples=[('Backlog','Исследование',None,None),('Исследование','Груминг','research_to_grooming',None),
                  ('Груминг','К реализации','grooming_passed',None),('К реализации','Декомпозиция',None,None),
                  ('Декомпозиция','Готово к разработке','development_ready','К выполнению'),
                  ('Готово к разработке','В разработке',None,'В работе'),
                  ('В разработке','Готово к выпуску',None,'Готово к релизу'),
                  ('Готово к выпуску','Приёмка',None,'На production'),
                  ('Приёмка','Реализован','production_accepted','На production')]
        for src,dst,approval,status in examples:
            p=plan(src,dst)
            if approval:approve(p,approval)
            if status:p['tasks']=[task(stage=status)]
            with self.subTest(edge=(src,dst)):self.assertEqual(stages.gaps(p),[])
        self.assertIn('transition_not_allowed',stages.gaps(plan('Исследование','Готово к разработке')))

    def test_returns_require_reason_and_new_scope_expires_old_decision(self):
        for src,dst in [('Груминг','Исследование'),('Декомпозиция','Груминг')]:
            p=plan(src,dst);self.assertIn('return_reason_required',stages.gaps(p))
            p['questions_resolved']=False;p['inventory_complete']=False
            self.assertEqual(stages.gaps(p),[])
        p=plan();approve(p,'research_to_grooming');p['scope_revision']='b'*64
        with self.assertRaises(ValueError):stages.normalize(p)

    def test_decomposition_requires_all_tasks_full_inventory_and_approval(self):
        p=plan('Декомпозиция','Готово к разработке');approve(p,'development_ready')
        self.assertIn('development_inventory_empty',stages.gaps(p))
        p['tasks']=[task(),task(id='FE-42')];self.assertEqual(stages.gaps(p),[])
        p['tasks'][1]['ready']=False;self.assertIn('decomposition_not_ready',stages.gaps(p))
        p['tasks'][1]['ready']=True;p['inventory_complete']=False
        self.assertIn('incomplete_inventory',stages.gaps(p))
        p['inventory_complete']=True;p['approvals']=[]
        self.assertIn('approval_required:development_ready',stages.gaps(p))

    def test_first_development_task_starts_epic_but_research_does_not(self):
        p=plan('Готово к разработке','В разработке');p['tasks']=[task(),task('research','В работе',id='BE-43')]
        self.assertIn('development_not_started',stages.gaps(p))
        p['tasks'][0]['stage']='В работе';self.assertEqual(stages.gaps(p),[])

    def test_exact_release_and_production_statuses_exclude_completed_research_and_cancelled(self):
        p=plan('В разработке','Готово к выпуску')
        p['tasks']=[task(stage='Готово к релизу'),task('research','Закрыто',id='BE-43'),task('cancelled','Отменено',id='FE-44')]
        self.assertEqual(stages.gaps(p),[])
        p['tasks'].append(task(stage='На dev',id='FE-45'))
        self.assertIn('development_not_release_ready',stages.gaps(p))
        p['tasks'].pop();p['from_stage']='Готово к выпуску';p['to_stage']='Приёмка'
        self.assertIn('development_not_on_production',stages.gaps(p))
        p['tasks'][0]['stage']='На production';self.assertEqual(stages.gaps(p),[])
        p['tasks'][0]['production_verified']=False;self.assertIn('development_not_on_production',stages.gaps(p))

    def test_user_production_acceptance_cannot_be_replaced_by_qa_or_closed_status(self):
        p=plan('Приёмка','Реализован');p['tasks']=[task(stage='Закрыто')]
        self.assertIn('approval_required:production_accepted',stages.gaps(p))
        approve(p,'production_accepted');self.assertEqual(stages.gaps(p),[])
        p['tasks'][0]['user_accepted']=False;self.assertIn('user_production_acceptance_missing',stages.gaps(p))

    def test_last_batch_cannot_replace_previously_recorded_full_inventory(self):
        p=plan('В разработке','Готово к выпуску');p['tasks']=[task(stage='Готово к релизу')]
        pm,_=marker(p,profile='epic-implementation');op,_=marker(p,profile='epic-implementation',role='youtrack-operator',verdict='synced')
        state={'profile':'epic-implementation','subagent_results':[pm,op],
               'epic_inventory':{'items':[{'item_id':'BE-42'},{'item_id':'FE-43'}]}}
        self.assertNotIn('project-sync',hooks.approved_agent_gates(state,'r1'))
        p['tasks'].append(task(stage='Готово к релизу',id='FE-43'))
        pm,_=marker(p,profile='epic-implementation');op,_=marker(p,profile='epic-implementation',role='youtrack-operator',verdict='synced')
        state['subagent_results']=[pm,op];self.assertIn('project-sync',hooks.approved_agent_gates(state,'r1'))

    def test_phase_verdict_and_operator_plan_contracts_all_profiles(self):
        p=plan();approve(p,'research_to_grooming')
        for profile in hooks.PROFILE_ROLE_VERDICTS:
            self.assertIsNone(marker(p,profile=profile)[1])
            self.assertIsNotNone(marker(p,profile=profile,phase='')[1])
            self.assertIsNotNone(marker(p,profile=profile,verdict='planned')[1])
            self.assertIsNotNone(marker(p,profile=profile,role='implementor',verdict='implemented',phase='')[1])
        pm,_=marker(p);op,_=marker(p,role='youtrack-operator',verdict='published')
        state={'profile':'task-creation','subagent_results':[op]}
        self.assertNotIn('project-publish',hooks.approved_agent_gates(state,'r1'))
        state['subagent_results']=[pm,op];self.assertIn('project-publish',hooks.approved_agent_gates(state,'r1'))
        op['epic_stage_plan']=copy.deepcopy(p);op['epic_stage_plan']['scope_revision']='b'*64
        self.assertNotIn('project-publish',hooks.approved_agent_gates(state,'r1'))

    def test_pending_user_and_confirmed_early_stage_do_not_fake_completed_backlog(self):
        p=plan();pm,error=marker(p,'awaiting_user');self.assertIsNone(error)
        state={'subagent_results':[pm]}
        self.assertTrue(stages.pending_user(state,'r1'));self.assertFalse(stages.pending_user(state,'r2'))
        self.assertFalse(stages.stage_checkpoint(state,'r1'))
        approve(p,'research_to_grooming');pm,_=marker(p);op,_=marker(p,role='youtrack-operator',verdict='synced')
        state['subagent_results']=[pm,op];self.assertTrue(stages.stage_checkpoint(state,'r1'))
        op['verdict']='partially_applied';self.assertFalse(stages.stage_checkpoint(state,'r1'))

    def test_stop_allows_interview_only_without_repository_changes_and_keeps_state_active(self):
        for profile in hooks.PROFILE_ROLE_VERDICTS:
            pm,_=marker(plan(),'awaiting_user',profile=profile)
            state={'active':True,'profile':profile,'state_health':'healthy','subagent_results':[pm]}
            with self.subTest(profile=profile),patch.object(hooks,'update_state',return_value=state),patch.object(hooks,'workspace_snapshot',return_value={}),patch.object(hooks,'snapshot_since_baseline',return_value={}),patch.object(hooks,'classify_paths',return_value={'paths':[]}),patch.object(hooks,'workspace_identity',return_value='r1'):
                self.assertIsNone(hooks.handle_stop({},{}))
            self.assertTrue(state['active']);self.assertNotIn('completed_at',state)

    def test_raw_content_duplicate_tasks_and_unapproved_cancellation_are_rejected(self):
        p=plan();p['raw_prompt']='private'
        self.assertIsNotNone(marker(p)[1])
        p=plan();p['tasks']=[task(),task()]
        with self.assertRaises(ValueError):stages.normalize(p)
        p['tasks']=[task('cancelled','Отменено')];p['tasks'][0]['exclusion_decision_ref']=''
        with self.assertRaises(ValueError):stages.normalize(p)
