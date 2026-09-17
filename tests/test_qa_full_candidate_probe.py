"""Exercise the read-only boundary in fresh processes, never real model calls."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from qa_full_candidate_probe import BASE_FILES, FIXED_NAME, FIXED_DIGEST


def payload(tmp_path, source):
    (tmp_path / '高炉前端数据/智能助手/backend').mkdir(parents=True)
    (tmp_path / '自动诊断服务').mkdir()
    sources = {name: b'"""Synthetic read-only guard fixture, not application coverage."""\n' for name in BASE_FILES}
    sources['ollama_proxy_server.py'] = source.encode('utf-8')
    return {'dependency_root': str(tmp_path), 'model_name': FIXED_NAME,
        'model_digest': FIXED_DIGEST,
        'sources': {name: base64.b64encode(raw).decode() for name,raw in sources.items()},
        'sha256': {name: hashlib.sha256(raw).hexdigest() for name,raw in sources.items()}}


def probe(data):
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/qa_full_candidate_probe.py')],
        input=json.dumps(data), capture_output=True, text=True, encoding='utf-8', timeout=30)
    report = json.loads(result.stdout)
    assert result.returncode == (0 if report['ok'] else 1), result.stderr
    return report


def test_import_guard_checks_every_frozen_module_and_hash(tmp_path):
    result = probe(payload(tmp_path, 'pass\n'))
    assert result['ok'] and result['frozen_modules_loaded'] == 16
    assert len([row for row in result['module_hashes'].values() if row['source'] == 'frozen_in_memory']) == 16
    assert result['side_effect_attempts'] == []
    assert not result['service_started'] and not result['semantic_accuracy_inferred']


@pytest.mark.parametrize('source,denied', [
    ('import socket\nsocket.socket().connect(("127.0.0.1", 1))\n', 'socket.connect'),
    ('import socket\nsocket.getaddrinfo("synthetic.invalid", 1)\n', 'socket.getaddrinfo'),
    ('import socket\nsocket.socket().bind(("127.0.0.1", 0))\n', 'socket.bind'),
    ('open(__file__ + ".unexpected", "w").write("fixture")\n', 'open_write'),
    ('import subprocess\nsubprocess.run(["synthetic-invalid-program"])\n', 'subprocess.Popen'),
    ('import threading\nthreading.Thread(target=lambda: None).start()\n', 'thread_start'),
    ('import sqlite3\nsqlite3.connect(":memory:")\n', 'database_connect'),
    ('import os\nos.mkdir(__file__ + ".unexpected")\n', 'os.mkdir'),
])
def test_full_import_blocks_external_side_effect_before_it_occurs(tmp_path, source, denied):
    result = probe(payload(tmp_path, source))
    assert not result['ok']
    assert result['error']['type'] == 'SideEffectDenied'
    assert result['side_effect_attempts'] == [denied]
    assert result['model_calls'] == result['question_posts'] == result['production_writes'] == 0
    assert not list(tmp_path.rglob('*.unexpected'))


def test_catching_rejected_io_does_not_turn_import_into_pass(tmp_path):
    source = 'import socket\ntry:\n    socket.socket().connect(("127.0.0.1", 1))\nexcept RuntimeError:\n    pass\n'
    result = probe(payload(tmp_path, source))
    assert result['error'] is None
    assert result['frozen_modules_loaded'] == 16
    assert not result['ok'] and result['side_effect_attempts'] == ['socket.connect']


def test_real_missing_import_is_reported_without_stubbing(tmp_path):
    result = probe(payload(tmp_path, 'import synthetic_nonexistent_dependency\n'))
    assert not result['ok']
    assert result['error'] == {'type': 'ModuleNotFoundError', 'missing_module': 'synthetic_nonexistent_dependency', 'importing': 'ollama_proxy_server'}


def test_native_dependency_is_bound_to_executed_source_bytes(tmp_path):
    data = payload(tmp_path, 'from synthetic_dependency import VALUE\nassert VALUE == 17\n')
    file = tmp_path / '高炉前端数据/智能助手/backend/synthetic_dependency.py'
    raw = b'VALUE = 17\n'
    file.write_bytes(raw)
    result = probe(data)
    assert result['ok'] and result['changed_or_unbound_dependencies'] == []
    assert result['module_hashes'][file.relative_to(tmp_path).as_posix()] == {
        'sha256': hashlib.sha256(raw).hexdigest(), 'source': 'dependency_readonly_source'}
    assert not list(tmp_path.rglob('__pycache__'))


def test_package_dependency_retains_native_relative_imports(tmp_path):
    data = payload(tmp_path, 'from synthetic_package import VALUE\nassert VALUE == 19\n')
    folder = tmp_path / '高炉前端数据/智能助手/backend/synthetic_package'
    folder.mkdir()
    (folder / '__init__.py').write_bytes(b'from .value import VALUE\n')
    (folder / 'value.py').write_bytes(b'VALUE = 19\n')
    result = probe(data)
    assert result['ok'] and result['changed_or_unbound_dependencies'] == []
    paths = [name for name in result['module_hashes'] if '/synthetic_package/' in name]
    assert len(paths) == 2 and not list(tmp_path.rglob('__pycache__'))


def test_runtime_pin_verifies_actual_dependency_before_source_exec(tmp_path):
    data = payload(tmp_path, 'from synthetic_dependency import VALUE\nassert VALUE == 17\n')
    file = tmp_path / '高炉前端数据/智能助手/backend/synthetic_dependency.py'
    raw = b'VALUE = 17\n'
    file.write_bytes(raw)
    data['runtime_dependency_pins'] = {file.relative_to(tmp_path).as_posix(): hashlib.sha256(raw).hexdigest()}
    report = probe(data)
    assert report['ok'] and report['runtime_dependency_pins'] == data['runtime_dependency_pins']
    assert report['runtime_dependency_pin_mismatches'] == []


def test_changed_pinned_dependency_never_executes_even_if_import_error_is_caught(tmp_path):
    data = payload(tmp_path, 'try:\n    import synthetic_dependency\nexcept ValueError:\n    pass\n')
    file = tmp_path / '高炉前端数据/智能助手/backend/synthetic_dependency.py'
    file.write_bytes(b'import socket\nsocket.socket().connect(("127.0.0.1",1))\n')
    path = file.relative_to(tmp_path).as_posix()
    data['runtime_dependency_pins'] = {path: hashlib.sha256(b'VALUE = 17\n').hexdigest()}
    report = probe(data)
    assert not report['ok'] and report['error'] is None
    assert report['runtime_dependency_pin_mismatches'] == [path]
    assert report['side_effect_attempts'] == [], 'Changed source must not execute before hash rejection'


def test_unimported_runtime_pin_cannot_be_reported_as_verified(tmp_path):
    data = payload(tmp_path, 'pass\n')
    path = '高炉前端数据/智能助手/backend/synthetic_dependency.py'
    (tmp_path / path).write_bytes(b'VALUE = 17\n')
    data['runtime_dependency_pins'] = {path: hashlib.sha256(b'VALUE = 17\n').hexdigest()}
    report = probe(data)
    assert not report['ok'] and report['runtime_dependency_pin_mismatches'] == [path]
