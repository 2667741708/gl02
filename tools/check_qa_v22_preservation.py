"""Verify every proxy AST node outside the requested renderer remains identical."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.codex_runtime/qa-routing-v22'


def main():
    before = ast.parse((RUNTIME / 'baseline/ollama_proxy_server.py').read_bytes())
    after = ast.parse((RUNTIME / 'candidate/ollama_proxy_server.py').read_bytes())
    def preserved(tree):
        return [ast.dump(node, include_attributes=False) for node in tree.body
                if not (isinstance(node, ast.FunctionDef) and node.name == 'deterministic_mcp_answer')]
    if preserved(before) != preserved(after):
        raise ValueError('Unrequested proxy feature AST changed')
    result = {'ok': True, 'schema': 'bf.qa.proxy-ast-preservation.v1',
              'unchanged_top_level_nodes': len(preserved(before)),
              'allowed_changed_symbol': 'deterministic_mcp_answer'}
    (RUNTIME / 'release/ast-preservation.json').write_bytes((json.dumps(result, indent=2)+'\n').encode('utf-8'))
    print(json.dumps(result))


if __name__ == '__main__': main()
