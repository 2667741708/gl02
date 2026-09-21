"""User-supplied numerical data never silently becomes a live sensor query."""
import ast
import hashlib
import json
import re
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_task_plan as planner
import qa_entity_resolution
import qa_evidence_policy as policy


@pytest.mark.parametrize('question', [
 '下面是风温数据：1200、1205、1203。请分析波动。',
 '仅基于下面的数据判断温度趋势：100、110、120。',
 '只根据以下数据计算最近温度的平均值：100、110、120。',
 '我提供的数据是温度100、110、120，请分析变化。',
 '这组温度数据是100、110、120，请计算平均值。',
 '以下为炉顶压力数值：100、110、120。请判断变化。',
 '下面的温度数据不足，请说明还缺哪些数据。',
 '下面是温度数据：“100、110、120”。请分析温度趋势。',
])
def test_provided_data_is_analyzed_without_live_lookup(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['user_supplied_data']
    assert plan['allowed_sources'] == ['user_message']
    assert not plan['allow_mcp_tools'] and not plan['allow_prefetch']
    assert not plan['search_knowledge'] and plan['no_live_lookup']
    assert policy.no_live_lookup(question)
    assert policy.direct_result(question) == {}


@pytest.mark.parametrize('suffix', [
 '查询当前炉顶压力', '再查询2026年9月15日炉顶压力平均值',
 '同时读取炉顶压力最新值', '当前炉顶压力是多少',
])
def test_provided_and_requested_live_data_keep_separate_sources(suffix):
    question = '我提供的风温数据是1200、1205、1203，请分析波动；' + suffix
    plan = planner.build_task_plan(question)
    assert set(plan['intents']) == {'user_supplied_data', 'live_data'}
    assert set(plan['allowed_sources']) == {'user_message', 'live_readonly_data'}
    assert plan['allow_mcp_tools'] and not plan['no_live_lookup']
    assert plan['entities'] == qa_entity_resolution.resolve_requested_entities(suffix)['variables']
    assert '风温' not in planner.live_query_text(question)
    assert '炉顶压力' in planner.live_query_text(question)
    assert not policy.no_live_lookup(question)


@pytest.mark.parametrize('prefix', ['仅基于下面的数据', '只根据以下数据', '只用我提供的数据'])
def test_explicit_exclusive_data_scope_cannot_be_overridden(prefix):
    question = '本轮' + prefix + '分析温度100、110、120；再查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    assert plan['all_tools_disabled'] and plan['no_live_lookup']
    assert not plan['allow_mcp_tools'] and not plan['allow_prefetch']
    assert plan['allowed_sources'] == ['user_message']
    result = policy.direct_result(question, {'mode': 'required', 'tools': ['query_gl02_sensors']})
    assert result['answer_route'] == 'tool_policy_conflict' and not result['tool_used']


@pytest.mark.parametrize('prefix', [
 '仅基于我提供的数据', '先只用我给的数据', '根据我提供的数据',
])
def test_subtask_data_scope_preserves_independent_live_request(prefix):
    question = prefix + '计算风温均值：1200、1205；同时查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    assert set(plan['intents']) == {'user_supplied_data', 'live_data'}
    assert plan['allow_mcp_tools'] and plan['allow_prefetch']
    assert not plan['all_tools_disabled'] and not plan['no_live_lookup']
    assert planner.live_query_text(question) == '同时查询当前炉顶压力'
    _, scope = actual_variable_scope()
    assert scope['qa_mcp_variables'](question) == ['P_top']


@pytest.mark.parametrize('source_request,intent,tool', [
 ('列出我最近问过的炉顶压力问题', 'conversation_history', 'search_qa_messages'),
 ('读取今天的日报', 'period_report', 'read_report_excerpt'),
])
def test_subtask_only_data_scope_preserves_nonlive_source(source_request, intent, tool):
    plan = planner.build_task_plan('先只用我提供的数据算风温均值：1200、1205；' + source_request)
    assert set(plan['intents']) == {'user_supplied_data', intent}
    assert plan['no_live_lookup'] and not plan['all_tools_disabled']
    assert planner.tool_allowed(tool, plan)


@pytest.mark.parametrize('data_request', ['查询这些温度数据的均值', '查看这组风温数据的趋势'])
def test_later_data_reference_stays_with_supplied_inputs(data_request):
    question = '我提供的风温数据是1200、1205；' + data_request
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['user_supplied_data']
    assert plan['no_live_lookup'] and not plan['allow_prefetch']
    assert planner.live_query_text(question) == ''


@pytest.mark.parametrize('prefix', ['全程只用我提供的数据', '不要调用任何工具；我提供的数据',
                                   '不要查询现场数据；我提供的数据'])
def test_explicit_global_ban_keeps_priority_over_independent_live_request(prefix):
    question = prefix + '是风温1200、1205；查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    assert plan['no_live_lookup'] and not plan['allow_prefetch']
    assert not planner.tool_allowed('query_gl02_sensors', plan)
    assert planner.live_query_text(question) == ''


@pytest.mark.parametrize('question', [
 '查询当前炉顶压力', '查询下面这些点的温度',
 '请说明《下面是温度数据操作规程》',
 '解释“下面是温度数据，请分析”的含义',
 '查询这些温度数据',
])
def test_data_marker_inside_quotes_or_query_is_not_provided_data(question):
    assert 'user_supplied_data' not in planner.build_task_plan(question)['intents']


@pytest.mark.parametrize('source_request,intent,tool', [
 ('列出我最近问过的炉顶压力问题', 'conversation_history', 'search_qa_messages'),
 ('读取今天的日报', 'period_report', 'read_report_excerpt'),
])
def test_provided_data_does_not_block_requested_nonlive_source(source_request, intent, tool):
    question = '我提供的风温数据是1200、1205、1203，请分析波动；' + source_request
    plan = planner.build_task_plan(question)
    assert set(plan['intents']) == {'user_supplied_data', intent}
    assert plan['no_live_lookup'] and not plan['all_tools_disabled']
    assert planner.tool_allowed(tool, plan)
    assert policy.direct_result(question, {'mode': 'required', 'tools': [tool]}) == {}


@pytest.mark.parametrize('question,expected', [
 ('下面是温度数据：100、110、120，请分析变化', False),
 ('我提供的风温数据是1200、1205；查询当前炉顶压力', True),
])
def test_actual_proxy_mcp_gate_obeys_source_scope(question, expected):
    path = ROOT / '.codex_runtime/qa-routing-v39/candidate-r3/ollama_proxy_server.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_should_use_tools')
    scope = {'qa_evidence_policy': policy, 'qa_task_plan': planner, 'Any': object,
     'QA_MCP_TOOLS_ENABLED': True, 'QA_MCP_TOOL_MODE': 'auto',
     'qa_answer_route': lambda _: 'ordinary', 'QA_ANSWER_ROUTE_CODE': 'code',
     'qa_verified_facts': SimpleNamespace(reusable_latest_read=lambda *args: False)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-source-gate>', 'exec'), scope)
    assert scope['qa_mcp_should_use_tools'](question, {'use_mcp_tools': True}, {}) is expected


def actual_variable_scope():
    tree = ast.parse((ROOT / '.codex_runtime/qa-routing-v39/candidate-r3/ollama_proxy_server.py').read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_variables')
    aliases = next(node for node in tree.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == 'SPOKEN_MCP_VARIABLE_ALIASES')
    scope = {'qa_task_plan': planner, 'qa_entity_resolution': qa_entity_resolution,
      'normalize_spoken_question': lambda text: str(text).lower(), 're': re,
      'SPOKEN_MCP_VARIABLE_ALIASES': ast.literal_eval(aliases.value),
      'qa_mcp_exact_variables': lambda text: [], 'qa_mcp_body_temperature_variables': lambda text: [],
      'qa_mcp_group_variables': lambda text: [], 'qa_mcp_catalog_variables': lambda text: []}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-variable-source>', 'exec'), scope)
    return tree, scope


@pytest.mark.parametrize('question,expected', [
 ('下面是风温数据：1200、1205，请分析波动', []),
 ('我提供的风温数据是1200、1205；查询当前炉顶压力', ['P_top']),
 ('本轮仅基于下面的数据分析风温1200、1205；查询当前炉顶压力', []),
])
def test_actual_alias_mapping_does_not_query_user_inputs(question, expected):
    _, scope = actual_variable_scope()
    assert scope['qa_mcp_variables'](question) == expected


def test_actual_analysis_context_does_not_add_hour_bundle_to_user_inputs():
    tree, scope = actual_variable_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_analysis_variables')
    scope.update(qa_evidence_policy=policy, qa_answer_route=lambda text: 'analysis',
      QA_ANSWER_ROUTE_ANALYSIS='analysis', QA_ANALYSIS_VARIABLE_BUNDLES=[])
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-analysis-context>', 'exec'), scope)
    assert scope['qa_mcp_analysis_variables']('下面是最近一小时的风温数据：1200、1205，请分析问题') == []


def test_actual_prepare_freezes_only_live_aliases():
    tree, scope = actual_variable_scope()
    branch = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
      and ast.unparse(node.test) == "'user_supplied_data' in task_plan['intents'] and 'live_data' in task_plan['intents']")
    question = '我提供的风温数据是1200、1205；查询当前炉顶压力'
    scope.update(task_plan=planner.build_task_plan(question), execution_question=question)
    exec(compile(ast.Module(body=[branch], type_ignores=[]), '<actual-prepare-source>', 'exec'), scope)
    assert scope['task_plan']['entities'] == ['P_top']


def test_frozen_candidate_preserves_source_and_same_base():
    candidate = ROOT / '.codex_runtime/qa-routing-v39/candidate-r3'
    prior = ROOT / '.codex_runtime/qa-routing-v38/candidate-r2'
    manifest = json.loads((candidate / 'package_manifest.private.json').read_bytes())
    assert len(manifest['files']) == 15 and len(manifest['inherited_v38_files_byte_identical']) == 13
    assert manifest['model_name'] == 'chiqiongblastfuenace:latest'
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not manifest['model_switch_allowed'] and not manifest['fallback_model_allowed']
    for name, item in manifest['files'].items():
        assert hashlib.sha256((candidate / name).read_bytes()).hexdigest() == item['sha256']
    for name in manifest['inherited_v38_files_byte_identical']:
        assert (candidate / name).read_bytes() == (prior / name).read_bytes()


def test_actual_duration_uses_external_window_instead_of_user_window():
    tree, scope = actual_variable_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_duration_minutes')
    chinese = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'chinese_int')
    exec(compile(ast.Module(body=[chinese, function], type_ignores=[]), '<actual-source-duration>', 'exec'), scope)
    question = '我提供的最近半小时风温数据是1200、1205；查询最近一小时炉顶压力'
    assert scope['qa_mcp_duration_minutes'](question) == 60


