"""Synthetic integration checks for the actual chart tool and proxy batch."""
import ast
import asyncio
import copy
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_tool_fallback as fallback

NAMES = [f'P_static_{height}_{position}' for height in ('lower', 'middle', 'upper') for position in 'ABCDEF']
ARGS = {'variables': NAMES, 'start_time': '2026-09-16T20:00:00+08:00', 'end_time': '2026-09-16T21:00:00+08:00'}


def chart_payload():
    return {'ok': True, 'tool': 'plot_gl02_trends', **ARGS,
            'requested_variables': NAMES, 'image_url': '/data/mcp_charts/fixture_chart.png',
            'series': [{'requested_variable': name, 'variable': {'variable_name': name, 'unit': 'kPa'},
                        'summary': {'count': 2, 'last': {'value': 10.0 + index, 'ts': '2026-09-16T20:59:00+08:00', 'quality': 'fixture_good'}},
                        'source': {'profile': 'synthetic_fixture', 'read_policy': 'readonly', 'private_padding': 'fixture' * 300}}
                       for index, name in enumerate(NAMES)]}


def load_functions(path, names, scope):
    nodes = [n for n in ast.parse(path.read_bytes()).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    for node in nodes:
        node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<actual-reviewed-source>', 'exec'), scope)
    return scope


def proxy_scope():
    return load_functions(ROOT / '.codex_runtime/qa-routing-v26/candidate/ollama_proxy_server.py',
        ['mcp_result_to_text', 'truncate_tool_text', 'try_load_json', 'deterministic_mcp_answer', 'qa_mcp_execute_parallel_batch'],
        {'json': json, 'asyncio': asyncio, 'QA_MCP_MAX_RESULT_CHARS': 12000, 'QA_MCP_MAX_PARALLEL_TOOL_CALLS': 2,
         'QA_MCP_PARALLEL_TOOL_CALLS': False, 'qa_tool_fallback': fallback, 'PROMPT_METRIC_ALIASES': {}})


def test_actual_proxy_delivers_all_eighteen_points_and_image():
    payload = chart_payload()
    text = json.dumps(payload)
    assert len(text) > 12000
    answer = proxy_scope()['deterministic_mcp_answer']('plot_gl02_trends', text, ARGS)
    assert '可核验 18 个' in answer and '![GL02趋势图](/data/mcp_charts/fixture_chart.png)' in answer
    assert all(name in answer for name in NAMES) and 'fixture_good' in answer
    assert '当前/末值' not in answer and 'private_padding' not in answer


def test_lifecycle_fallback_retains_successful_chart_and_declares_remaining_analysis():
    answer = fallback.summarize([{'name': 'plot_gl02_trends', 'arguments': ARGS, 'result_text': json.dumps(chart_payload())}])
    assert '后续分析未完成' in answer and '可核验 18 个' in answer and '![GL02趋势图]' in answer
    assert '没有可展示' not in answer


def test_sixteen_point_result_is_partial_against_eighteen_point_request():
    payload = chart_payload()
    payload['variables'] = NAMES[:16]
    payload['requested_variables'] = NAMES[:16]
    payload['series'] = payload['series'][:16]
    answer = fallback.trend_chart_answer(payload, ARGS)
    assert '请求 18 个测点，可核验 16 个' in answer
    assert all(name in answer.split('未完成测点：')[1] for name in NAMES[-2:])
    assert '不能视为全部测点已回答' in answer


@pytest.mark.parametrize('change', ['unsafe_url', 'source', 'timestamp', 'nan', 'object', 'count', 'duplicate', 'missing_unit', 'time_mismatch'])
def test_chart_validation_rejects_invalid_evidence_and_missing_units(change):
    payload = chart_payload()
    item = payload['series'][0]
    if change == 'unsafe_url': payload['image_url'] = '/data/mcp_charts/../../private.png'
    if change == 'source': item['source']['read_policy'] = 'write'
    if change == 'timestamp': item['summary']['last']['ts'] = '2026-09-17T20:59:00+08:00'
    if change == 'nan': item['summary']['last']['value'] = float('nan')
    if change == 'object': item['variable']['variable_name'] = 'P_other'
    if change == 'count': item['summary']['count'] = True
    if change == 'duplicate': payload['series'].append(copy.deepcopy(item))
    if change == 'missing_unit': item['variable']['unit'] = None
    if change == 'time_mismatch': payload['end_time'] = '2026-09-16T22:00:00+08:00'
    answer = fallback.trend_chart_answer(payload, ARGS)
    if change == 'unsafe_url': assert '![' not in answer and '图片地址未核实' in answer
    elif change == 'missing_unit': assert '单位未核实' in answer
    elif change == 'time_mismatch': assert '与请求不一致' in answer and '![' not in answer
    else: assert '可核验 17 个' in answer and NAMES[0] in answer.split('未完成测点：')[1]


def test_bounded_model_projection_is_valid_json_without_corrupting_full_evidence():
    text = json.dumps(chart_payload())
    before = text
    projection = fallback.model_result_text('plot_gl02_trends', text, ARGS, 12000)
    assert len(projection) <= 12000 and json.loads(projection)['bounded_projection']
    assert text == before and len(json.loads(text)['series']) == 18


def test_actual_parallel_batch_preserves_complete_typed_json():
    scope = proxy_scope()
    async def call_tool(*_):
        return SimpleNamespace(structuredContent=chart_payload())
    scope.update({'qa_mcp_tool_cache_get': lambda *_: None, 'qa_mcp_tool_cache_put': lambda *_: None,
                  'qa_request_control': SimpleNamespace(call_tool=call_tool),
                  'validate_tool_call': lambda *_: {'ok': True, 'policy': 'readonly'},
                  'compact_tool_result_for_event': lambda text: {'projection_only': True}})
    rows = asyncio.run(scope['qa_mcp_execute_parallel_batch'](
        tool_calls=[{'name': 'plot_gl02_trends', 'arguments': ARGS}], session=object(), tool_schemas={},
        tool_servers={}, policy_limits=object(), server_locks={}, tool_timeout_seconds=lambda: 1,
        round_number=1, planner_catalog_size=1))
    assert len(rows[0]['result_text']) > 12000
    assert len(json.loads(rows[0]['result_text'])['series']) == 18
    assert rows[0]['trace']['arguments'] == ARGS


def test_actual_tool_keeps_all_points_and_records_missing_coverage(tmp_path, monkeypatch):
    monkeypatch.setenv('BF_MCP_PLOT_WORKER', '1')
    calls = []
    def history(name, *_, **__):
        calls.append(name)
        data = [] if name == NAMES[-1] else [{'ts': '2026-09-16T20:59:00', 'value': 10, 'quality': 'fixture_good'}]
        return {'ok': True, 'data': data, 'variable': {'variable_name': name, 'unit': 'kPa'},
                'source': {'profile': 'fixture', 'read_policy': 'readonly'}}
    scope = load_functions(ROOT / '.codex_runtime/qa-routing-v26/candidate/bf_data_mcp_server.py', ['parse_variables_arg', 'plot_gl02_trends'],
        {'re': re, 'os': os, 'Path': Path, 'json': json, 'query_gl02_history': history,
         'validate_time_range': lambda a, b: (a, b), 'normalize_chart_scale': lambda x: x,
         'normalize_chart_type': lambda x: x, 'normalize_chart_theme': lambda x: x,
         'clamp_limit': lambda value, **_: value, 'MAX_HISTORY_LIMIT': 5000,
         'series_summary': lambda rows: {'count': len(rows), 'last': rows[-1] if rows else None},
         'render_trend_chart': lambda *_, **__: {'path': str(tmp_path / 'fixture.png'), 'url': '/data/mcp_charts/fixture.png', 'chart_type_used': 'small_multiples'}})
    payload = scope['plot_gl02_trends'](**ARGS, chart_type='small_multiples')
    assert calls == NAMES and payload['requested_variables'] == NAMES
    assert payload['covered_variables'] == NAMES[:-1] and payload['missing_variables'] == NAMES[-1:]
    with pytest.raises(ValueError, match='未静默截断'):
        scope['parse_variables_arg'](NAMES)  # The separate 16-point tool refuses, rather than dropping two.
    assert scope['parse_variables_arg'](NAMES, max_items=24) == NAMES
    calls.clear()
    with pytest.raises(ValueError, match='未静默截断'):
        scope['plot_gl02_trends']([f'P_fixture_{index}' for index in range(25)], ARGS['start_time'], ARGS['end_time'])
    assert calls == []
