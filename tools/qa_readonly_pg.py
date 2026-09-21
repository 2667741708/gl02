"""REQ-QA-READONLY-AUDIT-20260917: audit without pool or schema initialization."""
from __future__ import annotations

from contextlib import contextmanager
import re
from typing import Any

VERSION = 'qa-readonly-pg-v1'


class ReadOnlyAuditUnavailable(RuntimeError):
    """Fail closed without returning connection parameters or query contents."""


def _select(sql: str) -> None:
    # These audit programs use fixed SELECTs and bound parameters, not arbitrary SQL.
    if not isinstance(sql, str) or not re.match(r'^\s*SELECT\s', sql, re.I) or ';' in sql:
        raise ReadOnlyAuditUnavailable('Audit accepts one parameterized SELECT only')


class ReadOnlyCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(self, sql: str, params: Any = None):
        _select(sql)
        self._cursor.execute(sql, params or ())
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class ReadOnlyConnection:
    def __init__(self, connection: Any):
        self._connection = connection

    def execute(self, sql: str, params: Any = None):
        _select(sql)
        return ReadOnlyCursor(self._connection.execute(sql, params or ()))

    def cursor(self):
        return ReadOnlyCursor(self._connection.cursor())


@contextmanager
def readonly_pg_connect(*, statement_timeout_ms: int = 20000):
    """Enforce read-only at PostgreSQL startup, before the first query; always rollback.

    No assistant connection pool, ensure_schema_namespace, migration, commit, or
    settings mutation is invoked. The schema must already exist and be accessible.
    Credentials stay in the authorized environment and are never logged here.
    """
    if type(statement_timeout_ms) is not int or not 1 <= statement_timeout_ms <= 60000:
        raise ReadOnlyAuditUnavailable('Invalid audit statement timeout')
    from assistant_pg import pg_params, schema_name
    import psycopg
    from psycopg.rows import dict_row

    try:
        schema = schema_name()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', schema):
            raise ValueError('Invalid schema')
        params = dict(pg_params())
        params['options'] = (
            '-c default_transaction_read_only=on '
            f'-c search_path={schema},bf_sensor,public '
            f'-c statement_timeout={statement_timeout_ms} -c lock_timeout=3000'
        )
        params['connect_timeout'] = min(8, max(1, int(params.get('connect_timeout', 8))))
        params['autocommit'] = False
        params['row_factory'] = dict_row
        connection = psycopg.connect(**params)
    except Exception:
        raise ReadOnlyAuditUnavailable('Read-only audit connection unavailable') from None

    try:
        row = connection.execute(
            "SELECT pg_catalog.current_setting('default_transaction_read_only') AS default_readonly, "
            "pg_catalog.current_setting('transaction_read_only') AS transaction_readonly, "
            "pg_catalog.current_schema() AS active_schema"
        ).fetchone()
        if not row or row.get('default_readonly') != 'on' or row.get('transaction_readonly') != 'on' or row.get('active_schema') != schema:
            raise ReadOnlyAuditUnavailable('Read-only audit startup verification failed')
        yield ReadOnlyConnection(connection)
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()
