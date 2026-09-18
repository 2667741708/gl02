"""Explicit regulation and hierarchy fidelity, never substitute a same-word clause."""
import json
import pytest

from test_qa_document_knowledge import add_atomic, append_authority, connection, digest, run as selection_run
from test_qa_knowledge_reader_source_gate import ask as public_ask, database, pg_cluster, source


def run(conn, question):
    result = selection_run(conn, question)
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    return result


def ask(conn, question):
    result = public_ask(conn, question)
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    return result


def atomic_question(scope, wording='共同提示'):
    return f'《三规二制》{scope}在“1 工作前”中，关于“{wording}”需要记住什么？请按原文回答。'


def two_regulations(conn):
    add_atomic(conn, '1.1 共同提示：安全版条款。', regulation='安全操作规程')
    add_atomic(conn, '1.2 共同提示：技术版条款。', regulation='技术操作规程', chunk_id='technical-atomic')


@pytest.mark.parametrize('role,regulation', [('高炉工长', '技术操作规程'),
                                           ('岗位交接班制度', '安全操作规程')])
def test_public_atomic_entry_does_not_substitute_another_regulation(database, role, regulation):
    result = ask(database, atomic_question(role + '的' + regulation, '未确认条件，不得操作'))
    assert result['completion']['terminal_state'] == 'needs_clarification'
    assert result['completion']['reason'] == 'atomic_reference_not_found'


@pytest.mark.parametrize('regulation,expected,excluded', [('安全操作规程', '安全版', '技术版'),
                                                       ('技术操作规程', '技术版', '安全版')])
def test_same_wording_is_resolved_inside_explicit_regulation(connection, regulation, expected, excluded):
    two_regulations(connection)
    result = run(connection, atomic_question('高炉工长的' + regulation))
    assert result['completion']['terminal_state'] == 'completed'
    assert expected in result['answer'] and excluded not in result['answer']


def test_without_regulation_same_wording_stays_ambiguous(connection):
    two_regulations(connection)
    assert run(connection, atomic_question('高炉工长'))['completion']['reason'] == 'atomic_reference_ambiguous'


def test_ranking_cannot_prefer_an_exact_match_in_the_wrong_regulation(connection):
    add_atomic(connection, '1.1 共同提示：安全版条款。')
    add_atomic(connection, '1.2 共同提示指标：技术版条款。', regulation='技术操作规程', chunk_id='technical-prefix')
    result = run(connection, atomic_question('高炉工长的技术操作规程'))
    assert result['completion']['terminal_state'] == 'completed'
    assert '技术版' in result['answer'] and '安全版' not in result['answer']


@pytest.mark.parametrize('scope', ['高炉工长不要引用安全操作规程，只按技术操作规程',
                                 '高炉工长不是安全操作规程，按技术操作规程'])
def test_negative_regulation_is_not_a_positive_request(connection, scope):
    two_regulations(connection)
    result = run(connection, atomic_question(scope))
    assert result['completion']['terminal_state'] == 'completed'
    assert '技术版' in result['answer'] and '安全版' not in result['answer']


def test_exclusion_only_does_not_fall_back_to_the_forbidden_regulation(connection):
    two_regulations(connection)
    result = run(connection, atomic_question('高炉工长不要引用安全操作规程'))
    assert result['completion']['terminal_state'] == 'completed'
    assert '技术版' in result['answer'] and '安全版' not in result['answer']


def test_multiple_explicit_regulations_return_each_unique_original(connection):
    two_regulations(connection)
    result = run(connection, atomic_question('高炉工长分别按安全操作规程和技术操作规程'))
    assert result['completion']['terminal_state'] == 'completed'
    assert '技术版' in result['answer'] and '安全版' in result['answer']
    assert result['completion']['coverage']['matched_scopes'] == 2


def test_missing_requested_regulation_keeps_verified_original_as_partial(connection):
    add_atomic(connection, '1.1 共同提示：安全版条款。')
    result = run(connection, atomic_question('高炉工长分别按安全操作规程和技术操作规程'))
    assert result['completion']['terminal_state'] == 'partial'
    assert result['completion']['coverage']['missing_regulations'] == ['技术操作规程']
    assert '安全版' in result['answer']


def test_public_whole_scope_does_not_treat_role_name_as_an_extra_regulation(database):
    result = ask(database, '完整列出《三规二制》岗位交接班制度的安全操作规程原文')
    assert result['completion']['terminal_state'] == 'dependency_blocked'
    assert result['completion']['reason'] == 'requested_scope_missing'


