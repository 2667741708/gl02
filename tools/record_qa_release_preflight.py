"""Bind verified read-only evidence to a registered release recipe locally."""
import argparse
import json
from pathlib import Path
import re

from audit_qa_release_baseline_readonly import repo_path

ROOT = Path(__file__).resolve().parents[1]


def validate_preflight_evidence(baseline, evidence, expectation):
    """Bind both read-only gates to the same exact path-scoped candidate.

    A newer disjoint HEAD is valid; neither truthy flags nor empty partial lists
    establish a passed gate. Legacy evidence must be refreshed with the auditor.
    This function does not grant activation or authorize any model operation.
    """
    def require(value, message):
        if not value:
            raise ValueError(message)

    def repo_key(value):
        require(isinstance(value, str) and bool(value), 'Missing repository identity')
        key = value.replace('\\', '/').rstrip('/')
        if re.match(r'^[A-Za-z]:/', key):
            return key.casefold()
        require(key.startswith('/'), 'Repository must be absolute')
        return key

    require(expectation.get('schema') == 'bf.deploy.git-recordability-expectation.v1'
        and expectation.get('concurrency_mode') == 'path-scoped', 'Path-scoped expectation required')
    base = expectation.get('expected_head')
    require(isinstance(base, str) and re.fullmatch(r'[0-9a-f]{40}', base), 'Invalid base commit')
    targets = expectation.get('targets')
    reads = expectation.get('read_set')
    require(isinstance(targets, dict) and bool(targets) and isinstance(reads, list), 'Missing read/write scope')
    write_set = {repo_path(path) for path in targets}
    read_set = {repo_path(path) for path in reads}
    require(len(reads) == len(read_set) and not read_set & write_set, 'Duplicate or overlapping scope')
    desired = {}
    for path, row in targets.items():
        digest = row.get('sha256') if isinstance(row, dict) else None
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{64}', digest), 'Invalid candidate digest')
        desired[path] = digest.lower()

    require(baseline.get('schema') == 'bf.qa.readonly-baseline.v2', 'Refresh legacy baseline evidence')
    require(baseline.get('ok') is True and baseline.get('path_scope_ok') is True
        and baseline.get('head_stable') is True and baseline.get('base_is_ancestor') is True
        and baseline.get('integration_in_progress') is False and baseline.get('automatic_replay') is False
        and baseline.get('conflict_paths') == [] and baseline.get('dirty_scope') == '', 'Unsafe path baseline')
    require(repo_key(baseline.get('repo')) == repo_key(expectation.get('repo'))
        and baseline.get('base_head') == base
        and baseline.get('branch') == expectation.get('main_ref', 'refs/heads/production-8093'), 'Baseline identity mismatch')
    head = baseline.get('head')
    require(isinstance(head, str) and re.fullmatch(r'[0-9a-f]{40}', head)
        and type(baseline.get('head_match')) is bool and baseline['head_match'] == (head == base), 'Invalid baseline HEAD')
    changed = baseline.get('changed_paths_since_base')
    require(isinstance(changed, list) and len(set(changed)) == len(changed)
        and not {repo_path(p) for p in changed} & (read_set | write_set), 'Scoped history conflict')
    for name, scope, flag in [('dependencies', read_set, 'match'), ('compile_checks', write_set, 'sha_match')]:
        rows = baseline.get(name)
        require(isinstance(rows, list) and len(rows) == len(scope)
            and all(isinstance(row, dict) and row.get(flag) is True for row in rows)
            and {row.get('path') for row in rows} == scope, 'Incomplete or failed ' + name)

    require(evidence.get('schema') == 'bf.deploy.git-recordability-preflight.v1'
        and evidence.get('ok') is True and evidence.get('action') == 'recordable'
        and evidence.get('automatic_production_write') is False and evidence.get('eol_transition_paths') == []
        and evidence.get('concurrency_mode') == 'path-scoped', 'Candidate is not recordable')
    require(evidence.get('expected_head') == base and evidence.get('head') == head
        and type(evidence.get('head_advanced')) is bool and evidence['head_advanced'] == (head != base)
        and evidence.get('conflict_paths') == [] and evidence.get('changed_paths_since_base') == changed,
        'Read-only gates observed different history')
    for name, scope in [('read_set', read_set), ('changed_paths', write_set)]:
        paths = evidence.get(name)
        require(isinstance(paths, list) and len(paths) == len(scope) and set(paths) == scope,
            'Incomplete recordability ' + name)
    for name in ('candidate_hashes', 'staged_hashes'):
        hashes = evidence.get(name)
        require(isinstance(hashes, dict) and set(hashes) == write_set
            and all(isinstance(hashes[p], str) and hashes[p].lower() == desired[p] for p in write_set),
            'Unbound ' + name)
    return {'ok': True, 'base_head': base, 'observed_head': head,
        'head_advanced': head != base, 'path_scope_verified': True,
        'deployment_authorized': False, 'model_identity_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('v21','v22','v23','v24','v25','v26'), required=True)
    args = parser.parse_args()
    release = ROOT/f'.codex_runtime/qa-routing-{args.version}/release'
    baseline = json.loads((release/'readonly-baseline.json').read_text(encoding='utf-8'))
    evidence = json.loads((release/'git-recordability.json').read_text(encoding='utf-8'))
    expectation = json.loads((release/'recordability-expectation.json').read_text(encoding='utf-8'))
    binding = validate_preflight_evidence(baseline, evidence, expectation)
    registry=ROOT/'tools/qa_routing_release_extensions.json'
    recipes=json.loads(registry.read_text(encoding='utf-8'))
    for validation in recipes[args.version]['validations']:
        if validation['id']=='remote-readonly-preflight':
            validation.update(status='passed',evidence='Stable path-scoped ancestry and complete read/write hashes; staged recordability verified at same observed HEAD; no EOL migration')
    registry.write_bytes((json.dumps(recipes,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'version':args.version, **binding}))


if __name__=='__main__':main()
