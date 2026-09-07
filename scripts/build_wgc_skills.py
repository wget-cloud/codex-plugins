#!/usr/bin/env python3
"""Compile explicitly composed, portable WGC skills using only the stdlib."""
import argparse
import json
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def safe_file(root, name):
    part = PurePosixPath(name)
    if not name or name != part.as_posix() or part.is_absolute() or any(p in ('..', '.') for p in part.parts) or '\\' in name:
        raise ValueError('composition path must be a relative portable path')
    target = root / part
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('composition path escapes its root')
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('symlinks are not composition inputs or outputs')
        cursor = cursor.parent
    return target


def render(root):
    source = root / 'plugin-src/wget-cloud-implementation'
    output = root / 'plugins/wget-cloud-implementation/skills'
    manifest = json.loads((source / 'composition.json').read_text())
    if set(manifest) != {'version', 'skills'} or manifest['version'] != 1:
        raise ValueError('unsupported composition schema')
    rendered = {}
    used = set()
    for skill, entries in manifest['skills'].items():
        if skill not in {'wgc-implementation', 'wgc-bugfix', 'wgc-task-creation', 'wgc-epic-implementation'}:
            raise ValueError('unknown skill')
        for entry in entries:
            if set(entry) != {'target', 'sources'} or not isinstance(entry['sources'], list) or not entry['sources']:
                raise ValueError('each target requires explicit sources')
            destination = safe_file(output, skill + '/' + entry['target'])
            if destination in rendered:
                raise ValueError('duplicate composition target')
            pieces = []
            for name in entry['sources']:
                path = safe_file(source, name)
                if path.suffix not in {'.md', '.yaml'}:
                    raise ValueError('unsupported composition input')
                used.add(path)
                pieces.append(path.read_text(encoding='utf-8').rstrip())
            rendered[destination] = '\n\n'.join(pieces) + '\n'
    unexpected = set(output.rglob('*')) - set(rendered)
    if any(p.is_file() for p in unexpected):
        raise ValueError('undeclared output files: ' + ', '.join(str(p.relative_to(output)) for p in sorted(unexpected) if p.is_file()))
    unused = {p for p in source.rglob('*') if p.is_file() and p.suffix in {'.md', '.yaml'}} - used
    if unused:
        raise ValueError('unused composition sources: ' + ', '.join(str(p.relative_to(source)) for p in sorted(unused)))
    return rendered


def build(root=ROOT, check=False):
    rendered = render(root)
    stale = [p for p, content in rendered.items() if not p.exists() or p.read_text(encoding='utf-8') != content]
    if check and stale:
        raise ValueError('stale generated skills: ' + ', '.join(str(p.relative_to(root)) for p in stale))
    if not check:
        for path in stale:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered[path], encoding='utf-8')
    return len(rendered)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(f'WGC composition valid: {build(check=args.check)} portable files')
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
