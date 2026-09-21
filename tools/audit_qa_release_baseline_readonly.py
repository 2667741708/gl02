"""Read-only path-scoped production history, hashes and staged Python compile."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from pathlib import PurePosixPath


def repo_path(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Scope paths must be repository-relative POSIX paths')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('', '.', '..') for part in value.split('/')):
        raise ValueError('Unsafe scope path')
    return value


def within_root(root, path):
    resolved = path.resolve()
    if resolved == root:
        raise ValueError('Scope path must name a file inside its root')
    resolved.relative_to(root)
    return resolved


def audit(stage, git):
    expectation = json.loads((stage / 'recordability-expectation.json').read_text(encoding='utf-8'))
    gate = json.loads((stage / 'scope-gate.json').read_text(encoding='utf-8'))
    root = Path(expectation['repo']).resolve()
    base = expectation['expected_head']
    if len(base) != 40 or any(c not in '0123456789abcdef' for c in base):
        raise ValueError('Invalid base commit')
    targets = {repo_path(p): row for p, row in expectation['targets'].items()}
    read_set = {repo_path(p) for p in expectation['read_set']}
    if not targets or read_set & set(targets):
        raise ValueError('Read/write scopes must be nonempty and disjoint')
    if gate['head'] != base or set(gate['write_set']) != set(targets):
        raise ValueError('Scope gate and candidate expectation disagree')
    if len(gate['read_files']) != len(read_set) or {row['path'] for row in gate['read_files']} != read_set:
        raise ValueError('Every read dependency requires exactly one hash')
    for relative in set(targets) | read_set:
        within_root(root, root / relative)

    def run(*args, check=True):
        return subprocess.run([git, '-c', 'core.quotepath=false', '-C', str(root), *args],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)

    head = run('rev-parse', 'HEAD').stdout.decode('ascii').strip()
    branch = run('symbolic-ref', '--quiet', 'HEAD', check=False).stdout.decode('ascii').strip()
    expected_ref = expectation.get('main_ref', 'refs/heads/production-8093')
    in_progress = False
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        marker_path = Path(run('rev-parse', '--git-path', marker).stdout.decode('utf-8').strip())
        if not marker_path.is_absolute():
            marker_path = root / marker_path
        in_progress = in_progress or marker_path.exists()
    ancestor = run('merge-base', '--is-ancestor', base, head, check=False).returncode == 0
    changed = []
    conflicts = []
    if ancestor:
        changed = sorted(p.decode('utf-8') for p in run('diff', '--name-only', '-z', base, head, '--').stdout.split(b'\0') if p)
        conflicts = sorted(p.decode('utf-8') for p in run('diff', '--name-only', '-z', base, head, '--', *sorted(set(targets) | read_set)).stdout.split(b'\0') if p)
    scoped = sorted(set(targets) | read_set)
    dirty = run('status', '--porcelain=v1', '--untracked-files=all', '--', *scoped).stdout.decode('utf-8').strip()
    dependencies = []
    for row in gate['read_files']:
        path = root / row['path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        dependencies.append({'path': row['path'], 'match': digest == row['sha256'].lower()})
    compile_checks = []
    for relative, row in targets.items():
        candidate = within_root(stage.resolve(), Path(row['candidate_path']))
        raw = candidate.read_bytes()
        if candidate.suffix == '.py':
            compile(raw, str(candidate), 'exec')
        compile_checks.append({'path': relative, 'sha_match': hashlib.sha256(raw).hexdigest() == row['sha256'].lower(), 'target_exists': (root / relative).exists()})
    stable = (run('rev-parse', 'HEAD').stdout.decode('ascii').strip() == head and
              run('symbolic-ref', '--quiet', 'HEAD', check=False).stdout.decode('ascii').strip() == branch)
    history_ok = ancestor and branch == expected_ref and not conflicts and not in_progress and stable
    ok = history_ok and not dirty and all(x['match'] for x in dependencies) and all(x['sha_match'] for x in compile_checks)
    return {'schema': 'bf.qa.readonly-baseline.v2', 'platform': platform.system(),
            'python': platform.python_version(), 'repo': str(root), 'head': head, 'base_head': base,
            'head_match': head == base, 'head_stable': stable, 'branch': branch,
            'base_is_ancestor': ancestor, 'integration_in_progress': in_progress,
            'changed_paths_since_base': changed, 'conflict_paths': conflicts,
            'path_scope_ok': history_ok, 'dependencies': dependencies,
            'compile_checks': compile_checks, 'dirty_scope': dirty,
            'automatic_replay': False, 'ok': bool(ok)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--git', default='C:/Program Files/Git/cmd/git.exe')
    args = parser.parse_args()
    result = audit(args.stage, args.git)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
