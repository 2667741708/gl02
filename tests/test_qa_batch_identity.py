"""A tag match alone cannot make a paired online comparison valid."""
import importlib.util
import io
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('qa_batch_identity', Path(__file__).resolve().parents[1] / 'tools/run_qa_template_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)
NAME = 'chiqiongblastfuenace:latest'
PIN = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'


@pytest.mark.parametrize('resident', [[], [{'digest': 'other'}], [{'digest': PIN}, {'digest': PIN}]])
def test_matching_tag_with_wrong_residency_blocks_before_send(monkeypatch, tmp_path, resident):
    collector = tmp_path / 'collector.py'
    collector.write_bytes(b'# synthetic')
    plan = {'collector_sha256': batch.digest(collector), 'runtime_hashes': {},
            'model_identity': {'name': NAME, 'digest': PIN}}
    def read(url, **kwargs):
        data = {'models': [{'name': NAME, 'digest': PIN}] if url.endswith('/tags') else resident}
        return io.BytesIO(json.dumps(data).encode())
    monkeypatch.setattr(batch.urllib.request, 'urlopen', read)
    with pytest.raises(RuntimeError, match='resident model'):
        batch.verify(plan, tmp_path, collector)


def test_matching_tag_and_single_resident_accepts(monkeypatch, tmp_path):
    collector = tmp_path / 'collector.py'
    collector.write_bytes(b'# synthetic')
    plan = {'collector_sha256': batch.digest(collector), 'runtime_hashes': {},
            'model_identity': {'name': NAME, 'digest': PIN}}
    monkeypatch.setattr(batch.urllib.request, 'urlopen', lambda *args, **kwargs: io.BytesIO(
        json.dumps({'models': [{'name': NAME, 'digest': PIN}]}).encode()))
    batch.verify(plan, tmp_path, collector)


def test_even_approved_alternative_base_is_forbidden(monkeypatch, tmp_path):
    collector = tmp_path / 'collector.py'
    collector.write_bytes(b'# synthetic')
    plan = {'collector_sha256': batch.digest(collector), 'runtime_hashes': {},
            'model_identity': {'name': NAME, 'digest': PIN,
                               'approved_digests': [PIN, 'approved-second']}}
    monkeypatch.setattr(batch.urllib.request, 'urlopen', lambda *args, **kwargs: io.BytesIO(
        json.dumps({'models': [{'name': 'approved:latest', 'digest': 'approved-second'}]}).encode()))
    with pytest.raises(RuntimeError, match='multiple model digests forbidden'):
        batch.verify(plan, tmp_path, collector)


@pytest.mark.parametrize('identity', [None, {'name': NAME, 'digest': 'other'}, {'name': 'other:latest', 'digest': PIN}])
def test_plan_cannot_redefine_or_omit_immutable_base(monkeypatch, tmp_path, identity):
    collector = tmp_path / 'collector.py'
    collector.write_bytes(b'# synthetic')
    plan = {'collector_sha256': batch.digest(collector), 'runtime_hashes': {}, 'model_identity': identity}
    monkeypatch.setattr(batch.urllib.request, 'urlopen', lambda *args, **kwargs: pytest.fail('No request'))
    with pytest.raises(RuntimeError, match='immutable'):
        batch.verify(plan, tmp_path, collector)
