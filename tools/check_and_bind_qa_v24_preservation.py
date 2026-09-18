"""Verify proxy preservation and bind the evidence before release sealing."""
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    runtime = ROOT / '.codex_runtime/qa-routing-v24'
    release = runtime / 'release'
    def preserved(path):
        return [ast.dump(node, include_attributes=False) for node in ast.parse(path.read_bytes()).body
            if not (isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_should_use_tools')]
    before = preserved(runtime / 'baseline/ollama_proxy_server.py')
    if before != preserved(runtime / 'candidate/ollama_proxy_server.py'):
        raise ValueError('Unrequested proxy AST change')
    ast_result = {'ok': True, 'schema': 'bf.qa.proxy-ast-preservation.v1',
        'unchanged_top_level_nodes': len(before), 'allowed_changed_symbol': 'qa_mcp_should_use_tools'}
    (release / 'ast-preservation.json').write_bytes((json.dumps(ast_result, indent=2) + '\n').encode())
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
        if str(path) not in spec['sources']:
            spec['sources'].append(str(path))
        spec['validations'].append({'id': name, 'kind': 'deterministic', 'status': 'passed'})
    spec['sources'].extend([str(Path(__file__).resolve()), str(guard),
        str(ROOT / 'tests/qa_regression/qa_proxy_shared_features_20260917.json')])
    spec_path.write_bytes((json.dumps(spec, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    invocation = (ROOT / '.codex_runtime/qa-routing-v23/release/invoke-preflight.ps1').read_text(encoding='utf-8')
    (release / 'invoke-preflight.ps1').write_bytes(invocation.replace('v23', 'v24').replace('V23', 'V24').encode('utf-8'))
    print(json.dumps(ast_result))


if __name__ == '__main__':
    main()
