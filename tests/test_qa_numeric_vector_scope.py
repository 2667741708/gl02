"""User-supplied series are data, never an implicit production query."""
from pathlib import Path
import ast
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_task_plan as planner
import qa_evidence_policy as policy


SERIES = [
    '风温：[1000,1010,1020]，请计算平均值。',
    '风温=[1000,1010,1020]，分析趋势。',
    '炉顶压力：[180,181,179]千帕，计算最大值。',
    '温度（℃）=[100,110,120]，计算变化。',
    '总压差：[150，155，160]，分析趋势。',
    '压力：[+1.5,-2.5,3e1]，求平均值。',
    '风量：[1]，请分析这组数据。',
    '喷煤量=[10,11,12]，请计算平均值。',
    '采样值：[1,null,3]，说明缺失值的处理方式。',
    '温度：[1,NaN,3]，分析可用数据。',
    '压力：[1,None,3]，说明缺项。',
    '风温：[1000,1010,1020]请计算均值。',
]


@pytest.mark.parametrize('question', SERIES)
def test_literal_series_does_not_enable_live_tools(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['user_supplied_data']
    assert plan['allowed_sources'] == ['user_message']
    assert plan['no_live_lookup']
    assert not plan['allow_prefetch'] and not plan['allow_mcp_tools']
    assert not plan['search_knowledge']
    assert planner.live_query_text(question) == ''
    assert policy.direct_result(question) == {}
    assert not policy.code_requested(question)


@pytest.mark.parametrize('series', SERIES[:6])
def test_supplied_series_preserves_an_independent_live_subtask(series):
    live = '同时查询最近一小时炉顶压力'
    plan = planner.build_task_plan(series + '；' + live)
    assert set(plan['intents']) == {'user_supplied_data', 'live_data'}
    assert plan['allowed_sources'] == ['live_readonly_data', 'user_message']
    assert plan['allow_prefetch'] and plan['allow_mcp_tools']
    assert planner.live_query_text(series + '；' + live) == live


@pytest.mark.parametrize('source_request,intent,tool', [
    ('列出我最近问过的炉顶压力问题', 'conversation_history', 'search_qa_messages'),
    ('读取今天的日报', 'period_report', 'read_report_excerpt'),
    ('引用《高炉事故处理》的原文', 'document_knowledge', None),
])
def test_series_keeps_independent_authorized_record_sources(source_request, intent, tool):
    plan = planner.build_task_plan(SERIES[0] + '；' + source_request)
    assert set(plan['intents']) == {'user_supplied_data', intent}
    assert plan['no_live_lookup'] and not plan['allow_prefetch']
    if tool:
        assert planner.tool_allowed(tool, plan)
    else:
        assert plan['search_knowledge']


@pytest.mark.parametrize('question', [
    '请解释“风温：[1000,1010,1020]”这个写法。',
    '说明《风温：[1000,1010,1020]操作规程》的原文。',
    '查询最近30分钟的风温，返回数组。',
    '查询风温=[1000,1010]的实际记录。',
    '当前风温是1000摄氏度吗？',
    '当前风温：[1000,1010]吗？',
    '当前温度（℃）=[100,110]是否属实？',
    '查询[炉顶压力,总压差]最近30分钟的趋势。',
    '温度从7点到8点的数据，计算平均值。',
])
def test_reference_query_or_candidate_is_not_a_supplied_series(question):
    assert 'user_supplied_data' not in planner.build_task_plan(question)['intents']


def test_vector_commas_preserve_the_original_clause_without_masking_other_instructions():
    question = '风温=[1000,1010,1020]，请计算平均值；同时查询最近一小时炉顶压力'
    assert planner.instruction_clauses(question) == [
        '风温=[1000,1010,1020]', '请计算平均值', '同时查询最近一小时炉顶压力']
    assert planner.build_task_plan(question)['instruction_text'].endswith('同时查询最近一小时炉顶压力')


def test_exclusive_user_source_and_explicit_code_boundary_are_retained():
    question = '本轮只用以下数据：风温=[1000,1010]；同时查询最近一小时炉顶压力'
    plan = planner.build_task_plan(question)
    assert plan['all_tools_disabled'] and not plan['allow_prefetch']
    assert not plan['allow_mcp_tools']
    assert policy.code_requested('风温=[1000,1010]，请生成Python代码计算平均值。')


@pytest.mark.parametrize('series', SERIES[:6])
def test_actual_proxy_resolves_only_the_external_object(series):
    from test_qa_declared_input_scope import actual_proxy_scope
    tree, scope = actual_proxy_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'qa_mcp_variables')
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-vector-proxy-alias>', 'exec'), scope)
    assert scope['qa_mcp_variables'](series) == []
    assert scope['qa_mcp_variables'](series + '；同时查询最近一小时炉顶压力') == ['P_top']
