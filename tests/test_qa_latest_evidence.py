"""Recorded latest-read gaps and fail-closed defects, using synthetic actual-call seams."""
import ast
from copy import deepcopy
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_statistical_evidence as evidence
import qa_verified_facts as facts
import qa_evidence_policy
import qa_completion


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = load('latest_evidence_builder', ROOT / 'tools/build_qa_v32_latest_evidence_candidate.py')
BASE = ROOT / '.codex_runtime/qa-routing-v31/candidate'
OLD_FACTS = load('old_latest_facts', ROOT / '.codex_runtime/qa-routing-v32/baseline/qa_verified_facts.py')
OLD_EVIDENCE = load('old_v31_evidence', BASE / 'qa_statistical_evidence.py')
FALLBACKS = {'P_top': 'kPa'}


def item(name='P_top'):
    return {'ok': True, 'requested_variable': name, 'variable': {'variable_name': name, 'unit': 'kPa'},
        'latest': {'value': 4, 'ts': '2026-01-01T00:00:00', 'quality': 'Good',
            'collected_at': '2026-01-01T00:00:01'},
        'source': {'profile': 'synthetic_fixture', 'read_policy': 'readonly'}}


def payload(result=None):
    result = result or item()
    return {'ok': True, 'query_type': 'latest', 'variables': [result['requested_variable']], 'items': [result]}


def prefetch(result, module=facts):
    name = result['variable']['variable_name']
    return module.prefetch_outcome({'used': True, 'kind': 'latest', 'variable': name, 'latest': result},
        {'intents': ['live_data'], 'entities': [name]})


@pytest.fixture(scope='module')
def renderers():
    raw = (BASE / 'ollama_proxy_server.py').read_bytes()
    def create(text, helper):
        nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)
            and n.name in {'deterministic_mcp_answer', 'try_load_json'}]
        scope = {'Any': Any, 'Mapping': Mapping, 'json': json, 'qa_statistical_evidence': helper,
            'qa_verified_facts': facts, 'qa_evidence_policy': qa_evidence_policy,
            'PROMPT_METRIC_ALIASES': {'P_top': '顶压'}, 'PROMPT_METRIC_UNIT_FALLBACKS': FALLBACKS}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual-latest-renderer>', 'exec'), scope)
        return scope['deterministic_mcp_answer']
    return create(raw.decode(), OLD_EVIDENCE), create(builder.transform(raw).decode(), evidence)


def render(renderers, data, arguments=None, before=False):
    return renderers[0 if before else 1]('query_gl02_sensors', json.dumps(data), arguments)


def completion(data, arguments=None):
    return evidence.sensor_latest_completion(data, arguments, FALLBACKS)


def test_original_latest_renderer_reproduces_wrong_object_value_leak(renderers):
    data = payload()
    data['items'][0]['variable']['variable_name'] = 'DP_total'
    assert '4kPa' in render(renderers, data, before=True)
    assert '4kPa' not in render(renderers, data) and '未输出该项正式事实' in render(renderers, data)
    assert completion(data)['missing_objects'] == ['P_top']


@pytest.mark.parametrize('field,value', [('value', True), ('value', float('nan')), ('value', float('inf')),
    ('value', 10**400), ('value', '4'), ('ts', None), ('ts', 'unknown'), ('ts', '2026-01-01')])
def test_invalid_value_or_timestamp_is_not_an_observed_fact(renderers, field, value):
    data = payload()
    data['items'][0]['latest'][field] = value
    text = render(renderers, data)
    assert '最近一次已保存值' not in text and '未输出该项正式事实' in text
    assert completion(data)['complete'] is False
    assert prefetch(data['items'][0])['completion']['missing_objects'] == ['P_top']


@pytest.mark.parametrize('source', [{}, {'profile': True}, {'profile': ['bad']},
    {'profile': 'synthetic_fixture', 'read_policy': 'write'}, True])
def test_source_type_and_policy_fail_closed_without_crashing(renderers, source):
    data = payload()
    data['items'][0]['source'] = source
    assert '最近一次已保存值' not in render(renderers, data)
    assert prefetch(data['items'][0])['grounding_status'] == 'no_verified_evidence'


