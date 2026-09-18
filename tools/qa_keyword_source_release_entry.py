"""Sealed source-only entry; production DB write authorization remains separate."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys

import qa_keyword_source_transaction as tx

MODEL_NAME = 'chiqiongblastfuenace:latest'
MODEL_DIGEST = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
CONFIG_RELATIVE = 'tools/service_configs/22012_BFV4PreviewProxy8093.json'
IDENTITY_SQL = (
    "SELECT system_identifier::text AS system_identifier,current_database() AS dbname,"
    "current_user AS db_user,inet_server_addr()::text AS server_addr,inet_server_port() AS server_port,"
    "(current_setting('server_version_num')::integer/10000) AS version_major,"
    "current_schema() AS active_schema,pg_is_in_recovery() AS is_replica FROM pg_catalog.pg_control_system()"
)


class EntryError(RuntimeError):
    pass


def _bounded(path, maximum):
    path = Path(path)
    if path.stat().st_size > maximum:
        raise EntryError('sealed_input_unbounded')
    raw = path.read_bytes()
    if len(raw) > maximum:
        raise EntryError('sealed_input_unbounded')
    return raw


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_root(root):
    root = Path(root).absolute()
    # Reject Windows junctions as well as symbolic links before resolving.
    for ancestor in (root, *root.parents):
        if ancestor.exists():
            stat = ancestor.lstat()
            if ancestor.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
                raise EntryError('root_reparse_point_rejected')
    return root.resolve(strict=True)


def load_contract(raw, expected_sha, root, action, operation_id):
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha or '') or _digest(raw) != expected_sha:
        raise EntryError('sealed_entry_contract_digest_mismatch')
    value = tx.binding._decode(raw, expected_sha)
    required = {'schema', 'root_absolute', 'hostname_sha256', 'database_identity_sha256',
                'service_config_sha256', 'action', 'operation_id', 'model_name', 'model_digest',
                'knowledge_search_mode', 'embedding_generation', 'plan_sha256'}
    if (set(value) != required or value['schema'] != 'bf.qa.private-source-release-entry.v1'
            or value['action'] != action or value['operation_id'] != operation_id
            or value['model_name'] != MODEL_NAME or value['model_digest'] != MODEL_DIGEST
            or value['knowledge_search_mode'] != 'keyword' or value['embedding_generation'] is not False
            or value['plan_sha256'] != tx.PLAN_SHA
            or not re.fullmatch(r'qa-source-[a-z0-9-]{1,80}', operation_id or '')
            or action not in ('plan', 'publish', 'rollback', 'recover')):
        raise EntryError('sealed_entry_contract_mismatch')
    for key in ('hostname_sha256', 'database_identity_sha256', 'service_config_sha256'):
        if not isinstance(value[key], str) or not re.fullmatch(r'[0-9a-f]{64}', value[key]):
            raise EntryError('sealed_identity_digest_invalid')
    root = _safe_root(root)
    if _safe_root(value['root_absolute']) != root:
        raise EntryError('target_root_mismatch')
    if _digest(platform.node().casefold().encode('utf-8')) != value['hostname_sha256']:
        raise EntryError('target_host_mismatch')
    return value, root


def _config(root, contract):
    path = root / CONFIG_RELATIVE
    # Configuration can contain credentials; never print its values or exception.
    for ancestor in (path, *path.parents):
        if ancestor == root.parent:
            break
        if ancestor.exists() and (ancestor.is_symlink() or getattr(ancestor.lstat(), 'st_file_attributes', 0) & 0x400):
            raise EntryError('service_config_reparse_point_rejected')
    raw = _bounded(path, 1000000)
    if _digest(raw) != contract['service_config_sha256']:
        raise EntryError('service_config_digest_mismatch')
    config = tx.binding._decode(raw.lstrip(b'\xef\xbb\xbf'), _digest(raw.lstrip(b'\xef\xbb\xbf')))
    env = config.get('env')
    if not isinstance(env, dict) or env.get('BF_QA_KNOWLEDGE_SEARCH_MODE') != 'keyword':
        raise EntryError('keyword_service_configuration_required')
    return {key: str(value) for key, value in env.items()
            if isinstance(key, str) and key.startswith(('BF_ASSISTANT_PG', 'GL02_PG', 'PG'))}


@contextmanager
def _connection(root, contract):
    # All connections start read-only, including a write action's identity probe.
    env = _config(root, contract)
    saved = {key: value for key, value in os.environ.items()
             if key.startswith(('BF_ASSISTANT_PG', 'GL02_PG', 'PG'))}
    try:
        for key in list(os.environ):
            if key.startswith(('BF_ASSISTANT_PG', 'GL02_PG', 'PG')):
                os.environ.pop(key)
        os.environ.update(env)
        sys.path.insert(0, str(root / '高炉前端数据/智能助手/backend'))
        from assistant_pg import pg_params, schema_name
        import psycopg
        from psycopg.rows import dict_row
        if os.environ.get('BF_ASSISTANT_PG_SCHEMA', 'bf_assistant') != 'bf_assistant' or schema_name() != 'bf_assistant':
            raise EntryError('target_schema_mismatch')
        params = dict(pg_params())
        params.update(autocommit=False, row_factory=dict_row, connect_timeout=8,
                      options='-c default_transaction_read_only=on -c search_path=bf_assistant,bf_sensor,public '
                              '-c statement_timeout=20000 -c lock_timeout=3000')
        connection = psycopg.connect(**params)
        try:
            states = connection.execute("SELECT current_setting('default_transaction_read_only') AS default_state,"
                                        "current_setting('transaction_read_only') AS state").fetchone()
            if states != {'default_state': 'on', 'state': 'on'}:
                raise EntryError('startup_readonly_identity_probe_required')
            identity = connection.execute(IDENTITY_SQL).fetchone()
            if (not identity or identity['active_schema'] != 'bf_assistant'
                    or identity['is_replica'] is not False
                    or tx.snapshot_hash(dict(identity)) != contract['database_identity_sha256']):
                raise EntryError('target_database_identity_mismatch')
            connection.rollback()
            yield connection
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()
    finally:
        for key in list(os.environ):
            if key.startswith(('BF_ASSISTANT_PG', 'GL02_PG', 'PG')):
                os.environ.pop(key)
        os.environ.update(saved)


def _record(path, value, *, exclusive=False):
    # Append-only local attempt evidence. A claimed ID can never invoke a second write.
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_APPEND)
    fd = os.open(path, flags, 0o600)
    try:
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        with os.fdopen(fd, 'wb', closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)


def _claim(root, operation_id, action, contract_sha):
    directory = root / 'logs/qa_source_release_operations'
    for ancestor in (directory, directory.parent):
        if ancestor.exists() and (ancestor.is_symlink() or getattr(ancestor.lstat(), 'st_file_attributes', 0) & 0x400):
            raise EntryError('operation_record_reparse_point_rejected')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (operation_id + '.jsonl')
    try:
        _record(path, {'state': 'claimed_no_write_yet', 'operation_id': operation_id,
                       'action': action, 'contract_sha256': contract_sha, 'automatic_replay': False}, exclusive=True)
    except FileExistsError:
        raise EntryError('operation_already_claimed_readonly_recovery_required') from None
    return path


def _enable_write(connection):
    # Only reached after separate authorization, durable claim and read-only identity.
    tx._fresh(connection)
    connection.read_only = False


def run(*, root, artifact_dir, contract_path, contract_sha, action, operation_id, authorized=False):
    journal = None
    write_action = action in ('publish', 'rollback')
    if write_action and authorized is not True:
        raise EntryError('separate_database_write_authorization_required')
    try:
        contract, root = load_contract(_bounded(contract_path, 10000), contract_sha, root, action, operation_id)
        artifacts = Path(artifact_dir)
        plan = _bounded(artifacts / 'release_plan.private.json', 25000000)
        manifest = _bounded(artifacts / 'source_scope_manifest.json', 25000000)
        candidate = _bounded(artifacts / 'document_candidate.private.json', 25000000)
        prepared = tx.load_plan(plan, manifest, candidate)
        if action == 'plan':
            # Zero connection, configuration secret read, filesystem write or model call.
            return {'state': 'sealed_inputs_verified', 'release_id': prepared['release_id'],
                    'chunks': len(prepared['chunks']), 'database_connections': 0, 'database_writes': 0,
                    'model_calls': 0, 'question_posts': 0, 'automatic_replay': False}
        if write_action:
            journal = _claim(root, operation_id, action, contract_sha)
        with _connection(root, contract) as connection:
            if write_action:
                _record(journal, {'state': 'identity_verified_write_not_started'})
                _enable_write(connection)
                _record(journal, {'state': 'write_call_started_outcome_unverified', 'automatic_replay': False})
                if action == 'publish':
                    result = tx.publish(connection, plan, manifest, candidate, authorized=True)
                else:
                    result = tx.rollback_release(connection, plan, manifest, candidate, authorized=True)
                _record(journal, {'state': 'committed', 'result': result})
            else:
                result = tx.recover_release(connection, plan, manifest, candidate)
        return result
    except Exception as exc:
        code = str(exc) if isinstance(exc, (EntryError, tx.SourceTransactionError)) else 'entry_failed_' + type(exc).__name__
        if journal:
            try:
                _record(journal, {'state': 'unresolved_or_failed', 'error_code': code, 'automatic_replay': False})
            except Exception:
                raise EntryError('operation_record_update_failed_readonly_recovery_required') from None
        raise EntryError(code) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--artifact-dir', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--contract-sha', required=True)
    parser.add_argument('--action', choices=('plan', 'publish', 'rollback', 'recover'), required=True)
    parser.add_argument('--operation-id', required=True)
    parser.add_argument('--authorized-database-write', action='store_true',
                        help='Root must separately receive production DB authorization; this flag does not grant it.')
    args = parser.parse_args(argv)
    try:
        result = run(root=args.root, artifact_dir=args.artifact_dir, contract_path=args.contract,
                     contract_sha=args.contract_sha, action=args.action, operation_id=args.operation_id,
                     authorized=args.authorized_database_write)
    except EntryError as exc:
        print(json.dumps({'ok': False, 'error_code': str(exc), 'automatic_replay': False}))
        return 2
    print(json.dumps({'ok': True, **result}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
