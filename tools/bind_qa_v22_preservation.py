"""Bind verified preservation evidence into the local release before sealing."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    release = ROOT / '.codex_runtime/qa-routing-v22/release'
    spec_path = release / 'release-spec.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    for name, flag in [('ast-preservation.json', 'ok'), ('shared-feature-preservation.json', 'passed')]:
        path = release / name
        evidence = json.loads(path.read_text(encoding='utf-8'))
        if not evidence[flag]:
            raise ValueError('Preservation evidence failed')
        spec['sources'].append(str(path))
        spec['validations'].append({'id': name, 'kind': 'deterministic', 'status': 'passed'})
    spec['sources'].extend(str(ROOT / path) for path in [
        'tools/check_qa_v22_preservation.py', 'tools/bind_qa_v22_preservation.py',
        'tests/qa_regression/qa_proxy_shared_features_20260917.json',
        'tools/stage_qa_release.py', 'tools/prepare_qa_v9_invocations.py', 'tools/record_qa_release_preflight.py'])
    spec_path.write_bytes((json.dumps(spec, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'bound_preservation': True}))


if __name__ == '__main__': main()
