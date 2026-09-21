"""Explicit source exclusions must survive compound routing and child plans."""
import ast
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_task_plan as planner
import qa_document_knowledge as documents
import qa_document_compound as document_compound
import qa_history_compound as history
from test_qa_declared_input_scope import actual_proxy_scope
from test_qa_source_concept_scope import test_actual_proxy_owned_history_entry_keeps_scope_and_policy as check_owned_history_entry
from qa_frozen_candidate import latest_frozen_candidate


EXCLUSIONS = [
 ('不要查询聊天记录', 'conversation_history', 'search_qa_messages'),
 ('禁止读取历史问答', 'conversation_history', 'search_qa_messages'),
 ('不用检索对话记录', 'conversation_history', 'search_qa_messages'),
 ('不要读取日报', 'period_report', 'read_report_excerpt'),
 ('不需要查询生产报告', 'period_report', 'list_recent_reports'),
 ('不要引用制度原文', 'document_knowledge', None),
 ('不要查三规二制', 'document_knowledge', None),
]


class NoDatabaseRead:
    def __init__(self):
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError('The source was explicitly excluded')


@pytest.mark.parametrize('exclusion,intent,tool', EXCLUSIONS)
def test_excluded_source_does_not_create_live_compound_subtask(exclusion, intent, tool):
    question = exclusion + '；查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['live_data']
    assert plan['allow_mcp_tools'] and plan['allow_prefetch']
    assert planner.tool_allowed('query_gl02_sensors', plan)
    if tool:
        assert not planner.tool_allowed(tool, plan)
    assert history.split_request(question, plan) is None
    assert document_compound.prepare(NoDatabaseRead(), question, plan) is None


@pytest.mark.parametrize('exclusion,intent,tool', EXCLUSIONS)
def test_excluded_source_does_not_short_circuit_ordinary_explanation(exclusion, intent, tool):
    question = exclusion + '；解释提高风温的一般原因'
    plan = planner.build_task_plan(question)
    assert intent not in plan['intents']
    assert not plan['allow_mcp_tools'] and not plan['allow_prefetch']
    conn = NoDatabaseRead()
    assert documents.execute_document_question(conn, question, plan) is None
    assert conn.calls == 0


@pytest.mark.parametrize('exclusion,intent,tool,source_question', [
 ('不要读取聊天记录', 'conversation_history', 'search_qa_messages', '列出我最近问过什么问题'),
 ('禁止查询历史问答', 'conversation_history', 'search_qa_messages', '检索历史问答中顶压的回答'),
 ('不要读取日报', 'period_report', 'read_report_excerpt', '读取最新日报内容'),
 ('不要引用制度原文', 'document_knowledge', None, '按原文解释三规二制'),
])
def test_later_source_keyword_does_not_remove_global_exclusion(exclusion, intent, tool, source_question):
    plan = planner.build_task_plan(exclusion + '；' + source_question)
    assert intent in plan['intents']
    if tool:
        assert not planner.tool_allowed(tool, plan)
    else:
        conn = NoDatabaseRead()
        result = documents.execute_document_question(conn, exclusion + '；' + source_question, plan)
        assert result['completion']['reason'] == 'document_lookup_policy_blocked'
        assert conn.calls == 0


@pytest.mark.parametrize('suffix', ['查询当前炉顶压力', '读取最新日报内容'])
def test_compound_history_exclusion_is_propagated_to_execution_and_child_plan(monkeypatch, suffix):
    question = '不要读取聊天记录；列出我最近问过什么问题；' + suffix
    plan = planner.build_task_plan(question)
    pack = history.split_request(question, plan)
    calls = []
    monkeypatch.setattr(history.qa_history_projection, 'fetch_owned_history', lambda *args, **kwargs: calls.append(kwargs) or {'ok': True})
    result = history.execute(pack, NoDatabaseRead(), owner='synthetic-owner', before_message_id=10, selection={'mode': 'auto'})
    assert calls == []
    assert result['outcomes'][0]['completion']['terminal_state'] == 'dependency_blocked'
    child = history.execution_plan(pack['remainder_question'], pack)
    assert not planner.tool_allowed('search_qa_messages', child)
    assert planner.tool_allowed('query_gl02_sensors' if '当前' in suffix else 'read_report_excerpt', child)


def test_compound_formal_exclusion_is_checked_before_any_reader_call():
    question = '不要引用制度原文；按原文解释三规二制；查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    conn = NoDatabaseRead()
    pack = document_compound.prepare(conn, question, plan)
    assert conn.calls == 0
    assert all(item['completion']['reason'] == 'document_lookup_policy_blocked' for item in pack['outcomes'])


