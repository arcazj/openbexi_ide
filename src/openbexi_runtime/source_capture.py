"""Capture bounded committed Git trees without checkout hooks or archive extraction."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import uuid

from .session_store import canonical

MAX_FILE = 8 * 1024 * 1024
MAX_TREE = 64 * 1024 * 1024
MAX_FILES = 4096


def git(project, *args, input=None):
    result = subprocess.run(['git', '--no-replace-objects', '-C', str(project), *args],
                            input=input, capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Source capture requires a readable committed Git project')
    return result.stdout


def capture(project, script, directory):
    project = Path(project).resolve()
    root = Path(os.fsdecode(git(project, 'rev-parse', '--show-toplevel')).strip()).resolve()
    if project != root:
        raise ValueError('Durable session project must be the Git repository root')
    # A captured commit must actually be the source the caller is looking at.
    if git(project, 'status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('Commit tracked source and dependencies before durable submission')
    commit = git(project, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    tree = git(project, 'rev-parse', '--verify', commit + '^{tree}').decode().strip()
    entries = git(project, 'ls-tree', '-rlz', '--full-tree', commit).split(b'\0')
    rows, total, names = [], 0, set()
    for entry in filter(None, entries):
        meta, raw_name = entry.split(b'\t', 1)
        mode, kind, blob, size_text = meta.decode().split()
        name = raw_name.decode('utf-8')
        path = PurePosixPath(name)
        if (mode not in {'100644', '100755'} or kind != 'blob' or path.is_absolute()
                or '..' in path.parts or '\\' in name or ':' in name
                or any(part.endswith(('.', ' ')) or part.split('.')[0].upper() in
                       {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
                       for part in path.parts)
                or name.casefold() in names):
            raise ValueError('Captured trees require regular files and portable unique paths; links/submodules are unsupported')
        names.add(name.casefold())
        size = int(size_text)
        total += size
        if size > MAX_FILE or total > MAX_TREE or len(rows) >= MAX_FILES:
            raise ValueError('Captured Git tree exceeds source bounds')
        rows.append((name, blob, mode, size))
    if script not in {row[0] for row in rows}:
        raise ValueError('Procedure must be committed in the captured Git tree')
    # Unique captures isolate Development output between runs. Preserve failed
    # captures for diagnosis; never recursively remove an inferred directory.
    target = Path(directory) / 'captures' / uuid.uuid4().hex
    target.mkdir(parents=True)
    inventory = {}
    # One Git process reads every immutable object, keeping large dependency
    # trees from blocking a request on thousands of process startups.
    contents = git(project, 'cat-file', '--batch', input=''.join(row[1] + '\n' for row in rows).encode())
    offset = 0
    for name, blob, mode, size in rows:
        end = contents.index(b'\n', offset)
        if contents[offset:end].decode() != f'{blob} blob {size}':
            raise ValueError('Captured Git object identity differs')
        raw = contents[end + 1:end + 1 + size]
        offset = end + 2 + size
        if len(raw) != size or contents[offset - 1:offset] != b'\n':
            raise ValueError('Captured Git object is truncated')
        output = target / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        if mode == '100755':
            output.chmod(0o700)
        inventory[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'git_blob': blob, 'mode': mode}
    if offset != len(contents):
        raise ValueError('Captured Git object inventory differs')
    manifest = {'schema': 'openbexi.source-capture/1', 'git_commit': commit, 'git_tree': tree, 'files': inventory}
    digest = hashlib.sha256(canonical(manifest).encode()).hexdigest()
    # Outside the runnable tree: user output cannot overwrite its own manifest.
    target.with_suffix('.json').write_text(canonical(manifest), encoding='utf-8')
    return target, digest, manifest


def verify_capture(target, digest):
    target = Path(target)
    manifest_path = target.with_suffix('.json')
    if target.is_symlink() or target.is_junction() or manifest_path.is_symlink() or manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Invalid captured source manifest')
    raw = manifest_path.read_text(encoding='utf-8')
    if hashlib.sha256(raw.encode()).hexdigest() != digest:
        raise ValueError('Captured dependency manifest changed')
    manifest = json.loads(raw)
    actual = set()
    for path in target.rglob('*'):
        if path.is_symlink() or path.is_junction():
            raise ValueError('Captured source contains a link')
        if path.is_file():
            actual.add(path.relative_to(target).as_posix())
    if actual != set(manifest['files']):
        raise ValueError('Captured dependency inventory changed')
    for name, row in manifest['files'].items():
        path = target / name
        if (not path.resolve().is_relative_to(target.resolve()) or path.is_symlink()
                or any(parent.is_symlink() or parent.is_junction() for parent in path.parents if parent != target.parent)
                or path.stat().st_size > MAX_FILE
                or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']):
            raise ValueError('Captured source or dependency changed')
    return manifest
