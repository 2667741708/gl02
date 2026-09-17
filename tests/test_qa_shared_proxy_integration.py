"""Preserve live shared ABC33 code while retaining every frozen QA source gate."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
from build_qa_shared_proxy_candidate import EVIDENCE, EVIDENCE_SHA, PRIOR, PINS, validate_fragments, build_proxy
from probe_qa_shared_proxy_delta_readonly import IMPORT, SYMBOLS, prove_delta, selected, stable_ast_dump
from qa_frozen_candidate import latest_frozen_candidate


def fragments():
    raw = EVIDENCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EVIDENCE_SHA
    return json.loads(raw)


def fixture_before():
    # Include a literal whose indentation is semantic, rather than only pass bodies.
    return ('FLAG = 17\ndef with_public_detail_semantics():\n    return 1\n'
        'class Handler:\n    def handle_furnace_rule_detail(self):\n'
        '        return """first\n        indented literal\n        last"""\n'
        '    def handle_public_furnace_rule_breakdown(self):\n        return 3\n')


def fixture_after():
    return IMPORT + '\n' + fixture_before().replace('return 1\n', 'return 2\n')


def test_entire_shared_delta_is_covered_without_changing_other_semantics():
    proof = prove_delta(fixture_before(), fixture_after())
    assert proof['whole_ast_delta_covered'] is True
    assert proof['before_ast_sha256'] == proof['normalized_after_ast_sha256']


@pytest.mark.parametrize('mutation', [
    lambda s: s.replace('FLAG = 17', 'FLAG = 18'),
    lambda s: s + '\nimport os\n',
    lambda s: s + '\ndef unreviewed():\n    return 0\n',
    lambda s: s.replace(IMPORT, IMPORT + '\n' + IMPORT),
    lambda s: s.replace(IMPORT + '\n', ''),
    lambda s: s.replace('def handle_furnace_rule_detail(', 'def removed_detail('),
    lambda s: s + '\ndef with_public_detail_semantics():\n    return 99\n',
    lambda s: s.replace('    def handle_public_furnace_rule_breakdown', '    def other_breakdown'),
])
def test_unreviewed_changes_or_missing_duplicate_symbols_are_rejected(mutation):
    with pytest.raises(AssertionError):
        prove_delta(fixture_before(), mutation(fixture_after()))


def test_class_scope_parser_preserves_triple_quoted_literal_and_native_hashes():
    evidence = fragments()
    validate_fragments(evidence)
    for version in ('old', 'new'):
        for name, row in evidence[version].items():
            tree = ast.parse(('class Handler:\n' if name.startswith('Handler.') else '') + row['source'])
            node = tree.body[0].body[0] if name.startswith('Handler.') else tree.body[0]
            assert hashlib.sha256(stable_ast_dump(node).encode()).hexdigest() == row['ast_sha256']
    class_node = ast.parse(fixture_before()).body[-1]
    literal = next(n for n in ast.walk(class_node) if isinstance(n, ast.Constant) and isinstance(n.value, str))
    assert literal.value == 'first\n        indented literal\n        last'


@pytest.mark.parametrize('mutation', [
    lambda e: e.update(schema='stale'),
    lambda e: e.update(before='wrong'),
    lambda e: e.update(after='wrong'),
    lambda e: e.update(after_proxy_sha256='0' * 64),
    lambda e: e.update(before_proxy_sha256='0' * 64),
    lambda e: e.update(new_import='import os'),
    lambda e: e['dependency_hashes'].update({next(iter(PINS)): '0' * 64}),
    lambda e: e.update(whole_ast_delta_covered=False),
    lambda e: e.update(before_ast_sha256='0' * 64),
    lambda e: e.update(deployment_authorized=True),
    lambda e: e.update(production_writes=False),
    lambda e: e.update(question_posts=1),
    lambda e: e.update(model_calls=1),
    lambda e: e['new'].pop(next(iter(SYMBOLS))),
    lambda e: e['new']['with_public_detail_semantics'].update(ast_sha256='0' * 64),
    lambda e: e['new']['with_public_detail_semantics'].update(source='def wrong():\n    pass\n'),
    lambda e: e['new']['with_public_detail_semantics'].update(source='def with_public_detail_semantics():\r\n    pass\r\n'),
])
def test_wrong_unbound_or_mutating_fragment_evidence_is_rejected(mutation):
    evidence = copy.deepcopy(fragments())
    mutation(evidence)
    with pytest.raises(AssertionError):
        validate_fragments(evidence)


def test_frozen_merge_retains_v46_modules_and_exact_three_production_symbols():
    candidate, manifest = latest_frozen_candidate(ROOT)
    assert manifest['candidate'].startswith('v47-')
    assert manifest['runtime_dependency_pins'] == PINS
    evidence = fragments()
    before = (PRIOR / 'ollama_proxy_server.py').read_text(encoding='utf-8')
    after = (candidate / 'ollama_proxy_server.py').read_text(encoding='utf-8')
    assert build_proxy(before, evidence) == after
    assert selected(after) == evidence['new']
    assert prove_delta(before, after)['whole_ast_delta_covered']
    assert len(manifest['inherited_v46_files_byte_identical']) == 15
    for name in manifest['inherited_v46_files_byte_identical']:
        assert (candidate / name).read_bytes() == (PRIOR / name).read_bytes()
    for key in ('model_switch_allowed', 'fallback_model_allowed', 'same_name_weight_replacement_allowed'):
        assert manifest[key] is False


def test_shared_symbol_conflict_stops_before_overwriting_current_qa_code():
    before = (PRIOR / 'ollama_proxy_server.py').read_text(encoding='utf-8')
    evidence = fragments()
    original = evidence['old']['with_public_detail_semantics']['source']
    conflict = original + '\n'  # Change function semantics, not only formatting.
    tree = ast.parse(original)
    node = tree.body[0]
    lines = original.splitlines(keepends=True)
    lines.insert(node.end_lineno, '    return {"unreviewed": True}\n')
    conflict = ''.join(lines)
    assert original in before
    with pytest.raises(AssertionError, match='Shared symbol conflict'):
        build_proxy(before.replace(original, conflict), evidence)


@pytest.mark.parametrize('tool', ['build_qa_shared_proxy_candidate.py', 'probe_qa_shared_proxy_delta_readonly.py'])
def test_optimized_python_cannot_disable_candidate_guards(tool):
    result = subprocess.run([sys.executable, '-O', '-X', 'utf8', str(ROOT / 'tools' / tool), '--help'],
        capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode != 0 and 'assertions enabled' in result.stderr


@pytest.mark.skipif(sys.version_info < (3, 12), reason='Native 3.11 has no generic type AST')
def test_nonempty_generic_semantics_are_never_discarded_for_hash_compatibility():
    with pytest.raises(AssertionError, match='Generic type parameters'):
        stable_ast_dump(ast.parse('def generic[T](value: T):\n    return value\n'))
