"""Actual owner-scoped SQL and immutable multi-turn object/window ancestry."""
import json
from pathlib import Path
import sqlite3
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '高炉前端数据/智能助手/backend'))
import mcp_conversation_context as context


def seed():
    return context.bind_persisted_context(context.update_tool_context(None, '最近两小时顶压趋势', ['P_top'], 120, now=1000), 11)


def test_multiple_followups_keep_original_sources_then_explicit_latest_resets_window():
    second = context.bind_persisted_context(context.update_tool_context(seed(), '画出来', [], None, now=1100), 15)
    third = context.bind_persisted_context(context.update_tool_context(second, '继续', [], None, now=1200), 19)
    assert third['source_message_id'] == 19
    assert third['inheritance_provenance']['objects']['sources'] == {'P_top': 11}
    assert third['inheritance_provenance']['time_range']['source_message_id'] == 11
    latest = context.bind_persisted_context(context.update_tool_context(third, '它现在是多少', [], None, now=1250), 23)
    assert latest['inheritance_provenance']['objects']['sources'] == {'P_top': 11}
    assert latest['time_range'] is None and latest['inheritance_provenance']['time_range']['source_message_id'] is None
    assert latest['last_evidence'] == [] and latest['evidence_reuse'] is False


def test_added_object_has_its_own_turn_source_and_window_keeps_origin():
    second = context.bind_persisted_context(context.update_tool_context(seed(), '再加上总压差比较', ['DP_total'], None, now=1100), 15)
    assert second['inheritance_provenance']['objects']['sources'] == {'P_top': 11, 'DP_total': 15}
    assert second['inheritance_provenance']['time_range']['source_message_id'] == 11


@pytest.mark.parametrize('question,objects,minutes', [('新问题查当前风温', ['T_hotblast'], None),
                                                    ('这个最近30分钟趋势', [], 30)])
def test_explicit_replacement_anchors_only_changed_fields(question, objects, minutes):
    state = context.bind_persisted_context(context.update_tool_context(seed(), question, objects, minutes, now=1100), 15)
    if objects:
        assert state['inheritance_provenance']['objects']['sources'] == {'T_hotblast': 15}
    if minutes:
        assert state['inheritance_provenance']['time_range']['source_message_id'] == 15


@pytest.mark.parametrize('bad', [True, 0, -1, '11', None])
def test_client_shaped_message_ids_cannot_bind(bad):
    with pytest.raises(ValueError): context.bind_persisted_context(seed(), bad)


@pytest.fixture
def conn():
    database = sqlite3.connect(':memory:')
    database.row_factory = sqlite3.Row
    database.executescript('''CREATE TABLE qa_conversations(id TEXT, owner_subject TEXT);
        CREATE TABLE qa_messages(id INTEGER, conversation_id TEXT, role TEXT, hidden_context_json TEXT);
        INSERT INTO qa_conversations VALUES('a','owner-a'),('b','owner-b');''')
    hidden = json.dumps({'mcp_conversation_context': seed()})
    database.executemany('INSERT INTO qa_messages VALUES(?,?,?,?)',
                        [(11, 'a', 'user', hidden), (13, 'a', 'assistant', hidden), (21, 'b', 'user', hidden)])
    yield database
    database.close()


def test_actual_sql_load_is_owner_bound_and_uses_user_turn_not_assistant(conn):
    state = context.load_owned_tool_context(conn, 'a', 'owner-a')
    assert state['source_message_id'] == 11
    assert context.load_owned_tool_context(conn, 'a', 'owner-b') is None
    assert context.load_owned_tool_context(conn, 'b', 'owner-a') is None
    assert context.load_owned_tool_context(conn, 'a', '') is None


def test_existing_v2_user_state_is_bound_to_authorized_persisted_row(conn):
    legacy = context.update_tool_context(None, '顶压趋势', ['P_top'], 60, now=1200)
    conn.execute('INSERT INTO qa_messages VALUES(?,?,?,?)', (25, 'a', 'user', json.dumps({'mcp_conversation_context': legacy})))
    state = context.load_owned_tool_context(conn, 'a', 'owner-a')
    assert state['inheritance_provenance']['objects']['sources'] == {'P_top': 25}
    assert state['inheritance_provenance']['time_range']['source_message_id'] == 25


