"""Bounded task assessment and deterministic, risk-based team selection."""
import hashlib
import json
import re

DOMAINS = {'backend', 'frontend', 'site', 'front-lib', 'gitops'}
CRITICAL_SIGNALS = {'security', 'money', 'data', 'migration', 'contract', 'concurrency', 'incident', 'gitops'}
SIGNALS = CRITICAL_SIGNALS | {'architecture', 'cross-repo', 'browser', 'behavior', 'reliability'}
CHECKS = {'test', 'coverage', 'typecheck', 'lint', 'build', 'consumer', 'proto-gen', 'prisma', 'gitops-render', 'validate', 'browser', 'smoke', 'pack'}
FIELDS = {'assessment_revision', 'plan_revision', 'acceptance_revision', 'mode', 'complexity', 'risk', 'domains', 'risk_signals', 'assessed_paths', 'checks', 'test_disposition', 'rationale', 'evidence_refs', 'item_id', 'item_revision'}


def assessment_revision(value):
    material = {k: v for k, v in value.items() if k != 'assessment_revision'}
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def path_signals(paths):
    signals = set()
    for path in paths:
        name = path.lower().replace('\\', '/')
        if name.startswith('k8s:'):
            signals.add('gitops')
        if re.search(r'(?:^|[/_.:-])(auth|rbac|tenant|permissions?)(?:[/_.-]|$)', name):
            signals.add('security')
        if '/migration' in name or 'schema.prisma' in name:
            signals.add('migration')
        if name.endswith('.proto') or '/proto/' in name or 'openapi' in name:
            signals.add('contract')
        if name.startswith('wget-cloud-front-lib:') and any(s in name for s in ('/index.ts', 'package.json', '/domain-types/', '/widget-core/', '/site-blocks/', '/shared-lib/')):
            signals.add('contract')
    return signals


def normalize(value):
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError('TaskAssessment contains unknown fields or is not an object')
    required = FIELDS - {'item_id', 'item_revision'}
    if required - set(value):
        raise ValueError('TaskAssessment missing fields: ' + ', '.join(sorted(required - set(value))))
    result = dict(value)
    for key in ('plan_revision', 'acceptance_revision', 'rationale'):
        if not isinstance(value[key], str) or not 0 < len(value[key]) <= 500 or '\n' in value[key]:
            raise ValueError('TaskAssessment requires bounded ' + key)
    for key, allowed in (('domains', DOMAINS), ('risk_signals', SIGNALS), ('checks', CHECKS)):
        values = value[key]
        if not isinstance(values, list) or len(values) > 32 or any(not isinstance(v, str) or v not in allowed for v in values) or len(set(values)) != len(values):
            raise ValueError('TaskAssessment invalid ' + key)
        if values != sorted(values):
            raise ValueError(key + ' must be sorted')
    for key in ('assessed_paths', 'evidence_refs'):
        values = value[key]
        if not isinstance(values, list) or not 1 <= len(values) <= 100 or any(not isinstance(v, str) or not 0 < len(v) <= 200 or '\n' in v for v in values):
            raise ValueError('TaskAssessment requires bounded ' + key)
        if len(values) != len(set(values)):
            raise ValueError('TaskAssessment duplicate ' + key)
    if not value['domains'] or value['complexity'] not in {'small', 'medium', 'large'} or value['risk'] not in {'low', 'standard', 'critical'} or value['mode'] not in {'light', 'standard', 'full'} or value['test_disposition'] not in {'add', 'update', 'reuse', 'none'}:
        raise ValueError('TaskAssessment invalid route or disposition')
    signals = set(value['risk_signals'])
    detected = path_signals(value['assessed_paths'])
    if not detected <= signals:
        raise ValueError('TaskAssessment omits sensitive path signals: ' + ', '.join(sorted(detected - signals)))
    critical = bool(signals & (CRITICAL_SIGNALS | {'reliability'})) or 'gitops' in value['domains']
    if critical and value['risk'] != 'critical':
        raise ValueError('critical signals cannot lower risk')
    if (critical or value['risk'] == 'critical' or value['complexity'] == 'large' or signals & {'architecture', 'cross-repo'}) and value['mode'] != 'full':
        raise ValueError('critical/architecture/cross-repo/large tasks require Full')
    if value['risk'] == 'critical' and value['test_disposition'] == 'none':
        raise ValueError('critical + none is forbidden')
    if value['mode'] == 'light' and (value['risk'] != 'low' or value['complexity'] != 'small' or signals - {'browser'} or value['test_disposition'] != 'none'):
        raise ValueError('Light requires a small, nonbehavioral low-risk change and none')
    if ('item_id' in value) != ('item_revision' in value):
        raise ValueError('item_id and item_revision must be supplied together')
    if 'item_id' in value and (not isinstance(value['item_id'], str) or not 0 < len(value['item_id']) <= 200 or not re.fullmatch('[0-9a-f]{64}', str(value['item_revision']))):
        raise ValueError('invalid item identity')
    if value['assessment_revision'] != assessment_revision(value):
        raise ValueError('TaskAssessment assessment_revision must match its canonical SHA-256')
    return result


def active(state, item_id=None):
    for value in reversed(state.get('task_assessments', [])):
        if value.get('item_id') == item_id:
            return value
    return None


def required_gates(profile, task):
    gates = {'task-assessor'}
    if not task:
        return gates
    mode = task['mode']
    signals = set(task['risk_signals'])
    if profile == 'task-creation':
        gates |= {'backlog-review', 'effort-estimate', 'product', 'project', 'implementation-audit'}
        if mode == 'full':
            gates.add('architect')
        return gates
    gates.add('implementor')
    if mode != 'light':
        gates |= {'reviewer', 'qa'}
    if mode == 'full':
        gates |= {'architect', 'architecture-plan', 'architecture', 'test-maker'}
    if task['test_disposition'] in {'add', 'update'}:
        gates.add('test-maker')
    if profile == 'bugfix' and mode == 'full':
        gates |= {'bug-triage', 'evidence', 'root-cause', 'root-cause-review', 'reproducer'}
    mapping = {'security': 'security', 'contract': 'contract', 'data': 'data', 'migration': 'data', 'concurrency': 'reliability', 'reliability': 'reliability'}
    gates |= {gate for signal, gate in mapping.items() if signal in signals}
    if 'browser' in signals and mode != 'light':
        gates.add('browser')
    if 'gitops' in signals or 'gitops' in task['domains']:
        gates |= {'devops', 'infrastructure'}
    if profile == 'epic-implementation':
        gates.add('product-outcome')
    return gates


def invalidate(state, paths):
    """Scope expansion drops assessments; all writes drop affected completion evidence."""
    paths = set(paths)
    assessments = state.get('task_assessments', [])
    all_scope = {p for a in assessments for p in a['assessed_paths']}
    unknown = bool(paths - all_scope)
    removed = set()
    for task in assessments:
        owned = paths & set(task['assessed_paths'])
        if unknown or path_signals(owned) - set(task['risk_signals']):
            removed.add(task.get('item_id'))
    state['task_assessments'] = [a for a in assessments if a.get('item_id') not in removed]
    if removed:
        state['task_reassessment_required'] = True
    return removed