@pytest.mark.parametrize('question,intent', [
 ('解释“不要读取日报”这句话的含义', None),
 ('查询聊天记录；查询当前炉顶压力', 'conversation_history'),
 ('读取最新日报内容；查询当前炉顶压力', 'period_report'),
 ('按原文解释《三规二制》；查询当前炉顶压力', 'document_knowledge'),
])
def test_quoted_negation_and_positive_sources_preserve_existing_contracts(question, intent):
    plan = planner.build_task_plan(question)
    if intent:
        assert intent in plan['intents']
        assert plan['allow_mcp_tools'] and planner.tool_allowed('query_gl02_sensors', plan)
    else:
        assert not plan['allow_mcp_tools'] and not plan['all_tools_disabled']


@pytest.mark.parametrize('question', [
 '不要查询聊天记录但查询当前炉顶压力',
 '不要读取日报但是查询当前炉顶压力',
 '不要引用制度原文不过查询当前炉顶压力',
 '查询当前炉顶压力不要查询聊天记录',
 '查询当前炉顶压力不要读取日报',
 '查询当前炉顶压力不要引用制度原文',
])
def test_source_exclusion_can_be_separated_without_punctuation(question):
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['live_data']
    assert planner.tool_allowed('query_gl02_sensors', plan)


def test_excluded_report_objects_do_not_contaminate_live_object_or_query_text():
    question = '不要读取日报中风温变化；查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['live_data']
    assert planner.live_query_text(question) == '查询当前炉顶压力'


def test_excluded_named_book_preserves_explicit_document_lookup_prohibition():
    question = '不要读取《三规二制》；按原文解释三规二制'
    plan = planner.build_task_plan(question)
    assert plan['excluded_document_titles'] == ['三规二制'] and not plan['search_knowledge']
    assert documents.execute_document_question(NoDatabaseRead(), question, plan)['completion']['reason'] == 'document_lookup_policy_blocked'


def test_public_constraint_metadata_contains_no_raw_source_or_question():
    question = '不要读取《合成制度名称》；查询当前炉顶压力'
    public = planner.public_task_plan(planner.build_task_plan(question))
    assert public['excluded_document_count'] == 1
    assert question not in str(public) and '合成制度名称' not in str(public)


def test_actual_proxy_aliases_ignore_excluded_report_object():
    tree, scope = actual_proxy_scope()
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'qa_mcp_variables')
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-excluded-source-aliases>', 'exec'), scope)
    assert scope['qa_mcp_variables']('不要读取日报中风温变化；查询当前炉顶压力') == ['P_top']


@pytest.mark.parametrize('question,expected_calls', [
 ('不要读取聊天记录；列出我最近问过什么问题', 0),
 ('列出我最近问过什么问题；禁止查询聊天记录', 0),
 ('解释“不要读取聊天记录”这句话；列出我最近问过什么问题', 1),
])
def test_actual_proxy_owned_history_entry_checks_global_source_exclusions(question, expected_calls):
    check_owned_history_entry(question, expected_calls)


