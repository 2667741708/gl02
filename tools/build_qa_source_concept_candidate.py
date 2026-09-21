"""Freeze source-domain concepts over the verified V41 runtime closure."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v41/candidate-r1'
TARGET = ROOT / '.codex_runtime/qa-routing-v42/candidate-r1'
MODULE = 'qa_task_plan.py'


def main():
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    evidence = json.loads((ROOT / 'tests/qa_regression/response_style_source_scope_20260917.json').read_bytes())
    prior_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert sha(prior_raw) == evidence['private_candidate']['manifest_sha256']
    prior = json.loads(prior_raw)
    assert len(prior['files']) == 15 and not TARGET.exists()
    assert prior['model_name'] == 'chiqiongblastfuenace:latest'
    assert prior['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(prior[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    for name, raw in payloads.items():
        assert sha(raw) == prior['files'][name]['sha256']
    payloads[MODULE] = (ROOT / '高炉前端数据/智能助手/backend' / MODULE).read_bytes()
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'), filename=name)
    inherited = [name for name in prior['files'] if name != MODULE]
    assert len(inherited) == 14
    metadata = {'schema': 'bf.qa.private-source-concept-candidate.v1', 'candidate': 'v42-r1',
      'state': 'local_frozen_not_production_sealed', 'prior_manifest_sha256': sha(prior_raw),
      'files': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
      'inherited_v41_files_byte_identical': inherited, 'changed_module': MODULE,
      'proxy_bytes_unchanged': True, 'production_dependency_refresh_required': True,
      'additional_runtime_read_set': prior['additional_runtime_read_set'],
      'model_name': prior['model_name'], 'model_digest': prior['model_digest'],
      'model_switch_allowed': False, 'same_name_weight_replacement_allowed': False,
      'fallback_model_allowed': False, 'production_writes': 0, 'model_operations': 0}
    TARGET.mkdir(parents=True)
    for name, raw in payloads.items():
        with (TARGET / name).open('xb') as handle: handle.write(raw)
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode()
    with (TARGET / 'package_manifest.private.json').open('xb') as handle: handle.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': 15, 'inherited': 14,
      'manifest_sha256': sha(raw), 'production_sealed': False, 'model_operations': 0}))


if __name__ == '__main__':
    main()
