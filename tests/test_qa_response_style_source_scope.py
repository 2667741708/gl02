"""Response format alone must not invent a formal-document subtask."""
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_task_plan as planner
import qa_document_knowledge as documents
import qa_document_compound as compound
import qa_evidence_policy as policy
from qa_frozen_candidate import latest_frozen_candidate


class NoDatabaseRead:
    def execute(self, *args, **kwargs):
        raise AssertionError('No document database read was requested')


@pytest.mark.parametrize('prefix', ['下面是风温数据：1000、1010、1020，', '假设炉顶压力为180千帕，'])
@pytest.mark.parametrize('style', ['请完整说明', '请逐条解释', '请逐条说明', '请完整说明并解释'])
def test_response_style_preserves_supplied_data_scope(prefix, style):
    question = prefix + style + '增加10%的计算过程'
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['user_supplied_data']
    assert plan['allowed_sources'] == ['user_message']
    assert not plan['search_knowledge'] and not plan['allow_mcp_tools'] and not plan['allow_prefetch']
    assert plan['no_live_lookup'] and policy.direct_result(question) == {}


@pytest.mark.parametrize('question', [
 '完整说明风温波动的一般原因', '逐条解释提高风温与焦比的关系',
 '请逐条说明MCP原理', '请完整说明一次函数y=2x+1的斜率',
 '请逐条回答为什么需要核对数据质量',
])
def test_general_explanation_style_does_not_request_formal_document(question):
    plan = planner.build_task_plan(question)
    assert 'document_knowledge' not in plan['intents']
    assert not plan['allow_prefetch'] and not plan['allow_mcp_tools']
    assert policy.direct_result(question) == {}


@pytest.mark.parametrize('question', [
 '请完整说明《高炉操作规程》', '请逐条解释《高炉操作规程》',
 '完整说明三规二制高炉工长安全操作规程', '逐条解释高炉工长安全操作规程',
 '请按原文完整说明所指文档', '请按原文逐条说明所指条款',
])
def test_real_document_reference_keeps_formal_source(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['document_knowledge']
    assert plan['search_knowledge'] and plan['allowed_sources'] == ['knowledge_base']
    assert not plan['allow_prefetch']


@pytest.mark.parametrize('suffix,intent,tool', [
 ('再查询当前炉顶压力', 'live_data', 'query_gl02_sensors'),
 ('逐条列出我最近问过什么问题', 'conversation_history', 'search_qa_messages'),
 ('读取今天日报并完整说明主要变化', 'period_report', 'read_report_excerpt'),
])
def test_format_preserves_independent_external_source(suffix, intent, tool):
    question = '下面是风温数据：1000、1010，请完整说明计算过程；' + suffix
    plan = planner.build_task_plan(question)
    assert set(plan['intents']) == {'user_supplied_data', intent}
    assert planner.tool_allowed(tool, plan)


@pytest.mark.parametrize('question', ['完整说明风温波动的一般原因', '逐条解释提高风温与焦比的关系'])
def test_actual_document_entry_does_not_short_circuit_ordinary_explanation(question):
    plan = planner.build_task_plan(question)
    assert documents.execute_document_question(NoDatabaseRead(), question, plan) is None


@pytest.mark.parametrize('style', ['完整说明', '逐条解释'])
def test_actual_compound_entry_does_not_replace_data_question_with_missing_book(style):
    question = '下面是风温数据：1000、1010，请' + style + '波动'
    plan = planner.build_task_plan(question)
    assert compound.prepare(NoDatabaseRead(), question, plan) is None


def test_real_unknown_book_keeps_clarification_and_explicit_tool_ban():
    question = '请完整说明《高炉操作规程》'
    result = documents.execute_document_question(NoDatabaseRead(), question, planner.build_task_plan(question))
    assert result['completion']['reason'] == 'document_reference_unresolved'
    assert result['model_request_count'] == 0 and not result['knowledge_manifest']
    blocked = '不要调用任何工具；' + question
    result = documents.execute_document_question(NoDatabaseRead(), blocked, planner.build_task_plan(blocked))
    assert result['completion']['reason'] == 'document_lookup_policy_blocked'


@pytest.mark.parametrize('question,expected', [
 ('下面是风温数据：1000、1010，请完整说明波动', False),
 ('逐条解释提高风温与焦比的关系', False),
 ('下面是风温数据：1000、1010，请完整说明波动；再查询当前炉顶压力', True),
 ('请完整说明《高炉操作规程》', False),
])
def test_actual_current_proxy_mcp_gate_preserves_source_scope(question, expected):
    candidate, _ = latest_frozen_candidate(ROOT)
    tree = ast.parse((candidate / 'ollama_proxy_server.py').read_bytes())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_should_use_tools')
    assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
      and any(isinstance(target, ast.Name) and target.id == 'use_mcp_tools' for target in node.targets)
      and 'task_plan.get' in ast.unparse(node.value) and 'qa_mcp_should_use_tools' in ast.unparse(node.value))
    scope = {'qa_task_plan': planner, 'qa_evidence_policy': policy, 'Any': object,
      'QA_MCP_TOOLS_ENABLED': True, 'QA_MCP_TOOL_MODE': 'auto',
      'qa_answer_route': lambda _: 'ordinary', 'QA_ANSWER_ROUTE_CODE': 'code',
      'qa_verified_facts': SimpleNamespace(reusable_latest_read=lambda *args: False)}
    scope.update(task_plan=planner.build_task_plan(question), routing_question=question,
      payload={'use_mcp_tools': True}, mcp_prefetch={}, tool_selection={'mode': 'auto'})
    exec(compile(ast.Module(body=[function, assignment], type_ignores=[]), '<actual-style-source-selection>', 'exec'), scope)
    assert scope['use_mcp_tools'] is expected


def test_response_style_snapshot_keeps_fixed_base_and_all_other_files():
    candidate = ROOT / '.codex_runtime/qa-routing-v41/candidate-r1'
    prior = ROOT / '.codex_runtime/qa-routing-v40/candidate-r2'
    raw = (candidate / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '697a0c119288ec792465e7ce22156cd2ce6d89c6b7f58866431f42b84d6d80e3'
    manifest = json.loads(raw)
    assert len(manifest['files']) == 15 and len(manifest['inherited_v40_files_byte_identical']) == 14
    assert manifest['model_name'] == 'chiqiongblastfuenace:latest'
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(manifest[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    for name, item in manifest['files'].items():
        assert hashlib.sha256((candidate / name).read_bytes()).hexdigest() == item['sha256']
    for name in manifest['inherited_v40_files_byte_identical']:
        assert (candidate / name).read_bytes() == (prior / name).read_bytes()