def test_actual_sensor_clock_parser_receives_only_external_clock():
    tree, scope = actual_variable_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_sensor_query_plan')
    observed = []
    class ParsedEnough(Exception): pass
    def parse(text):
        observed.append(text)
        raise ParsedEnough
    scope.update(Any=object, qa_evidence_policy=policy,
      qa_time_window_plan=SimpleNamespace(parse_explicit_clock_range=parse))
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-source-clock>', 'exec'), scope)
    question = '我提供的9点到10点的风温数据是1200、1205；查询今天14点到15点的炉顶压力'
    with pytest.raises(ParsedEnough): scope['qa_mcp_sensor_query_plan'](question)
    assert observed == ['查询今天14点到15点的炉顶压力']


def test_actual_routing_question_filters_user_inputs_but_keeps_answer_question():
    tree, scope = actual_variable_scope()
    assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
      and any(isinstance(target, ast.Name) and target.id == 'routing_question' for target in node.targets)
      and 'enrich_routing_question' in ast.unparse(node.value))
    question = '我提供的最近半小时风温数据是1200、1205；查询最近一小时炉顶压力'
    scope.update(execution_question=question, task_plan=planner.build_task_plan(question), tool_context={},
      enrich_routing_question=lambda text, context: text)
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), '<actual-routed-source>', 'exec'), scope)
    assert scope['routing_question'] == '查询最近一小时炉顶压力'
    assert scope['execution_question'] == question
