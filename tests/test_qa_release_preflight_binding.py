"""Real disjoint Git histories bind both gates without authorizing deployment."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from record_qa_release_preflight import validate_preflight_evidence
from test_qa_deployment_path_scope import deployment, git, GIT, audit_module

GUARD = ROOT.parents[1] / '.codex/skills/deploy-8093-guarded-update/scripts/git_record_guard.py'


@pytest.fixture
def bound_gates(deployment):
    repo, stage, base = deployment
    expectation = json.loads((stage / 'recordability-expectation.json').read_bytes())
    expectation.update(schema='bf.deploy.git-recordability-expectation.v1', concurrency_mode='path-scoped')
    (stage / 'recordability-expectation.json').write_text(json.dumps(expectation), encoding='utf-8', newline='\n')
    (repo / '样式.css').write_text('a {color:red}\n', encoding='utf-8', newline='\n')
    git(repo, 'add', '样式.css')
    git(repo, 'commit', '-qm', 'unrelated presentation')
    (repo / '样式.css').write_text('unrelated staged work\n', encoding='utf-8', newline='\n')
    git(repo, 'add', '样式.css')
    (repo / '另一个.txt').write_text('untracked\n', encoding='utf-8')
    baseline = audit_module.audit(stage, GIT)
    index = (repo / '.git/index').read_bytes()
    head = git(repo, 'rev-parse', 'HEAD')
    status = git(repo, 'status', '--porcelain')
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(GUARD), 'preflight-candidate',
        '--expectation', str(stage / 'recordability-expectation.json')], capture_output=True,
        text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert (repo / '.git/index').read_bytes() == index
    assert git(repo, 'rev-parse', 'HEAD') == head and git(repo, 'status', '--porcelain') == status
    return baseline, evidence, expectation


def test_actual_auditor_and_temporary_index_gate_accept_disjoint_head_and_preserve_staged_work(bound_gates):
    baseline, evidence, expectation = bound_gates
    assert baseline['head_match'] is False and evidence['head_advanced'] is True
    bound = validate_preflight_evidence(*bound_gates)
    assert bound['ok'] and bound['path_scope_verified'] and bound['head_advanced']
    assert bound['deployment_authorized'] is False and bound['model_identity_verified'] is False


@pytest.mark.parametrize('section,key,value', [
    (0, 'schema', 'bf.qa.readonly-baseline.v1'), (0, 'ok', 1),
    (0, 'head_stable', False), (0, 'base_is_ancestor', False),
    (0, 'path_scope_ok', False), (0, 'integration_in_progress', True),
    (0, 'automatic_replay', True), (0, 'head_match', True),
    (0, 'conflict_paths', ['助手.py']), (0, 'dirty_scope', 'M 助手.py'),
    (0, 'repo', '/wrong-repo'), (0, 'branch', 'refs/heads/wrong'),
    (0, 'base_head', 'a' * 40), (0, 'head', 'a' * 40),
    (0, 'changed_paths_since_base', ['依赖.py']),
    (0, 'dependencies', []), (0, 'compile_checks', []),
    (1, 'schema', 'wrong'), (1, 'ok', 1), (1, 'action', 'requires_eol_migration'),
    (1, 'automatic_production_write', True), (1, 'eol_transition_paths', ['助手.py']),
    (1, 'head', 'a' * 40), (1, 'expected_head', 'a' * 40),
    (1, 'head_advanced', False), (1, 'changed_paths_since_base', []),
    (1, 'conflict_paths', ['助手.py']), (1, 'read_set', []),
    (1, 'changed_paths', []), (1, 'candidate_hashes', {}), (1, 'staged_hashes', {}),
    (2, 'concurrency_mode', 'strict-head'),
])
def test_stale_partial_unsafe_or_truthy_evidence_cannot_bind(bound_gates, section, key, value):
    values = copy.deepcopy(bound_gates)
    values[section][key] = value
    with pytest.raises(ValueError):
        validate_preflight_evidence(*values)


@pytest.mark.parametrize('section,list_name', [(0, 'dependencies'), (0, 'compile_checks'), (1, 'changed_paths'), (1, 'read_set')])
def test_duplicate_scope_rows_do_not_cover_missing_evidence(bound_gates, section, list_name):
    values = copy.deepcopy(bound_gates)
    values[section][list_name].append(copy.deepcopy(values[section][list_name][0]))
    with pytest.raises(ValueError):
        validate_preflight_evidence(*values)
