"""Installation never reenables the permissive manager after any failure."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = 'C:/Program Files/PowerShell/7/pwsh.exe'


@pytest.mark.parametrize('mode', ['success', 'original_disabled', 'partial_disable', 'drain_failed',
    'baseline_drift', 'backup_failed', 'install_failed', 'verification_failed', 'rollback_failed'])
def test_transaction_restores_only_verified_guard(mode):
    p = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File',
        str(ROOT / 'tests/qa_regression/fixed_manager_install_harness.ps1'), '-Mode', mode],
        capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert p.returncode == 0, p.stderr
    result = json.loads(p.stdout)
    success = mode in ['success', 'original_disabled']
    assert result['failed'] == (not success)
    assert result['accepted'] == success
    assert result['enabled'] == (mode == 'success')
    if not success:
        assert 'enable' not in result['actions']
    if mode in ['install_failed', 'verification_failed', 'rollback_failed']:
        assert 'rollback' in result['actions']
    if mode in ['partial_disable', 'drain_failed', 'baseline_drift', 'backup_failed']:
        assert 'install' not in result['actions']
