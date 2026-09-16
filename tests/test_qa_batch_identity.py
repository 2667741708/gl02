"""A tag match alone cannot make a paired online comparison valid."""
import importlib.util
import io
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('qa_batch_identity', Path(__file__).resolve().parents[1] / 'tools/run_qa_template_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


@pytest.mark.parametrize('resident', [[], [{'digest': 'other'}], [{'digest': 'fixed'}, {'digest': 'fixed'}]])
def test_matching_tag_with_wrong_residency_blocks_before_send(monkeypatch, tmp_path, resident):
    collector = tmp_path / 'collector.py'
    collector.write_bytes(b'# synthetic')
    plan = {'collector_sha256': batch.digest(collector), 'runtime_hashes': {},
            'model_identity': {'name': 'approved:latest', 'digest': 'fixed'}}
    def read(url, **kwargs):
        data = {'models': [{'name': 'approved:latest', 'digest': 'fixed'}] if url.endswith('/tags') else resident}
        return io.BytesIO(json.dumps(data).encode())
    monkeypatch.setattr(batch.urllib.request, 'urlopen', read)
    with pytest.raises(RuntimeError, match='resident model'):
        batch.verify(plan, tmp_path, collector)


def test_matching_tag_and_single_resident_accepts(monkeypatch, tmp_path):
    collector = tmp_path / 'collector.py'
    collector.write_bytes(b'# synthetic')
    plan = {'collector_sha256': batch.digest(collector), 'runtime_hashes': {},
            'model_identity': {'name': 'approved:latest', 'digest': 'fixed'}}
    monkeypatch.setattr(batch.urllib.request, 'urlopen', lambda *args, **kwargs: io.BytesIO(
        json.dumps({'models': [{'name': 'approved:latest', 'digest': 'fixed'}]}).encode()))
    batch.verify(plan, tmp_path, collector)


def test_approved_model_strata_records_actual_digest(monkeypatch, tmp_path):
    collector = tmp_path / 'collector.py'
    collector.write_bytes(b'# synthetic')
    plan = {'collector_sha256': batch.digest(collector), 'runtime_hashes': {},
            'model_identity': {'name': 'approved:latest', 'digest': 'fixed',
                               'approved_digests': ['fixed', 'approved-second']}}
    monkeypatch.setattr(batch.urllib.request, 'urlopen', lambda *args, **kwargs: io.BytesIO(
        json.dumps({'models': [{'name': 'approved:latest', 'digest': 'approved-second'}]}).encode()))
    assert batch.verify(plan, tmp_path, collector)['digest'] == 'approved-second'
