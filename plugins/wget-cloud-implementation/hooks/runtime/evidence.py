"""Metadata-only verification records; never persist commands or output."""
import hashlib
import json


def environment_key(context):
    return hashlib.sha256(str(context.get('cwd', context.get('root', ''))).encode()).hexdigest()


def record(command_record, revision, environment, scope, owner):
    return {**command_record, 'revision': revision, 'environment': environment,
            'scope': sorted(scope)[:100], 'owner': owner[:200], 'successful': True}


def invalidate(verification, changed_paths):
    changed = set(changed_paths)
    for key in list(verification):
        scope = set(verification[key].get('scope', []))
        if not scope or not changed.isdisjoint(scope):
            verification.pop(key, None)
