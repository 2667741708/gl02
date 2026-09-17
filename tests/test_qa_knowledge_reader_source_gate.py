"""Original-source runtime entry with immutable synthetic expectations and native PG."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_keyword_source_transaction as tx
import qa_knowledge_source_binding as binding
import qa_knowledge_reader_source_gate as gate
import qa_document_knowledge as documents
import qa_document_compound as compound
import qa_task_plan
from test_qa_keyword_source_transaction import pg_cluster
from test_qa_knowledge_source_binding import encode


@pytest.fixture
def source(monkeypatch):
    specifications = [
        ('1', '高炉工长', '安全操作规程', ['1 工作前', '1.1 未确认条件，不得操作。', '设备 | 要求\n阀门 | 确认关闭']),
        ('27', '岗位交接班制度', '岗位交接班制度', ['1 工作前', '1.1 未确认条件，不得操作。', '记录 | 交接\n状态 | 双方确认']),
        ('28', '生产联系确认制', '生产联系确认制', ['1 工作前', '1.1 未联系确认，不得执行。', '联系 | 确认\n人员 | 接收确认']),
    ]
    chunks, atoms, block = [], [], 0
    for code, role, regulation, lines in specifications:
        start = block
        rows = [('atomic', str(i), text, start + i, start + i) for i, text in enumerate(lines)]
        rows += [('topic', '1', '\n'.join(lines[:2]), start, start + 1),
                 ('section', '1', '\n'.join(lines), start, start + len(lines) - 1)]
        atoms.extend(lines)
        block += len(lines)
        for kind, index, text, first, last in rows:
            chunks.append({
                'chunk_id': 'signed-' + code + '-' + kind + '-' + index,
                'granularity': kind, 'chapter_code': code, 'chapter_title': role,
                'regulation_type': regulation, 'section_code': '1', 'hierarchy_path': ['1 工作前'],
                'title': role + ' - ' + regulation + (' - 第1部分' if kind == 'section' else ' - ' + index),
                'source_block_start': first, 'source_block_end': last,
                'content': text, 'content_hash': binding.sha(text),
                'enriched_content': '【岗位/制度】' + code + '. ' + role + '\n【规程类型】' + regulation
                                    + '\n【层级路径】1 工作前\n【原文】\n' + text,
            })
    authority = '\n'.join(atoms)
    monkeypatch.setattr(binding, 'AUTHORITY_SHA', binding.sha(authority))
    fingerprints = []
    for chunk in chunks:
        fingerprints.append({key: chunk[key] for key in ('chunk_id', 'granularity', 'chapter_code',
                                                         'regulation_type', 'source_block_start', 'source_block_end')}
                            | {'content_sha256': chunk['content_hash'],
                               'enriched_content_sha256': binding.sha(chunk['enriched_content']),
                               'role_name_sha256': binding.sha(chunk['chapter_title'])})
    manifest = {'schema': 'bf.qa.source-scope-manifest.v1', 'source_docx_sha256': binding.SOURCE_SHA,
                'candidate_authority_sha256': binding.AUTHORITY_SHA, 'chunk_fingerprints': fingerprints,
                'item_gate': {'verified': True, 'semantic_verified': False, 'missing_occurrences': 0,
                              'extra_occurrences': 0, 'order_matches': True,
                              'expected_items': len(atoms), 'actual_items': len(atoms)},
                'chunk_gate': {'verified': True, 'semantic_verified': False, 'error_counts': {},
                               'chunks': len(chunks), 'atomics': len(atoms), 'topic_completeness_verified': False}}
    raw = encode(manifest)
    monkeypatch.setattr(binding, 'MANIFEST_SHA', tx.hashlib.sha256(raw).hexdigest())
    candidate = {'chunks': chunks}
    rows = binding.keyword_rows(candidate)
    doc = {'doc_id': binding.DOC_ID, 'version': binding.VERSION, 'full_text': authority,
           'content_hash': binding.AUTHORITY_SHA, 'title': '冀钢炼铁三规二制', 'source_file': 'synthetic-controlled-source',
           'knowledge_category': '三规二制', 'task_scope_json': '[]', 'authority_level': 'knowledge_doc',
           'created_at': '2026-01-01T00:00:00+00:00', 'updated_at': '2026-09-17T00:00:00+00:00'}
    signed = dict(doc_id=binding.DOC_ID, release_id=gate.RELEASE_ID, authority_sha256=binding.AUTHORITY_SHA,
                  manifest_sha256=binding.MANIFEST_SHA, manifest_text=raw.decode('utf-8'))
    rows = [dict(row, source_file=doc['source_file'], created_at=doc['updated_at']) for row in rows]
    snapshot = {'document': doc, 'chunks': rows, 'binding': signed, 'embedding_count': 0}
    # Expectations come from immutable fixture literals before DB insertion.
    doc_hash, rows_hash = gate.projection(doc, rows)
    monkeypatch.setattr(gate, 'DOC_SHA', doc_hash)
    monkeypatch.setattr(gate, 'CHUNKS_SHA', rows_hash)
    full = {'document': doc, 'chunks': sorted(rows, key=lambda row: row['chunk_id']), 'binding': signed, 'embeddings': []}
    snapshot['release'] = dict(release_id=gate.RELEASE_ID, doc_id=binding.DOC_ID, state='applied',
                               manifest_sha256=binding.MANIFEST_SHA, plan_sha256=gate.PLAN_SHA,
                               after_snapshot_sha256=gate.digest(full))
    return snapshot


@pytest.fixture
def database(pg_cluster, source):
    conn = pg_cluster()
    try:
        conn.execute('DROP SCHEMA IF EXISTS bf_assistant CASCADE')
        conn.execute((ROOT / 'tests/qa_regression/keyword_source_pg_fixture.sql').read_text(encoding='utf-8'))
        conn.execute((ROOT / 'schema/20260917_qa_keyword_source_release.sql').read_text(encoding='utf-8'))
        tx._insert(conn, tx.DOC, tx.DOC_COLUMNS, [source['document']])
        tx._insert(conn, tx.CHUNKS, tx.CHUNK_COLUMNS, source['chunks'])
        conn.execute(
            'INSERT INTO bf_assistant.qa_knowledge_source_releases '
            '(release_id,doc_id,state,before_snapshot_json,before_snapshot_sha256,after_snapshot_sha256,'
            'manifest_sha256,plan_sha256,applied_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (gate.RELEASE_ID, binding.DOC_ID, 'applied', Jsonb({}), '0' * 64,
             source['release']['after_snapshot_sha256'], binding.MANIFEST_SHA, gate.PLAN_SHA, datetime.now(timezone.utc)),
        )
        tx._insert(conn, tx.BINDINGS, tx.BINDING_COLUMNS, [source['binding']])
        conn.execute('SET search_path=bf_assistant,bf_sensor,public')
        conn.commit()
        yield conn
    finally:
        conn.close()


class QueryCounter:
    def __init__(self, connection):
        self.connection, self.queries = connection, []
    def execute(self, sql, params):
        self.queries.append(sql)
        return self.connection.execute(sql.replace('?', '%s'), params)


def ask(database, question):
    counter = QueryCounter(database)
    result = documents.execute_document_question(counter, question, qa_task_plan.build_task_plan(question))
    assert len(counter.queries) == 1 and counter.queries[0] == gate.SNAPSHOT_SQL
    return result


def test_signed_source_gate_is_independent_of_row_order_and_does_not_claim_semantics(source):
    source['chunks'].reverse()
    result = gate.verify(source)
    assert result['original_source_scope_verified'] and result['database_snapshot_verified']
    assert not result['semantic_verified'] and not result['topic_completeness_verified']
    assert result['model_calls'] == 0


@pytest.mark.parametrize('field', gate.CHUNK_FIELDS)
def test_every_actual_retrieval_field_is_bound_even_if_self_hashes_are_updated(source, field):
    changed = copy.deepcopy(source)
    changed['chunks'][0][field] = 'polluted'
    with pytest.raises(gate.ReaderSourceError):
        gate.verify(changed)


@pytest.mark.parametrize('field', gate.DOC_FIELDS)
def test_document_identity_and_full_original_are_fixed(source, field):
    source['document'][field] = 'polluted'
    with pytest.raises(gate.ReaderSourceError):
        gate.verify(source)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'extra', 'binding', 'release', 'rolled_back',
                                  'after_hash', 'manifest_bytes', 'path', 'vectors', 'vector_bool'])
def test_missing_polluted_or_stale_source_never_passes(source, change):
    if change == 'missing':
        source['chunks'].pop()
    elif change == 'duplicate':
        source['chunks'].append(copy.deepcopy(source['chunks'][0]))
    elif change == 'extra':
        source['chunks'].append(dict(source['chunks'][0], chunk_id='foreign-extra'))
    elif change in ('binding', 'release'):
        source[change] = None
    elif change == 'rolled_back':
        source['release']['state'] = 'rolled_back'
    elif change == 'after_hash':
        source['release']['after_snapshot_sha256'] = '0' * 64
    elif change == 'manifest_bytes':
        source['binding']['manifest_text'] += ' '
    elif change == 'path':
        source['chunks'][0]['source_file'] = 'another-reference'
    else:
        source['embedding_count'] = 1 if change == 'vectors' else False
    with pytest.raises(gate.ReaderSourceError):
        gate.verify(source)


@pytest.mark.parametrize('code,table,regulation', [
    (27, '状态 | 双方确认', '岗位交接班制度'), (28, '人员 | 接收确认', '生产联系确认制'),
])
def test_runtime_reads_complete_short_clauses_and_whole_tables_in_one_snapshot(database, code, table, regulation):
    result = ask(database, f'完整列出《三规二制》第{code}章{regulation}原文')
    assert result['completion']['terminal_state'] == 'completed'
    assert table in result['answer'] and '不得' in result['answer']
    assert result['completion']['coverage']['original_source']['original_source_scope_verified']
    assert result['model_request_count'] == 0


def test_atomic_same_wording_uses_requested_role_instead_of_fixed_high_furnace_foreman(database):
    result = ask(database, '岗位交接班制度在“1 工作前”中，关于“未确认条件，不得操作”需要记住什么？请按原文回答。')
    assert result['completion']['terminal_state'] == 'completed'
    assert '【岗位交接班制度 / 岗位交接班制度】' in result['answer']
    assert '【高炉工长 /' not in result['answer']


def test_unknown_named_role_does_not_expand_complete_request_to_whole_book(database):
    result = ask(database, '完整列出《三规二制》搬运工安全操作规程原文')
    assert result['completion']['terminal_state'] == 'needs_clarification'
    assert result['completion']['reason'] == 'chapter_selection_required'
    assert '阀门 | 确认关闭' not in result['answer']


def test_deleting_tail_after_verified_read_invalidates_next_result(database):
    q = '完整列出《三规二制》第27章岗位交接班制度原文'
    assert ask(database, q)['completion']['terminal_state'] == 'completed'
    database.execute("DELETE FROM rag_chunk WHERE chunk_id=%s", ('signed-27-atomic-2',))
    database.commit()
    result = ask(database, q)
    assert result['completion']['terminal_state'] == 'dependency_blocked'
    assert result['completion']['reason'] == 'original_source_fixed_projection_mismatch'
    assert '双方确认' not in result['answer']


def test_search_metadata_drift_is_not_hidden_by_document_hash_or_cache(database):
    q = '完整列出《三规二制》第28章生产联系确认制原文'
    assert ask(database, q)['completion']['terminal_state'] == 'completed'
    database.execute("UPDATE rag_chunk SET search_text=%s WHERE chunk_id=%s", ('polluted-source', 'signed-28-section-1'))
    database.commit()
    result = ask(database, q)
    assert result['completion']['terminal_state'] == 'dependency_blocked'


def test_missing_binding_preserves_compound_data_subtask_and_marks_partial(database):
    database.execute('DELETE FROM qa_knowledge_source_bindings')
    database.commit()
    q = '完整列出《三规二制》第27章岗位交接班制度原文；查看当前炉顶压力是多少'
    pack = compound.prepare(QueryCounter(database), q, qa_task_plan.build_task_plan(q))
    answer, result = compound.compose('实际只读压力事实', {'completion': {'terminal_state': 'completed'}},
                                     {'document_compound': pack})
    assert result['completion']['terminal_state'] == 'partial'
    assert '实际只读压力事实' in answer and '尚未通过核验' in answer
    assert pack['outcomes'][0]['completion']['reason'] == 'original_source_binding_unavailable'


def test_runtime_select_is_valid_with_startup_readonly_connection(database, pg_cluster):
    with pg_cluster(readonly=True) as reader:
        reader.execute('SET search_path=bf_assistant,bf_sensor,public')
        result = ask(reader, '完整列出《三规二制》第28章生产联系确认制原文')
        assert result['completion']['terminal_state'] == 'completed'
        assert reader.execute("SELECT current_setting('transaction_read_only') AS state").fetchone()['state'] == 'on'
        reader.rollback()


def test_concurrent_change_after_select_cannot_mix_versions_in_the_current_answer(database, pg_cluster):
    class CursorAfterSelect:
        def __init__(self, cursor):
            self.cursor = cursor
        def fetchone(self):
            frozen = self.cursor.fetchone()
            database.execute('UPDATE rag_chunk SET search_text=%s WHERE chunk_id=%s',
                             ('later-version', 'signed-27-section-1'))
            database.commit()
            return frozen
    class ChangeAfterSelect(QueryCounter):
        def execute(self, sql, params):
            return CursorAfterSelect(super().execute(sql, params))
    q = '完整列出《三规二制》第27章岗位交接班制度原文'
    with pg_cluster(readonly=True) as reader:
        reader.execute('SET search_path=bf_assistant,bf_sensor,public')
        wrapper = ChangeAfterSelect(reader)
        result = documents.execute_document_question(wrapper, q, qa_task_plan.build_task_plan(q))
        assert len(wrapper.queries) == 1 and result['completion']['terminal_state'] == 'completed'
        assert '状态 | 双方确认' in result['answer']
        assert ask(reader, q)['completion']['terminal_state'] == 'dependency_blocked'
        reader.rollback()
