"""Bind V25 AST and existing access/routing feature contracts before sealing."""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys

from build_qa_v25_clock_chart_candidate import CHANGED

ROOT = Path(__file__).resolve().parents[1]


def prepare_invocation():
    release = ROOT / '.codex_runtime/qa-routing-v25/release'
    invocation = (ROOT / '.codex_runtime/qa-routing-v24/release/invoke-preflight.ps1').read_text(encoding='utf-8')
    (release / 'invoke-preflight.ps1').write_bytes(invocation.replace('v24', 'v25').replace('V24', 'V25').encode('utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--invocation-only', action='store_true')
    args = parser.parse_args()
    if args.invocation_only:
        prepare_invocation()
        print(json.dumps({'ok': True, 'preflight_invocation_prepared': True}))
        return
    runtime = ROOT / '.codex_runtime/qa-routing-v25'
    release = runtime / 'release'
    def preserved(path):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(path.read_bytes()).body
                if not (isinstance(n, ast.FunctionDef) and n.name in CHANGED)]
    before = preserved(runtime / 'baseline/ollama_proxy_server.py')
    if before != preserved(runtime / 'candidate/ollama_proxy_server.py'):
        raise ValueError('Unrequested proxy AST change')
    result = {'ok': True, 'schema': 'bf.qa.proxy-ast-preservation.v1',
              'unchanged_top_level_nodes': len(before), 'allowed_changed_symbols': sorted(CHANGED)}
    (release / 'ast-preservation.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    guard = Path('C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/scripts/shared_feature_contract_guard.py')
    subprocess.run([sys.executable, '-X', 'utf8', str(guard), '--contract',
        str(ROOT / 'tests/qa_regression/qa_proxy_shared_features_20260917.json'),
        '--feature', 'qa_existing_routing', '--feature', 'qa_existing_access_and_asr',
        '--artifact', 'proxy=' + str(runtime / 'candidate/ollama_proxy_server.py'),
        '--output', str(release / 'shared-feature-preservation.json')], check=True, cwd=ROOT)
    spec_path = release / 'release-spec.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    for name, flag in [('ast-preservation.json', 'ok'), ('shared-feature-preservation.json', 'passed')]:
        path = release / name
        if not json.loads(path.read_text(encoding='utf-8'))[flag]:
            raise ValueError('Failed evidence')
        spec['sources'].append(str(path))
        spec['validations'].append({'id': name, 'kind': 'deterministic', 'status': 'passed'})
    spec['sources'].extend([str(Path(__file__).resolve()), str(guard),
        str(ROOT / 'tests/qa_regression/qa_proxy_shared_features_20260917.json')])
    spec_path.write_bytes((json.dumps(spec, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    prepare_invocation()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
