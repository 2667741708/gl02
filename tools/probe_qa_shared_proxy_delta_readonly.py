"""Read a pinned production proxy delta; allow exactly three reviewed symbols."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess

if not __debug__:
    raise RuntimeError('Shared proxy evidence requires Python assertions enabled')

SYMBOLS = {'with_public_detail_semantics', 'Handler.handle_furnace_rule_detail',
    'Handler.handle_public_furnace_rule_breakdown'}
IMPORT = 'from furnace_display_policy import build_display_policy, build_unified_summary, display_name as furnace_display_name'
PROXY = '高炉前端数据/智能助手/backend/ollama_proxy_server.py'
DEPENDENCIES = ('高炉前端数据/智能助手/backend/furnace_display_policy.py',
    '高炉前端数据/智能助手/backend/abc_score_explanation.py')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def stable_ast_dump(node):
    """Match 3.11 evidence without dropping nonempty 3.12+ type semantics."""
    clone = copy.deepcopy(node)
    for item in ast.walk(clone):
        if 'type_params' in item._fields:
            assert not getattr(item, 'type_params', None), 'Generic type parameters require separate review'
            item._fields = tuple(field for field in item._fields if field != 'type_params')
    options = {'include_attributes': False}
    # 3.13 omits empty fields by default; 3.11 includes them.
    if 'show_empty' in ast.dump.__code__.co_varnames:
        options['show_empty'] = True
    return ast.dump(clone, **options)


def selected(text):
    result = {}
    lines = text.splitlines(keepends=True)
    def visit(body, prefix=''):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                key = prefix + node.name
                if key in SYMBOLS:
                    assert key not in result, 'Duplicate reviewed symbol'
                    first = min([node.lineno] + [item.lineno for item in getattr(node, 'decorator_list', [])])
                    result[key] = {'source': ''.join(lines[first - 1:node.end_lineno]),
                        'ast_sha256': sha(stable_ast_dump(node).encode())}
                if isinstance(node, ast.ClassDef): visit(node.body, key + '.')
    visit(ast.parse(text).body)
    assert set(result) == SYMBOLS, 'Missing reviewed symbol'
    return result


def prove_delta(before, after):
    old_tree, new_tree = ast.parse(before), ast.parse(after)
    old = {}
    def collect(body, prefix=''):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                key = prefix + node.name
                if key in SYMBOLS:
                    assert key not in old, 'Duplicate old symbol'
                    old[key] = node
                if isinstance(node, ast.ClassDef): collect(node.body, key + '.')
    collect(old_tree.body)
    assert set(old) == SYMBOLS
    seen = set()
    def normalize(body, prefix=''):
        for index, node in enumerate(body):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                key = prefix + node.name
                if key in SYMBOLS:
                    assert key not in seen, 'Duplicate new symbol'
                    body[index] = copy.deepcopy(old[key]); seen.add(key)
                elif isinstance(node, ast.ClassDef): normalize(node.body, key + '.')
    normalize(new_tree.body)
    imports = [node for node in new_tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
        and ast.unparse(node) == IMPORT]
    assert len(imports) == 1, 'Expected exact reviewed import'
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and ast.unparse(node) == IMPORT for node in old_tree.body)
    new_tree.body.remove(imports[0])
    assert seen == SYMBOLS
    a, b = stable_ast_dump(old_tree), stable_ast_dump(new_tree)
    assert a == b, 'Unhandled shared proxy change; stop, do not overwrite'
    return {'whole_ast_delta_covered': True, 'before_ast_sha256': sha(a.encode()),
        'normalized_after_ast_sha256': sha(b.encode())}


def probe(root, before, after):
    root = Path(root).resolve()
    git = 'C:/Program Files/Git/cmd/git.exe'
    def read(*args): return subprocess.check_output([git, '-C', str(root), *args])
    assert read('rev-parse', 'HEAD').decode().strip() == after, 'Production head changed'
    a = read('show', before + ':' + PROXY)
    b = read('show', after + ':' + PROXY)
    assert (root / PROXY).read_bytes() == b, 'Live proxy differs from pinned Git object'
    before_text, after_text = a.decode('utf-8'), b.decode('utf-8')
    coverage = prove_delta(before_text, after_text)
    result = {'schema': 'bf.qa.shared-proxy-fragments.v2', 'before': before, 'after': after,
        'before_proxy_sha256': sha(a), 'after_proxy_sha256': sha(b),
        'old': selected(before_text), 'new': selected(after_text), 'new_import': IMPORT,
        'dependency_hashes': {name: sha((root / name).read_bytes()) for name in DEPENDENCIES},
        **coverage, 'deployment_authorized': False,
        'production_writes': 0, 'model_calls': 0, 'question_posts': 0}
    assert read('rev-parse', 'HEAD').decode().strip() == after, 'Head changed during read'
    assert (root / PROXY).read_bytes() == b, 'Proxy changed during read'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.root, args.before, args.after), ensure_ascii=False))
