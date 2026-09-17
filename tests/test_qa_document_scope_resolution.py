"""Formal book identity and complete explicit chapter scope, independent of models."""
import pytest

from test_qa_knowledge_reader_source_gate import ask, database, documents, pg_cluster, source
import qa_task_plan


@pytest.mark.parametrize('title', ['新版三规二制讲义', '其他公司的三规二制', '三规二制摘要'])
def test_unknown_quoted_title_never_queries_registered_book(title):
    class NoDatabase:
        calls = 0
        def execute(self, *args):
            self.calls += 1
            raise AssertionError('unknown source must not query registered book')
    conn = NoDatabase()
    question = f'完整列出《{title}》高炉工长原文'
    result = documents.execute_document_question(conn, question, qa_task_plan.build_task_plan(question))
    assert result['completion']['reason'] == 'document_reference_unresolved'
    assert conn.calls == 0


@pytest.mark.parametrize('title', ['三规二制', '冀钢炼铁三规二制'])
def test_registered_quoted_aliases_keep_correct_source(database, title):
    result = ask(database, f'完整列出《{title}》第27章原文')
    assert result['completion']['terminal_state'] == 'completed'
    assert result['completion']['coverage']['original_source']['original_source_scope_verified']


@pytest.mark.parametrize('selector', ['第27章和第28章', '第27、28章', '第27，28章',
                                     '第27至28章', '第27章到第28章'])
def test_every_explicit_chapter_is_answered(database, selector):
    result = ask(database, f'完整列出《三规二制》{selector}原文')
    assert result['completion']['terminal_state'] == 'completed'
    assert '岗位交接班制度' in result['answer'] and '生产联系确认制' in result['answer']
    assert '记录 | 交接' in result['answer'] and '联系 | 确认' in result['answer']
    # ask() independently asserts exactly one fixed snapshot SELECT.


@pytest.mark.parametrize('selector', ['第27章和第99章', '第27、99章', '第27至29章'])
def test_unknown_requested_chapter_cannot_be_silently_omitted(database, selector):
    result = ask(database, f'完整列出《三规二制》{selector}原文')
    assert result['completion']['terminal_state'] == 'needs_clarification'
    assert result['completion']['reason'] == 'chapter_unknown'


@pytest.mark.parametrize('selector', ['第27章高炉工长', '高炉工长第27章'])
def test_explicit_chapter_and_adjacent_role_cannot_contradict(database, selector):
    result = ask(database, f'完整列出《三规二制》{selector}原文')
    assert result['completion']['terminal_state'] == 'needs_clarification'
    assert result['completion']['reason'] == 'chapter_reference_conflict'


def test_reversed_chapter_range_needs_clarification(database):
    result = ask(database, '完整列出《三规二制》第28至27章原文')
    assert result['completion']['reason'] == 'chapter_range_invalid'


def test_atomic_clause_can_bind_role_from_explicit_chapter(database):
    result = ask(database, '《三规二制》第27章在“1 工作前”中，关于“未确认条件，不得操作”需要记住什么？请按原文回答。')
    assert result['completion']['terminal_state'] == 'completed'
    assert '岗位交接班制度' in result['answer'] and '高炉工长' not in result['answer']


def test_non_foreman_atomic_role_without_book_uses_registered_source(database):
    result = ask(database, '岗位交接班制度在“1 工作前”中，关于“未确认条件，不得操作”需要记住什么？请按原文回答。')
    assert result['completion']['terminal_state'] == 'completed'
    assert '岗位交接班制度' in result['answer'] and '高炉工长' not in result['answer']


def test_separate_named_role_and_explicit_chapter_union_is_not_a_conflict(database):
    result = ask(database, '完整列出《三规二制》第27章原文，同时列出高炉工长原文')
    assert result['completion']['terminal_state'] == 'completed'
    assert '岗位交接班制度' in result['answer'] and '高炉工长' in result['answer']
    assert '记录 | 交接' in result['answer'] and '设备 | 要求' in result['answer']


@pytest.mark.parametrize('separator', ['；同时', '；'])
def test_compound_scopes_keep_each_clause_regulation_filter(database, separator):
    result = ask(database, f'完整列出《三规二制》第27章原文{separator}列出高炉工长安全操作规程原文')
    assert result['completion']['terminal_state'] == 'completed'
    assert '记录 | 交接' in result['answer'] and '设备 | 要求' in result['answer']


def test_unavailable_requested_chapter_regulation_is_explicit_partial(database):
    result = ask(database, '完整列出《三规二制》第1章和第27章的安全操作规程原文')
    assert result['completion']['terminal_state'] == 'partial'
    assert result['completion']['coverage']['missing_chapters'] == ['岗位交接班制度']
    assert '设备 | 要求' in result['answer']
