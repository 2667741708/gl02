"""Real isolated native PostgreSQL/pgvector tests; no production connection."""
import copy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import socket
import subprocess
import sys

import psycopg
from psycopg.adapt import Loader
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import qa_keyword_source_transaction as transaction
import qa_knowledge_source_binding as binding
import prepare_qa_keyword_source_release as release
from test_qa_knowledge_source_binding import bundle, encode


@pytest.fixture(scope='session')
def pg_cluster(tmp_path_factory):
    data = tmp_path_factory.mktemp('keyword-native-pg').resolve()
    assert data.is_relative_to((ROOT / '.codex_runtime').resolve()), 'Use a new private --basetemp'
    binaries = Path('C:/Program Files/PostgreSQL/16/bin')
    assert (binaries / 'initdb.exe').is_file() and (binaries / 'pg_ctl.exe').is_file()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    def command(program, *args):
        # Windows daemon children can inherit pipe handles after pg_ctl exits.
        # A regular file avoids communicate() waiting for their eventual EOF.
        with (data.parent / (data.name + '-' + program + '-command.log')).open('ab') as log:
            result = subprocess.run([str(binaries / program), *map(str, args)], stdout=log, stderr=log,
                                    timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, 'Isolated PostgreSQL command failed: ' + program
    command('initdb.exe', '-D', data, '-A', 'trust', '-U', 'codex_qa_pg_test', '--encoding=UTF8', '--locale=C')
    started = False
    try:
        started = True
        command('pg_ctl.exe', '-D', data, '-l', data / 'postgres-test.log', '-o',
                f'-p {port} -h 127.0.0.1 -F -c max_connections=15 -c log_min_error_statement=panic', '-w', 'start')
        def connect(readonly=False):
            conn = psycopg.connect(host='127.0.0.1', port=port, dbname='postgres', user='codex_qa_pg_test',
                                   row_factory=dict_row, connect_timeout=5,
                                   options='-c default_transaction_read_only=' + ('on' if readonly else 'off'))
            # Native GUC paths are ACP bytes on this Windows build. Read only this
            # probe's text field as bytes; normal database text stays UTF8.
            class NativePathLoader(Loader):
                def load(self, value):
                    return bytes(value)
            with conn.cursor() as cursor:
                cursor.adapters.register_loader(25, NativePathLoader)
                row = cursor.execute("SELECT current_user AS role,"
                                     "current_setting('data_directory') AS data_dir").fetchone()
            assert row['role'] == 'codex_qa_pg_test'
            path_bytes = row['data_dir']
            try:
                native_path = path_bytes.decode('utf-8')
            except UnicodeDecodeError:
                native_path = path_bytes.decode('mbcs')
            assert Path(native_path).resolve() == data
            conn.rollback()
            return conn
        yield connect
    finally:
        if started and (data / 'postmaster.pid').exists():
            command('pg_ctl.exe', '-D', data, '-m', 'fast', '-w', 'stop')


@pytest.fixture
def prepared(pg_cluster, bundle, monkeypatch):
    manifest, candidate, baseline = bundle
    plan, _ = release.build_plan(manifest, candidate, baseline)
    old_text = '旧甲\r\n旧乙'
    old_hash = binding.sha(old_text.replace('\r\n', '\n'))
    plan['expected_before'].update(content_hash=old_hash, canonical_text_sha256=old_hash,
                                   chunk_counts={'three_rules_atomic': 2}, embedding_count=2)
    plan_bytes = encode(plan)
    monkeypatch.setattr(transaction, 'PLAN_SHA', hashlib.sha256(plan_bytes).hexdigest())
    connection = pg_cluster()
    try:
        connection.execute('DROP SCHEMA IF EXISTS bf_assistant CASCADE')
        connection.execute((ROOT / 'tests/qa_regression/keyword_source_pg_fixture.sql').read_text(encoding='utf-8'))
        connection.commit()
        connection.execute((ROOT / 'schema/20260917_qa_keyword_source_release.sql').read_text(encoding='utf-8'))
        doc = dict(doc_id=binding.DOC_ID, title='合成制度', source_file='controlled-test-source',
                   knowledge_category='三规二制', task_scope_json='[]', version=release.OLD_VERSION,
                   authority_level='knowledge_doc', full_text=old_text, content_hash=old_hash,
                   created_at='2026-01-01T00:00:00+00:00', updated_at='2026-01-01T00:00:00+00:00')
        transaction._insert(connection, transaction.DOC, transaction.DOC_COLUMNS, [doc, dict(doc, doc_id='foreign-document')])
        old = []
        for index, text in enumerate(['旧甲', '旧乙']):
            old.append(dict(plan['chunks'][0], chunk_id=f'old-{index}', content=text, content_hash=binding.sha(text),
                            enriched_content='旧源\n' + text, chunk_type='three_rules_atomic',
                            source_file=doc['source_file'], created_at=doc['created_at'], search_text='old-search'))
        foreign = dict(old[0], chunk_id='foreign-chunk', doc_id='foreign-document')
        transaction._insert(connection, transaction.CHUNKS, transaction.CHUNK_COLUMNS, old + [foreign])
        vectors = [dict(chunk_id=row['chunk_id'], embedding_model='historical-synthetic-vector', embedding='[1,2,3]',
                        embedding_dimension=3, embedding_text_hash='0' * 64, updated_at=doc['created_at'])
                   for row in old + [foreign]]
        transaction._insert(connection, transaction.EMBEDDINGS, transaction.EMBED_COLUMNS, vectors, vector=True)
        connection.execute(
            f'INSERT INTO {transaction.RELEASES} (release_id,doc_id,state,before_snapshot_json,before_snapshot_sha256,'
            'after_snapshot_sha256,manifest_sha256,plan_sha256,applied_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            ('previous-test-release', binding.DOC_ID, 'applied', Jsonb({}), '0' * 64, '0' * 64, '0' * 64, '0' * 64,
             datetime.now(timezone.utc))
        )
        transaction._insert(connection, transaction.BINDINGS, transaction.BINDING_COLUMNS,
                            [dict(doc_id=binding.DOC_ID, release_id='previous-test-release',
                                  authority_sha256=old_hash, manifest_sha256='0' * 64, manifest_text='legacy-test-map')])
        connection.commit()
        before = transaction._snapshot(connection, lock=False)
        foreign_before = foreign_snapshot(connection)
        connection.rollback()
        yield connection, plan_bytes, manifest, candidate, before, foreign_before
    finally:
        connection.close()


