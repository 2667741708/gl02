"""Distinguish a source-domain definition from reading actual source records."""
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
import qa_history_compound as history
import qa_evidence_policy as policy
from qa_frozen_candidate import latest_frozen_candidate


CONCEPTS = [
 '日报是什么？', '请解释日报和周报有什么区别', '完整说明月报的用途',
 '生产报告的定义是什么', '报表一般有什么作用', '如何编写日报？',
 '聊天记录是什么意思？', '解释历史问答的用途', '完整说明历史会话的含义',
 '对话记录与聊天记录有什么区别', '历史问答这个概念是什么',
 '日报通常包括什么内容',
]


class NoDatabaseRead:
    def execute(self, *args, **kwargs):
        raise AssertionError('A concept explanation did not request stored records')


@pytest.mark.parametrize('question', CONCEPTS)
def test_source_concept_does_not_read_actual_records(question):
    plan = planner.build_task_plan(question)
    assert not {'document_knowledge', 'conversation_history', 'period_report', 'live_data'} & set(plan['intents'])
    assert not plan['allow_mcp_tools'] and not plan['allow_prefetch']
    assert not planner.tool_allowed('search_qa_messages', plan)
    assert not planner.tool_allowed('read_report_excerpt', plan)
    assert documents.execute_document_question(NoDatabaseRead(), question, plan) is None


@pytest.mark.parametrize('question,intent,tool', [
 ('今天日报的主要内容是什么', 'period_report', 'read_report_excerpt'),
 ('昨天日报和今天日报有什么区别', 'period_report', 'read_report_excerpt'),
 ('查询日报的主要内容', 'period_report', 'read_report_excerpt'),
 ('读取最近的生产报告并解释其中压差变化的含义', 'period_report', 'read_report_excerpt'),
 ('我的聊天记录是什么', 'conversation_history', 'search_qa_messages'),
 ('历史问答里关于顶压的回答是什么', 'conversation_history', 'search_qa_messages'),
 ('列出我最近问过什么问题', 'conversation_history', 'search_qa_messages'),
 ('检索历史问答并解释顶压含义', 'conversation_history', 'search_qa_messages'),
])
def test_actual_records_and_read_actions_keep_original_source(question, intent, tool):
    plan = planner.build_task_plan(question)
    assert intent in plan['intents'] and planner.tool_allowed(tool, plan)


@pytest.mark.parametrize('question,intents', [
 ('解释日报和周报的区别；查询当前炉顶压力', {'live_data'}),
 ('说明聊天记录的作用；读取今天日报', {'period_report'}),
 ('解释日报的用途；列出我最近问过什么问题', {'conversation_history'}),
 ('下面是风温数据：1000、1010；解释日报的用途', {'user_supplied_data'}),
 ('下面是风温数据：1000、1010；解释聊天记录的用途', {'user_supplied_data'}),
 ('完整说明历史问答的含义；按原文解释《三规二制》', {'document_knowledge'}),
])
def test_concept_clause_does_not_invent_compound_source(question, intents):
    plan = planner.build_task_plan(question)
    assert set(plan['intents']) == intents
    assert history.split_request(question, plan) is None


@pytest.mark.parametrize('question', [
 '按原文说明《生产日报编写制度》的含义',
 '请说明《历史问答记录制度》的用途',
 '解释三规二制高炉工长安全操作规程的含义',
])
def test_explicit_formal_source_never_becomes_generic_concept(question):
    plan = planner.build_task_plan(question)
    assert 'document_knowledge' in plan['intents'] and plan['search_knowledge']


def test_explicit_all_tools_ban_still_blocks_actual_record_read():
    plan = planner.build_task_plan('不要调用任何工具；解释日报用途；读取今天日报')
    assert 'period_report' in plan['intents']
    assert plan['all_tools_disabled'] and not plan['allow_mcp_tools']
    assert not planner.tool_allowed('read_report_excerpt', plan)


@pytest.mark.parametrize('concept', ['解释日报用途', '说明聊天记录作用'])
def test_concept_does_not_lift_exclusive_user_input_constraint(concept):
    plan = planner.build_task_plan('仅用我提供的风温数据分析变化；' + concept)
    assert plan['intents'] == ['user_supplied_data']
    assert plan['allowed_sources'] == ['user_message']
    assert plan['all_tools_disabled'] and plan['no_live_lookup']


@pytest.mark.parametrize('question,expected', [
 ('日报是什么？', False), ('历史问答的作用是什么', False),
 ('解释日报的用途；查询当前炉顶压力', True), ('读取今天日报并解释顶压变化', True),
])
def test_actual_proxy_outer_mcp_selection_respects_source_concepts(question, expected):
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
    exec(compile(ast.Module(body=[function, assignment], type_ignores=[]), '<actual-source-concept-selection>', 'exec'), scope)
    assert scope['use_mcp_tools'] is expected


@pytest.mark.parametrize('question,expected_calls', [
 ('历史问答的含义是什么', 0),
 ('下面是风温数据：1000、1010；解释聊天记录的用途', 0),
 ('列出我最近问过什么问题', 1),
 ('不要调用任何工具；列出我最近问过什么问题', 0),
])
def test_actual_proxy_owned_history_entry_keeps_scope_and_policy(question, expected_calls):
    candidate, _ = latest_frozen_candidate(ROOT)
    tree = ast.parse((candidate / 'ollama_proxy_server.py').read_bytes())
    entry = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
      and ast.unparse(node.test) == "task_plan.get('intents') == ['conversation_history']"
      and 'fetch_owned_history' in ast.unparse(node))
    calls = []

    def fetch(conn, *, owner, before_message_id, question):
        calls.append((owner, before_message_id, question))
        return {'ok': True}

    scope = {'qa_task_plan': planner, 'qa_history_projection': SimpleNamespace(fetch_owned_history=fetch),
      'task_plan': planner.build_task_plan(question), 'tool_selection': {'mode': 'auto'},
      'hidden_context': {}, 'history_result': None, 'conn': NoDatabaseRead(),
      'owner_subject': 'synthetic-owner', 'user_message_id': 10, 'question': question}
    exec(compile(ast.Module(body=[entry], type_ignores=[]), '<actual-owned-history-entry>', 'exec'), scope)
    assert len(calls) == expected_calls
    if calls:
        assert calls == [('synthetic-owner', 10, question)]
    if scope['task_plan']['all_tools_disabled']:
        assert scope['history_result']['error'] == 'history_tool_selection_blocked'


def test_frozen_source_concept_candidate_keeps_base_and_other_runtime_files():
    candidate = ROOT / '.codex_runtime/qa-routing-v42/candidate-r1'
    prior = ROOT / '.codex_runtime/qa-routing-v41/candidate-r1'
    raw = (candidate / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'b7b74e1d68d986ca3ac98abf3acfe9f001d099854af1fb1129716b4175c714cf'
    manifest = json.loads(raw)
    assert len(manifest['files']) == 15 and len(manifest['inherited_v41_files_byte_identical']) == 14
    assert manifest['model_name'] == 'chiqiongblastfuenace:latest'
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(manifest[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    for name, item in manifest['files'].items():
        assert hashlib.sha256((candidate / name).read_bytes()).hexdigest() == item['sha256']
    for name in manifest['inherited_v41_files_byte_identical']:
        assert (candidate / name).read_bytes() == (prior / name).read_bytes()
