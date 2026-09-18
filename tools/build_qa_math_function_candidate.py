"""Freeze the no-code mathematical-function correction over verified V37."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v37/candidate-r2'
TARGET = ROOT / '.codex_runtime/qa-routing-v38/candidate-r2'
MODULE = 'qa_evidence_policy.py'


def main():
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    evidence = json.loads((ROOT / 'tests/qa_regression/compound_source_scope_20260917.json').read_bytes())
    prior_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert sha(prior_raw) == evidence['private_candidate']['manifest_sha256']
    prior = json.loads(prior_raw)
    assert len(prior['files']) == 15 and not TARGET.exists()
    assert prior['model_name'] == 'chiqiongblastfuenace:latest'
    assert prior['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    for name, raw in payloads.items():
        assert sha(raw) == prior['files'][name]['sha256']
    payloads[MODULE] = (ROOT / '高炉前端数据/智能助手/backend' / MODULE).read_bytes()
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'), filename=name)
    scope = {}
    exec(compile(payloads[MODULE], MODULE, 'exec'), scope)
    assert not scope['code_requested']('给出一次函数y=2x+1的斜率')
    assert scope['direct_result']('给出数学函数的Python代码')['answer_route'] == 'code_disabled'
    inherited = [name for name in prior['files'] if name != MODULE]
    assert len(inherited) == 14
    metadata = {'schema': 'bf.qa.private-local-math-function-candidate.v1', 'candidate': 'v38-r2',
      'state': 'local_frozen_not_production_sealed', 'prior_manifest_sha256': sha(prior_raw),
      'files': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
      'inherited_v37_files_byte_identical': inherited, 'changed_module': MODULE,
      'proxy_bytes_unchanged': True, 'production_dependency_refresh_required': True,
      'additional_runtime_read_set': prior['additional_runtime_read_set'],
      'model_name': prior['model_name'], 'model_digest': prior['model_digest'],
      'model_switch_allowed': False, 'same_name_weight_replacement_allowed': False,
      'fallback_model_allowed': False, 'production_writes': 0, 'model_operations': 0}
    TARGET.mkdir(parents=True)
    for name, raw in payloads.items():
        with (TARGET / name).open('xb') as handle:
            handle.write(raw)
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode()
    with (TARGET / 'package_manifest.private.json').open('xb') as handle:
        handle.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': len(payloads),
      'inherited': len(inherited), 'manifest_sha256': sha(raw), 'production_sealed': False, 'model_operations': 0}))


if __name__ == '__main__':
    main()