def test_old_prefetch_accepts_boolean_source_but_new_prefetch_rejects():
    result = item()
    result['source']['profile'] = True
    assert OLD_FACTS.latest_item('P_top', result).source == 'True'
    assert facts.latest_item('P_top', result) is None


@pytest.mark.parametrize('args', [{'variables': ['DP_total']}, {'variables': 'P_top'},
    {'query_type': 'statistics'}, {'variables': [True]}])
def test_argument_contract_cannot_be_replaced_by_returned_payload(renderers, args):
    data = payload()
    assert '最近一次已保存值' not in render(renderers, data, args)
    assert completion(data, args)['complete'] is False


def test_schema_valid_whitespace_and_exact_alias_remain_supported(renderers):
    result = item()
    result['requested_variable'] = '顶压'
    result['variable'].update(aliases=['顶压'], unit='')
    data = payload(result)
    text = render(renderers, data, {'variables': [' 顶压 ']})
    assert '最近一次已保存值 4kPa' in text and '单位来源' in text
    assert completion(data, {'variables': [' 顶压 ']})['complete'] is True


def test_small_nonzero_latest_value_is_not_rounded_to_zero(renderers):
    result = item()
    result['latest']['value'] = 0.00004
    assert '4e-05kPa' in render(renderers, payload(result))
    assert '4e-05kPa' in prefetch(result)['answer']


@pytest.mark.parametrize('field', ['unit', 'quality', 'collected_at', 'read_policy'])
def test_missing_metadata_preserves_value_and_marks_partial(renderers, field):
    result = item('synthetic_unregistered')
    parent = result['variable'] if field == 'unit' else result['source'] if field == 'read_policy' else result['latest']
    parent.pop(field)
    data = payload(result)
    text = render(renderers, data)
    assert '最近一次已保存值 4' in text and completion(data)['complete'] is False
    out = prefetch(result)
    assert '最近一次已保存值 4' in out['answer'] and out['completion']['terminal_state'] == 'partial'
    assert out['model_request_count'] == 0 and out['completion']['missing_evidence_fields']
    if field == 'read_policy':
        assert ' / readonly' not in out['answer'] and '只读策略字段未提供' in out['answer']


@pytest.mark.parametrize('quality', ['Held', 'Bad', 'Uncertain', 192, True, 'arbitrary_private_quality'])
def test_quality_is_disclosed_without_normality_or_arbitrary_label_echo(renderers, quality):
    result = item()
    result['latest']['quality'] = quality
    text = render(renderers, payload(result))
    assert '质量' in text and '不能确认此刻无异常' in text
    if quality == 'Held': assert '不能证明新增实测或真实炉况稳定' in text
    if quality == 192: assert '原始标记 192（释义未核实）' in text
    assert 'arbitrary_private_quality' not in text


def test_pspace_read_marker_is_not_labelled_physical_collection(renderers):
    result = item()
    result['source'].update(profile='pspace_243', engine='pspace_python_api')
    text = render(renderers, payload(result))
    assert '接口读取标记时间 2026-01-01T00:00:01' in text
    assert '标记时间不等于原传感器物理采样时刻' in text


def test_date_only_collection_is_missing_and_not_replaced_from_data_time(renderers):
    result = item()
    result['latest']['collected_at'] = '2026-01-01'
    text = render(renderers, payload(result))
    assert '工具采集标记时间 未核实' in text
    assert 'collection_time' in completion(payload(result))['missing_evidence_fields']['P_top']


def derived():
    result = item('T_top')
    result['variable']['unit'] = '℃'
    result['source']['derived'] = True
    result['latest'].update(value=2.5, quality='DERIVED_AVERAGE', components=[
        {'component': f'T_top_{name}', 'value': value, 'ts': result['latest']['ts'], 'quality': 'Good'}
        for name, value in zip('ABCD', [1, 2, 3, 4])])
    return result


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'mixed_time', 'wrong_latest_time',
    'wrong_mean', 'nonfinite', 'typed_container', 'typed_row'])
