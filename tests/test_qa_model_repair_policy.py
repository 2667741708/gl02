"""No live model or task calls: test actual recovery decisions with isolated dependencies."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which('pwsh') or 'C:/Program Files/PowerShell/7/pwsh.exe'
pytestmark = pytest.mark.skipif(not Path(PWSH).exists(), reason='PowerShell 7 required')


def run_case(tmp_path, mode, actual=False, fixture='model_activation_dependency_fixture_r2.ps1'):
    command = [PWSH, '-NoLogo', '-NoProfile', '-File',
                              str(ROOT / 'tests/qa_regression/model_repair_policy_harness.ps1'),
                              '-PolicyFile', str(ROOT / 'tools/qa_model_repair_policy.ps1'),
                              '-RepairFile', str(ROOT / 'tools/qa_model_repair_stable_function.ps1'),
                              '-Workdir', str(tmp_path), '-Mode', mode]
    if actual:
        command += ['-ActualDependency', str(ROOT / 'tests/qa_regression' / fixture)]
        if fixture == 'model_activation_dependency_fixture_r2.ps1':
            command += ['-SwitchFile', str(ROOT / 'tools/qa_model_switch_stable_function.ps1')]
    process = subprocess.run(command, capture_output=True, text=True,
                             encoding='utf-8', timeout=30)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def test_healthy_approved_fallback_is_sticky_and_state_reconciled(tmp_path):
    result = run_case(tmp_path, 'healthy')
    assert not result['failed']
    assert result['alias'] == 'digest0' and result['resident']
    assert result['state'] == {'desired_model_id': 'm1', 'effective_model_id': 'm0', 'digest': 'digest0', 'fallback_active': True}
    assert 'activate_m0_RepairResident' in result['calls']
    assert not any(x.startswith(('alias_', 'warmup_', 'health_pause_', 'rollback_')) for x in result['calls'])


def test_secondary_status_failure_does_not_switch_healthy_resident(tmp_path):
    result = run_case(tmp_path, 'healthy_status_error')
    assert result['failed'] and result['alias'] == 'digest0' and result['resident']
    assert not any(x.startswith(('alias_', 'warmup_', 'health_pause_', 'rollback_')) for x in result['calls'])
    assert not (tmp_path / 'state.json.repair-policy.json').exists()


def test_failed_warmup_restores_alias_state_and_records_bounded_cooldown(tmp_path):
    result = run_case(tmp_path, 'all_fail')
    assert result['failed'] and not result['activation_success']
    assert result['alias'] == 'digest0' and result['health_enabled']
    assert result['state'] == {'desired_model_id': 'm1', 'effective_model_id': 'm1', 'digest': 'digest1'}
    assert result['calls'].index('rollback_synthetic:0') < result['calls'].index('activate_m0_Repair')
    policy = json.loads((tmp_path / 'state.json.repair-policy.json').read_text())
    assert set(policy['failures']) == {'m0', 'm1'}
    assert all(x['attempts'] == 1 and x['cooldown_seconds'] == 60 for x in policy['failures'].values())


def test_failure_rollback_precedes_successful_fallback(tmp_path):
    result = run_case(tmp_path, 'fallback_success')
    assert not result['failed'] and result['alias'] == 'digest0' and result['resident']
    assert result['state']['effective_model_id'] == 'm0' and result['state']['fallback_active']
    assert result['calls'].index('rollback_synthetic:0') < result['calls'].index('activate_m0_Repair')
    assert result['health_enabled']


def test_cooling_candidates_never_activate_or_pause_task(tmp_path):
    result = run_case(tmp_path, 'cooldown_all')
    assert result['failed'] and result['alias'] == 'digest0'
    assert not any(x.startswith(('activate_', 'alias_', 'warmup_', 'health_pause_')) for x in result['calls'])


def test_preferred_cooldown_allows_other_approved_fallback(tmp_path):
    result = run_case(tmp_path, 'cooldown_preferred')
    assert not result['failed'] and result['state']['effective_model_id'] == 'm0'
    assert not any(x.startswith('activate_m1') for x in result['calls'])


def test_partially_failed_task_pause_is_restored_before_exit(tmp_path):
    result = run_case(tmp_path, 'pause_partial_error')
    assert result['failed'] and result['health_enabled'] and result['alias'] == 'digest0'
    assert 'health_pause_True' in result['calls'] and 'health_pause_False' in result['calls']
    assert not any(x.startswith('activate_') for x in result['calls'])


def test_previously_disabled_health_task_stays_disabled(tmp_path):
    result = run_case(tmp_path, 'original_health_disabled')
    assert not result['failed'] and not result['health_enabled']
    assert not any(x.startswith('health_pause_') for x in result['calls'])


def test_rollback_failure_halts_before_next_candidate(tmp_path):
    result = run_case(tmp_path, 'rollback_error')
    assert result['failed'] and not result['activation_success'] and result['health_enabled']
    assert not any(x.startswith('activate_m0') for x in result['calls'])


def test_invalid_cooldown_policy_blocks_before_model_task_changes(tmp_path):
    result = run_case(tmp_path, 'invalid_policy')
    assert result['failed'] and not result['activation_success']
    assert not any(x.startswith(('activate_', 'alias_', 'warmup_', 'health_pause_')) for x in result['calls'])


def test_exponential_cooldown_caps_at_fifteen_minutes_and_expires(tmp_path):
    result = run_case(tmp_path, 'policy_backoff')
    assert result['seconds'] == [60, 120, 240, 480, 900, 900, 900, 900]
    assert result['cooling_before'] and not result['cooling_at']


@pytest.mark.parametrize('mode', ['policy_bad_count', 'policy_bad_time'])
def test_corrupt_cooldown_fields_are_rejected(tmp_path, mode):
    assert run_case(tmp_path, mode)['rejected']


@pytest.mark.parametrize('mode,failed,effective', [
    ('healthy', False, 'm0'), ('healthy_status_error', True, 'm1'), ('all_fail', True, 'm1'),
    ('fallback_success', False, 'm0'), ('cooldown_all', True, 'm1'), ('cooldown_preferred', False, 'm0'),
    ('pause_partial_error', True, 'm1'), ('original_health_disabled', False, 'm1'),
    ('rollback_error', True, 'm1'), ('invalid_policy', True, 'm1')])
def test_actual_frozen_activation_dependency_obeys_recovery_contract(tmp_path, mode, failed, effective):
    result = run_case(tmp_path, mode, actual=True)
    assert result['failed'] is failed, result
    assert result['state']['effective_model_id'] == effective, result
    assert result['health_enabled'] is (mode != 'original_health_disabled'), result
    if mode != 'rollback_error':
        assert result['alias'] == ('digest1' if mode == 'original_health_disabled' else 'digest0'), result
    if mode in {'healthy', 'healthy_status_error', 'cooldown_all', 'invalid_policy', 'pause_partial_error'}:
        assert not any(x.startswith(('rollback_', 'warmup_')) for x in result['calls']), result


def test_switch_pause_failure_leaves_observed_alias_and_skips_warmup(tmp_path):
    result = run_case(tmp_path, 'switch_pause_partial_error', actual=True)
    assert result['failed'] and result['health_enabled'] and result['alias'] == 'digest0', result
    assert result['state']['effective_model_id'] == 'm0' and result['state']['digest'] == 'digest0', result
    assert not any(x.startswith(('rollback_', 'warmup_')) for x in result['calls']), result


def test_switch_failure_rolls_back_observed_alias_despite_stale_saved_state(tmp_path):
    result = run_case(tmp_path, 'switch_stale_activation_error', actual=True)
    assert result['failed'] and result['health_enabled'] and result['alias'] == 'digest0', result
    assert result['state']['effective_model_id'] == 'm0' and result['state']['digest'] == 'digest0', result
    assert result['state']['last_error'] == 'switch_failed'
    assert 'rollback_synthetic:0' in result['calls']


def test_frozen_predecessor_reproduces_wrong_switch_rollback(tmp_path):
    result = run_case(tmp_path, 'switch_pause_partial_error', actual=True, fixture='model_activation_dependency_fixture.ps1')
    assert result['failed'] and result['health_enabled']
    assert result['alias'] == 'digest1' and 'rollback_synthetic:1' in result['calls'], result
