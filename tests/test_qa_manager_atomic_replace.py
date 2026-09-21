"""Windows PowerShell 7/.NET actual File.Replace behavior, using synthetic files only."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = Path('C:/Program Files/PowerShell/7/pwsh.exe')
pytestmark = pytest.mark.skipif(not PWSH.exists(), reason='Actual Windows PowerShell 7 required')


def run(tmp_path, mode):
    process = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-File',
                              str(ROOT / 'tests/qa_regression/manager_atomic_replace_harness.ps1'),
                              '-Installer', str(ROOT / 'tools/install_qa_single_base_manager.ps1'),
                              '-Workdir', str(tmp_path), '-Mode', mode],
                             capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert process.returncode == 0, process.stderr
    value = json.loads(process.stdout)
    assert value['extracted_functions'] == ['Invoke-ManagerAtomicReplace']
    assert not value['top_level_executed'] and value['model_operations'] == 0 and value['remote_operations'] == 0
    assert value['after']['state'] == value['before']['state']
    return value


def test_install_atomically_consumes_source_and_preserves_old_destination(tmp_path):
    value = run(tmp_path, 'install')
    assert not value['failed'] and value['completed']
    assert value['after']['source'] is None
    assert value['after']['destination'] == value['before']['source']
    assert value['after']['backup'] == value['before']['destination']
    assert value['after']['failed_candidate'] is None


def test_rollback_atomically_consumes_old_backup_and_preserves_failed_candidate(tmp_path):
    value = run(tmp_path, 'rollback')
    assert not value['failed'] and value['completed']
    assert value['install']['source'] is None
    assert value['install']['destination'] == value['before']['source']
    assert value['install']['backup'] == value['before']['destination']
    assert value['after']['destination'] == value['before']['destination']
    assert value['after']['failed_candidate'] == value['before']['source']
    assert value['after']['source'] is None and value['after']['backup'] is None


@pytest.mark.parametrize('mode', ['null_backup', 'empty_backup', 'whitespace_backup', 'existing_backup',
                                 'missing_source', 'missing_destination', 'backup_parent_missing', 'backup_directory'])
def test_rejected_or_failed_replace_preserves_files_and_never_marks_completed(tmp_path, mode):
    value = run(tmp_path, mode)
    assert value['failed'] and not value['completed'] and value['install'] is None
    for name in ['source', 'destination', 'backup', 'state']:
        assert value['after'][name] == value['before'][name]
    assert value['after']['failed_candidate'] is None


def test_old_null_overload_reproduces_windows_failure_without_replacement(tmp_path):
    value = run(tmp_path, 'old_null')
    assert value['failed'] and not value['completed']
    assert value['inner_error_type'] == 'System.ArgumentException'
    assert value['after']['destination'] == value['before']['destination']
    assert value['after']['source'] == value['before']['source']
    assert value['after']['backup'] is None


def test_owned_harness_and_test_are_utf8_no_bom_lf():
    for name in ['tests/qa_regression/manager_atomic_replace_harness.ps1', 'tests/test_qa_manager_atomic_replace.py']:
        data = (ROOT / name).read_bytes()
        data.decode('utf-8', errors='strict')
        assert not data.startswith(b'\xef\xbb\xbf') and b'\r' not in data
