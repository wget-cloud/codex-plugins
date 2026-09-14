"""Bounded, privacy-safe identity coverage across epic execution batches.

This verifies coverage/revisions, not the truth of external evidence. The
orchestrator still independently reads YouTrack and verifies referenced artifacts.
"""
import hashlib
import json
import re

LIMIT = 10000
DISPOSITIONS = {'implemented', 'already-delivered', 'blocked-by-external', 'deferred', 'cancelled'}


def normalize(value):
    if not isinstance(value, dict) or set(value) != {'revision', 'items', 'external_dependencies'}:
        raise ValueError('epic_inventory requires revision, items and external_dependencies')
    result = {}
    all_ids = set()
    for field in ('items', 'external_dependencies'):
        entries = value[field]
        if not isinstance(entries, list) or len(entries) > LIMIT or (field == 'items' and not entries):
            raise ValueError('epic inventory must be complete and bounded; never truncate it')
        result[field] = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'item_id', 'item_revision'}:
                raise ValueError('inventory entries allow only identity and revision')
            identity, revision = entry['item_id'], entry['item_revision']
            if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', identity) or identity in all_ids:
                raise ValueError('inventory IDs must be unique issue IDs, including external dependencies')
            if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{64}', revision):
                raise ValueError('inventory item_revision must be SHA-256')
            all_ids.add(identity)
            result[field].append(dict(entry))
        result[field].sort(key=lambda e: e['item_id'])
    digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if value['revision'] != digest:
        raise ValueError('epic inventory revision must hash its canonical complete contents')
    result['revision'] = digest
    return result


def covers_batch(snapshot, selected):
    identities = {(e['item_id'], e['item_revision']) for e in snapshot['items']}
    return all((e['item_id'], e['item_revision']) in identities for e in selected)


def normalize_report(value, snapshot):
    if not snapshot or not isinstance(value, dict) or set(value) != {'inventory_revision', 'items', 'external_dependencies'}:
        raise ValueError('epic_reconciliation requires a complete frozen inventory')
    if value['inventory_revision'] != snapshot['revision']:
        raise ValueError('epic reconciliation inventory revision is stale')
    for field in ('items', 'external_dependencies'):
        rows = value[field]
        expected = {e['item_id']: e['item_revision'] for e in snapshot[field]}
        if not isinstance(rows, list) or len(rows) != len(expected):
            raise ValueError('epic reconciliation must cover every inventory item and external dependency')
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {'item_id','item_revision','disposition','evidence_refs','decision_ref'}:
                raise ValueError('reconciliation allows only bounded disposition and evidence references')
            identity = row['item_id']
            if not isinstance(identity,str) or identity in seen or identity not in expected or row['item_revision'] != expected[identity]:
                raise ValueError('reconciliation identity/revision mismatch')
            seen.add(identity)
            allowed = DISPOSITIONS if field == 'items' else {'satisfied', 'blocking', 'not-required'}
            if row['disposition'] not in allowed:
                raise ValueError('invalid inventory disposition')
            refs = row['evidence_refs']
            if not isinstance(refs,list) or not 1 <= len(refs) <= 10 or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}',x) for x in refs):
                raise ValueError('evidence references must be bounded opaque handles, not raw content')
            decision = row['decision_ref']
            if not isinstance(decision,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{0,200}',decision):
                raise ValueError('invalid decision reference')
            if row['disposition'] in {'cancelled','deferred','not-required'} and not decision:
                raise ValueError('scope exclusions require an explicit user decision reference')
    # JSON copy prevents caller mutation of an accepted report.
    return json.loads(json.dumps(value))


def complete(report, snapshot):
    try:
        normalize_report(report, snapshot)
    except (ValueError, TypeError, KeyError):
        return False
    return not any(row['disposition'] in {'blocked-by-external','deferred','blocking'}
                   for field in ('items','external_dependencies') for row in report[field])