def test_frozen_source_exclusion_candidate_preserves_base_and_unrelated_runtime():
    # Historical acceptance binds its own immutable V43 closure. Current entry
    # executions bind the newest fully hash-verified closure independently.
    candidate = ROOT / '.codex_runtime/qa-routing-v43/candidate-r6'
    manifest_raw = (candidate / 'package_manifest.private.json').read_bytes()
    manifest = json.loads(manifest_raw)
    evidence = json.loads((ROOT / 'tests/qa_regression/source_exclusion_scope_20260917.json').read_bytes())
    assert hashlib.sha256(manifest_raw).hexdigest() == evidence['private_candidate']['manifest_sha256']
    prior = ROOT / '.codex_runtime/qa-routing-v42/candidate-r1'
    public = json.loads((ROOT / 'tests/qa_regression/source_concept_scope_20260917.json').read_bytes())
    assert hashlib.sha256((prior / 'package_manifest.private.json').read_bytes()).hexdigest() == public['private_candidate']['manifest_sha256']
    assert len(manifest['files']) == 15 and len(manifest['inherited_v42_files_byte_identical']) == 11
    assert set(manifest['changed_modules']) == {'qa_task_plan.py', 'qa_document_compound.py', 'qa_document_knowledge.py', 'qa_history_compound.py'}
    assert manifest['model_name'] == 'chiqiongblastfuenace:latest'
    assert manifest['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(manifest[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    for name, item in manifest['files'].items():
        assert hashlib.sha256((candidate / name).read_bytes()).hexdigest() == item['sha256']
    for name in manifest['inherited_v42_files_byte_identical']:
        assert (candidate / name).read_bytes() == (prior / name).read_bytes()
    current, current_manifest = latest_frozen_candidate(ROOT)
    for name in manifest['changed_modules']:
        assert (current / name).read_bytes() == (ROOT / '高炉前端数据/智能助手/backend' / name).read_bytes()
        assert hashlib.sha256((current / name).read_bytes()).hexdigest() == current_manifest['files'][name]['sha256']


@pytest.mark.parametrize('excluded_title,allowed_title,expected_calls', [
 ('旧规程', '新规程', 0),
 ('旧规程', '三规二制', 1),
 ('高炉事故处理', '三规二制', 1),
 ('三规二制', '冀钢炼铁三规二制', 0),
 ('三规二制', '三规二制', 0),
])
def test_named_source_exclusion_does_not_forbid_another_allowed_book(excluded_title, allowed_title, expected_calls):
    question = f'不要引用《{excluded_title}》；请按原文解释《{allowed_title}》'
    plan = planner.build_task_plan(question)
    conn = NoDatabaseRead()
    result = documents.execute_document_question(conn, question, plan)
    assert conn.calls == expected_calls
    same_source = excluded_title == allowed_title or {excluded_title, allowed_title} <= {'三规二制', '冀钢炼铁三规二制'}
    if same_source:
        assert result['completion']['reason'] == 'document_lookup_policy_blocked'
    elif expected_calls:
        assert result['completion']['reason'] == 'original_source_snapshot_unavailable'
    else:
        assert result['completion']['reason'] == 'document_reference_unresolved'


def test_named_exclusion_survives_compound_document_child_plan():
    question = '不要引用《三规二制》；按原文解释《冀钢炼铁三规二制》；查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    conn = NoDatabaseRead()
    pack = document_compound.prepare(conn, question, plan)
    assert conn.calls == 0
    assert all(item['completion']['reason'] == 'document_lookup_policy_blocked' for item in pack['outcomes'])


def test_different_allowed_book_is_not_blocked_by_compound_named_exclusion():
    question = '不要引用《旧规程》；按原文解释《三规二制》；查询当前炉顶压力'
    plan = planner.build_task_plan(question)
    conn = NoDatabaseRead()
    pack = document_compound.prepare(conn, question, plan)
    assert conn.calls == 1
    assert all(item['completion']['reason'] == 'original_source_snapshot_unavailable' for item in pack['outcomes'])


@pytest.mark.parametrize('separator', ['并引用', '同时依据', '以及读取', '并按原文解释', '但是引用', '并总结', '并根据', '并且读取', '且引用'])
def test_named_negative_and_positive_book_actions_split_without_punctuation(separator):
    question = '不要引用《旧规程》' + separator + '《三规二制》'
    plan = planner.build_task_plan(question)
    assert plan['intents'] == ['document_knowledge']
    assert planner.active_source_clauses(question) == [separator + '《三规二制》']
    conn = NoDatabaseRead()
    result = documents.execute_document_question(conn, question, plan)
    assert conn.calls == 1 and result['completion']['reason'] == 'original_source_snapshot_unavailable'


def test_multiple_named_prohibited_books_keep_independent_allowed_book():
    question = '不要引用《旧规程》和《过期规程》；请按原文解释《三规二制》'
    plan = planner.build_task_plan(question)
    assert plan['excluded_document_titles'] == ['旧规程', '过期规程']
    conn = NoDatabaseRead()
    result = documents.execute_document_question(conn, question, plan)
    assert conn.calls == 1 and result['completion']['reason'] == 'original_source_snapshot_unavailable'


@pytest.mark.parametrize('source_question,expected_calls,reason', [
 ('不要读取三规二制；按原文解释《新规程》', 0, 'document_reference_unresolved'),
 ('不要读取高炉事故处理；按原文解释《三规二制》', 1, 'original_source_snapshot_unavailable'),
 ('不要读取冀钢炼铁三规二制；按原文解释《三规二制》', 0, 'document_lookup_policy_blocked'),
])
def test_unquoted_known_book_alias_has_exact_source_scope(source_question, expected_calls, reason):
    plan = planner.build_task_plan(source_question)
    conn = NoDatabaseRead()
    result = documents.execute_document_question(conn, source_question, plan)
    assert conn.calls == expected_calls and result['completion']['reason'] == reason


def test_negative_bare_book_keeps_its_verb_when_other_book_is_requested():
    question = '不要引用三规二制；引用高炉事故处理'
    assert planner.instruction_clauses(question) == ['不要引用三规二制', '引用高炉事故处理']
    plan = planner.build_task_plan(question)
    assert plan['excluded_document_titles'] == ['三规二制']
    assert planner.active_source_clauses(question) == ['引用高炉事故处理']


def test_explicit_knowledge_base_exclusion_disables_general_keyword_retrieval():
    plan = planner.build_task_plan('不要查询知识库；解释风温升高的一般原因')
    assert plan['source_exclusions'] == ['knowledge_base']
    assert not plan['search_knowledge'] and not plan['allow_mcp_tools']


def test_explicit_knowledge_base_exclusion_also_blocks_direct_formal_reader():
    question = '禁止检索知识库；按原文解释《三规二制》'
    conn = NoDatabaseRead()
    result = documents.execute_document_question(conn, question, planner.build_task_plan(question))
    assert conn.calls == 0 and result['completion']['reason'] == 'document_lookup_policy_blocked'
