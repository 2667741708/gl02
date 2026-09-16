"""Read-only exact production HEAD, dependency hashes and staged Python compile."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    expectation = json.loads((args.stage / 'recordability-expectation.json').read_text(encoding='utf-8'))
    gate = json.loads((args.stage / 'scope-gate.json').read_text(encoding='utf-8'))
    root = Path(expectation['repo'])
    git = 'C:/Program Files/Git/cmd/git.exe'
    head = subprocess.check_output([git, '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    dependencies = []
    for row in gate['read_files']:
        path = root / row['path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        dependencies.append({'path': row['path'], 'match': digest.lower() == row['sha256'].lower()})
    compile_checks = []
    for relative, row in expectation['targets'].items():
        candidate = Path(row['candidate_path'])
        compile(candidate.read_bytes(), str(candidate), 'exec')
        compile_checks.append({'path': relative, 'sha_match': hashlib.sha256(candidate.read_bytes()).hexdigest().lower() == row['sha256'].lower(), 'target_exists': (root / relative).exists()})
    scoped = list(expectation['targets']) + expectation['read_set']
    dirty = subprocess.check_output([git, '-c', 'core.quotepath=false', '-C', str(root), 'status', '--short', '--', *scoped], encoding='utf-8').strip()
    result = {'schema': 'bf.qa.readonly-baseline.v1', 'platform': platform.system(), 'python': platform.python_version(), 'head': head, 'head_match': head == expectation['expected_head'], 'dependencies': dependencies, 'compile_checks': compile_checks, 'dirty_scope': dirty, 'ok': head == expectation['expected_head'] and all(x['match'] for x in dependencies) and all(x['sha_match'] for x in compile_checks) and not dirty}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
