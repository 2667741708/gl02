"""Reproduce recorded V24 deficiencies against the fixed-base production-derived proxy."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_statistical_evidence as evidence
import qa_verified_facts
import qa_evidence_policy

spec = importlib.util.spec_from_file_location('statistics_builder', ROOT / 'tools/build_qa_v28_statistics_candidate.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
BASE = ROOT / '.codex_runtime/qa-routing-v27/candidate/ollama_proxy_server.py'


def sample(**changes):
    result = {'ok': True, 'variable': {'variable_name': 'P_top', 'unit': 'kPa'},
        'start_time': '2026-01-01T00:00:00', 'end_time': '2026-01-01T00:30:00',
        'statistics': {'count': 31, 'avg': 4, 'stddev': 0.1, 'min': 3.8, 'max': 4.2,
            'delta': -0.00004, 'slope_per_min': -0.000002,
            'endpoint_direction': '下降', 'regression_direction': '下降', 'recent_direction': '下降',
            'recent_delta': -0.00003, 'trend': '下降',
            'first': {'value': 4, 'ts': '2026-01-01T00:00:00', 'quality': 'Held'},
            'last': {'value': 3.99996, 'ts': '2026-01-01T00:30:00', 'quality': 'Held'},
            'future_statistic': {'included': True}},
        'source': {'profile': 'synthetic_fixture', 'read_policy': 'readonly'}}
    result.update(changes)
    return result


def namespace(after=True):
    raw = BASE.read_bytes()
    text = builder.transform(raw).decode() if after else raw.decode()
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and
        n.name in builder.CHANGED | {'try_load_json'}]
    scope = {'Any': Any, 'Mapping': Mapping, 'json': json, 'datetime': datetime, 'timedelta': timedelta,
        'qa_statistical_evidence': evidence, 'qa_verified_facts': qa_verified_facts,
        'qa_evidence_policy': qa_evidence_policy,
        'PROMPT_METRIC_ALIASES': {'P_top': '顶压'}, 'PROMPT_METRIC_UNIT_FALLBACKS': {'P_top': 'kPa'}}
    exec(compile(ast.Module(body=nodes,type_ignores=[]), '<actual-proxy-statistics>', 'exec'), scope)
    return scope


def render(result, after=True, payload_changes=None, arguments=None):
    item = {'requested_variable': 'P_top', **result}
    payload = {'ok': True, 'query_type': 'stats', 'variables': ['P_top'],
        'start_time': '2026-01-01T00:00:00', 'end_time': '2026-01-01T00:30:00', 'items': [item]}
    payload.update(payload_changes or {})
    return namespace(after)['deterministic_mcp_answer']('query_gl02_sensors', json.dumps(payload), arguments)


def test_original_renderer_reproduces_zero_change_and_missing_quality_and_unit_lineage():
    result = sample(variable={'variable_name': 'P_top', 'unit': ''})
    before, after = render(result, False), render(result, True)
    assert '变化量 -0kPa' in before and '下降' in before
    assert '首样本质量' not in before and '单位来源' not in before
    assert '变化量 -4e-05kPa' in after
    assert '最近15分钟变化量 -3e-05kPa' in after
    assert '首样本质量 Held' in after and '窗口内各类质量数量和比例未核实' in after
    assert '不能据此确认新增实测或真实炉况稳定' in after
    assert '单位来源：已登记的GL02规范变量单位合同' in after


@pytest.mark.parametrize('value', [0.00004, -0.00004, 1e-15, -1e-15])
def test_nonzero_display_preserves_sign_and_magnitude(value):
    text = evidence.number(value)
    assert float(text) == pytest.approx(value, rel=1e-10, abs=0)
    assert float(text) != 0


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), '0.1', 10**400])
def test_invalid_numeric_types_and_nonfinite_values_do_not_become_facts(value):
    assert evidence.number(value) == '无法判断'


def test_negative_zero_does_not_display_false_negative_direction():
    assert evidence.number(-0.0) == '0'


def test_only_registered_exact_unit_fallback_and_no_conversion():
    assert evidence.unit_contract({'unit': 'Pa'}, 'P_top', {'P_top': 'kPa'})['unit'] == 'Pa'
    assert evidence.unit_contract({'unit': ''}, 'P_top', {'P_top': 'kPa'})['source'] == 'canonical_gl02_contract'
    missing = evidence.unit_contract({}, 'P_top_A', {'P_top': 'kPa'})
    assert missing['unit'] == '' and missing['source'] == 'missing'
    assert '不用于正式跨量比较' in missing['disclosure']


def test_quality_does_not_echo_untrusted_labels_or_invent_window_held_percentage():
    text = evidence.quality_context({'count': 31, 'first': {'quality': 'Held'}, 'last': {'quality': 'password=private'}})
    assert 'Held' in text and '末样本质量 未核实' in text
    assert 'password=' not in text and '100%' not in text
    assert '端点标记不代表整窗质量' in text


def test_summary_keeps_all_statistics_metadata_and_independent_copy():
    result = sample()
    original = deepcopy(result)
    summary = evidence.prefetch_summary('P_top', result['start_time'], result['end_time'], result)
    assert summary['evidence_valid']
    assert summary['stddev'] == 0.1 and summary['unit'] == 'kPa'
    assert summary['statistics'] == result['statistics']
    assert summary['variable_metadata'] == result['variable']
    summary['statistics']['future_statistic']['included'] = False
    assert result == original


@pytest.mark.parametrize('bad', ['zero_count', 'boolean_count', 'nan_count', 'noninteger_count',
    'wrong_object', 'wrong_window', 'missing_source', 'typed_source', 'write_source', 'missing_values', 'not_ok'])
def test_summary_completeness_rejects_invalid_evidence(bad):
    result = sample()
    if bad == 'zero_count': result['statistics']['count'] = 0
    if bad == 'boolean_count': result['statistics']['count'] = True
    if bad == 'nan_count': result['statistics']['count'] = float('nan')
    if bad == 'noninteger_count': result['statistics']['count'] = 2.5
    if bad == 'wrong_object': result['variable']['variable_name'] = 'other'
    if bad == 'wrong_window': result['end_time'] = '2026-01-01T01:00:00'
    if bad == 'missing_source': result['source'] = {}
    if bad == 'typed_source': result['source']['profile'] = True
    if bad == 'write_source': result['source']['read_policy'] = 'write'
    if bad == 'missing_values': result['statistics'].update(avg=None,min=None,max=None,first={},last={})
    if bad == 'not_ok': result['ok'] = False
    summary = evidence.prefetch_summary('P_top', '2026-01-01T00:00:00', '2026-01-01T00:30:00', result)
    assert not summary['evidence_valid'] and not evidence.summary_has_data(summary)


def test_zero_measured_values_are_real_evidence_and_missing_unit_is_not_repaired():
    result = sample(variable={'variable_name':'P_top','unit':''})
    result['statistics'].update(avg=0,min=0,max=0)
    summary = evidence.prefetch_summary('P_top', result['start_time'], result['end_time'], result)
    assert summary['evidence_valid'] and summary['avg'] == 0
    assert summary['unit'] == ''  # Source evidence and inherited rendering units stay distinct.


def test_old_prefetch_completeness_reproduces_empty_stats_false_positive():
    pack = {'used': True, 'kind':'statistics','variable':'P_top', 'summary':{
        'start_time':'2026-01-01T00:00:00','end_time':'2026-01-01T00:30:00',
        'count':0,'avg':None,'min':None,'max':None,'first':{},'last':{}}}
    assert namespace(False)['qa_mcp_prefetch_is_complete'](pack)
    assert not namespace(True)['qa_mcp_prefetch_is_complete'](pack)


def test_actual_prefetch_preserves_stddev_unit_and_future_statistics():
    def run(after):
        scope = namespace(after)
        scope.update(QA_MCP_PREFETCH_ENABLED=True, QA_ANSWER_ROUTE_CODE='code_generation',
            QA_ANSWER_ROUTE_ANALYSIS='analysis_required', qa_answer_route=lambda _: 'analysis_required',
            qa_time_window_plan=SimpleNamespace(temporal_intent=lambda _:False,explicit_clock_intent=lambda _:False),
            qa_entity_resolution=SimpleNamespace(resolve_requested_entities=lambda _: {'unresolved':[]}),
            qa_mcp_chart_plan=lambda _:None, qa_mcp_direct_tool_intent=lambda _:False,
            qa_mcp_analysis_variables=lambda _:['P_top'],qa_mcp_duration_minutes=lambda _:30,
            normalize_spoken_question=str,parse_mcp_ts=lambda value:datetime.fromisoformat(value) if value else None)
        def query(variable,begin,end,**kwargs):
            return sample(start_time=begin,end_time=end)
        scope['load_mcp_data_module']=lambda:SimpleNamespace(
            get_latest_gl02_value=lambda *a,**kw:{'latest':{'ts':'2026-01-01T00:30:00'}},
            query_gl02_statistics=query)
        return scope['qa_mcp_prefetch']('看看顶压半小时变化')
    before,after=run(False),run(True)
    assert 'stddev' not in before['summary'] and 'unit' not in before['summary']
    assert after['summary']['stddev']==0.1 and after['summary']['unit']=='kPa'
    assert after['summary']['statistics']['future_statistic']=={'included':True}
    assert 'Held' in after['context_text'] and 'stddev' in after['context_text']


def test_actual_prefetch_forbidden_live_query_does_not_load_data_module():
    scope=namespace()
    scope['load_mcp_data_module']=lambda:pytest.fail('No database access')
    assert not scope['qa_mcp_prefetch']('不要查询现场数据，只用我提供的数据')['used']


def test_single_prefetch_cannot_reuse_another_object_summary():
    result=sample()
    summary=evidence.prefetch_summary('P_top',result['start_time'],result['end_time'],result)
    assert evidence.summary_has_data(summary)
    pack={'used':True,'kind':'statistics','variable':'DP_total','summary':summary}
    assert not namespace()['qa_mcp_prefetch_is_complete'](pack)


@pytest.mark.parametrize('count', [0, None, True, 2.5, float('nan')])
def test_renderer_does_not_present_empty_or_malformed_count_as_completed_statistics(count):
    result=sample()
    result['statistics']['count']=count
    text=render(result)
    assert '无有效样本或样本数量未核实' in text
    assert 'STDDEV_POP' not in text and 'CV =' not in text


def test_renderer_does_not_invent_source_or_readonly_field():
    text=render(sample(source={}))
    assert '来源未核实' in text and '只读策略字段未提供' in text
    assert 'gl02-data / readonly' not in text
    assert 'STDDEV_POP' not in text and 'CV =' not in text and '全窗口趋势' not in text


@pytest.mark.parametrize('bad', ['wrong_object', 'wrong_window', 'write_source', 'typed_source',
    'missing_variables', 'wrong_variables', 'missing_window', 'argument_window', 'argument_variables'])
def test_direct_renderer_cannot_bypass_object_source_or_requested_window(bad):
    result, changes, args = sample(), {}, None
    if bad == 'wrong_object': result['variable']['variable_name'] = 'DP_total'
    if bad == 'wrong_window': result['end_time'] = '2026-01-01T01:00:00'
    if bad == 'write_source': result['source']['read_policy'] = 'write'
    if bad == 'typed_source': result['source']['profile'] = True
    if bad == 'missing_variables': changes['variables'] = None
    if bad == 'wrong_variables': changes['variables'] = ['DP_total']
    if bad == 'missing_window': changes['start_time'] = None
    if bad == 'argument_window': args = {'end_time': '2026-01-01T01:00:00'}
    if bad == 'argument_variables': args = {'variables': ['DP_total']}
    text = render(result, payload_changes=changes, arguments=args)
    assert '统计证据的对象、来源或时间窗未核实' in text
    assert 'STDDEV_POP' not in text and 'CV =' not in text and '全窗口趋势' not in text
    assert '每分钟斜率' not in text and '变化量' not in text


@pytest.mark.parametrize('field,value', [('aliases', ['顶压']), ('legacy_variable_names', ['顶压']),
    ('short_name', '顶压'), ('point_id', '顶压'), ('tag_long_name', '顶压'), ('tag', '顶压')])
def test_direct_renderer_accepts_only_explicit_metadata_alias_bindings(field, value):
    result = sample()
    result['requested_variable'] = '顶压'
    result['variable'][field] = value
    text = render(result, payload_changes={'variables': ['顶压']})
    assert 'STDDEV_POP' in text and '统计证据的对象' not in text


def test_direct_renderer_does_not_guess_aliases_from_descriptions():
    result = sample(requested_variable='顶压')
    result['variable']['description'] = '顶压可能对应多个点'
    text = render(result, payload_changes={'variables': ['顶压']})
    assert '统计证据的对象、来源或时间窗未核实' in text and 'STDDEV_POP' not in text
