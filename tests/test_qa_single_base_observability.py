"""Actual PowerShell control flow separates identity, dependencies, safe telemetry."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from test_qa_single_model_guard import ROOT, PWSH, PIN, run

pytestmark = pytest.mark.skipif(not Path(PWSH).exists(), reason='PowerShell 7 required')
SECRET = 'fixture-password-private-user-token'


@pytest.mark.parametrize('port', [8093, 8094])
@pytest.mark.parametrize('failure', ['timeout', 'connection', 'http', 'nested', 'task_timeout', 'missing', 'false', 'truthy'])
def test_dependency_failure_preserves_verified_identity_without_rewarm(tmp_path, port, failure):
    value = run(tmp_path, f'status{port}_{failure}')
    assert not value['failed'], value
    assert value['state']['identity_ready'] and value['state']['identity_locked']
    assert value['state']['digest'] == PIN
    assert not value['state']['dependencies_ready'] and not value['state']['assistant_ready']
    assert not value['result']['assistant_ready'] and value['calls'] == []
    assert value['status_reads'] == 2
    statuses = {x['service']: x for x in value['state']['dependency_status']}
    assert not statuses[f'status{port}']['ok']
    expected_kind = {'timeout': 'timeout', 'connection': 'connection_error', 'http': 'http_error', 'nested': 'timeout', 'task_timeout': 'timeout'}.get(failure, 'contract_error')
    assert statuses[f'status{port}']['failure_kind'] == expected_kind
    assert statuses[f'status{8094 if port == 8093 else 8093}']['ok']
    assert SECRET not in json.dumps(value)
    events = [x['data'] for x in value['events'] if x['data']['stage'] == f'status{port}' and x['data']['outcome'] == 'failed']
    assert len(events) == 1
    assert events[0]['actual_resident_digest'] == PIN
    if failure == 'http':
        assert events[0]['http_status'] == 503
    if failure in ('connection', 'nested'):
        assert events[0]['inner_exception_types']


def test_missing_dependency_configuration_does_not_mark_full_health(tmp_path):
    value = run(tmp_path, 'missing_status_endpoint')
    assert not value['failed'] and value['state']['identity_ready']
    assert value['state']['last_error'] == 'dependency_degraded'
    assert not value['state']['assistant_ready'] and value['calls'] == []


@pytest.mark.parametrize('mode', ['warmup_cancel', 'status8093_cancel', 'status8094_cancel', 'logger_cancel'])
def test_cancellation_is_not_swallowed_or_completed(tmp_path, mode):
    value = run(tmp_path, mode)
    assert value['failed'] and value['state'] is None
    assert value['exception_type'] == 'System.OperationCanceledException'
    assert value['message'] == 'fixed_operation_cancelled'
    assert SECRET not in json.dumps(value)
    assert value['calls'].count('warmup_same_fixed_base') <= 1


def test_native_pipeline_stop_stops_before_any_warmup_or_success_output(tmp_path):
    process = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(ROOT / 'tests/qa_regression/single_model_guard_harness.ps1'),
                              '-GuardFile', str(ROOT / 'tools/qa_single_model_guard_functions.ps1'), '-Workdir', str(tmp_path), '-Mode', 'logger_pipeline_stop'],
                             capture_output=True, text=True, encoding='utf-8', timeout=30)
    # Native PipelineStopped ends the host pipeline itself, including the fixture's JSON emitter.
    assert (tmp_path / 'pipeline-stop-observed.txt').exists()
    assert not process.stdout.strip()
    assert SECRET not in process.stderr
    assert not (tmp_path / 'state.json').exists()
    assert not (tmp_path / 'mutation-trace.txt').exists()


@pytest.mark.parametrize('mode', ['state_passed_log_cancel', 'state_final_error'])
def test_state_finalization_failure_only_leaves_pending_false_state(tmp_path, mode):
    value = run(tmp_path, mode)
    assert value['failed'] and value['result'] is None
    assert value['state']['identity_ready'] and value['state']['digest'] == PIN
    assert not value['state']['recovery_complete'] and not value['state']['assistant_ready']
    assert SECRET not in json.dumps(value) and value['calls'] == []
    if mode == 'state_passed_log_cancel':
        assert value['exception_type'] == 'System.OperationCanceledException'


def test_native_pipeline_stop_after_pending_write_cannot_leave_green_state(tmp_path):
    process = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(ROOT / 'tests/qa_regression/single_model_guard_harness.ps1'),
                              '-GuardFile', str(ROOT / 'tools/qa_single_model_guard_functions.ps1'), '-Workdir', str(tmp_path), '-Mode', 'state_passed_pipeline_stop'],
                             capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert (tmp_path / 'pipeline-stop-observed.txt').exists() and not process.stdout.strip()
    assert SECRET not in process.stderr
    state = json.loads((tmp_path / 'state.json').read_text(encoding='utf-8'))
    assert not state['recovery_complete'] and not state['assistant_ready'] and state['identity_ready']
    assert not (tmp_path / 'mutation-trace.txt').exists()


@pytest.mark.parametrize('mode', ['installed_api_error', 'resident_api_error', 'cp_error', 'warmup_error', 'state_error', 'state_error_log_error', 'state_error_log_cancel'])
def test_raw_sensitive_errors_never_escape_and_original_exception_is_retained(tmp_path, mode):
    value = run(tmp_path, mode)
    assert value['failed'] and value['state'] is None
    assert value['message'].startswith('fixed_')
    assert value['inner_exception_type'] is not None
    assert SECRET not in json.dumps(value)
    assert value['calls'].count('warmup_same_fixed_base') <= 1
    if mode not in ('state_error_log_error', 'state_error_log_cancel'):
        assert any(x['data']['outcome'] == 'failed' for x in value['events'])


@pytest.mark.parametrize('mode', ['log_error', 'state_started_log_error', 'state_passed_log_error'])
def test_log_failure_does_not_mask_health_or_trigger_model_operations(tmp_path, mode):
    value = run(tmp_path, mode)
    assert not value['failed'] and value['state']['identity_ready']
    assert not value['result']['observability_ok'] and not value['result']['assistant_ready']
    assert not value['state']['observability_ok'] and not value['state']['assistant_ready']
    assert value['calls'] == []


def test_empty_residency_observation_is_unknown_not_expected_digest(tmp_path):
    value = run(tmp_path, 'empty_resident')
    before = [x['data'] for x in value['events'] if x['data']['stage'] == 'resident-before' and x['data']['outcome'] == 'passed']
    assert before and all(x['actual_resident_digest'] is None for x in before)
    assert value['state']['digest'] == PIN and value['calls'].count('warmup_same_fixed_base') == 1


def test_wrong_resident_records_actual_digest_without_changing_it(tmp_path):
    value = run(tmp_path, 'wrong_resident')
    failures = [x['data'] for x in value['events'] if x['data']['outcome'] == 'failed']
    assert failures[0]['stage'] == 'resident-before'
    assert failures[0]['actual_resident_digest'].startswith('9111be')
    assert value['calls'] == [] and value['state'] is None


def test_sensitive_digest_is_rejected_and_never_enters_telemetry(tmp_path):
    value = run(tmp_path, 'resident_digest_sensitive')
    assert value['failed'] and value['state'] is None and value['calls'] == []
    public_error_and_telemetry = {'message': value['message'], 'events': value['events']}
    assert SECRET not in json.dumps(public_error_and_telemetry)
    failures = [x['data'] for x in value['events'] if x['data']['outcome'] == 'failed']
    assert failures and failures[0]['actual_resident_digest'] is None


@pytest.mark.parametrize('mode,field', [('resident_after_error', 'actual_resident_digest'),
                                     ('alias_after_api_error', 'actual_alias_digest'),
                                     ('installed_after_api_error', 'actual_installed_digest')])
def test_failed_reobservation_clears_old_digest_instead_of_claiming_current_identity(tmp_path, mode, field):
    value = run(tmp_path, mode)
    assert value['failed'] and value['state'] is None and value['calls'] == []
    failures = [x['data'] for x in value['events'] if x['data']['outcome'] == 'failed']
    assert failures and failures[0][field] is None
    assert SECRET not in json.dumps(value)


def test_null_schema_after_valid_resident_read_clears_old_identity(tmp_path):
    value = run(tmp_path, 'resident_after_null')
    assert value['failed'] and value['state'] is None and value['calls'] == []
    failures = [x['data'] for x in value['events'] if x['data']['outcome'] == 'failed']
    assert failures and failures[0]['actual_resident_digest'] is None


def test_stage_observations_are_allowlisted_and_cover_true_execution(tmp_path):
    value = run(tmp_path, 'empty_and_wrong_alias')
    stages = {x['data']['stage'] for x in value['events']}
    assert {'installed-version-check', 'resident-before', 'alias-check', 'alias-repair', 'warmup', 'resident-after', 'status8093', 'status8094', 'state-write'} <= stages
    allowed = {'stage', 'outcome', 'code', 'expected_digest', 'actual_installed_digest', 'actual_alias_digest', 'actual_resident_digest', 'exception_type', 'inner_exception_types', 'http_status', 'failure_kind'}
    assert all(set(x['data']) == allowed for x in value['events'])


def test_builder_freezes_ast_inventory_and_rejects_overwrite(tmp_path):
    baseline = ROOT.parents[1] / 'tools/ollama_model_switch/manage_ollama_model_switch.ps1'
    assert baseline.exists(), 'Verified read-only production baseline required'
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == '856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa'
    output = tmp_path / 'frozen-candidate.ps1'
    command = [PWSH, '-NoLogo', '-NoProfile', '-File', str(ROOT / 'tools/build_qa_single_model_guard_candidate.ps1'), '-Baseline', str(baseline), '-Output', str(output)]
    process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert process.returncode == 0, process.stderr
    proof = json.loads(process.stdout)
    data = output.read_bytes()
    assert proof['ok'] and proof['protected_functions'] > 0 and proof['protected_top_level_statements'] > 0
    assert proof['candidate_sha256'] == hashlib.sha256(data).hexdigest()
    assert len(proof['changed_functions']) == 5 and len(proof['new_functions']) == 9
    assert not data.startswith(b'\xef\xbb\xbf') and b'\r' not in data
    data.decode('utf-8', errors='strict')
    again = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert again.returncode != 0 and output.read_bytes() == data


@pytest.mark.parametrize('busy', [False, True])
def test_actual_manager_mutex_dispatch_does_not_run_overlapping_repair(tmp_path, busy):
    baseline = ROOT.parents[1] / 'tools/ollama_model_switch/manage_ollama_model_switch.ps1'
    output = tmp_path / 'mutex-candidate.ps1'
    build = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(ROOT / 'tools/build_qa_single_model_guard_candidate.ps1'), '-Baseline', str(baseline), '-Output', str(output)], capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert build.returncode == 0, build.stderr
    command = [PWSH, '-NoLogo', '-NoProfile', '-File', str(ROOT / 'tests/qa_regression/single_model_mutex_harness.ps1'), '-Candidate', str(output), '-Workdir', str(tmp_path)]
    if busy:
        command.append('-Busy')
    process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    if busy:
        assert result['skipped'] and result['reason'] == 'operation_in_progress'
        assert 'result' not in result
    else:
        assert result['result']['synthetic_repair_called']
