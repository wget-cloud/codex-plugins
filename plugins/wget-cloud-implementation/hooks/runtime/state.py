"""Conservative v4 migration and bounded lifecycle state validation."""
from .contracts import STATE_VERSION, ADAPTIVE_LEDGER_LIMIT, RESULT_LEDGER_LIMIT
from . import teams


def migrate_state_v4(state):
    previous = state.get('version')
    if previous in (2, 3):
        # Preserve identity/baseline only: old approvals lack a TaskAssessment binding.
        for key in ('subagent_results', 'test_assessments', 'task_assessments'):
            state[key] = []
        state['verification'] = {}
        state['subagent_inputs'] = {}
        selected = state.get('selected_items', [])
        if not isinstance(selected, list):
            state['state_health'] = 'malformed'
            state['repository_reaudit_required'] = True
            selected = []
            state['selected_items'] = []
        for item in selected:
            if isinstance(item, dict):
                item['gates'] = []
        state['task_reassessment_required'] = True
        state['migration'] = {'from': previous, 'to': STATE_VERSION, 'invalidated': 'legacy approvals and verification; fresh TaskAssessment required'}
    elif previous not in (None, STATE_VERSION):
        state['state_health'] = 'unsupported_version'
        state['repository_reaudit_required'] = True
    state['version'] = STATE_VERSION
    for key, limit in (('test_assessments', ADAPTIVE_LEDGER_LIMIT), ('task_assessments', ADAPTIVE_LEDGER_LIMIT), ('selected_items', ADAPTIVE_LEDGER_LIMIT), ('subagent_results', RESULT_LEDGER_LIMIT)):
        values = state.setdefault(key, [])
        if not isinstance(values, list) or len(values) > limit or any(not isinstance(v, dict) for v in values):
            state['state_health'] = 'malformed'
            state['repository_reaudit_required'] = True
    try:
        tasks = state.get('task_assessments', [])
        identities = set()
        for task in tasks:
            teams.normalize(task)
            key = task.get('item_id')
            if key in identities:
                raise ValueError('duplicate assessment')
            identities.add(key)
    except (ValueError, TypeError, KeyError, AttributeError):
        state['task_assessments'] = []
        state['state_health'] = 'malformed'
        state['repository_reaudit_required'] = True
    return state
