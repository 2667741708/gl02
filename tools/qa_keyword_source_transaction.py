"""Owned-connection single-document source transactions; no credentials or transport."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '高炉前端数据/智能助手/backend'))
import qa_knowledge_source_binding as binding

PLAN_SHA = '7ca28451af71cc389076bba21774f75540597a4e926ed4e0a0bf9280dd7dd16d'
DOC = 'bf_assistant.rag_document'
CHUNKS = 'bf_assistant.rag_chunk'
EMBEDDINGS = 'bf_assistant.rag_chunk_embedding'
RELEASES = 'bf_assistant.qa_knowledge_source_releases'
BINDINGS = 'bf_assistant.qa_knowledge_source_bindings'
DOC_COLUMNS = ('doc_id', 'title', 'source_file', 'knowledge_category', 'task_scope_json', 'version',
               'authority_level', 'full_text', 'content_hash', 'created_at', 'updated_at')
CHUNK_COLUMNS = ('chunk_id', 'doc_id', 'parent_chunk_id', 'title', 'content', 'enriched_content', 'summary',
                 'keywords_json', 'entities_json', 'phenomenon_json', 'parameter_names_json', 'chunk_type',
                 'token_count', 'source_file', 'knowledge_category', 'task_scope_json', 'authority_level',
                 'source_priority', 'content_hash', 'created_at', 'search_text')
EMBED_COLUMNS = ('chunk_id', 'embedding_model', 'embedding', 'embedding_dimension', 'embedding_text_hash', 'updated_at')
BINDING_COLUMNS = ('doc_id', 'release_id', 'authority_sha256', 'manifest_sha256', 'manifest_text')
RELEASE_COLUMNS = ('release_id', 'doc_id', 'state', 'before_snapshot_json', 'before_snapshot_sha256',
                   'after_snapshot_sha256', 'manifest_sha256', 'plan_sha256', 'applied_at', 'rolled_back_at')


class SourceTransactionError(RuntimeError):
    pass


class CommitUncertain(SourceTransactionError):
    pass


def snapshot_hash(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def load_plan(raw, manifest_bytes, candidate_bytes):
    plan = binding._decode(raw, PLAN_SHA)
    if (plan.get('schema') != 'bf.qa.private-keyword-release-plan.v1'
            or plan.get('doc_id') != binding.DOC_ID or plan.get('release_id') != 'qa-source-keyword-20260917-r2'
            or plan.get('manifest_sha256') != binding.MANIFEST_SHA
            or plan.get('manifest_text') != manifest_bytes.decode('utf-8')
            or plan.get('knowledge_search_mode') != 'keyword' or plan.get('embedding_generation') is not False
            or plan.get('model_digest') != 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'):
        raise SourceTransactionError('sealed_plan_contract_mismatch')
    binding.verify_prepared_source(manifest_bytes, candidate_bytes, plan.get('document_update'), plan.get('chunks'))
    return plan


def _fresh(connection):
    if connection.autocommit is not False or int(connection.info.transaction_status) != 0:
        raise SourceTransactionError('fresh_owned_transaction_connection_required')


def _schema(connection):
    expected = {'rag_document': DOC_COLUMNS, 'rag_chunk': CHUNK_COLUMNS, 'rag_chunk_embedding': EMBED_COLUMNS,
                'qa_knowledge_source_bindings': BINDING_COLUMNS, 'qa_knowledge_source_releases': RELEASE_COLUMNS}
    rows = connection.execute(
        "SELECT table_name,column_name,data_type,udt_name,udt_schema FROM information_schema.columns "
        "WHERE table_schema='bf_assistant' AND table_name=ANY(%s)", (list(expected),)
    ).fetchall()
    actual = {table: {} for table in expected}
    for row in rows:
        actual[row['table_name']][row['column_name']] = (row['data_type'], row['udt_name'])
        if row['table_name'] == 'rag_chunk_embedding' and row['column_name'] == 'embedding' and row['udt_schema'] != 'public':
            raise SourceTransactionError('source_vector_namespace_changed')
    for table, columns in expected.items():
        if set(actual[table]) != set(columns):
            raise SourceTransactionError('source_schema_columns_changed')
        for name in columns:
            expected_type = ('USER-DEFINED', 'vector') if table == 'rag_chunk_embedding' and name == 'embedding' else (
                ('integer', 'int4') if name in ('token_count', 'source_priority', 'embedding_dimension') else
                ('jsonb', 'jsonb') if name == 'before_snapshot_json' else
                ('timestamp with time zone', 'timestamptz') if name in ('applied_at', 'rolled_back_at') else ('text', 'text'))
            if actual[table][name] != expected_type:
                raise SourceTransactionError('source_schema_types_changed')
    constraints = connection.execute(
        "SELECT cls.relname AS table_name,ns.nspname AS source_schema,con.contype AS kind,con.confdeltype AS delete_action,"
        "target.relname AS target_table,target_ns.nspname AS target_schema,ARRAY(SELECT a.attname FROM pg_catalog.pg_attribute a "
        "WHERE a.attrelid=con.conrelid AND a.attnum=ANY(con.conkey) "
        "ORDER BY array_position(con.conkey,a.attnum)) AS source_columns,"
        "ARRAY(SELECT a.attname FROM pg_catalog.pg_attribute a WHERE a.attrelid=con.confrelid "
        "AND a.attnum=ANY(con.confkey) ORDER BY array_position(con.confkey,a.attnum)) AS target_columns "
        "FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class cls ON cls.oid=con.conrelid "
        "JOIN pg_catalog.pg_namespace ns ON ns.oid=cls.relnamespace "
        "LEFT JOIN pg_catalog.pg_class target ON target.oid=con.confrelid "
        "LEFT JOIN pg_catalog.pg_namespace target_ns ON target_ns.oid=target.relnamespace "
        "WHERE (ns.nspname='bf_assistant' AND cls.relname=ANY(%s)) "
        "OR (target_ns.nspname='bf_assistant' AND target.relname=ANY(%s))", (list(expected), list(expected))
    ).fetchall()
    keys = {(row['table_name'], row['kind'], tuple(row['source_columns'])) for row in constraints}
    primary = {'rag_document': 'doc_id', 'rag_chunk': 'chunk_id', 'rag_chunk_embedding': 'chunk_id',
               'qa_knowledge_source_releases': 'release_id', 'qa_knowledge_source_bindings': 'doc_id'}
    if any((table, 'p', (column,)) not in keys for table, column in primary.items()):
        raise SourceTransactionError('source_schema_primary_key_changed')
    foreign = {(row['table_name'], tuple(row['source_columns']), row['target_table'],
                tuple(row['target_columns']), row['delete_action']) for row in constraints if row['kind'] == 'f'}
    if any(row['target_schema'] != 'bf_assistant' or row['source_schema'] != 'bf_assistant'
           for row in constraints if row['kind'] == 'f'):
        raise SourceTransactionError('source_schema_foreign_namespace_changed')
    if any(row['table_name'] not in expected for row in constraints if row['kind'] == 'f'):
        raise SourceTransactionError('source_schema_incoming_dependency_unreviewed')
    required = {('rag_chunk', ('doc_id',), 'rag_document', ('doc_id',), 'c'),
                ('rag_chunk_embedding', ('chunk_id',), 'rag_chunk', ('chunk_id',), 'c'),
                ('qa_knowledge_source_releases', ('doc_id',), 'rag_document', ('doc_id',), 'a'),
                ('qa_knowledge_source_bindings', ('doc_id',), 'rag_document', ('doc_id',), 'a'),
                ('qa_knowledge_source_bindings', ('release_id',), 'qa_knowledge_source_releases', ('release_id',), 'a')}
    if required != foreign:
        raise SourceTransactionError('source_schema_foreign_key_changed')
    triggers = connection.execute(
        "SELECT t.tgname FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='bf_assistant' "
        "AND c.relname=ANY(%s) AND NOT t.tgisinternal AND t.tgenabled<>'D' LIMIT 1", (list(expected),)
    ).fetchone()
    extension = connection.execute(
        "SELECT 1 AS installed FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace "
        "WHERE e.extname='vector' AND n.nspname='public'"
    ).fetchone()
    if triggers or not extension:
        raise SourceTransactionError('source_trigger_or_vector_extension_unreviewed')


def _begin(connection):
    connection.execute("SET LOCAL lock_timeout='3s'")
    connection.execute("SET LOCAL statement_timeout='20s'")
    if connection.execute("SELECT current_setting('transaction_read_only') AS state").fetchone()['state'] != 'off':
        raise SourceTransactionError('write_connection_required')
    lock = connection.execute("SELECT pg_try_advisory_xact_lock(8093,20260917) AS acquired").fetchone()
    if lock['acquired'] is not True:
        raise SourceTransactionError('source_release_lock_busy')
    expected_tables = [table.split('.')[1] for table in (DOC, CHUNKS, EMBEDDINGS, RELEASES, BINDINGS)]
    existing = connection.execute(
        "SELECT c.relname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='bf_assistant' AND c.relkind='r' AND c.relname=ANY(%s)", (expected_tables,)
    ).fetchall()
    if {row['relname'] for row in existing} != set(expected_tables):
        raise SourceTransactionError('source_schema_columns_changed')
    # Hold metadata stable through COMMIT: prevent a new trigger/incoming FK from
    # being installed after catalog preflight but before DELETE. Readers remain allowed.
    connection.execute('LOCK TABLE ' + ','.join((DOC, CHUNKS, EMBEDDINGS, RELEASES, BINDINGS))
                       + ' IN SHARE ROW EXCLUSIVE MODE NOWAIT')
    _schema(connection)


def _snapshot(connection, *, lock):
    suffix = ' FOR UPDATE' if lock else ''
    doc = connection.execute(f'SELECT * FROM {DOC} WHERE doc_id=%s' + suffix, (binding.DOC_ID,)).fetchone()
    if not doc or not isinstance(doc['full_text'], str) or len(doc['full_text']) > 2000000:
        raise SourceTransactionError('source_document_missing_or_unbounded')
    chunks = connection.execute(f'SELECT * FROM {CHUNKS} WHERE doc_id=%s ORDER BY chunk_id' + suffix,
                                (binding.DOC_ID,)).fetchall()
    embeddings = connection.execute(
        f'SELECT e.chunk_id,e.embedding_model,e.embedding::text AS embedding,e.embedding_dimension,'
        f'e.embedding_text_hash,e.updated_at FROM {EMBEDDINGS} e JOIN {CHUNKS} c ON c.chunk_id=e.chunk_id '
        'WHERE c.doc_id=%s ORDER BY e.chunk_id' + (' FOR UPDATE OF e' if lock else ''), (binding.DOC_ID,)
    ).fetchall()
    source_binding = connection.execute(f'SELECT * FROM {BINDINGS} WHERE doc_id=%s' + suffix, (binding.DOC_ID,)).fetchone()
    if len(chunks) > 10000 or len(embeddings) > 10000:
        raise SourceTransactionError('source_snapshot_unbounded')
    return {'document': dict(doc), 'chunks': [dict(row) for row in chunks],
            'embeddings': [dict(row) for row in embeddings], 'binding': dict(source_binding) if source_binding else None}


def _baseline(before, plan):
    expected, doc = plan['expected_before'], before['document']
    canonical = doc['full_text'].replace('\r\n', '\n').replace('\r', '\n')
    if (doc['doc_id'] != binding.DOC_ID or doc['version'] != expected['version']
            or doc['content_hash'] != expected['content_hash'] or binding.sha(canonical) != expected['canonical_text_sha256']
            or dict(Counter(row['chunk_type'] for row in before['chunks'])) != expected['chunk_counts']
            or len(before['embeddings']) != expected['embedding_count']):
        raise SourceTransactionError('source_baseline_drift')


def _after(before, plan):
    stamp = datetime.now(timezone.utc).isoformat()
    document = dict(before['document'], **plan['document_update'], updated_at=stamp)
    chunks = [dict(row, source_file=before['document']['source_file'], created_at=stamp) for row in plan['chunks']]
    source_binding = {'doc_id': binding.DOC_ID, 'release_id': plan['release_id'],
                      'authority_sha256': binding.AUTHORITY_SHA, 'manifest_sha256': binding.MANIFEST_SHA,
                      'manifest_text': plan['manifest_text']}
    return {'document': document, 'chunks': sorted(chunks, key=lambda row: row['chunk_id']),
            'embeddings': [], 'binding': source_binding}


def _insert(connection, table, columns, rows, *, vector=False):
    if not rows:
        return
    placeholders = ['%s::public.vector' if vector and name == 'embedding' else '%s' for name in columns]
    sql = f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join(placeholders)})'
    with connection.cursor() as cursor:
        cursor.executemany(sql, [tuple(row[name] for name in columns) for row in rows])


def _replace(connection, snapshot):
    # Never delete the document: releases and other consumers retain its identity.
    doc = snapshot['document']
    columns = [name for name in DOC_COLUMNS if name != 'doc_id']
    result = connection.execute(f'UPDATE {DOC} SET ' + ','.join(name + '=%s' for name in columns) + ' WHERE doc_id=%s',
                                tuple(doc[name] for name in columns) + (binding.DOC_ID,))
    if result.rowcount != 1:
        raise SourceTransactionError('source_document_update_count_invalid')
    connection.execute(f'DELETE FROM {EMBEDDINGS} WHERE chunk_id IN (SELECT chunk_id FROM {CHUNKS} WHERE doc_id=%s)',
                       (binding.DOC_ID,))
    connection.execute(f'DELETE FROM {CHUNKS} WHERE doc_id=%s', (binding.DOC_ID,))
    _insert(connection, CHUNKS, CHUNK_COLUMNS, snapshot['chunks'])
    _insert(connection, EMBEDDINGS, EMBED_COLUMNS, snapshot['embeddings'], vector=True)
    connection.execute(f'DELETE FROM {BINDINGS} WHERE doc_id=%s', (binding.DOC_ID,))
    if snapshot['binding']:
        _insert(connection, BINDINGS, BINDING_COLUMNS, [snapshot['binding']])


def _run(connection, action, *, authorized):
    if authorized is not True:
        raise SourceTransactionError('explicit_database_write_authorization_required')
    _fresh(connection)
    try:
        _begin(connection)
        result = action()
    except Exception as exc:
        try:
            connection.rollback()
        except Exception:
            raise SourceTransactionError('precommit_failure_rollback_unverified') from None
        if isinstance(exc, SourceTransactionError):
            raise exc from None
        raise SourceTransactionError('precommit_failure_rolled_back_' + type(exc).__name__) from None
    try:
        connection.commit()
    except Exception:
        # A driver error cannot prove COMMIT did not reach the database.
        try:
            connection.rollback()
        except Exception:
            pass
        raise CommitUncertain('commit_outcome_uncertain_readonly_recovery_required') from None
    return result


def publish(connection, plan_bytes, manifest_bytes, candidate_bytes, *, authorized=False):
    """Caller owns the fresh connection and separate DB authorization. No auto replay."""
    plan = load_plan(plan_bytes, manifest_bytes, candidate_bytes)
    def action():
        from psycopg.types.json import Jsonb
        if connection.execute(f'SELECT release_id FROM {RELEASES} WHERE release_id=%s', (plan['release_id'],)).fetchone():
            raise SourceTransactionError('release_already_recorded_readonly_recovery_required')
        before = _snapshot(connection, lock=True)
        _baseline(before, plan)
        collision = connection.execute(f'SELECT chunk_id FROM {CHUNKS} WHERE chunk_id=ANY(%s) AND doc_id<>%s LIMIT 1',
                                      ([row['chunk_id'] for row in plan['chunks']], binding.DOC_ID)).fetchone()
        if collision:
            raise SourceTransactionError('source_chunk_id_owned_by_other_document')
        after = _after(before, plan)
        connection.execute(
            f'INSERT INTO {RELEASES} (release_id,doc_id,state,before_snapshot_json,before_snapshot_sha256,'
            'after_snapshot_sha256,manifest_sha256,plan_sha256,applied_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (plan['release_id'], binding.DOC_ID, 'applied', Jsonb(before), snapshot_hash(before), snapshot_hash(after),
             binding.MANIFEST_SHA, PLAN_SHA, datetime.now(timezone.utc))
        )
        _replace(connection, after)
        actual = _snapshot(connection, lock=False)
        if snapshot_hash(actual) != snapshot_hash(after):
            raise SourceTransactionError('source_after_snapshot_mismatch')
        binding.verify_database_source(manifest_bytes, candidate_bytes, actual['document'], actual['chunks'])
        return {'state': 'applied', 'release_id': plan['release_id'], 'before_sha256': snapshot_hash(before),
                'after_sha256': snapshot_hash(after), 'chunks': len(after['chunks']), 'embeddings': 0,
                'semantic_verified': False, 'model_operations': 0, 'automatic_replay': False}
    return _run(connection, action, authorized=authorized)


def rollback_release(connection, plan_bytes, manifest_bytes, candidate_bytes, *, authorized=False):
    plan = load_plan(plan_bytes, manifest_bytes, candidate_bytes)
    def action():
        release = connection.execute(f'SELECT * FROM {RELEASES} WHERE release_id=%s FOR UPDATE',
                                     (plan['release_id'],)).fetchone()
        if (not release or release['doc_id'] != binding.DOC_ID or release['state'] != 'applied'
                or release['plan_sha256'] != PLAN_SHA or release['manifest_sha256'] != binding.MANIFEST_SHA):
            raise SourceTransactionError('rollback_release_identity_or_state_mismatch')
        actual = _snapshot(connection, lock=True)
        if snapshot_hash(actual) != release['after_snapshot_sha256']:
            raise SourceTransactionError('rollback_blocked_after_snapshot_drift')
        before = release['before_snapshot_json']
        if snapshot_hash(before) != release['before_snapshot_sha256']:
            raise SourceTransactionError('rollback_archive_digest_mismatch')
        _baseline(before, plan)
        collision = connection.execute(f'SELECT chunk_id FROM {CHUNKS} WHERE chunk_id=ANY(%s) AND doc_id<>%s LIMIT 1',
                                      ([row['chunk_id'] for row in before['chunks']], binding.DOC_ID)).fetchone()
        if collision:
            raise SourceTransactionError('rollback_chunk_id_owned_by_other_document')
        _replace(connection, before)
        if snapshot_hash(_snapshot(connection, lock=False)) != release['before_snapshot_sha256']:
            raise SourceTransactionError('rollback_before_snapshot_mismatch')
        connection.execute(f"UPDATE {RELEASES} SET state='rolled_back',rolled_back_at=%s WHERE release_id=%s",
                           (datetime.now(timezone.utc), plan['release_id']))
        return {'state': 'rolled_back', 'release_id': plan['release_id'], 'restored_sha256': release['before_snapshot_sha256'],
                'model_operations': 0, 'automatic_replay': False}
    return _run(connection, action, authorized=authorized)


def recover_release(connection, plan_bytes, manifest_bytes, candidate_bytes):
    """Read-only recovery. A missing journal never licenses an automatic replay."""
    plan = load_plan(plan_bytes, manifest_bytes, candidate_bytes)
    _fresh(connection)
    connection.isolation_level = 2  # psycopg IsolationLevel.REPEATABLE_READ, before BEGIN.
    try:
        readonly = connection.execute("SELECT current_setting('default_transaction_read_only') AS default_state,"
                                      "current_setting('transaction_read_only') AS state").fetchone()
        if readonly['default_state'] != 'on' or readonly['state'] != 'on':
            raise SourceTransactionError('startup_readonly_recovery_connection_required')
        _schema(connection)
        release = connection.execute(f'SELECT * FROM {RELEASES} WHERE release_id=%s', (plan['release_id'],)).fetchone()
        state = 'not_recorded_unresolved'
        if release:
            if (release['doc_id'] != binding.DOC_ID or release['plan_sha256'] != PLAN_SHA
                    or release['manifest_sha256'] != binding.MANIFEST_SHA
                    or release['state'] not in ('applied', 'rolled_back')):
                raise SourceTransactionError('recovery_release_identity_mismatch')
            if snapshot_hash(release['before_snapshot_json']) != release['before_snapshot_sha256']:
                raise SourceTransactionError('recovery_archive_digest_mismatch')
            _baseline(release['before_snapshot_json'], plan)
            current = snapshot_hash(_snapshot(connection, lock=False))
            expected = release['after_snapshot_sha256'] if release['state'] == 'applied' else release['before_snapshot_sha256']
            state = release['state'] + '_snapshot_verified' if current == expected else 'recorded_snapshot_drift_unresolved'
        return {'state': state, 'release_id': plan['release_id'], 'database_writes': 0, 'automatic_replay': False}
    except Exception as exc:
        if isinstance(exc, SourceTransactionError):
            raise exc from None
        raise SourceTransactionError('readonly_recovery_failed_' + type(exc).__name__) from None
    finally:
        try:
            connection.rollback()
        except Exception:
            raise SourceTransactionError('readonly_recovery_cleanup_unverified') from None
