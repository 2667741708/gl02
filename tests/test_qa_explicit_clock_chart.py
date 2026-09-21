"""Historical request fidelity and actual production-derived routing seams."""
import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_entity_resolution as entities
import qa_evidence_policy as policy
import qa_task_plan as planner
import qa_time_window_plan as temporal

NOW = datetime(2026, 9, 17, 10, 0, tzinfo=temporal.LOCAL_TZ)


@pytest.mark.parametrize('question,start,end', [
    ('查一下顶压昨晚八点到九点的数据', '2026-09-16T20:00:00+08:00', '2026-09-16T21:00:00+08:00'),
    ('查顶压昨天8:00至9:00', '2026-09-16T08:00:00+08:00', '2026-09-16T09:00:00+08:00'),
    ('查看顶压前天二十三点半到凌晨一点一刻', '2026-09-15T23:30:00+08:00', '2026-09-16T01:15:00+08:00'),
    ('画出顶压2026年9月16日晚上十一点到一点', '2026-09-16T23:00:00+08:00', '2026-09-17T01:00:00+08:00'),
    ('统计顶压9月16日上午八点三刻至九点半', '2026-09-16T08:45:00+08:00', '2026-09-16T09:30:00+08:00'),
    ('查看顶压2026-09-16 20:00到21:00', '2026-09-16T20:00:00+08:00', '2026-09-16T21:00:00+08:00'),
])
def test_user_clock_window_retained_across_dates_and_midnight(question, start, end):
    result = temporal.parse_explicit_clock_range(question, anchor=NOW.astimezone(timezone.utc))
    assert result['ok'] and result['start'].isoformat() == start and result['end'].isoformat() == end


@pytest.mark.parametrize('question', [
    '查顶压昨晚八点', '查顶压八点到八点', '查顶压25:00到26:00',
    '查顶压昨天8:60至9:00', '查顶压2026年13月1日8:00至9:00',
    '查顶压今天20:00到21:00', '查顶压昨天八点到今天九点',
    '查顶压昨天8:00:01至9:00:02', '查顶压8:到9:',
    '查顶压昨天1000点到九点', '查顶压昨天八点到九点十分半',
    '查顶压昨天上午十三点到十四点',
])
def test_invalid_or_incomplete_clock_clarifies_instead_of_querying_last_hour(question):
    result = temporal.parse_explicit_clock_range(question, anchor=NOW)
    assert result and not result['ok'] and '不会改查最近一小时' in result['blocked_reason']


def test_decimal_height_is_not_a_date_or_clock():
    assert temporal.parse_explicit_clock_range('把20.35米A到F静压力最近两小时画出来', anchor=NOW) is None
    assert temporal.parse_explicit_clock_range('解释“顶压八点到九点”这句话', anchor=NOW) is None


def test_three_heights_keep_all_eighteen_registered_positions():
    result = entities.resolve_requested_entities('把三个高度A到F静压力最近两小时分别画出来。')
    expected = [f'P_static_{height}_{letter}' for height in ('lower', 'middle', 'upper') for letter in 'ABCDEF']
    assert result['variables'] == expected and not result['unresolved']
    descending = entities.resolve_requested_entities('查23.488米静压力C至A最近半小时')
    assert descending['variables'] == ['P_static_middle_C', 'P_static_middle_B', 'P_static_middle_A']
    assert entities.resolve_requested_entities('查静压力A至F')['unresolved']
    assert entities.resolve_requested_entities('画三个高度A到H静压力')['unresolved']


@pytest.mark.parametrize('question', ['查一下顶压昨晚八点到九点的数据', '把三个高度A到F静压力最近两小时分别画出来。'])
def test_original_user_actions_enable_only_reviewed_live_reads(question):
    plan = planner.build_task_plan(question)
    assert 'live_readonly_data' in plan['allowed_sources']
    assert [name for name in ['query_gl02_sensors', 'plot_gl02_trends', 'delete_sensor'] if planner.tool_allowed(name, plan)] == ['query_gl02_sensors', 'plot_gl02_trends']


@pytest.mark.parametrize('question', ['不要查现场数据，分析顶压昨晚八点到九点', '只用我给的数据画顶压曲线', '解释“查一下顶压昨晚八点到九点”的含义'])
def test_no_live_and_quoted_examples_remain_no_tool(question):
    assert 'live_readonly_data' not in planner.build_task_plan(question)['allowed_sources']


def proxy_scope():
    path = ROOT / '.codex_runtime/qa-routing-v25/candidate/ollama_proxy_server.py'
    assert path.exists(), 'V25 production-derived candidate is required for integration'
    names = {'qa_mcp_explicit_time_range', 'qa_mcp_prefetch', 'qa_mcp_chart_plan', 'qa_mcp_standard_analysis_plan',
             'qa_mcp_sensor_query_plan', 'qa_mcp_body_temperature_statistics_plan', 'qa_mcp_preflight_answer', 'deterministic_mcp_answer'}
    nodes = [n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n, ast.FunctionDef) and n.name in names]
    def variables(q):
        result = entities.resolve_requested_entities(q)['variables']
        return result or (['T_body_L10_D'] if '10层D' in q else ['P_top'])
    class FrozenClock:
        @staticmethod
        def now(tz=None):
            return NOW.astimezone(tz or temporal.LOCAL_TZ)
    # Execute actual candidate functions; only time, catalog and downstream
    # effects are controlled. A prefetch effect must never happen in these tests.
    scope = {'Any': object, 'datetime': FrozenClock, 'timedelta': timedelta, 'LOCAL_TZ': temporal.LOCAL_TZ,
             'json': json, 'try_load_json': json.loads, 're': __import__('re'), 'qa_entity_resolution': entities, 'qa_evidence_policy': policy,
             'qa_time_window_plan': temporal, 'qa_mcp_variables': variables, 'qa_mcp_analysis_variables': variables,
             'qa_answer_route': lambda q: 'analysis' if '统计' in q or '平均' in q else 'direct',
             'QA_ANSWER_ROUTE_CODE': 'code_generation', 'QA_ANSWER_ROUTE_ANALYSIS': 'analysis',
             'QA_MCP_PREFETCH_ENABLED': True, 'QA_MCP_STANDARD_VARIABLES': ['P_top'],
             'qa_mcp_duration_minutes': lambda q: 120 if '两小时' in q else None,
             'qa_mcp_current_user_text': lambda q: q.split('\n[服务端对话状态：', 1)[0],
             'normalize_spoken_question': lambda q: q, 'qa_mcp_body_temperature_variables': lambda q: ['T_body_L10_D'] if '10层D' in q else [],
             'qa_mcp_catalog_variables': lambda q: [], 'PROMPT_METRIC_UNIT_FALLBACKS': {}, 'metric_label': lambda x: x}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<production-derived-clock-seams>', 'exec'), scope)
    return scope


