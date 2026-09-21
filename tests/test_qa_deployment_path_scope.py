"""Real Git histories prove unrelated commits are safe and scoped drift is not."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qa_scope_audit', ROOT / 'tools/audit_qa_release_baseline_readonly.py')
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)
GIT = shutil.which('git')


def git(repo, *args):
    return subprocess.check_output([GIT, '-C', str(repo), *args], text=True, encoding='utf-8').strip()


@pytest.fixture
def deployment(tmp_path):
    repo = tmp_path / '生产程序'
    repo.mkdir()
    git(repo, 'init', '-b', 'production-8093')
    git(repo, 'config', 'user.name', 'Fixture')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    git(repo, 'config', 'core.autocrlf', 'false')
    for name, text in [('助手.py', 'value = 1\n'), ('依赖.py', 'value = 2\n'), ('样式.css', 'a {}\n')]:
        (repo / name).write_text(text, encoding='utf-8', newline='\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'initial')
    base = git(repo, 'rev-parse', 'HEAD')
    stage = tmp_path / 'stage'
    stage.mkdir()
    candidate = stage / '助手.py'
    candidate.write_text('value = 3\n', encoding='utf-8', newline='\n')
    expectation = {'repo': str(repo), 'expected_head': base, 'targets': {'助手.py': {
        'candidate_path': str(candidate), 'sha256': hashlib.sha256(candidate.read_bytes()).hexdigest()}}, 'read_set': ['依赖.py']}
    gate = {'head': base, 'write_set': ['助手.py'], 'read_files': [{'path': '依赖.py',
        'sha256': hashlib.sha256((repo / '依赖.py').read_bytes()).hexdigest()}]}
    (stage / 'recordability-expectation.json').write_text(json.dumps(expectation), encoding='utf-8')
    (stage / 'scope-gate.json').write_text(json.dumps(gate), encoding='utf-8')
    return repo, stage, base


def test_unrelated_commit_and_dirty_files_are_preserved(deployment):
    repo, stage, base = deployment
    (repo / '样式.css').write_text('a {color:red}\n', encoding='utf-8')
    git(repo, 'add', '样式.css')
    git(repo, 'commit', '-qm', 'unrelated presentation')
    (repo / '样式.css').write_text('unrelated dirty\n', encoding='utf-8')
    (repo / '别的文件.txt').write_text('untracked\n', encoding='utf-8')
    before = git(repo, 'status', '--porcelain')
    result = audit_module.audit(stage, GIT)
    assert result['ok'] and result['path_scope_ok'] and not result['head_match']
    assert result['changed_paths_since_base'] == ['样式.css']
    assert result['conflict_paths'] == [] and result['base_head'] == base
    assert git(repo, 'status', '--porcelain') == before


@pytest.mark.parametrize('name', ['助手.py', '依赖.py'])
def test_committed_scope_change_blocks_until_exact_revert(deployment, name):
    repo, stage, _ = deployment
    original = (repo / name).read_bytes()
    (repo / name).write_bytes(original + b'# changed\n')
    git(repo, 'add', name)
    git(repo, 'commit', '-qm', 'scoped change')
    assert not audit_module.audit(stage, GIT)['ok']
    git(repo, 'revert', '--no-edit', 'HEAD')
    # Restored exact bytes are safe; the final tree and all dependency hashes agree.
    assert audit_module.audit(stage, GIT)['ok']


@pytest.mark.parametrize('path', ['../outside.py', '..\\outside.py', 'subdir\\..\\outside.py',
                                  'C:/outside.py', '/outside.py', 'a/../outside.py', './a.py', 'a//b.py'])
@pytest.mark.parametrize('scope', ['read', 'write'])
def test_unsafe_repository_path_rejected_before_any_git_or_file_read(deployment, path, scope):
    _, stage, _ = deployment
    expectation = json.loads((stage / 'recordability-expectation.json').read_text())
    if scope == 'read':
        expectation['read_set'] = [path]
    else:
        row = expectation['targets'].pop('助手.py')
        expectation['targets'] = {path: row}
    (stage / 'recordability-expectation.json').write_text(json.dumps(expectation), encoding='utf-8')
    with pytest.raises(ValueError):
        audit_module.audit(stage, 'must-not-execute')


def test_candidate_cannot_escape_reviewed_stage(deployment):
    repo, stage, _ = deployment
    expectation = json.loads((stage / 'recordability-expectation.json').read_text())
    expectation['targets']['助手.py']['candidate_path'] = str(repo / '助手.py')
    (stage / 'recordability-expectation.json').write_text(json.dumps(expectation), encoding='utf-8')
    with pytest.raises(ValueError):
        audit_module.audit(stage, GIT)


@pytest.mark.parametrize('mode', ['unstaged', 'staged', 'untracked_read', 'untracked_write', 'detached', 'diverged', 'merge', 'bad_candidate', 'scope_mismatch'])
def test_unsafe_state_is_blocked(deployment, mode):
    repo, stage, _ = deployment
    if mode in ('unstaged', 'staged'):
        (repo / '依赖.py').write_text('value = 5\n', encoding='utf-8')
        if mode == 'staged':
            git(repo, 'add', '依赖.py')
    elif mode.startswith('untracked'):
        name = '依赖.py' if mode == 'untracked_read' else '助手.py'
        git(repo, 'rm', '--cached', name)
        git(repo, 'commit', '-qm', 'untrack scoped file')
    elif mode == 'detached':
        git(repo, 'checkout', '--detach')
    elif mode == 'diverged':
        git(repo, 'checkout', '--orphan', 'unrelated')
        git(repo, 'commit', '-qm', 'different history')
        git(repo, 'branch', '-M', 'production-8093')
    elif mode == 'merge':
        marker = Path(git(repo, 'rev-parse', '--git-path', 'MERGE_HEAD'))
        if not marker.is_absolute():
            marker = repo / marker
        marker.write_text(git(repo, 'rev-parse', 'HEAD'), encoding='ascii')
    elif mode == 'bad_candidate':
        (stage / '助手.py').write_text('value = 9\n', encoding='utf-8')
    else:
        gate = json.loads((stage / 'scope-gate.json').read_text())
        gate['write_set'] = ['样式.css']
        (stage / 'scope-gate.json').write_text(json.dumps(gate), encoding='utf-8')
        with pytest.raises(ValueError, match='disagree'):
            audit_module.audit(stage, GIT)
        return
    assert not audit_module.audit(stage, GIT)['ok']


@pytest.mark.parametrize('mode,accepted', [('unrelated_commit', True), ('auditor_tampered', False), ('dependency_drift', False)])
def test_actual_powershell_baseline_gate(deployment, mode, accepted):
    repo, stage, _ = deployment
    source = (ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1').read_text(encoding='utf-8')
    function = source[source.index('function Assert-Baselines {'):source.index('function Port-Pid')]
    auditor = stage / 'audit_qa_release_baseline_readonly.py'
    auditor.write_bytes((ROOT / 'tools/audit_qa_release_baseline_readonly.py').read_bytes())
    gate = json.loads((stage / 'scope-gate.json').read_text())
    gate['baseline_auditor_sha256'] = hashlib.sha256(auditor.read_bytes()).hexdigest()
    (stage / 'scope-gate.json').write_text(json.dumps(gate), encoding='utf-8')
    plan = {'changes': [{'target': str(repo / '助手.py'), 'current_exists': True,
                        'current_sha256': hashlib.sha256((repo / '助手.py').read_bytes()).hexdigest()}]}
    (stage / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
    if mode == 'unrelated_commit':
        (repo / '样式.css').write_text('a {color:green}\n', encoding='utf-8')
        git(repo, 'add', '样式.css')
        git(repo, 'commit', '-qm', 'unrelated styles')
    elif mode == 'auditor_tampered':
        auditor.write_bytes(auditor.read_bytes() + b'\n# tampered\n')
    else:
        (repo / '依赖.py').write_text('value = 8\n', encoding='utf-8')

    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    fixture = '\n'.join([
        "$ErrorActionPreference = 'Stop'",
        "if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'Core7 required' }",
        "$Utf8 = [Text.UTF8Encoding]::new($false)",
        '[Console]::InputEncoding = $Utf8', '[Console]::OutputEncoding = $Utf8', '$OutputEncoding = $Utf8',
        "$PSDefaultParameterValues['*:Encoding'] = 'utf8'",
        '$Root = ' + quote(repo), '$StageRoot = ' + quote(stage), '$Python = ' + quote(sys.executable),
        "$Gate = Get-Content -LiteralPath (Join-Path $StageRoot 'scope-gate.json') -Raw | ConvertFrom-Json",
        "$Plan = Get-Content -LiteralPath (Join-Path $StageRoot 'plan.json') -Raw | ConvertFrom-Json",
        'function Hash([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }',
        function,
        "try { Assert-Baselines; @{accepted=$true} | ConvertTo-Json } catch { @{accepted=$false; error_type=$_.Exception.GetType().Name} | ConvertTo-Json }",
    ])
    script = stage / 'actual-baseline-gate.ps1'
    script.write_text(fixture, encoding='utf-8', newline='\n')
    before = git(repo, 'status', '--porcelain')
    result = subprocess.run(['C:/Program Files/PowerShell/7/pwsh.exe', '-NoLogo', '-NoProfile', '-File', str(script)],
                            capture_output=True, text=True, encoding='utf-8', check=True)
    assert json.loads(result.stdout)['accepted'] is accepted
    assert git(repo, 'status', '--porcelain') == before