def foreign_snapshot(connection):
    doc = connection.execute(f"SELECT * FROM {transaction.DOC} WHERE doc_id='foreign-document'").fetchone()
    chunk = connection.execute(f"SELECT * FROM {transaction.CHUNKS} WHERE chunk_id='foreign-chunk'").fetchone()
    embedding = connection.execute(f"SELECT embedding::text AS vector,* FROM {transaction.EMBEDDINGS} "
                                   "WHERE chunk_id='foreign-chunk'").fetchone()
    return {'doc': dict(doc), 'chunk': dict(chunk), 'embedding': dict(embedding)}


def current(connection):
    value = transaction._snapshot(connection, lock=False)
    connection.rollback()
    return value


def publish(prepared, connection=None):
    conn, plan, manifest, candidate, _, _ = prepared
    return transaction.publish(connection or conn, plan, manifest, candidate, authorized=True)


def rollback(prepared):
    conn, plan, manifest, candidate, _, _ = prepared
    return transaction.rollback_release(conn, plan, manifest, candidate, authorized=True)


def test_real_pgvector_publish_and_rollback_restore_exact_source_vector_and_binding(prepared):
    conn, _, _, _, before, foreign = prepared
    receipt = publish(prepared)
    assert receipt['state'] == 'applied' and receipt['embeddings'] == 0
    assert current(conn)['document']['created_at'] == before['document']['created_at']
    assert current(conn)['binding']['release_id'] == receipt['release_id']
    assert foreign_snapshot(conn) == foreign
    conn.rollback()
    assert rollback(prepared)['state'] == 'rolled_back'
    assert current(conn) == before
    assert foreign_snapshot(conn) == foreign
    conn.rollback()
    with pytest.raises(transaction.SourceTransactionError, match='identity_or_state'):
        rollback(prepared)


def test_duplicate_release_never_replaces_an_applied_source(prepared):
    publish(prepared)
    after = current(prepared[0])
    with pytest.raises(transaction.SourceTransactionError, match='already_recorded'):
        publish(prepared)
    assert current(prepared[0]) == after


