"""Prove production feature preservation before sealing the V26 three-file fix."""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys

from build_qa_v26_chart_evidence_candidate import CHANGED

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--invocation-only', action='store_true')
    args = parser.parse_args()
    runtime = ROOT / '.codex_runtime/qa-routing-v26'
    release = runtime / 'release'
    invocation = (ROOT / '.codex_runtime/qa-routing-v25/release/invoke-preflight.ps1').read_text(encoding='utf-8')
    (release / 'invoke-preflight.ps1').write_bytes(invocation.replace('v25', 'v26').replace('V25', 'V26').encode('utf-8'))
    if args.invocation_only:
        print('PASS: V26 preflight invocation prepared')
        return
    def protected(path, changed, extra_import=False):
        return [ast.dump(n, include_attributes=False) for n in ast.parse(path.read_bytes()).body
                if not (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in changed)
                and not (extra_import and isinstance(n, ast.Import) and [a.name for a in n.names] == ['qa_tool_fallback'])]
    before = protected(runtime / 'baseline/ollama_proxy_server.py', CHANGED, True)
    if before != protected(runtime / 'candidate/ollama_proxy_server.py', CHANGED, True):
        raise ValueError('Unrequested proxy AST change')
    mcp_before = protected(runtime / 'baseline/bf_data_mcp_server.py', {'parse_variables_arg', 'plot_gl02_trends'})
    if mcp_before != protected(runtime / 'candidate/bf_data_mcp_server.py', {'parse_variables_arg', 'plot_gl02_trends'}):
        raise ValueError('Unrequested MCP AST change')
    result = {'ok': True, 'schema': 'bf.qa.proxy-ast-preservation.v1', 'unchanged_top_level_nodes': len(before),
              'allowed_changed_symbols': sorted(CHANGED), 'allowed_extra_import': 'qa_tool_fallback',
              'unchanged_mcp_nodes': len(mcp_before), 'allowed_mcp_changed_symbols': ['parse_variables_arg', 'plot_gl02_trends']}
    (release / 'ast-preservation.json').write_bytes((json.dumps(result, indent=2)+'\n').encode('utf-8'))
    guard = Path('C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/scripts/shared_feature_contract_guard.py')
    subprocess.run([sys.executable, '-X', 'utf8', str(guard), '--contract', str(ROOT / 'tests/qa_regression/qa_proxy_shared_features_20260917.json'),
                    '--feature', 'qa_existing_routing', '--feature', 'qa_existing_access_and_asr',
                    '--artifact', 'proxy=' + str(runtime / 'candidate/ollama_proxy_server.py'),
                    '--output', str(release / 'shared-feature-preservation.json')], check=True, cwd=ROOT)
    path = release / 'release-spec.json'
    spec = json.loads(path.read_text(encoding='utf-8'))
    for name, flag in [('ast-preservation.json', 'ok'), ('shared-feature-preservation.json', 'passed')]:
        evidence = release / name
        if not json.loads(evidence.read_text(encoding='utf-8'))[flag]: raise ValueError('Failed feature gate')
        spec['sources'].append(str(evidence))
        spec['validations'].append({'id': name, 'kind': 'deterministic', 'status': 'passed'})
    spec['sources'].extend([str(guard), str(ROOT / 'tests/qa_regression/qa_proxy_shared_features_20260917.json')])
    path.write_bytes((json.dumps(spec, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
