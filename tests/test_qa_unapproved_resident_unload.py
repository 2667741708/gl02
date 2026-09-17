"""Actual pure PowerShell assertion: permit only the observed, drained unload boundary."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = Path('C:/Program Files/PowerShell/7/pwsh.exe')
pytestmark = pytest.mark.skipif(not PWSH.exists(), reason='Actual PowerShell 7 required')


def run(mode):
    process = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-File',
                              str(ROOT / 'tests/qa_regression/unapproved_resident_unload_harness.ps1'),
                              '-Controller', str(ROOT / 'tools/unload_qa_unapproved_resident_once.ps1'), '-Mode', mode],
                             capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert process.returncode == 0, process.stderr
    value = json.loads(process.stdout)
    assert value['extracted_functions'] == ['Assert-UnapprovedResidentUnloadBoundary']
    assert not value['top_level_executed']
    assert value['network_calls'] == value['model_operations'] == value['task_operations'] == 0
    return value


@pytest.mark.parametrize('mode', ['healthy', 'extra_registered_tag'])
def test_exact_fixed_installed_source_and_unapproved_single_resident_with_drained_task_are_valid(mode):
    assert not run(mode)['failed']


@pytest.mark.parametrize('mode', [
    'tags_null', 'tags_empty', 'tags_string', 'tags_dictionary', 'tags_single_object',
    'tags_missing_fixed', 'tags_missing_public', 'tags_duplicate_fixed', 'tags_duplicate_public',
    'fixed_name_case', 'fixed_wrong_tag', 'fixed_wrong_digest', 'fixed_digest_upper', 'fixed_digest_short',
    'public_name_case', 'public_wrong_digest', 'public_digest_upper', 'public_digest_short',
    'tags_missing_name', 'tags_missing_digest',
    'resident_null', 'resident_empty', 'resident_string', 'resident_dictionary', 'resident_single_object',
    'resident_multiple', 'resident_duplicate', 'resident_wrong_name', 'resident_name_case',
    'resident_wrong_digest', 'resident_digest_upper', 'resident_digest_short',
    'resident_missing_name', 'resident_missing_digest',
    'manager_wrong', 'manager_upper', 'manager_short', 'catalog_wrong', 'catalog_upper', 'catalog_short',
    'task_enabled', 'task_null_enabled', 'task_string_enabled', 'task_numeric_enabled',
    'task_running', 'task_running_case', 'task_ready', 'task_queued', 'task_unknown',
    'task_empty', 'task_null_state', 'task_disabled_case', 'task_numeric_state',
])
def test_identity_shape_source_or_task_uncertainty_blocks_pure_boundary(mode):
    assert run(mode)['failed'], mode


def test_owned_fixture_and_test_encoding_are_utf8_no_bom_lf():
    for name in ['tests/qa_regression/unapproved_resident_unload_harness.ps1', 'tests/test_qa_unapproved_resident_unload.py']:
        data = (ROOT / name).read_bytes()
        data.decode('utf-8', errors='strict')
        assert not data.startswith(b'\xef\xbb\xbf') and b'\r' not in data
