"""Actual supervisor functions, local synthetic fixtures; no network or models."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/run_qa_single_base_background.py'
spec = importlib.util.spec_from_file_location('background_under_test', SOURCE)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def good():
    return ({'models': [{'name': worker.NAME, 'digest': worker.PIN}, {'name': 'chiqiongblastfuenace:1', 'digest': worker.PIN}]},
            {'models': [{'name': worker.NAME, 'digest': worker.PIN}]})


@pytest.mark.parametrize('bad', [None, [], 'models', {}, {'models': None}, {'models': {}}, {'models': 'x'}, {'models': [None]}])
def test_unknown_metadata_is_not_ready(bad):
    tags, resident = good()
    assert not worker.identity_matches(bad, resident)
    assert not worker.identity_matches(tags, bad)


@pytest.mark.parametrize('change', ['empty', 'multiple', 'wrong_name', 'wrong_digest', 'upper_digest', 'truncated_digest', 'missing_digest', 'alias_duplicate', 'version_missing', 'version_wrong'])
def test_identity_defects_block(change):
    tags, resident = good()
    if change == 'empty': resident['models'] = []
    elif change == 'multiple': resident['models'] *= 2
    elif change == 'wrong_name': resident['models'][0]['name'] = 'other:latest'
    elif change == 'wrong_digest': resident['models'][0]['digest'] = '9' * 64
    elif change == 'upper_digest': resident['models'][0]['digest'] = worker.PIN.upper()
    elif change == 'truncated_digest': resident['models'][0]['digest'] = worker.PIN[:12]
    elif change == 'missing_digest': resident['models'][0].pop('digest')
    elif change == 'alias_duplicate': tags['models'].append(copy.deepcopy(tags['models'][0]))
    elif change == 'version_missing': tags['models'].pop()
    elif change == 'version_wrong': tags['models'][1]['digest'] = '9' * 64
    assert not worker.identity_matches(tags, resident)


def test_exact_frozen_identity():
    assert worker.identity_matches(*good())


@pytest.mark.parametrize('bad', [1, 'true', False, None])
def test_status_must_be_boolean(monkeypatch, bad):
    status = dict.fromkeys(('ok', 'proxy_ok', 'ollama_ok', 'model_ok'), True)
    status['model_ok'] = bad
    monkeypatch.setattr(worker, 'get_json', lambda _: status)
    assert not worker.readiness_status()


def test_status_sample_cannot_hide_alias_flip(monkeypatch):
    tags, resident = good()
    flipped = copy.deepcopy(tags)
    flipped['models'][0]['digest'] = '9' * 64
    values = iter([tags, resident, dict.fromkeys(('ok', 'proxy_ok', 'ollama_ok', 'model_ok'), True), flipped, resident])
    monkeypatch.setattr(worker, 'get_json', lambda _: next(values))
    assert worker.observe() == (False, 'fixed_model_identity_not_ready')


def plan():
    return {'model_identity': {'name': worker.NAME, 'digest': worker.PIN, 'approved_digests': [worker.PIN]},
            'cases': [{'case_id': 'SYNTHETIC-' + str(i), 'prompt': '合成问题'} for i in range(822)]}


@pytest.mark.parametrize('change', ['alternate', 'wrong_base', 'duplicate', 'unknown', 'path', 'count'])
def test_invalid_cohort_or_base_rejected(change):
    p = plan()
    if change == 'alternate': p['model_identity']['approved_digests'].append('9' * 64)
    elif change == 'wrong_base': p['model_identity']['digest'] = '9' * 64
    elif change == 'duplicate': p['cases'][1]['case_id'] = p['cases'][0]['case_id']
    elif change == 'unknown': p['cases'][0]['case_id'] = 'TPL-10C8C8FAF2C694EF'
    elif change == 'path': p['cases'][0]['case_id'] = '../escape'
    elif change == 'count': p['cases'].pop()
    with pytest.raises(ValueError): worker.validate_plan(p)


def fixture(tmp_path, monkeypatch, batch_source='raise RuntimeError("must not run while waiting")\n'):
    root, stage = tmp_path / 'root', tmp_path / 'stage'
    root.mkdir(); stage.mkdir()
    catalog = root / '数据库同步和存取/config/点位语义目录.json'
    catalog.parent.mkdir(parents=True); catalog.write_text('{}', encoding='utf-8')
    runtime = root / 'backend.py'; runtime.write_text('# synthetic\n', encoding='utf-8')
    p = plan(); p.update(runtime_hashes={'backend.py': worker.sha(runtime)}, catalog_sha256=worker.sha(catalog))
    sources = {'worker.py': '# synthetic\n', 'batch.py': batch_source, 'collector.py': '# synthetic\n',
               'templates.remaining.plan.json': json.dumps(p), 'start.ps1': '# synthetic\n'}
    for name, content in sources.items(): (stage / name).write_text(content, encoding='utf-8')
    manifest = {'files': {name: worker.sha(stage / name) for name in sources}}
    (stage / 'manifest.private.json').write_text(json.dumps(manifest), encoding='utf-8')
    digest = worker.sha(stage / 'manifest.private.json')
    output = root / 'logs/run'; output.mkdir(parents=True)
    (output / 'launch.claim').write_text(json.dumps({'manifest_sha256': digest, 'automatic_replay': False}), encoding='utf-8')
    args = argparse.Namespace(root=root, stage=stage, output=output, manifest_sha256=digest)
    original = worker.sha
    monkeypatch.setattr(worker, 'sha', lambda p: worker.MANAGER_SHA if p == Path('F:/Ollama/model-switch/manage_ollama_model_switch.ps1') else original(p))
    return args, manifest


def test_waiting_does_not_invoke_batch_and_can_stop(tmp_path, monkeypatch):
    args, _ = fixture(tmp_path, monkeypatch)
    observed = []
    monkeypatch.setattr(worker, 'observe', lambda: (observed.append(True) and True, 'fixed_model_identity_not_ready'))
    monkeypatch.setattr(worker.time, 'sleep', lambda _: (args.output / 'STOP').write_text('stop', encoding='utf-8'))
    monkeypatch.setattr(worker, 'get_json', lambda _: pytest.fail('waiting fixture must not access network'))
    worker.run(args)
    state = worker.read(args.output / 'progress.json')
    assert observed == [True]
    assert state['state'] == 'stopped_before_sending' and state['requests'] == 0
    assert not (args.output / 'batch').exists()
    with pytest.raises(FileExistsError): worker.run(args)


@pytest.mark.parametrize('change', ['runtime', 'manifest', 'batch', 'catalog'])
def test_changed_sealed_inputs_fail_before_batch(tmp_path, monkeypatch, change):
    args, manifest = fixture(tmp_path, monkeypatch)
    path = {'runtime': args.root / 'backend.py', 'manifest': args.stage / 'manifest.private.json',
            'batch': args.stage / 'batch.py', 'catalog': args.root / '数据库同步和存取/config/点位语义目录.json'}[change]
    path.write_text('{"changed":true}', encoding='utf-8')
    with pytest.raises(ValueError): worker.verify_inputs(args.stage, args.root, manifest, args.manifest_sha256)


def test_three_stable_observations_then_one_batch_invocation(tmp_path, monkeypatch):
    fake_batch = '''import json
from pathlib import Path
import sys
def verify(*args): return None
def require_request_budget(*args): return None
def main():
    out=Path(sys.argv[sys.argv.index('--output')+1]);out.mkdir()
    (out/'single-invocation').write_text('one')
    (out/'progress.json').write_text(json.dumps({'state':'completed','requests':822,'completed':822}))
'''
    args, _ = fixture(tmp_path, monkeypatch, fake_batch)
    ready = iter([True, True, False, True, True, True])
    observations = []
    def observe():
        result = next(ready); observations.append(result); return result, 'synthetic'
    monkeypatch.setattr(worker, 'observe', observe)
    monkeypatch.setattr(worker.time, 'sleep', lambda _: None)
    monkeypatch.setattr(worker, 'get_json', lambda _: pytest.fail('fake batch never calls network'))
    worker.run(args)
    assert observations == [True, True, False, True, True, True]
    state = worker.read(args.output / 'progress.json')
    assert state['state'] == 'completed' and state['requests'] == 822
    assert state['final_answer_review'] == 'pending_semantic_review'
    assert (args.output / 'batch/single-invocation').read_text() == 'one'
