"""Exercise the actual frozen renderer; fixtures contain no production measurements."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_statistical_evidence as evidence
import qa_verified_facts
import qa_evidence_policy


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = module('renderer_contract_builder', ROOT / 'tools/build_qa_v31_renderer_contract_candidate.py')
BASE = ROOT / '.codex_runtime/qa-routing-v30/candidate-r2'
FROZEN_EVIDENCE = module('frozen_v30_evidence', BASE / 'qa_statistical_evidence.py')


@pytest.fixture(scope='module')
def renderers():
    raw = (BASE / 'ollama_proxy_server.py').read_bytes()
    def create(text, helper):
        nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)
            and n.name in {'deterministic_mcp_answer', 'try_load_json'}]
        scope = {'Any': Any, 'Mapping': Mapping, 'json': json,
            'qa_statistical_evidence': helper, 'qa_verified_facts': qa_verified_facts,
            'qa_evidence_policy': qa_evidence_policy, 'PROMPT_METRIC_ALIASES': {'P_top': '顶压'},
            'PROMPT_METRIC_UNIT_FALLBACKS': {'P_top': 'kPa'}}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual-renderer>', 'exec'), scope)
        return scope['deterministic_mcp_answer']
    return create(raw.decode(), FROZEN_EVIDENCE), create(builder.transform(raw).decode(), evidence)


def payload():
    begin, end = '2026-01-01T00:00:00', '2026-01-01T00:30:00'
    return {'ok': True, 'query_type': 'stats', 'variables': ['P_top'],
        'start_time': begin, 'end_time': end, 'items': [{'ok': True, 'requested_variable': 'P_top',
        'variable': {'variable_name': 'P_top', 'unit': ''},
        'source': {'profile': 'synthetic_fixture', 'read_policy': 'readonly'},
        'start_time': begin, 'end_time': end, 'statistics': {'count': 2, 'avg': 4, 'stddev': 0.1,
        'min': 3.9, 'max': 4.1, 'first': {'value': 3.9}, 'last': {'value': 4.1}}}]}


def render(renderers, data, args=None, before=False):
    return renderers[0 if before else 1]('query_gl02_sensors', json.dumps(data), args)


def test_frozen_renderer_reproduces_schema_valid_whitespace_false_rejection(renderers):
    data = payload()
    args = {'variables': [' P_top ']}
    assert 'STDDEV_POP' not in render(renderers, data, args, before=True)
    assert 'STDDEV_POP' in render(renderers, data, args)


@pytest.mark.parametrize('delimiter', [',', '，', '、', ';', '；', '\n'])
def test_packed_list_values_match_actual_sensor_parser(renderers, delimiter):
    data = payload()
    data['variables'].append('DP_total')
    args = {'variables': [f' P_top{delimiter}DP_total ', 'P_top']}
    text = render(renderers, data, args)
    assert 'STDDEV_POP' in text and '统计证据的对象' not in text
    nodes = [n for n in ast.parse((BASE / 'bf_data_mcp_server.py').read_text(encoding='utf-8')).body
        if isinstance(n, ast.FunctionDef) and n.name == 'parse_variables_arg']
    scope = {'Any': Any, 're': re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual-sensor-parser>', 'exec'), scope)
    assert evidence.sensor_variables(args['variables']) == scope['parse_variables_arg'](args['variables'], max_items=80)


def test_sensor_limit_is_80_not_generic_default_16(renderers):
    data = payload()
    data['variables'] += [f'synthetic_{i}' for i in range(79)]
    assert 'STDDEV_POP' in render(renderers, data, {'variables': data['variables']})
    data['variables'].append('synthetic_over_limit')
    assert 'STDDEV_POP' not in render(renderers, data, {'variables': data['variables']})


@pytest.mark.parametrize('variables', ['P_top', [True], [None], [], ['  '], ['DP_total'], ['P_top', 'DP_total']])
def test_invalid_or_disagreeing_argument_lists_cannot_bypass_binding(renderers, variables):
    assert 'STDDEV_POP' not in render(renderers, payload(), {'variables': variables})


@pytest.mark.parametrize('field,value', [('aliases', ['顶压']), ('legacy_variable_names', ['顶压']),
    ('short_name', '顶压'), ('point_id', '顶压'), ('tag_long_name', '顶压'), ('tag', '顶压')])
def test_exact_alias_inherits_canonical_unit_with_disclosure(renderers, field, value):
    data = payload()
    data['variables'] = ['顶压']
    item = data['items'][0]
    item['requested_variable'] = '顶压'
    item['variable'][field] = value
    assert '单位未登记' in render(renderers, data, before=True)
    text = render(renderers, data)
    assert '均值 4kPa' in text and '单位来源：已登记的GL02规范变量单位合同' in text
    item['variable']['unit'] = 'Pa'
    text = render(renderers, data)
    assert '均值 4Pa' in text and '均值 4000' not in text and '单位来源' not in text


def test_description_does_not_bind_unit_or_unlock_statistics(renderers):
    data = payload()
    data['variables'] = ['顶压']
    item = data['items'][0]
    item['requested_variable'] = '顶压'
    item['variable']['description'] = '顶压可能对应多个点'
    assert evidence.request_unit_contract(item['variable'], '顶压', {'P_top': 'kPa'})['unit'] == ''
    assert 'STDDEV_POP' not in render(renderers, data)


@pytest.mark.parametrize('field,value', [('variable', True), ('source', True), ('source', ['bad']),
    ('latest', []), ('statistics', True), ('first', True), ('last', ['bad'])])
def test_invalid_item_cannot_discard_neighboring_valid_facts(renderers, field, value):
    data = payload()
    broken = deepcopy(data['items'][0])
    if field in {'first', 'last'}:
        broken['statistics'][field] = value
    else:
        broken[field] = value
    data['items'].insert(0, broken)
    text = render(renderers, data)
    assert '工具返回字段结构无效' in text and text.count('总体标准差 STDDEV_POP') == 1


def test_original_container_exception_reproduced_before_fix(renderers):
    data = payload()
    data['items'][0]['source'] = True
    with pytest.raises(AttributeError):
        render(renderers, data, before=True)
    assert '工具返回字段结构无效' in render(renderers, data)


@pytest.mark.parametrize('items', [True, {'bad': 1}, None, 'bad'])
def test_invalid_list_returns_explicit_outcome_without_exception(renderers, items):
    data = payload()
    data['items'] = items
    assert '结果列表结构无效' in render(renderers, data)


def test_non_object_item_is_recorded_and_valid_neighbor_is_preserved(renderers):
    data = payload()
    data['items'].insert(0, True)
    text = render(renderers, data)
    assert '工具返回项结构无效' in text and 'STDDEV_POP' in text


@pytest.mark.parametrize('field,value', [('variable_name', 'DP_total'), ('read_policy', 'write'),
    ('end_time', '2026-01-01T01:00:00')])
def test_existing_fail_closed_evidence_checks_remain(renderers, field, value):
    data = payload()
    item = data['items'][0]
    if field == 'variable_name': item['variable'][field] = value
    elif field == 'read_policy': item['source'][field] = value
    else: item[field] = value
    assert 'STDDEV_POP' not in render(renderers, data)


def test_source_hash_drift_is_rejected():
    with pytest.raises(ValueError, match='Frozen V30'):
        builder.transform((BASE / 'ollama_proxy_server.py').read_bytes() + b'\n')


def test_frozen_candidate_preserves_mcp_and_all_model_completion_quality_modules():
    candidate = ROOT / '.codex_runtime/qa-routing-v31/candidate'
    for name in ('bf_data_mcp_server.py', 'qa_fixed_model_identity.py', 'qa_completion.py', 'qa_window_quality.py'):
        assert (candidate / name).read_bytes() == (BASE / name).read_bytes()
    assert hashlib.sha256((candidate / 'bf_data_mcp_server.py').read_bytes()).hexdigest() == builder.MCP_SHA
