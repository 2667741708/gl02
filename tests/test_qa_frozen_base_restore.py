import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = Path('C:/Program Files/PowerShell/7/pwsh.exe')


@pytest.mark.parametrize('mode,failed,samples,pauses', [
    ('healthy_numeric', False, 0, 0), ('healthy_disabled', False, 0, 0),
    ('enabled', True, 0, 0), ('enabled_string', True, 0, 0),
    ('running', True, 0, 0), ('unknown', True, 0, 0), ('invalid_numeric', True, 0, 0),
    ('wrong_source', True, 0, 0), ('multiple_resident', True, 0, 0), ('unknown_resident', True, 0, 0),
    ('wait_empty', False, 1, 0), ('wait_delayed', False, 3, 2), ('wait_busy', True, 3, 2),
    ('wait_unknown', True, 1, 0), ('wait_changed', True, 1, 0),
])
def test_actual_ast_boundary_and_wait_without_network(mode, failed, samples, pauses):
    result = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-File',
                             str(ROOT / 'tests/qa_regression/frozen_base_restore_harness.ps1'),
                             '-Controller', str(ROOT / 'tools/restore_qa_frozen_base_once.ps1'), '-Mode', mode],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert (value['failed'], value['samples'], value['pauses']) == (failed, samples, pauses)
    assert not value['top_level_executed'] and value['model_posts'] == 0
