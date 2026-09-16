"""Validate bounded epic transition assertions. No network or authority inference.

The orchestrator must verify MCP snapshots and human decision provenance.
These predicates cannot prove that an agent's assertions match the real world.
"""
import json
import re

STAGES = {'Backlog', 'Исследование', 'Груминг', 'К реализации', 'Декомпозиция',
          'Готово к разработке', 'В разработке', 'Готово к выпуску', 'Приёмка', 'Реализован'}
TASK_STAGES = {'К выполнению', 'В работе', 'Ревью', 'Готово к dev', 'На dev',
               'Тестирование', 'Готово к релизу', 'На production', 'Закрыто', 'Отменено'}
FACTS = {'inventory_complete', 'epic_described', 'questions_resolved', 'grooming_complete',
         'decomposition_complete', 'blocking_findings'}
KINDS = {'research_to_grooming', 'grooming_passed', 'development_ready', 'production_accepted'}
VERDICTS = {'stage_ready', 'awaiting_user', 'stage_blocked'}


def handle(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}', value) is not None


def normalize(value):
    fields = FACTS | {'epic_id', 'scope_revision', 'from_stage', 'to_stage', 'tasks', 'approvals', 'evidence_refs'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('EpicStagePlan requires its exact field set')
    if not handle(value['epic_id']) or not isinstance(value['scope_revision'], str) or not re.fullmatch('[a-f0-9]{64}', value['scope_revision']):
        raise ValueError('EpicStagePlan requires epic identity and scope revision')
    if value['from_stage'] not in STAGES or value['to_stage'] not in STAGES:
        raise ValueError('EpicStagePlan unknown stage')
    if any(type(value[f]) is not bool for f in FACTS):
        raise ValueError('EpicStagePlan facts must be boolean')
    refs = value['evidence_refs']
    if not isinstance(refs, list) or not 1 <= len(refs) <= 20 or not all(handle(r) for r in refs):
        raise ValueError('EpicStagePlan requires bounded evidence handles')
    tasks = value['tasks']
    if not isinstance(tasks, list) or len(tasks) > 10000:
        raise ValueError('EpicStagePlan task inventory exceeds bound')
    seen = set()
    for t in tasks:
        if not isinstance(t, dict) or set(t) != {'id', 'kind', 'stage', 'ready', 'completed', 'production_verified', 'user_accepted', 'evidence_ref', 'exclusion_decision_ref'}:
            raise ValueError('EpicStagePlan invalid task fields')
        if not handle(t['id']) or t['id'] in seen or t['kind'] not in {'development', 'research', 'cancelled'} or t['stage'] not in TASK_STAGES:
            raise ValueError('EpicStagePlan invalid task identity, kind or stage')
        seen.add(t['id'])
        if any(type(t[k]) is not bool for k in ('ready', 'completed', 'production_verified', 'user_accepted')) or not handle(t['evidence_ref']):
            raise ValueError('EpicStagePlan invalid task evidence')
        if t['kind'] == 'cancelled':
            if t['stage'] != 'Отменено' or not handle(t['exclusion_decision_ref']):
                raise ValueError('Cancelled task needs actual status and user scope decision')
        elif t['exclusion_decision_ref'] != '':
            raise ValueError('Only cancelled tasks have exclusion decisions')
        elif t['stage'] == 'Отменено':
            raise ValueError('Cancelled status requires an explicit scope exclusion decision')
    approvals = value['approvals']
    if not isinstance(approvals, list) or len(approvals) > 4:
        raise ValueError('EpicStagePlan invalid approvals')
    kinds = set()
    for a in approvals:
        if not isinstance(a, dict) or set(a) != {'kind', 'scope_revision', 'decision_ref'}:
            raise ValueError('EpicStagePlan invalid approval fields')
        if a['kind'] not in KINDS or a['kind'] in kinds or a['scope_revision'] != value['scope_revision'] or not handle(a['decision_ref']):
            raise ValueError('EpicStagePlan stale or invalid approval')
        kinds.add(a['kind'])
    return json.loads(json.dumps(value))


def gaps(plan):
    p = normalize(plan)
    source, target = p['from_stage'], p['to_stage']
    pair = source, target
    edges = {('Backlog', 'Исследование'), ('Исследование', 'Груминг'), ('Груминг', 'Исследование'),
             ('Груминг', 'К реализации'), ('К реализации', 'Декомпозиция'), ('Декомпозиция', 'Груминг'),
             ('Декомпозиция', 'Готово к разработке'), ('Готово к разработке', 'В разработке'),
             ('В разработке', 'Готово к выпуску'), ('Готово к выпуску', 'Приёмка'), ('Приёмка', 'Реализован')}
    if pair not in edges:
        return ['transition_not_allowed']
    missing = []
    backwards = pair in {('Груминг', 'Исследование'), ('Декомпозиция', 'Груминг')}
    if backwards:
        if p['questions_resolved'] and not p['blocking_findings']:
            missing.append('return_reason_required')
        return missing
    if not p['inventory_complete']:
        missing.append('incomplete_inventory')
    if not p['epic_described']:
        missing.append('epic_description_required')
    if source != 'Backlog':
        if not p['questions_resolved']:
            missing.append('questions_open')
        if p['blocking_findings']:
            missing.append('blocking_findings')
        if any(t['kind'] == 'research' and not t['completed'] for t in p['tasks']):
            missing.append('research_incomplete')
    approval = {('Исследование', 'Груминг'): 'research_to_grooming', ('Груминг', 'К реализации'): 'grooming_passed',
                ('Декомпозиция', 'Готово к разработке'): 'development_ready', ('Приёмка', 'Реализован'): 'production_accepted'}.get(pair)
    if approval and not any(a['kind'] == approval for a in p['approvals']):
        missing.append('approval_required:' + approval)
    if source in {'Груминг', 'К реализации'} and not p['grooming_complete']:
        missing.append('grooming_incomplete')
    dev = [t for t in p['tasks'] if t['kind'] == 'development']
    if source in {'Декомпозиция', 'Готово к разработке', 'В разработке', 'Готово к выпуску', 'Приёмка'} and not dev:
        missing.append('development_inventory_empty')
    if pair == ('Декомпозиция', 'Готово к разработке') and (not p['decomposition_complete'] or not all(t['ready'] for t in dev)):
        missing.append('decomposition_not_ready')
    if pair == ('Готово к разработке', 'В разработке') and not any(t['stage'] not in {'К выполнению', 'Отменено'} for t in dev):
        missing.append('development_not_started')
    if target == 'Готово к выпуску' and not all(t['completed'] and t['stage'] == 'Готово к релизу' for t in dev):
        missing.append('development_not_release_ready')
    if target == 'Приёмка' and not all(t['production_verified'] and t['stage'] == 'На production' for t in dev):
        missing.append('development_not_on_production')
    if target == 'Реализован' and not all(t['production_verified'] and t['user_accepted'] and t['stage'] in {'На production', 'Закрыто'} for t in dev):
        missing.append('user_production_acceptance_missing')
    return missing


def pending_user(state, revision):
    """An interview pause is not a fabricated completed backlog."""
    for r in reversed(state.get('subagent_results', [])):
        if r.get('role') == 'project-manager' and r.get('phase') == 'lifecycle':
            if r.get('input_revision') != revision or r.get('verdict') != 'awaiting_user':
                return False
            try:
                missing = gaps(r['epic_stage_plan'])
                return any(g == 'questions_open' or g.startswith('approval_required:') for g in missing)
            except (ValueError, KeyError, TypeError):
                return False
    return False


def matches_inventory(plan, state):
    """A forward milestone cannot shrink a previously recorded full inventory."""
    known = state.get('epic_inventory')
    if not known or (plan['from_stage'], plan['to_stage']) in {
            ('Груминг', 'Исследование'), ('Декомпозиция', 'Груминг')}:
        return True
    return {t['id'] for t in plan['tasks']} == {t['item_id'] for t in known.get('items', [])}


def stage_checkpoint(state, revision):
    """Confirmed early-stage progress may end a turn without completing backlog."""
    results = state.get('subagent_results', [])
    managers = [r for r in results if r.get('role') == 'project-manager' and r.get('phase') == 'lifecycle']
    if not managers:
        return False
    pm = managers[-1]
    if pm.get('verdict') != 'stage_ready' or pm.get('input_revision') != revision:
        return False
    try:
        plan = normalize(pm['epic_stage_plan'])
        if gaps(plan) or not matches_inventory(plan, state) or plan['to_stage'] not in {'Исследование', 'Груминг', 'К реализации', 'Декомпозиция'}:
            return False
    except (ValueError, KeyError, TypeError):
        return False
    operators = [r for r in results if r.get('role') == 'youtrack-operator']
    return bool(operators and operators[-1].get('input_revision') == revision
                and operators[-1].get('verdict') in {'synced', 'published', 'no_changes'}
                and operators[-1].get('epic_stage_plan') == plan
                and operators[-1].get('assessment_revision') == pm.get('assessment_revision'))
