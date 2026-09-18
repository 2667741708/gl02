"""Compound source requests and scoped prohibitions, without production I/O."""
import ast
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_document_compound as documents
import qa_document_knowledge as formal
import qa_evidence_policy as policy
import qa_history_compound as history
import qa_history_projection as projection
import qa_task_plan as planner


@pytest.mark.parametrize('question,first', [
 ('按三规二制解释顶压控制要求，并分析昨天炉顶压力的平均值。', 'document_knowledge'),
 ('按三规二制解释顶压控制要求，并查询今天8点到9点炉顶压力的平均值。', 'document_knowledge'),
 ('按三规二制解释顶压控制要求，并查询今天八点到九点炉顶压力的平均值。', 'document_knowledge'),
 ('按三规二制解释顶压控制要求，并查询今天25点到26点炉顶压力的平均值。', 'document_knowledge'),
 ('按三规二制解释顶压控制要求，并对比最近30分钟和前30分钟的炉顶压力。', 'document_knowledge'),
 ('检索历史问答的顶压回答；查询昨天炉顶压力的平均值。', 'conversation_history'),
 ('读取今天的日报；查询今天8点到9点炉顶压力的平均值。', 'period_report'),
])
def test_independent_dated_or_clock_data_subtask_is_not_dropped(question, first):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == [first, 'live_data']
    assert planner.tool_allowed('query_gl02_statistics', plan)
    assert plan['allow_prefetch']


@pytest.mark.parametrize('question,intent', [
 ('查询昨天日报中炉顶压力的平均值。', 'period_report'),
 ('检索历史问答关于昨天炉顶压力的平均值。', 'conversation_history'),
 ('请按原文解释《昨天8点顶压查询操作规程》。', 'document_knowledge'),
])
def test_time_inside_nonlive_source_does_not_create_external_data_task(question, intent):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == [intent]
    assert not planner.tool_allowed('query_gl02_statistics', plan)


@pytest.mark.parametrize('question,tool', [
 ('列出我最近问过的顶压问题，不要查询现场数据库。', 'search_qa_messages'),
 ('读取今天的日报，不要查询现场数据库。', 'read_report_excerpt'),
])
def test_no_live_prohibition_preserves_requested_nonlive_source(question, tool):
    plan = planner.build_task_plan(question)
    assert plan['no_live_lookup'] and not plan['allow_prefetch']
    assert planner.tool_allowed(tool, plan)
    assert not planner.tool_allowed('query_gl02_statistics', plan)
    assert policy.direct_result(question, {'mode': 'required', 'tools': [tool]}) == {}


@pytest.mark.parametrize('suffix', ['不要调用工具', '不要使用任何工具', '不要查询数据库'])
def test_global_prohibition_keeps_all_mcp_domains_disabled(suffix):
    question = '列出我最近问过的顶压问题；' + suffix
    plan = planner.build_task_plan(question)
    assert plan['all_tools_disabled'] and not plan['allow_mcp_tools']
    assert not planner.tool_allowed('search_qa_messages', plan)
    assert policy.direct_result(question, {'mode': 'required', 'tools': ['search_qa_messages']})['answer_route'] == 'tool_policy_conflict'


def test_live_required_tool_still_conflicts_with_no_live_prohibition():
    question = '列出我最近问过的顶压问题，不要查询现场数据库。'
    result = policy.direct_result(question, {'mode': 'required', 'tools': ['query_gl02_statistics']})
    assert result['answer_route'] == 'tool_policy_conflict' and not result['tool_used']