def test_derived_average_cannot_claim_complete_aligned_components(renderers, defect):
    result = derived()
    rows = result['latest']['components']
    if defect == 'missing': rows.pop()
    elif defect == 'duplicate': rows[3] = deepcopy(rows[2])
    elif defect == 'mixed_time': rows[0]['ts'] = '2026-01-01T00:01:00'
    elif defect == 'wrong_latest_time': result['latest']['ts'] = '2026-01-01T00:01:00'
    elif defect == 'wrong_mean': result['latest']['value'] = 9
    elif defect == 'nonfinite': rows[0]['value'] = float('nan')
    elif defect == 'typed_container': result['latest']['components'] = True
    else: rows[0] = None
    text = render(renderers, payload(result))
    assert '返回值不能当作同一时刻A-D完整均值' in text
    assert completion(payload(result))['complete'] is False
    assert 'derived_component_alignment' in prefetch(result)['completion']['missing_evidence_fields']['T_top']


def test_aligned_components_can_be_recomputed_but_do_not_invent_collection_time(renderers):
    result = derived()
    assert sum(row['value'] for row in result['latest']['components']) / 4 == result['latest']['value']
    assert 'A-D四组件同一时刻且均值复算一致' in render(renderers, payload(result))
    result['latest'].pop('collected_at')
    text = render(renderers, payload(result))
    assert '工具采集标记时间 未核实' in text and completion(payload(result))['complete'] is False


def test_duplicate_or_failed_object_is_partial_and_valid_neighbor_survives(renderers):
    data = payload()
    bad = item('DP_total')
    bad['source'] = {}
    data['variables'].append('DP_total')
    data['items'].append(bad)
    text = render(renderers, data)
    assert '最近一次已保存值 4kPa' in text
    assert completion(data)['covered_objects'] == ['P_top'] and completion(data)['missing_objects'] == ['DP_total']
    data['items'].append(deepcopy(data['items'][0]))
    assert completion(data)['covered_objects'] == []


def test_actual_tool_loop_return_keeps_latest_partial_and_does_not_complete_analysis():
    text = builder.transform((BASE / 'ollama_proxy_server.py').read_bytes()).decode()
    tree = ast.parse(text)
    loop = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'qa_mcp_tool_loop_async')
    returns = [n.value for n in ast.walk(loop) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    result = next(node for node in returns if any(isinstance(v, ast.Name) and v.id == 'direct_answer' for v in node.values))
    expression = next(v for k, v in zip(result.keys, result.values) if isinstance(k, ast.Constant) and k.value == 'completion')
    code = compile(ast.Expression(body=expression), '<actual-completion-exit>', 'eval')
    latest = completion(payload())
    scope = {'comparison': None, 'qa_completion': qa_completion, 'latest_completion': latest,
        'final_answer_route': 'grounded_fact_only'}
    assert eval(code, scope)['complete'] is True
    scope['final_answer_route'] = 'mcp_grounded_analysis'
    assert eval(code, scope)['complete'] is None  # Latest facts do not prove requested analysis complete.
    latest['complete'] = False
    latest['terminal_state'] = 'partial'
    assert eval(code, scope)['complete'] is False


def test_finite_overflow_is_safe_for_existing_statistics_and_no_mcp_requery():
    assert not facts.finite(10**400)
    assert facts.cv_contract({'avg': 10**400, 'stddev': 1}, 'kPa')['value'] is None
    assert prefetch(item())['model_request_count'] == 0


def test_existing_nonlatest_completion_and_frozen_modules_are_preserved():
    assert completion({'query_type': 'statistics'}) is None
    candidate = ROOT / '.codex_runtime/qa-routing-v32' / builder.TARGET_NAME
    for name in ('bf_data_mcp_server.py', 'qa_completion.py', 'qa_window_quality.py', 'qa_fixed_model_identity.py'):
        assert (candidate / name).read_bytes() == (BASE / name).read_bytes()
