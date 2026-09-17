"""The actual guard functions never activate or reload an alternative approved base."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which('pwsh') or 'C:/Program Files/PowerShell/7/pwsh.exe'
pytestmark = pytest.mark.skipif(not Path(PWSH).exists(), reason='PowerShell 7 required')
PIN = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'


def run(tmp_path, mode):
    process = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(ROOT / 'tests/qa_regression/single_model_guard_harness.ps1'),
                              '-GuardFile', str(ROOT / 'tools/qa_single_model_guard_functions.ps1'),
                              '-Workdir', str(tmp_path), '-Mode', mode], capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize('mode', ['healthy', 'initialize'])
def test_same_base_healthy_never_mutates_model_or_task(tmp_path, mode):
    value = run(tmp_path, mode)
    assert not value['failed'], value
    assert value['alias'] == PIN and value['loaded'][0]['digest'] == PIN
    assert value['state']['digest'] == PIN and value['state']['identity_locked']
    assert not value['state']['fallback_active'] and not value['state']['model_switch_allowed']
    assert not any(x.startswith(('warmup_', 'restore_')) for x in value['calls'])


def test_wrong_alias_is_restored_to_already_resident_identical_base(tmp_path):
    value = run(tmp_path, 'alias_repair')
    assert not value['failed'] and value['alias'] == PIN and value['loaded'][0]['digest'] == PIN
    assert 'restore_same_fixed_alias' in value['calls'] and 'warmup_same_fixed_base' not in value['calls']


def test_empty_resident_only_loads_identical_base(tmp_path):
    value = run(tmp_path, 'empty_resident')
    assert not value['failed'] and value['loaded'][0]['digest'] == PIN
    assert value['calls'].count('warmup_same_fixed_base') == 1


@pytest.mark.parametrize('mode', ['wrong_resident', 'multiple_residents', 'missing_fixed', 'bad_catalog',
                                 'switch_same', 'switch_other', 'sanitize', 'direct_other', 'direct_fallback',
                                 'bad_catalog_alias', 'bad_catalog_tag', 'duplicate_catalog', 'installed_wrong_digest',
                                 'resident_null', 'resident_missing', 'resident_string', 'missing_resident_digest',
                                 'wrong_resident_name', 'alias_unknown', 'alias_api_error', 'installed_api_error',
                                 'resident_digest_sensitive', 'resident_single_object', 'resident_dictionary', 'initialize_empty', 'initialize_wrong', 'initialize_multiple'])
def test_switch_fallback_or_identity_drift_blocks_without_mutation(tmp_path, mode):
    value = run(tmp_path, mode)
    assert value['failed'] and value['state'] is None, value
    assert not value['calls'], value


@pytest.mark.parametrize('mode', ['cp_error', 'warmup_error', 'state_error', 'resident_after_error',
                                 'warmup_no_resident', 'warmup_alias_drift', 'warmup_wrong_resident',
                                 'alias_recheck_error', 'post_status_drift'])
def test_failure_never_tries_another_base_or_marks_completed(tmp_path, mode):
    value = run(tmp_path, mode)
    assert value['failed'] and value['state'] is None, value
    assert value['calls'].count('warmup_same_fixed_base') <= 1
    assert set(value['calls']) <= {'restore_same_fixed_alias', 'warmup_same_fixed_base'}


def test_empty_resident_and_wrong_alias_only_restore_and_reload_fixed_base(tmp_path):
    value = run(tmp_path, 'empty_and_wrong_alias')
    assert not value['failed'], value
    assert value['calls'] == ['restore_same_fixed_alias', 'warmup_same_fixed_base']
    assert value['result']['identity_ready'] and value['result']['assistant_ready']
