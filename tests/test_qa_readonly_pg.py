"""Startup read-only must precede every audit query and schema initializer."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qa_readonly_pg', ROOT / 'tools/qa_readonly_pg.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class Cursor:
    def __init__(self, connection, rows=None):
        self.connection = connection
        self.rows = rows if rows is not None else [{'value': 7}]

    def execute(self, sql, params):
        self.connection.queries.append((sql, params))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def close(self):
        self.connection.events.append('cursor-close')


class Connection:
    def __init__(self):
        self.events, self.queries = [], []
        self.startup = {'default_readonly': 'on', 'transaction_readonly': 'on', 'active_schema': 'bf_assistant'}

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        return Cursor(self, [self.startup] if len(self.queries) == 1 else None)

    def cursor(self):
        return Cursor(self)

    def rollback(self):
        self.events.append('rollback')

    def close(self):
        self.events.append('close')

    def commit(self):
        pytest.fail('Audit must not commit')


@pytest.fixture
def runtime(monkeypatch):
    connection, calls = Connection(), []
    pg, psycopg, rows = ModuleType('assistant_pg'), ModuleType('psycopg'), ModuleType('psycopg.rows')
    pg.schema_name = lambda: 'bf_assistant'
    pg.pg_params = lambda: {'host': 'synthetic-host', 'user': 'synthetic-user', 'password': 'synthetic-secret', 'connect_timeout': 80}
    pg.raw_pg_connect = pg.ensure_schema_namespace = pg._get_connection_pool = lambda *args: pytest.fail('Unsafe assistant connector invoked')
    def connect(**params):
        calls.append(params)
        assert not connection.queries, 'Startup options must precede first query'
        return connection
    psycopg.connect, rows.dict_row = connect, object()
    for name, value in [('assistant_pg', pg), ('psycopg', psycopg), ('psycopg.rows', rows)]:
        monkeypatch.setitem(sys.modules, name, value)
    return SimpleNamespace(connection=connection, calls=calls, pg=pg, psycopg=psycopg)


def test_startup_readonly_and_existing_namespace_before_any_audit_query(runtime):
    with audit.readonly_pg_connect() as connection:
        assert connection.execute('SELECT value WHERE id=%s', (7,)).fetchone() == {'value': 7}
        assert len(runtime.connection.queries) == 2
        assert not hasattr(connection, 'commit')
        assert not hasattr(connection, 'executescript')
    options = runtime.calls[0]['options']
    assert 'default_transaction_read_only=on' in options
    assert 'search_path=bf_assistant,bf_sensor,public' in options
    assert 'statement_timeout=20000' in options and 'lock_timeout=3000' in options
    assert runtime.calls[0]['autocommit'] is False and runtime.calls[0]['connect_timeout'] == 8
    assert runtime.connection.queries[1][1] == (7,)
    assert runtime.connection.events == ['rollback', 'close']


@pytest.mark.parametrize('field,value', [('default_readonly', 'off'), ('transaction_readonly', 'off'),
                                       ('active_schema', 'public'), ('active_schema', None)])
def test_startup_mismatch_blocks_before_body(runtime, field, value):
    runtime.connection.startup[field] = value
    with pytest.raises(audit.ReadOnlyAuditUnavailable, match='startup verification'):
        with audit.readonly_pg_connect():
            pytest.fail('Audit body must not run')
    assert len(runtime.connection.queries) == 1
    assert runtime.connection.events == ['rollback', 'close']


@pytest.mark.parametrize('timeout', [True, False, 0, -1, 60001, 1.5, '20000', None])
def test_timeout_rejected_before_connection(runtime, timeout):
    with pytest.raises(audit.ReadOnlyAuditUnavailable):
        with audit.readonly_pg_connect(statement_timeout_ms=timeout):
            pytest.fail('Audit body must not run')
    assert not runtime.calls


@pytest.mark.parametrize('schema', ['bad;CREATE', 'space schema', 'quote"', 'bad-option=on', ''])
def test_schema_options_cannot_be_injected(runtime, schema):
    runtime.pg.schema_name = lambda: schema
    with pytest.raises(audit.ReadOnlyAuditUnavailable):
        with audit.readonly_pg_connect():
            pytest.fail('Audit body must not run')
    assert not runtime.calls


@pytest.mark.parametrize('sql', ['CREATE SCHEMA audit', 'SET transaction_read_only=off', 'INSERT INTO t VALUES(1)',
                                'DELETE FROM t', 'UPDATE t SET v=1', 'BEGIN', 'COMMIT',
                                'SELECT 1; SET default_transaction_read_only=off', None])
@pytest.mark.parametrize('via_cursor', [False, True])
def test_audit_rejects_mutation_and_multiple_statements_before_database(runtime, sql, via_cursor):
    with audit.readonly_pg_connect() as connection:
        target = connection.cursor() if via_cursor else connection
        before = len(runtime.connection.queries)
        with pytest.raises(audit.ReadOnlyAuditUnavailable, match='one parameterized SELECT'):
            target.execute(sql)
        assert len(runtime.connection.queries) == before


def test_body_failure_rolls_back_and_closes_without_commit(runtime):
    with pytest.raises(ValueError, match='synthetic body error'):
        with audit.readonly_pg_connect() as connection:
            connection.execute('SELECT 7')
            raise ValueError('synthetic body error')
    assert runtime.connection.events == ['rollback', 'close']


def test_connect_error_does_not_publish_credentials(runtime):
    def fail(**params):
        raise RuntimeError('synthetic-secret')
    runtime.psycopg.connect = fail
    with pytest.raises(audit.ReadOnlyAuditUnavailable) as error:
        with audit.readonly_pg_connect():
            pytest.fail('Audit body must not run')
    assert 'synthetic-secret' not in str(error.value)
    assert error.value.__suppress_context__


def test_rollback_error_still_closes(runtime):
    def fail():
        runtime.connection.events.append('rollback')
        raise RuntimeError('synthetic rollback failure')
    runtime.connection.rollback = fail
    with pytest.raises(RuntimeError, match='rollback failure'):
        with audit.readonly_pg_connect():
            pass
    assert runtime.connection.events == ['rollback', 'close']


def test_actual_compat_facade_retains_placeholder_binding_and_blocks_insert(runtime):
    actual_spec = importlib.util.spec_from_file_location('actual_assistant_pg', ROOT / '高炉前端数据/智能助手/backend/assistant_pg.py')
    actual = importlib.util.module_from_spec(actual_spec)
    sys.modules[actual_spec.name] = actual
    try:
        actual_spec.loader.exec_module(actual)
        with audit.readonly_pg_connect() as raw:
            connection = actual.PgCompatConnection(raw)
            assert connection.execute('SELECT value WHERE id=?', (7,)).fetchone() == {'value': 7}
            assert runtime.connection.queries[-1] == ('SELECT value WHERE id=%s', (7,))
            before = len(runtime.connection.queries)
            with pytest.raises(audit.ReadOnlyAuditUnavailable):
                connection.execute('INSERT INTO qa_messages(content) VALUES(?)', ('synthetic',))
            assert len(runtime.connection.queries) == before
    finally:
        sys.modules.pop(actual_spec.name, None)


@pytest.mark.parametrize('filename', ['audit_qa_document_provenance_readonly.py', 'audit_qa_context_provenance_readonly.py',
                                    'audit_qa_knowledge_manifest_readonly.py', 'check_qa_knowledge_candidate_readonly.py'])
def test_all_four_actual_audit_entrypoints_use_safe_connector(filename):
    source = (ROOT / 'tools' / filename).read_text(encoding='utf-8')
    tree = ast.parse(source)
    calls = [node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert 'readonly_pg_connect' in calls and 'raw_pg_connect' not in calls
    assert 'SET TRANSACTION READ ONLY' not in source.upper()


def test_probe_emits_heading_counts_not_original_text():
    probe_spec = importlib.util.spec_from_file_location('source_probe', ROOT / 'tools/probe_qa_readonly_pg.py')
    probe = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(probe)
    text = '1. 岗位甲……1\n2. 岗位乙....2\n1. 岗位甲三规二制\n安全操作规程\n1.1 原文机密\n2. 岗位乙\n'
    result = probe.source_heading_signals(text)
    assert result['toc_unique_codes'] == 2
    assert result['exact_body_heading_counts'] == {'1': 1, '2': 1}
    assert result['marked_chapter_heading_counts'] == {'1': 1}
    assert result['exact_regulation_heading_counts'] == {'安全操作规程': 1}
    assert result['scope_confirmed'] is False
    assert '原文机密' not in str(result) and '岗位甲' not in str(result)


def test_manifest_main_never_emits_sample_body_or_recorded_user_path(runtime, monkeypatch, tmp_path, capsys):
    config = tmp_path / 'tools/service_configs/22012_BFV4PreviewProxy8093.json'
    config.parent.mkdir(parents=True)
    config.write_text('{"env":{}}', encoding='utf-8')
    monkeypatch.setitem(sys.modules, 'qa_readonly_pg', audit)
    monkeypatch.setattr(sys, 'argv', ['audit', '--root', str(tmp_path)])
    original = runtime.connection.execute
    def execute(sql, params=()):
        if 'AS active_schema' in sql:
            return original(sql, params)
        runtime.connection.queries.append((sql, params))
        if 'FROM rag_document' in sql:
            return Cursor(runtime.connection, [{'doc_id': 'synthetic-book', 'title': 'Book', 'content_hash': 'hash',
                                               'source_file': 'C:/Users/PrivateIdentity/book.docx'}])
        if 'GROUP BY authority_level' in sql:
            return Cursor(runtime.connection, [])
        if 'to_regclass' in sql:
            return Cursor(runtime.connection, [{'relation': None}])
        if 'FROM rag_chunk' in sql:
            return Cursor(runtime.connection, [{'chunk_id': 'synthetic', 'chunk_type': 'three_rules_atomic', 'content_hash': 'hash',
                                               'header': 'PrivateOriginalClause', 'title': 'PrivateOriginalClause'}])
        pytest.fail('Unexpected audit query')
    runtime.connection.execute = execute
    manifest_spec = importlib.util.spec_from_file_location('actual_manifest', ROOT / 'tools/audit_qa_knowledge_manifest_readonly.py')
    manifest = importlib.util.module_from_spec(manifest_spec)
    manifest_spec.loader.exec_module(manifest)
    manifest.main()
    output = capsys.readouterr().out
    assert 'PrivateIdentity' not in output and 'PrivateOriginalClause' not in output
    result = json.loads(output)
    assert result['documents'] == [{'doc_id': 'synthetic-book', 'title': 'Book', 'content_hash': 'hash'}]
    assert result['samples'] == [{'chunk_id': 'synthetic', 'chunk_type': 'three_rules_atomic', 'content_hash': 'hash'}]
    assert all('source_file' not in sql and 'enriched_content' not in sql for sql, _ in runtime.connection.queries)


@pytest.mark.parametrize('matches', [True, False])
def test_original_docx_summary_distinguishes_bytes_from_scope_validation(matches):
    source_spec = importlib.util.spec_from_file_location('actual_source_audit', ROOT / 'tools/audit_qa_source_docx_readonly.py')
    source = importlib.util.module_from_spec(source_spec)
    source_spec.loader.exec_module(source)
    text = 'PrivateOriginalClause'
    expected = hashlib.sha256(text.encode()).hexdigest() if matches else '0' * 64
    item = SimpleNamespace(chapter_code='1', regulation_type='安全操作规程')
    chunks = [SimpleNamespace(content=text, granularity='atomic'), SimpleNamespace(content='NotAuthority', granularity='topic')]
    result = source.summarize({1: 'PrivateRole'}, [item], chunks, '1' * 64, expected)
    assert result['authority_bytes_match'] is matches
    assert result['scope_validation'] == 'shared_source_parser_preparation_only' and result['semantic_passed'] == 0
    assert result['chunk_counts'] == {'atomic': 1, 'topic': 1}
    assert 'PrivateOriginalClause' not in str(result) and 'PrivateRole' not in str(result)


@pytest.mark.parametrize('expected', ['', 'invalid', '0' * 63, '0' * 65])
def test_docx_comparison_requires_exact_authority_hash(expected):
    source_spec = importlib.util.spec_from_file_location('actual_source_audit', ROOT / 'tools/audit_qa_source_docx_readonly.py')
    source = importlib.util.module_from_spec(source_spec)
    source_spec.loader.exec_module(source)
    with pytest.raises(ValueError, match='authority SHA-256'):
        source.summarize({}, [], [], '1' * 64, expected)