@pytest.fixture
def database():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''CREATE TABLE qa_conversations(id INTEGER, owner_subject TEXT);
      CREATE TABLE qa_messages(id INTEGER, conversation_id INTEGER, role TEXT, content TEXT, created_at TEXT);
      INSERT INTO qa_conversations VALUES(1,'synthetic-a'),(2,'synthetic-b');
      INSERT INTO qa_messages VALUES(1,1,'assistant','炉顶压力本身份历史回答','2026-09-01'),
        (2,2,'assistant','炉顶压力其他身份历史回答','2026-09-01'),
        (10,1,'user','炉顶压力本轮问题','2026-09-01');''')
    yield conn
    conn.close()


def test_history_source_survives_split_without_bypassing_owner_or_cutoff(database):
    question = '检索历史问答中炉顶压力的回答；读取今天的日报；不要查询现场数据库。'
    pack = history.split_request(question, planner.build_task_plan(question))
    assert not pack['tools_disabled']
    result = history.execute(pack, database, owner='synthetic-a', before_message_id=10, selection={'mode': 'auto'})
    answer = result['outcomes'][0]['answer']
    assert '本身份历史回答' in answer and '其他身份' not in answer and '本轮问题' not in answer
    assert result['outcomes'][0]['completion']['complete'] is True
    json.dumps(result, ensure_ascii=False, allow_nan=False)


def test_live_prohibition_survives_remainder_when_policy_clause_was_consumed():
    question = '检索历史问答中炉顶压力的回答，不要查询现场数据库；读取今天的日报。'
    pack = history.split_request(question, planner.build_task_plan(question))
    child = history.execution_plan('查询当前炉顶压力', pack)
    assert child['no_live_lookup'] and not child['allow_prefetch']
    assert not planner.tool_allowed('query_gl02_statistics', child)
    report = history.execution_plan('读取今天的日报', pack)
    assert planner.tool_allowed('read_report_excerpt', report)


def test_global_tool_prohibition_survives_history_split(database):
    question = '检索历史问答中炉顶压力的回答；读取今天的日报；不要调用工具。'
    pack = history.split_request(question, planner.build_task_plan(question))
    assert pack['tools_disabled']
    result = history.execute(pack, database, owner='synthetic-a', before_message_id=10, selection={'mode': 'auto'})
    assert result['outcomes'][0]['completion']['reason'] == 'history_tool_selection_blocked'
    assert not history.execution_plan('读取今天的日报', pack)['allow_mcp_tools']


def proxy_tree():
    path = ROOT / '.codex_runtime/qa-routing-v37/candidate-r2/ollama_proxy_server.py'
    if not path.exists():
        path = ROOT / '.codex_runtime/qa-routing-v36/candidate-r1/ollama_proxy_server.py'
    return ast.parse(path.read_text(encoding='utf-8'))


@pytest.mark.parametrize('suffix,expected_calls', [('不要查询现场数据库', 1), ('不要调用工具', 0)])
def test_actual_proxy_pure_history_branch_enforces_source_plan(database, suffix, expected_calls):
    branch = next(node for node in ast.walk(proxy_tree()) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "task_plan.get('intents') == ['conversation_history']")
    calls = []
    def fetch(conn, **kwargs):
        calls.append(kwargs)
        return {'ok': True}
    namespace = {'task_plan': planner.build_task_plan('列出我最近问过的顶压问题；' + suffix),
      'qa_task_plan': planner, 'use_mcp_tools': True, 'hidden_context': {},
      'tool_selection': {'mode': 'auto'}, 'qa_history_projection': SimpleNamespace(fetch_owned_history=fetch),
      'conn': database, 'owner_subject': 'synthetic-a', 'user_message_id': 10, 'question': 'synthetic'}
    exec(compile(ast.Module(body=[branch], type_ignores=[]), '<actual-history-source-gate>', 'exec'), namespace)
    assert len(calls) == expected_calls
    if calls:
        assert calls[0]['owner'] == 'synthetic-a' and calls[0]['before_message_id'] == 10
    else:
        assert namespace['history_result']['error'] == 'history_tool_selection_blocked'


def test_document_prefetch_cannot_reenable_globally_forbidden_live_source():
    original = planner.build_task_plan('解释三规二制原文；检索历史问答；不要查询现场数据库')
    prepared = {'hidden_context': {'qa_task_plan': original}, 'document_compound': {'remainder_question': '查询当前炉顶压力'}}
    assert not documents.prefetch_plan(prepared)['allow_prefetch']


def test_public_plan_exposes_constraint_flags_without_raw_text():
    public = planner.public_task_plan(planner.build_task_plan('列出我最近问过的顶压问题；不要调用工具'))
    assert public['no_live_lookup'] and public['all_tools_disabled']
    assert 'instruction_text' not in public and 'quoted_spans' not in public


@pytest.mark.parametrize('question', ['检索历史问答中炉顶压力的回答', '列出我最近问过的炉顶压力问题；不要查询现场数据库。'])
def test_history_selector_does_not_search_the_entire_instruction(database, question):
    result = projection.fetch_owned_history(database, owner='synthetic-a', before_message_id=10, question=question)
    assert result['keyword'] == '炉顶压力' and result['count'] == 1
    assert '其他身份' not in projection.history_outcome(result)['answer']


@pytest.mark.parametrize('question,expected', [
 ('读取今天的日报；不要查询现场数据库', True),
 ('查询当前炉顶压力；不要查询现场数据库', False),
 ('读取今天的日报；不要调用工具', False),
])
def test_actual_proxy_tool_gate_distinguishes_nonlive_source_from_all_tools(question, expected):
    function = next(node for node in proxy_tree().body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_should_use_tools')
    namespace = {'qa_evidence_policy': policy, 'qa_task_plan': planner, 'Any': object,
      'QA_MCP_TOOLS_ENABLED': True, 'QA_MCP_TOOL_MODE': 'auto',
      'qa_answer_route': lambda _: 'ordinary', 'QA_ANSWER_ROUTE_CODE': 'code',
      'qa_verified_facts': SimpleNamespace(reusable_latest_read=lambda *args: False)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-nonlive-tool-gate>', 'exec'), namespace)
    assert namespace['qa_mcp_should_use_tools'](question, {'use_mcp_tools': True}, {}) is expected


@pytest.mark.parametrize('question,expected_fallback', [
 ('读取今天的日报；不要查询现场数据库', False),
 ('查询当前炉顶压力；不要查询现场数据库', True),
 ('读取今天的日报；不要调用工具', True),
])
def test_actual_proxy_loop_does_not_replace_allowed_report_lookup_with_generic_answer(question, expected_fallback):
    function = next(node for node in proxy_tree().body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'qa_mcp_tool_loop_async')
    gate = next(node for node in function.body if isinstance(node, ast.If) and 'qa_mcp_no_realtime_requested(raw_question)' in ast.unparse(node.test))
    namespace = {'forced_mode': False, 'raw_question': question, 'task_plan': planner.build_task_plan(question),
                 'qa_mcp_no_realtime_requested': policy.no_live_lookup}
    condition = compile(ast.Expression(body=gate.test), '<actual-no-live-loop-gate>', 'eval')
    assert eval(condition, namespace) is expected_fallback


@pytest.mark.parametrize('suffix', ['不要调用工具', '不要查询数据库'])
def test_forbidden_document_lookup_never_reads_internal_database(suffix):
    calls = []
    class Connection:
        def execute(self, *args):
            calls.append('DB')
            return SimpleNamespace(fetchone=lambda: None)
    question = '请说明《三规二制》原文；' + suffix
    result = formal.execute_document_question(Connection(), question, planner.build_task_plan(question))
    assert calls == []
    assert result['completion']['reason'] == 'document_lookup_policy_blocked'


def test_forbidden_document_lookup_survives_compound_source_split(monkeypatch):
    calls = []
    def lookup(*args):
        calls.append('DB')
        return formal._outcome('synthetic', 'completed', 'verified')
    monkeypatch.setattr(formal, 'execute_document_question', lookup)
    question = '请说明《三规二制》原文；读取今天的日报；不要调用工具'
    pack = documents.prepare(None, question, planner.build_task_plan(question))
    assert calls == [] and '日报' in pack['remainder_question']
    assert pack['outcomes'][0]['completion']['reason'] == 'document_lookup_policy_blocked'