def test_regulation_name_in_quoted_clause_is_literal_not_a_filter(connection):
    add_atomic(connection, '1.1 技术操作规程的引用必须核验。')
    result = run(connection, atomic_question('高炉工长', '技术操作规程的引用'))
    assert result['completion']['terminal_state'] == 'completed'
    assert '安全操作规程' in result['answer']


def test_another_role_in_quoted_clause_is_literal_not_an_extra_scope(connection):
    body = '2 交接说明'
    header = '【岗位/制度】27. 岗位交接班制度\n【规程类型】岗位交接班制度\n【原文】\n' + body
    connection.execute('INSERT INTO rag_chunk VALUES(?,?,?,?,?,?,?,?)',
                       ('another-role-section', 'bf_three_rules_two_systems_20260712',
                        '岗位交接班制度 - 岗位交接班制度 - 第1部分', body, header,
                        digest(body), 'knowledge_doc', 'three_rules_section'))
    append_authority(connection, body)
    add_atomic(connection, '1.1 必须联系岗位交接班制度负责人并确认。')
    result = run(connection, atomic_question('高炉工长', '必须联系岗位交接班制度负责人'))
    assert result['completion']['terminal_state'] == 'completed'
    assert '【高炉工长 / 安全操作规程】' in result['answer']


@pytest.mark.parametrize('actual_path,requested_path', [('11 工作前', '1 工作前'),
                                                       ('11.1 工作前', '1.1 工作前')])
def test_hierarchy_number_cannot_match_a_substring_of_another_number(connection, actual_path, requested_path):
    add_atomic(connection, '1.1 共同提示：安全版条款。', path=actual_path)
    question = atomic_question('高炉工长').replace('“1 工作前”', '“' + requested_path + '”')
    assert run(connection, question)['completion']['reason'] == 'atomic_reference_not_found'


def test_public_multiple_regulations_reports_each_missing_type(database):
    result = ask(database, atomic_question('第27章分别按岗位交接班制度和安全操作规程', '未确认条件，不得操作'))
    assert result['completion']['terminal_state'] == 'partial'
    assert result['completion']['coverage']['missing_regulations'] == ['安全操作规程']


def test_whole_chapter_missing_type_is_partial_even_when_role_is_present(database):
    result = ask(database, '完整列出《三规二制》高炉工长的安全操作规程和技术操作规程原文')
    assert result['completion']['terminal_state'] == 'partial'
    assert result['completion']['coverage']['missing_regulations_by_chapter'] == {'高炉工长': ['技术操作规程']}


def test_contradictory_positive_and_negative_regulation_is_clarification(connection):
    two_regulations(connection)
    result = run(connection, atomic_question('高炉工长按安全操作规程，但不引用安全操作规程'))
    assert result['completion']['terminal_state'] == 'needs_clarification'
    assert result['completion']['reason'] == 'regulation_scope_conflict'


def test_multiple_atomic_blocks_are_paged_without_cutting_table(connection):
    safety = '1.1 共同提示：安全版。\n名称 | 要求\n' + '甲 | 安全表格行\n' * 1400
    technical = '1.2 共同提示：技术版。\n名称 | 要求\n' + '乙 | 技术表格行\n' * 1400
    add_atomic(connection, safety)
    add_atomic(connection, technical, regulation='技术操作规程', chunk_id='large-technical')
    question = atomic_question('高炉工长分别按安全操作规程和技术操作规程')
    first = run(connection, question)
    assert first['completion']['terminal_state'] == 'partial'
    assert first['completion']['coverage']['pages'] == 2
    assert safety in first['answer'] and technical not in first['answer']
    second = run(connection, question + '读取第2页。')
    assert second['completion']['terminal_state'] == 'partial'
    assert technical in second['answer'] and safety not in second['answer']


def test_multiple_atomic_page_out_of_bounds_is_clarification(connection):
    two_regulations(connection)
    result = run(connection, atomic_question('高炉工长分别按安全操作规程和技术操作规程') + '读取第99页。')
    assert result['completion']['reason'] == 'page_out_of_range'


def test_one_ambiguous_type_keeps_another_unique_type_as_partial(connection):
    two_regulations(connection)
    add_atomic(connection, '1.3 共同提示：另一个安全版条款。', chunk_id='ambiguous-safety')
    result = run(connection, atomic_question('高炉工长分别按安全操作规程和技术操作规程'))
    assert result['completion']['terminal_state'] == 'partial'
    assert result['completion']['coverage']['ambiguous_regulations'] == ['安全操作规程']
    assert '技术版' in result['answer'] and '另一个安全版' not in result['answer']
