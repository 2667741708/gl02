"""Freeze supplied-record routing over the verified V43 closure."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v43/candidate-r6'
MODULES = ('qa_task_plan.py',)


def main(revision='r1'):
    assert revision in {'r1', 'r2', 'r3'}
    target = ROOT / '.codex_runtime/qa-routing-v44' / ('candidate-' + revision)
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    evidence = json.loads((ROOT / 'tests/qa_regression/source_exclusion_scope_20260917.json').read_bytes())
    prior_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert sha(prior_raw) == evidence['private_candidate']['manifest_sha256']
    prior = json.loads(prior_raw)
    assert len(prior['files']) == 15 and not target.exists()
    assert prior['model_name'] == 'chiqiongblastfuenace:latest'
    assert prior['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(prior[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    for name, raw in payloads.items(): assert sha(raw) == prior['files'][name]['sha256']
    for name in MODULES: payloads[name] = (ROOT / '高炉前端数据/智能助手/backend' / name).read_bytes()
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'), filename=name)
    inherited = [name for name in prior['files'] if name not in MODULES]
    assert len(inherited) == 14
    metadata = {'schema': 'bf.qa.private-supplied-record-candidate.v1', 'candidate': 'v44-' + revision,
      'state': 'local_frozen_not_production_sealed', 'prior_manifest_sha256': sha(prior_raw),
      'files': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
      'inherited_v43_files_byte_identical': inherited, 'changed_modules': list(MODULES),
      'proxy_bytes_unchanged': True, 'production_dependency_refresh_required': True,
      'additional_runtime_read_set': prior['additional_runtime_read_set'],
      'model_name': prior['model_name'], 'model_digest': prior['model_digest'],
      'model_switch_allowed': False, 'same_name_weight_replacement_allowed': False,
      'fallback_model_allowed': False, 'production_writes': 0, 'model_operations': 0}
    target.mkdir(parents=True)
    for name, raw in payloads.items():
        with (target / name).open('xb') as handle: handle.write(raw)
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode()
    with (target / 'package_manifest.private.json').open('xb') as handle: handle.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': 15, 'inherited': 14,
      'manifest_sha256': sha(raw), 'production_sealed': False, 'model_operations': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', choices=('r1', 'r2', 'r3'), default='r1')
    main(parser.parse_args().revision)