class ConnectionFault:
    def __init__(self, connection, mode):
        self.connection, self.mode = connection, mode
    def __getattr__(self, name):
        return getattr(self.connection, name)
    def execute(self, sql, args=None):
        result = self.connection.execute(sql, args)
        if self.mode == 'after_delete' and sql.startswith('DELETE FROM bf_assistant.rag_chunk WHERE'):
            raise RuntimeError('synthetic sensitive row detail')
        return result
    def commit(self):
        if self.mode == 'committed_then_disconnected':
            self.connection.commit()
        raise OSError('synthetic transport uncertainty')


def test_failure_after_target_delete_rolls_back_journal_and_all_data(prepared):
    conn, _, _, _, before, foreign = prepared
    with pytest.raises(transaction.SourceTransactionError, match='precommit_failure_rolled_back_RuntimeError') as error:
        publish(prepared, ConnectionFault(conn, 'after_delete'))
    assert 'sensitive row' not in str(error.value)
    assert current(conn) == before and foreign_snapshot(conn) == foreign
    conn.rollback()


@pytest.mark.parametrize('mode,expected', [('committed_then_disconnected', 'applied_snapshot_verified'),
                                         ('not_committed', 'not_recorded_unresolved')])
def test_commit_uncertainty_requires_readonly_recovery_without_replay(prepared, pg_cluster, mode, expected):
    conn, plan, manifest, candidate, before, _ = prepared
    with pytest.raises(transaction.CommitUncertain):
        publish(prepared, ConnectionFault(conn, mode))
    with pg_cluster(readonly=True) as reader:
        receipt = transaction.recover_release(reader, plan, manifest, candidate)
    assert receipt['state'] == expected and receipt['automatic_replay'] is False
    if mode == 'not_committed':
        assert current(conn) == before


def test_rollback_rejects_later_source_drift(prepared):
    conn = prepared[0]
    publish(prepared)
    conn.execute(f'UPDATE {transaction.CHUNKS} SET title=%s WHERE chunk_id=%s', ('later-change', 'synthetic-0'))
    conn.commit()
    drift = current(conn)
    with pytest.raises(transaction.SourceTransactionError, match='after_snapshot_drift'):
        rollback(prepared)
    assert current(conn) == drift


def test_rollback_rejects_corrupted_before_archive(prepared):
    conn = prepared[0]
    publish(prepared)
    conn.execute(f'UPDATE {transaction.RELEASES} SET before_snapshot_json=%s WHERE release_id=%s',
                 (Jsonb({}), 'qa-source-keyword-20260917-r2'))
    conn.commit()
    after = current(conn)
    with pytest.raises(transaction.SourceTransactionError, match='archive_digest'):
        rollback(prepared)
    assert current(conn) == after


def test_recovery_rejects_corrupted_before_archive(prepared, pg_cluster):
    conn, plan, manifest, candidate, _, _ = prepared
    publish(prepared)
    conn.execute(f'UPDATE {transaction.RELEASES} SET before_snapshot_json=%s WHERE release_id=%s',
                 (Jsonb({}), 'qa-source-keyword-20260917-r2'))
    conn.commit()
    with pg_cluster(readonly=True) as reader:
        with pytest.raises(transaction.SourceTransactionError, match='recovery_archive_digest'):
            transaction.recover_release(reader, plan, manifest, candidate)


def test_publish_rejects_baseline_content_drift(prepared):
    conn = prepared[0]
    conn.execute(f'UPDATE {transaction.DOC} SET full_text=%s WHERE doc_id=%s', ('changed-old-source', binding.DOC_ID))
    conn.commit()
    drift = current(conn)
    with pytest.raises(transaction.SourceTransactionError, match='baseline_drift'):
        publish(prepared)
    assert current(conn) == drift


def test_publish_rejects_new_id_owned_by_other_document(prepared):
    conn = prepared[0]
    row = dict(current(conn)['chunks'][0], chunk_id='synthetic-0', doc_id='foreign-document')
    transaction._insert(conn, transaction.CHUNKS, transaction.CHUNK_COLUMNS, [row])
    conn.commit()
    before = current(conn)
    with pytest.raises(transaction.SourceTransactionError, match='owned_by_other_document'):
        publish(prepared)
    assert current(conn) == before


