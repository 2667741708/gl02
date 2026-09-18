"""Source labels on supplied data must not imply permission to fetch records."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_task_plan as planner
import qa_document_knowledge as documents
import qa_document_compound as document_compound
import qa_history_compound as history
import qa_evidence_policy as policy
from test_qa_declared_input_scope import actual_proxy_scope
from test_qa_source_concept_scope import test_actual_proxy_owned_history_entry_keeps_scope_and_policy as check_history


SUPPLIED = [
 '下面是日报数据：100、110、120；计算平均值',
 '以下是周报数值：100、110、120；分析变化',
 '下面是月报数据：100、110、120；计算极差',
 '以下为生产报告数据：100、110、120；判断趋势',
 '我提供的报表数据为100、110、120；计算平均值',
 '下面是聊天记录数据：100、110、120；分析波动',
 '以下是对话记录数据：100、110、120；计算极差',
 '下面是历史问答数据：100、110、120；计算平均值',
 '以下是历史会话数值：100、110、120；分析变化',
 '我给的聊天记录数据为100、110、120；计算变化',
 '下面是《合成日报》数据：100、110、120；计算平均值',
 '我提供的《三规二制》温度数据为100、110、120；计算平均值',
 '下面是制度数据：100、110、120；解释这些数值的波动',
 '以下是操作规程数据：100、110、120；计算极差',
]


class NoRead:
    def __init__(self): self.calls = 0
    def execute(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError('Supplied inputs are already in the user message')


@pytest.mark.parametrize('question', SUPPLIED)
def test_supplied_record_label_does_not_enable_source_tools(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['user_supplied_data']
    assert plan['allowed_sources'] == ['user_message']
    assert not plan['allow_mcp_tools'] and not plan['allow_prefetch'] and not plan['search_knowledge']
    assert not planner.tool_allowed('search_qa_messages', plan)
    assert not planner.tool_allowed('read_report_excerpt', plan)
    assert planner.live_query_text(question) == ''
    conn = NoRead()
    assert documents.execute_document_question(conn, question, plan) is None
    assert document_compound.prepare(conn, question, plan) is None
    assert history.split_request(question, plan) is None
    assert conn.calls == 0
    assert policy.direct_result(question) == {}


@pytest.mark.parametrize('prefix', SUPPLIED[:6])
def test_supplied_record_label_keeps_independent_current_query(prefix):
    question = prefix + '；查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    assert set(plan['intents']) == {'user_supplied_data', 'live_data'}
    assert planner.tool_allowed('query_gl02_sensors', plan)
    assert not planner.tool_allowed('read_report_excerpt', plan)
    assert not planner.tool_allowed('search_qa_messages', plan)
    assert planner.live_query_text(question) == '查询当前炉顶压力'
    assert history.split_request(question, plan) is None


@pytest.mark.parametrize('question,intent,tool', [
 ('读取今天日报数据；计算平均值', 'period_report', 'read_report_excerpt'),
 ('查询聊天记录里的顶压数据', 'conversation_history', 'search_qa_messages'),
 ('按原文解释《三规二制》', 'document_knowledge', None),
 ('读取日报里温度分别为100、110、120的记录', 'period_report', 'read_report_excerpt'),
 ('检索历史问答中温度为100的回答', 'conversation_history', 'search_qa_messages'),
 ('按规程解释温度为100度的条款', 'document_knowledge', None),
])
def test_external_record_request_is_still_an_external_source(question, intent, tool):
    plan = planner.build_task_plan(question)
    assert intent in plan['intents'] and 'user_supplied_data' not in plan['intents']
    assert planner.tool_allowed(tool, plan) if tool else plan['search_knowledge']


@pytest.mark.parametrize('suffix,intent,tool', [
 ('读取最新日报内容', 'period_report', 'read_report_excerpt'),
 ('列出我最近问过什么问题', 'conversation_history', 'search_qa_messages'),
 ('按原文解释《三规二制》', 'document_knowledge', None),
])
def test_supplied_record_inputs_do_not_block_independent_record_source(suffix, intent, tool):
    question = '下面是日报数据：100、110、120；计算平均值；' + suffix
    plan = planner.build_task_plan(question)
    assert set(plan['intents']) == {'user_supplied_data', intent}
    assert not plan['all_tools_disabled']
    assert planner.tool_allowed(tool, plan) if tool else plan['search_knowledge']


@pytest.mark.parametrize('question', [SUPPLIED[0], SUPPLIED[5], SUPPLIED[11]])
def test_actual_proxy_aliases_ignore_supplied_source_objects(question):
    tree, scope = actual_proxy_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_variables')
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-supplied-record-alias>', 'exec'), scope)
    assert scope['qa_mcp_variables'](question) == []
    assert scope['qa_mcp_variables'](question + '；查询当前炉顶压力') == ['P_top']


@pytest.mark.parametrize('question,expected', [(SUPPLIED[0], False), (SUPPLIED[5], False),
 (SUPPLIED[0] + '；查询当前炉顶压力', True)])
def test_actual_proxy_outer_mcp_selection_respects_supplied_records(question, expected):
    tree, scope = actual_proxy_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_should_use_tools')
    assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
      and any(isinstance(target, ast.Name) and target.id == 'use_mcp_tools' for target in node.targets)
      and 'task_plan.get' in ast.unparse(node.value) and 'qa_mcp_should_use_tools' in ast.unparse(node.value))
    scope.update(Any=object, QA_MCP_TOOLS_ENABLED=True, QA_MCP_TOOL_MODE='auto',
      qa_answer_route=lambda _: 'ordinary', QA_ANSWER_ROUTE_CODE='code',
      qa_verified_facts=SimpleNamespace(reusable_latest_read=lambda *args: False),
      task_plan=planner.build_task_plan(question), routing_question=question,
      payload={'use_mcp_tools': True}, mcp_prefetch={}, tool_selection={'mode': 'auto'})
    exec(compile(ast.Module(body=[function, assignment], type_ignores=[]), '<actual-supplied-record-mcp>', 'exec'), scope)
    assert scope['use_mcp_tools'] is expected


@pytest.mark.parametrize('question,expected_calls', [(SUPPLIED[5], 0),
 (SUPPLIED[5] + '；列出我最近问过什么问题', 1)])
def test_actual_proxy_owned_history_entry_does_not_fetch_supplied_records(monkeypatch, question, expected_calls):
    # The pure-history branch must not read a mixed input/history request.
    # Execute the actual compound assignment as well, preserving its owner and
    # cutoff arguments rather than mistaking the pure branch for the full path.
    check_history(question, 0)
    tree, _ = actual_proxy_scope()
    assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
      and any(isinstance(target, ast.Name) and target.id == 'history_compound' for target in node.targets)
      and isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'qa_history_compound.execute')
    calls = []
    def fetch(conn, *, owner, before_message_id, question):
        calls.append((owner, before_message_id, question))
        return {'ok': True, 'source': {'type': 'owner_scoped_qa_history'}}
    monkeypatch.setattr(history.qa_history_projection, 'fetch_owned_history', fetch)
    plan = planner.build_task_plan(question)
    pack = history.split_request(question, plan)
    scope = {'qa_history_compound': history, 'history_request': pack, 'conn': NoRead(),
      'owner_subject': 'synthetic-owner', 'user_message_id': 10, 'history_tool_selection': {'mode': 'auto'}}
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), '<actual-supplied-record-history-compound>', 'exec'), scope)
    assert len(calls) == expected_calls
    if calls:
        assert calls == [('synthetic-owner', 10, '列出我最近问过什么问题')]
        assert '下面是聊天记录数据' in pack['remainder_question']


@pytest.mark.parametrize('question,intent,tool', [
 ('请核实我提供的日报数据与今天日报是否一致', 'period_report', 'read_report_excerpt'),
 ('请确认我提供的聊天记录数据和我的历史会话是否相符', 'conversation_history', 'search_qa_messages'),
 ('请查询我提供的报表数据在生产系统里的真实值', 'period_report', 'read_report_excerpt'),
 ('请验证我提供的《三规二制》温度数据是否符合正式原文', 'document_knowledge', None),
])
def test_explicit_verification_of_provided_record_is_not_only_an_input_declaration(question, intent, tool):
    plan = planner.build_task_plan(question)
    assert intent in plan['intents']
    assert planner.tool_allowed(tool, plan) if tool else plan['search_knowledge']


@pytest.mark.parametrize('question', [
 '请确认我提供的日报数据100、110、120的平均值',
 '请验证我提供的报表数据100、110、120的极差',
 '请检查我提供的聊天记录数据100、110、120有没有漏项',
])
def test_local_validation_of_supplied_record_data_does_not_request_originals(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['user_supplied_data']
    assert plan['allowed_sources'] == ['user_message']
    assert not plan['allow_mcp_tools'] and not plan['search_knowledge']


@pytest.mark.parametrize('question,intent,tool', [
 ('请核实我提供的日报数据与今天日报是否一致', 'period_report', 'read_report_excerpt'),
 ('请确认我提供的聊天记录数据和我的历史会话是否相符', 'conversation_history', 'search_qa_messages'),
 ('请查询我提供的报表数据在生产系统里的真实值', 'period_report', 'read_report_excerpt'),
])
def test_verification_of_supplied_records_reaches_actual_outer_tool_gate(question, intent, tool):
    test_actual_proxy_outer_mcp_selection_respects_supplied_records(question, True)
    assert planner.tool_allowed(tool, planner.build_task_plan(question))


def test_formal_verification_of_supplied_values_reaches_bound_reader():
    question = '请验证我提供的《三规二制》温度数据是否符合正式原文'
    plan = planner.build_task_plan(question)
    conn = NoRead()
    result = documents.execute_document_question(conn, question, plan)
    assert conn.calls == 1
    assert result['completion']['reason'] == 'original_source_snapshot_unavailable'
