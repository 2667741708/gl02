"""Declared assumptions and literal input values are not external measurements."""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_task_plan as planner
import qa_evidence_policy as policy
import qa_entity_resolution
from qa_frozen_candidate import latest_frozen_candidate


@pytest.mark.parametrize('question', [
 '假设炉顶压力为180千帕，请计算升高10%后的压力。',
 '假定风温数据为1000、1010、1020，请计算平均值。',
 '假如温度数值为100、110、120，请分析波动。',
 '给定温度数值100、110、120，计算平均值。',
 '已知风量数值为100、110、120，计算变化。',
 '设炉顶压力为180千帕，计算下降10%后的压力。',
 '假设最近一小时的温度数据为100、110、120，判断趋势。',
 '请假定风温为1000摄氏度，计算提高20度后的风温。',
 '温度数值为100、110、120，请计算平均值。',
 '风量数据分别为100、110、120，请分析变化。',
 '炉顶压力从150升到180千帕，计算变化百分比。',
 '风温由1000提高到1020摄氏度，请计算变化量。',
 '当前炉顶压力为180千帕，请计算增加10%后的压力。',
 '炉顶压力是180千帕，这个数值合理吗？',
])
def test_declared_inputs_use_user_message_without_live_reads(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['user_supplied_data']
    assert plan['allowed_sources'] == ['user_message']
    assert plan['no_live_lookup'] and not plan['allow_prefetch']
    assert not plan['allow_mcp_tools'] and not plan['search_knowledge']
    assert planner.live_query_text(question) == ''
    assert policy.direct_result(question) == {}


@pytest.mark.parametrize('prefix', [
 '假设最近半小时风温为1000、1010',
 '给定风温数值1000、1010',
 '风温由1000提高到1020',
])
def test_declared_inputs_keep_independent_real_query(prefix):
    question = prefix + '，请计算变化；同时查询最近一小时炉顶压力'
    plan = planner.build_task_plan(question)
    assert set(plan['intents']) == {'user_supplied_data', 'live_data'}
    assert plan['allow_mcp_tools'] and plan['allow_prefetch']
    assert planner.live_query_text(question) == '同时查询最近一小时炉顶压力'


@pytest.mark.parametrize('question', [
 '查询给定变量的当前温度数据',
 '请读取已知变量的最近一小时温度数据',
 '请查询炉顶压力为180千帕的历史记录',
 '当前炉顶压力是180千帕吗？',
 '现在风温为1000摄氏度吗？',
 '解释“假设炉顶压力为180千帕”的含义',
 '请说明《已知温度为100度操作规程》',
 '按规程解释温度为100度的条款',
])
def test_query_question_quote_or_formal_clause_is_not_input_declaration(question):
    assert 'user_supplied_data' not in planner.build_task_plan(question)['intents']


@pytest.mark.parametrize('question', ['当前炉顶压力是180千帕吗？', '现在风温为1000摄氏度吗？',
                                   '当前炉顶压力是否为180千帕？'])
def test_current_candidate_value_requires_real_read(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['live_data']
    assert plan['allow_prefetch'] and plan['allow_mcp_tools']
    assert planner.live_query_text(question) == question


@pytest.mark.parametrize('source_request,intent,tool', [
 ('列出我最近问过的炉顶压力问题', 'conversation_history', 'search_qa_messages'),
 ('读取今天的日报', 'period_report', 'read_report_excerpt'),
])
def test_assumption_does_not_block_independent_nonlive_source(source_request, intent, tool):
    plan = planner.build_task_plan('假设风温为1000摄氏度，请计算提高20度的结果；' + source_request)
    assert set(plan['intents']) == {'user_supplied_data', intent}
    assert planner.tool_allowed(tool, plan)
    assert plan['no_live_lookup'] and not plan['all_tools_disabled']


@pytest.mark.parametrize('question', [
 '温度从7点到8点的数据，请计算平均值',
 '炉顶压力由9点到10点的记录，请统计最大值',
 '温度数据为2026年9月15日的数据，请读取平均值',
 '温度为7点至8点的数据，请计算平均值',
])
def test_clock_or_date_numbers_do_not_assert_measurement_values(question):
    plan = planner.build_task_plan(question)
    assert 'user_supplied_data' not in plan['intents']
    assert plan['allow_prefetch'] and plan['allow_mcp_tools']


def actual_proxy_scope():
    candidate, _ = latest_frozen_candidate(ROOT)
    tree = ast.parse((candidate / 'ollama_proxy_server.py').read_bytes())
    aliases = next(node for node in tree.body if isinstance(node, ast.AnnAssign)
      and isinstance(node.target, ast.Name) and node.target.id == 'SPOKEN_MCP_VARIABLE_ALIASES')
    scope = {'qa_task_plan': planner, 'qa_entity_resolution': qa_entity_resolution,
      'qa_evidence_policy': policy, 'normalize_spoken_question': lambda text: str(text).lower(), 're': re,
      'SPOKEN_MCP_VARIABLE_ALIASES': ast.literal_eval(aliases.value),
      'qa_mcp_exact_variables': lambda text: [], 'qa_mcp_body_temperature_variables': lambda text: [],
      'qa_mcp_group_variables': lambda text: [], 'qa_mcp_catalog_variables': lambda text: []}
    return tree, scope


@pytest.mark.parametrize('question,expected', [
 ('假设最近半小时的风温为1000、1010，请计算变化', []),
 ('假设最近半小时的风温为1000、1010；查询最近一小时炉顶压力', ['P_top']),
 ('当前炉顶压力是180千帕吗？', ['P_top']),
])
def test_actual_proxy_aliases_use_only_external_inputs(question, expected):
    tree, scope = actual_proxy_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_variables')
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-declared-input-alias>', 'exec'), scope)
    assert scope['qa_mcp_variables'](question) == expected


@pytest.mark.parametrize('question,expected', [
 ('假设炉顶压力为180千帕，请计算升高10%的结果', False),
 ('当前炉顶压力是180千帕吗？', True),
])
def test_actual_proxy_tool_gate_respects_declaration_and_verification(question, expected):
    tree, scope = actual_proxy_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_should_use_tools')
    scope.update(Any=object, QA_MCP_TOOLS_ENABLED=True, QA_MCP_TOOL_MODE='auto',
      qa_answer_route=lambda _: 'ordinary', QA_ANSWER_ROUTE_CODE='code',
      qa_verified_facts=SimpleNamespace(reusable_latest_read=lambda *args: False))
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-declared-input-gate>', 'exec'), scope)
    assert scope['qa_mcp_should_use_tools'](question, {'use_mcp_tools': True}, {}) is expected


def test_actual_duration_ignores_assumed_window():
    tree, scope = actual_proxy_scope()
    functions = [next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
      for name in ('chinese_int', 'qa_mcp_duration_minutes')]
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<actual-declared-input-duration>', 'exec'), scope)
    assert scope['qa_mcp_duration_minutes']('假设最近半小时风温为1000、1010；查询最近一小时炉顶压力') == 60


def test_candidate_keeps_fixed_base_and_all_other_files():
    candidate = ROOT / '.codex_runtime/qa-routing-v40/candidate-r2'
    prior = ROOT / '.codex_runtime/qa-routing-v39/candidate-r3'
    manifest = json.loads((candidate / 'package_manifest.private.json').read_bytes())
    assert len(manifest['files']) == 15 and len(manifest['inherited_v39_files_byte_identical']) == 14
    assert manifest['model_name'] == 'chiqiongblastfuenace:latest'
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(manifest[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    public = json.loads((ROOT / 'tests/qa_regression/declared_input_scope_20260917.json').read_bytes())
    assert hashlib.sha256((candidate / 'package_manifest.private.json').read_bytes()).hexdigest() == public['private_candidate']['manifest_sha256']
    assert manifest['files']['qa_task_plan.py']['sha256'] == public['private_candidate']['changed_module_sha256']
    for name, item in manifest['files'].items():
        assert hashlib.sha256((candidate / name).read_bytes()).hexdigest() == item['sha256']
    for name in manifest['inherited_v39_files_byte_identical']:
        assert (candidate / name).read_bytes() == (prior / name).read_bytes()