def test_rollback_rejects_old_id_reused_by_other_document(prepared):
    conn = prepared[0]
    publish(prepared)
    row = dict(prepared[4]['chunks'][0], doc_id='foreign-document')
    transaction._insert(conn, transaction.CHUNKS, transaction.CHUNK_COLUMNS, [row])
    conn.commit()
    after = current(conn)
    with pytest.raises(transaction.SourceTransactionError, match='rollback_chunk_id'):
        rollback(prepared)
    assert current(conn) == after


def test_concurrent_release_lock_blocks_without_mutation(prepared, pg_cluster):
    with pg_cluster() as holder:
        holder.execute('SELECT pg_advisory_xact_lock(8093,20260917)')
        with pytest.raises(transaction.SourceTransactionError, match='lock_busy'):
            publish(prepared)
    assert current(prepared[0]) == prepared[4]


def test_missing_migration_is_not_created_by_publish(prepared):
    conn = prepared[0]
    conn.execute(f'DROP TABLE {transaction.BINDINGS}')
    conn.commit()
    with pytest.raises(transaction.SourceTransactionError, match='schema_columns_changed'):
        publish(prepared)
    assert conn.execute("SELECT to_regclass('bf_assistant.qa_knowledge_source_bindings') AS name").fetchone()['name'] is None
    conn.rollback()


def test_unreviewed_incoming_cascade_is_blocked_before_target_delete(prepared):
    conn = prepared[0]
    conn.execute(f'CREATE TABLE bf_assistant.citation_events (id text PRIMARY KEY,chunk_id text '
                 f'REFERENCES {transaction.CHUNKS}(chunk_id) ON DELETE CASCADE)')
    conn.execute("INSERT INTO bf_assistant.citation_events VALUES ('must-preserve','old-0')")
    conn.commit()
    with pytest.raises(transaction.SourceTransactionError, match='incoming_dependency'):
        publish(prepared)
    assert current(conn) == prepared[4]
    assert conn.execute('SELECT count(*) AS count FROM bf_assistant.citation_events').fetchone()['count'] == 1
    conn.rollback()


def test_unreviewed_trigger_is_blocked_before_mutation(prepared):
    conn = prepared[0]
    conn.execute("CREATE FUNCTION bf_assistant.synthetic_trigger() RETURNS trigger LANGUAGE plpgsql "
                 "AS 'BEGIN RETURN NEW; END;'")
    conn.execute(f'CREATE TRIGGER unreviewed_source_trigger BEFORE UPDATE ON {transaction.DOC} '
                 'FOR EACH ROW EXECUTE FUNCTION bf_assistant.synthetic_trigger()')
    conn.commit()
    with pytest.raises(transaction.SourceTransactionError, match='trigger_or_vector_extension'):
        publish(prepared)
    assert current(conn) == prepared[4]


def test_catalog_preflight_tables_remain_locked_against_trigger_install(prepared, pg_cluster):
    conn = prepared[0]
    conn.execute("CREATE FUNCTION bf_assistant.concurrent_trigger() RETURNS trigger LANGUAGE plpgsql "
                 "AS 'BEGIN RETURN NEW; END;'")
    conn.commit()
    transaction._begin(conn)
    try:
        with pg_cluster() as other:
            other.execute("SET LOCAL lock_timeout='100ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                other.execute(f'CREATE TRIGGER concurrent_source_trigger BEFORE UPDATE ON {transaction.DOC} '
                              'FOR EACH ROW EXECUTE FUNCTION bf_assistant.concurrent_trigger()')
            other.rollback()
    finally:
        conn.rollback()
    assert current(conn) == prepared[4]


def test_recovery_rejects_write_connection(prepared, pg_cluster):
    _, plan, manifest, candidate, _, _ = prepared
    with pg_cluster() as reader:
        with pytest.raises(transaction.SourceTransactionError, match='startup_readonly'):
            transaction.recover_release(reader, plan, manifest, candidate)


def test_unauthorized_publish_and_active_transaction_are_rejected(prepared):
    conn, plan, manifest, candidate, before, _ = prepared
    with pytest.raises(transaction.SourceTransactionError, match='explicit_database_write_authorization'):
        transaction.publish(conn, plan, manifest, candidate)
    conn.execute('SELECT 1')
    with pytest.raises(transaction.SourceTransactionError, match='fresh_owned'):
        publish(prepared)
    conn.rollback()
    assert current(conn) == before
