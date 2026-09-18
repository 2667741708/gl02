"""A mutable alias agreeing with its resident is not proof of the fixed base."""
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixed_runtime_probe', ROOT / 'tools/probe_qa_paired_runtime_readonly.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
NAME = 'chiqiongblastfuenace:latest'
PIN = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
RETIRED = '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'


@pytest.mark.parametrize('alias,resident,alias_after,expected', [
 (PIN, [PIN], PIN, True),
 (RETIRED, [RETIRED], RETIRED, False),
 ('f' * 64, ['f' * 64], 'f' * 64, False),
 (PIN, [PIN], RETIRED, False),
 (RETIRED, [PIN], RETIRED, False),
 (PIN, [], PIN, False),
 (PIN, [PIN, PIN], PIN, False),
])
def test_actual_runtime_probe_requires_fixed_digest_and_stable_alias(monkeypatch, tmp_path, capsys, alias, resident, alias_after, expected):
    catalog = tmp_path / '数据库同步和存取/config/点位语义目录.json'
    catalog.parent.mkdir(parents=True)
    catalog.write_bytes(b'{}')
    scoped = tmp_path / 'probe.txt'
    scoped.write_bytes(b'non-sensitive-fixture')
    gate = tmp_path / 'scope.json'
    gate.write_text(json.dumps({'read_files': [{'path': 'probe.txt'}], 'write_set': []}), encoding='utf-8')
    calls = []
    def request(url, timeout):
        calls.append(url)
        if url.endswith('/api/ollama/status'):
            payload = {'ok': True}
        elif url.endswith('/api/tags'):
            tag_calls = sum(item.endswith('/api/tags') for item in calls)
            payload = {'models': [{'name': NAME, 'digest': alias if tag_calls == 1 else alias_after}]}
        elif url.endswith('/api/ps'):
            payload = {'models': [{'name': NAME, 'digest': digest} for digest in resident]}
        else:
            raise AssertionError('Only read-only metadata endpoints are allowed')
        return io.BytesIO(json.dumps(payload).encode())
    def build_opener(handler):
        assert isinstance(handler, probe.urllib.request.ProxyHandler) and handler.proxies == {}
        return SimpleNamespace(open=request)
    monkeypatch.setattr(probe.urllib.request, 'build_opener', build_opener)
    monkeypatch.setattr(probe.subprocess, 'check_output', lambda *a, **k: 'fixture-production-head\n')
    monkeypatch.setattr(sys, 'argv', ['probe', '--root', str(tmp_path), '--scope-file', str(gate)])
    code = probe.main()
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] is expected
    assert code == (0 if expected else 1)
    assert all('/api/chat' not in url and '/api/generate' not in url for url in calls)
    assert result['expected_model_identity'] == {'name': NAME, 'digest': PIN}
    assert result['fixed_identity_ready'] is expected
    assert result['loopback_proxy_disabled'] and result['metadata_errors'] == []
    assert calls[-3:] == ['http://127.0.0.1:11434/api/tags', 'http://127.0.0.1:11434/api/ps', 'http://127.0.0.1:11434/api/tags']


@pytest.mark.parametrize('relative', ['../outside', '/absolute', '../repo/inside'])
def test_runtime_scope_rejects_paths_outside_reviewed_root(tmp_path, relative):
    with pytest.raises(ValueError, match='reviewed repository'):
        probe.scoped_paths(tmp_path, {'read_files': [{'path': relative}], 'write_set': []})


def test_runtime_probe_pin_matches_canonical_identity_module():
    import ast
    module = ast.parse((ROOT / '高炉前端数据/智能助手/backend/qa_fixed_model_identity.py').read_bytes())
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in module.body
      if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
      and node.targets[0].id in {'MODEL_NAME', 'MODEL_DIGEST'}}
    assert constants == {'MODEL_NAME': probe.MODEL_NAME, 'MODEL_DIGEST': probe.MODEL_DIGEST}


@pytest.mark.parametrize('tags_before,resident,tags_after', [
 (None, None, None),
 ([{'name': NAME}], [{'digest': PIN}], [{'name': NAME}]),
 ([{'name': NAME, 'digest': PIN}] * 2, [{'digest': PIN}], [{'name': NAME, 'digest': PIN}]),
 ([{'name': NAME, 'digest': PIN}], [{'name': 'other:latest', 'digest': PIN}], [{'name': NAME, 'digest': PIN}]),
])
def test_malformed_or_duplicate_identity_metadata_never_marks_ready(tags_before, resident, tags_after):
    assert not all(probe.pin_status(tags_before, resident, tags_after).values())


def test_metadata_failure_keeps_scoped_hashes_and_does_not_claim_ready(monkeypatch, tmp_path, capsys):
    catalog = tmp_path / '数据库同步和存取/config/点位语义目录.json'
    catalog.parent.mkdir(parents=True)
    catalog.write_bytes(b'{}')
    scoped = tmp_path / 'probe.txt'
    scoped.write_bytes(b'non-sensitive-fixture')
    scope = {'read_files': [{'path': 'probe.txt'}], 'write_set': ['not-created-yet.py']}
    def request(url, timeout):
        raise OSError('sensitive diagnostic details must never enter the report')
    monkeypatch.setattr(probe.urllib.request, 'build_opener', lambda handler: SimpleNamespace(open=request))
    monkeypatch.setattr(probe.subprocess, 'check_output', lambda *a, **k: 'fixture-production-head\n')
    monkeypatch.setattr(sys, 'argv', ['probe', '--root', str(tmp_path), '--scope-json', json.dumps(scope)])
    assert probe.main() == 1
    rendered = capsys.readouterr().out
    result = json.loads(rendered)
    assert not result['ok'] and not result['fixed_identity_ready']
    assert result['runtime_hashes']['probe.txt'] and result['runtime_hashes']['not-created-yet.py'] is None
    assert len(result['metadata_errors']) == 4 and 'sensitive diagnostic details' not in rendered
    assert result['head'] == 'fixture-production-head'