def test_actual_chart_plan_keeps_eighteen_objects_and_two_hours_without_prefetch():
    scope = proxy_scope()
    q = '把三个高度A到F静压力最近两小时分别画出来。'
    plan = scope['qa_mcp_chart_plan'](q)
    assert plan['tool'] == 'plot_gl02_trends' and plan['arguments']['chart_type'] == 'small_multiples'
    assert len(plan['arguments']['variables']) == 18
    assert plan['arguments']['start_time'] == '2026-09-17T08:00:00+08:00'
    assert plan['arguments']['end_time'] == '2026-09-17T10:00:00+08:00'
    assert scope['qa_mcp_prefetch'](q) == {'used': False, 'reason': 'requires_chart_workflow'}


def test_actual_historical_query_overrides_stale_latest_suffix_and_never_prefetches():
    scope = proxy_scope()
    q = '查一下顶压昨晚八点到九点的数据\n[服务端对话状态：查询意图：latest]'
    plan = scope['qa_mcp_sensor_query_plan'](q)
    assert plan['arguments']['query_type'] == 'history'
    assert plan['arguments']['start_time'].endswith('T20:00:00+08:00')
    assert plan['arguments']['end_time'].endswith('T21:00:00+08:00')
    assert plan['arguments']['max_points_per_variable'] == 5000
    assert scope['qa_mcp_prefetch'](q)['reason'] == 'requires_explicit_clock_workflow'


@pytest.mark.parametrize('function', ['qa_mcp_sensor_query_plan', 'qa_mcp_chart_plan', 'qa_mcp_standard_analysis_plan', 'qa_mcp_body_temperature_statistics_plan'])
def test_actual_query_builders_do_not_fallback_for_invalid_clock(function):
    scope = proxy_scope()
    q = '查询10层D炉体温度和顶压昨天25:00到26:00平均值关系图'
    assert scope[function](q) is None
    assert '未调用任何数据工具' in scope['qa_mcp_preflight_answer'](q)


def history_payload():
    return {'ok': True, 'query_type': 'history', 'start_time': '2026-09-16T20:00:00+08:00', 'end_time': '2026-09-16T21:00:00+08:00',
            'max_points_per_variable': 5000, 'items': [{'requested_variable': 'P_top', 'ok': True,
            'variable': {'variable_name': 'P_top', 'unit': 'kPa'}, 'start_time': '2026-09-16T20:00:00+08:00', 'end_time': '2026-09-16T21:00:00+08:00',
            'source': {'engine': 'fixture', 'read_policy': 'readonly'}, 'count': 2,
            'data': [{'ts': '2026-09-16T20:01:00+08:00', 'value': 212.4, 'quality': 'Held:60s'},
                     {'ts': '2026-09-16T21:00:00+08:00', 'value': 217.8, 'quality': 'good'}]}]}


def test_history_renderer_retains_actual_records_quality_and_window():
    payload = history_payload()
    answer = temporal.format_history_answer(payload)
    assert '212.4 kPa' in answer and '217.8 kPa' in answer and 'Held:60s' in answer
    assert '21:00:00+08:00' in answer and '标定尚未核实' in answer
    # The actual production dispatcher must render history, not return blank.
    assert proxy_scope()['deterministic_mcp_answer']('query_gl02_sensors', json.dumps(payload)) == answer


@pytest.mark.parametrize('mutation', ['time', 'object', 'source', 'count', 'nan', 'missing_unit', 'limit'])
def test_history_evidence_mismatch_and_limits_are_not_silently_passed(mutation):
    payload = history_payload(); item = payload['items'][0]
    if mutation == 'time': item['end_time'] = '2026-09-16T22:00:00+08:00'
    elif mutation == 'object': item['variable']['variable_name'] = 'Q_blast'
    elif mutation == 'source': item['source']['read_policy'] = 'write'
    elif mutation == 'count': item['count'] = 3
    elif mutation == 'nan': item['data'][0]['value'] = float('nan')
    elif mutation == 'missing_unit': item['variable']['unit'] = ''
    elif mutation == 'limit': item['limit'] = 2
    answer = temporal.format_history_answer(payload)
    if mutation in {'time', 'object', 'source', 'count'}:
        assert '未展示为有效数据' in answer and '212.4' not in answer
    elif mutation == 'nan': assert '有限数值' in answer and 'nan' not in answer
    elif mutation == 'missing_unit': assert '不能核实单位' in answer
    elif mutation == 'limit': assert '不能宣称覆盖全部记录' in answer