@pytest.mark.parametrize('conversation,owner,message_id', [('a','owner-b',11), ('b','owner-a',21),
                                                         ('a','owner-a',13), ('a','owner-a',21)])
def test_actual_sql_persist_cannot_write_wrong_owner_role_or_conversation(conn, conversation, owner, message_id):
    original = conn.execute('SELECT hidden_context_json FROM qa_messages WHERE id=?', (message_id,)).fetchone()[0]
    with pytest.raises(ValueError):
        context.persist_owned_context_binding(conn, conversation, owner, message_id, {'mcp_conversation_context': seed()})
    assert conn.execute('SELECT hidden_context_json FROM qa_messages WHERE id=?', (message_id,)).fetchone()[0] == original


def test_persist_binding_does_not_mutate_caller_and_is_read_back_with_sql(conn):
    hidden = {'mcp_conversation_context': context.update_tool_context(seed(), '再加上总压差比较', ['DP_total'], None, now=1100), 'other': 'kept'}
    conn.execute('INSERT INTO qa_messages VALUES(?,?,?,?)', (15, 'a', 'user', json.dumps(hidden)))
    bound = context.persist_owned_context_binding(conn, 'a', 'owner-a', 15, hidden)
    assert 'source_message_id' not in hidden['mcp_conversation_context'] and bound['other'] == 'kept'
    loaded = context.load_owned_tool_context(conn, 'a', 'owner-a')
    assert loaded['inheritance_provenance']['objects']['sources'] == {'P_top': 11, 'DP_total': 15}


def test_malformed_or_future_ancestry_is_not_trusted():
    state = seed()
    state['inheritance_provenance']['objects']['sources']['P_top'] = 999
    state['inheritance_provenance']['time_range']['source_message_id'] = True
    bound = context.bind_persisted_context(state, 15)
    assert bound['inheritance_provenance']['objects']['sources'] == {'P_top': 15}
    assert bound['inheritance_provenance']['time_range']['source_message_id'] == 15
    state['inheritance_provenance'] = ['corrupt']
    assert context.bind_persisted_context(state, 15)['source_message_id'] == 15


def test_persisted_ancestry_cannot_reference_another_owners_turn(conn):
    poisoned = seed()
    poisoned['inheritance_provenance']['objects']['sources']['P_top'] = 21
    conn.execute('INSERT INTO qa_messages VALUES(?,?,?,?)', (25, 'a', 'user', json.dumps({'mcp_conversation_context': poisoned})))
    assert context.load_owned_tool_context(conn, 'a', 'owner-a') is None
    with pytest.raises(ValueError, match='ancestry'):
        context.persist_owned_context_binding(conn, 'a', 'owner-a', 25, {'mcp_conversation_context': poisoned})


def test_actual_production_cursor_adapter_without_rowcount_supports_binding(conn):
    from assistant_pg import PgCompatConnection, CursorAdapter
    class RawCursor:
        def execute(self, sql, args):
            self.cursor = conn.execute(sql.replace('%s', '?'), args)
        def fetchall(self): return self.cursor.fetchall()
        def fetchone(self): return self.cursor.fetchone()
    class RawConnection:
        def cursor(self): return RawCursor()
        def commit(self): conn.commit()
    wrapped = PgCompatConnection(RawConnection())
    assert not hasattr(CursorAdapter(None), 'rowcount')
    bound = context.persist_owned_context_binding(wrapped, 'a', 'owner-a', 11,
                                                  {'mcp_conversation_context': seed()})
    assert bound['mcp_conversation_context']['source_message_id'] == 11
    assert context.load_owned_tool_context(wrapped, 'a', 'owner-a')['source_message_id'] == 11
    with pytest.raises(ValueError):
        context.persist_owned_context_binding(wrapped, 'a', 'owner-b', 11,
                                             {'mcp_conversation_context': seed()})
