from __future__ import annotations

import os
import re
import threading
import atexit
from dataclasses import dataclass
from typing import Any


ASSISTANT_SCHEMA = os.environ.get("BF_ASSISTANT_PG_SCHEMA", "bf_assistant")
ASSISTANT_REQUIRED_TABLES = (
    "furnace_snapshots",
    "qa_conversations",
    "qa_messages",
    "period_reports",
    "report_template",
    "report_instance",
    "qa_projects",
    "project_assets",
    "qa_message_context_refs",
    "rag_document",
    "rag_chunk",
    "rag_query_log",
)

_SERIAL_ID_TABLES = {
    "furnace_snapshots",
    "qa_messages",
    "period_reports",
    "report_template",
    "report_instance",
    "qa_projects",
    "project_assets",
    "qa_message_context_refs",
}

_POOL_LOCK = threading.Lock()
_CONNECTION_POOL: Any | None = None
_POOL_IMPORT_FAILED = False
_SCHEMA_READY_LOCK = threading.Lock()
_ASSISTANT_SCHEMA_READY = False


def _validate_ident(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise RuntimeError(f"非法 PostgreSQL 标识符: {value!r}")
    return value


def schema_name() -> str:
    return _validate_ident(ASSISTANT_SCHEMA)


def _qmark_to_psycopg(sql: str) -> str:
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _named_to_psycopg(sql: str) -> str:
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == ":" and not in_single and not in_double:
            prev_ch = sql[i - 1] if i > 0 else ""
            next_ch = sql[i + 1] if i + 1 < len(sql) else ""
            if prev_ch != ":" and re.match(r"[A-Za-z_]", next_ch or ""):
                match = re.match(r":([A-Za-z_][A-Za-z0-9_]*)", sql[i:])
                if match:
                    out.append(f"%({match.group(1)})s")
                    i += len(match.group(0))
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


def _normalize_sql(sql: str) -> str:
    text = sql.strip()
    text = re.sub(r"\bIFNULL\s*\(", "COALESCE(", text, flags=re.IGNORECASE)
    text = _named_to_psycopg(text)
    return _qmark_to_psycopg(text)


@dataclass
class CursorAdapter:
    conn: Any
    cursor: Any | None = None
    rows: list[dict[str, Any]] | None = None
    lastrowid: int | None = None

    def fetchone(self) -> dict[str, Any] | None:
        if self.rows is not None:
            return self.rows[0] if self.rows else None
        if self.cursor is None:
            return None
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self) -> list[dict[str, Any]]:
        if self.rows is not None:
            return list(self.rows)
        if self.cursor is None:
            return []
        return [dict(row) for row in self.cursor.fetchall()]


class PgCompatConnection:
    """Small sqlite-like facade used by the existing 8092 assistant code.

    The old 8092 assistant code used `sqlite3.Connection.execute(...)` with
    question-mark placeholders. This facade keeps that call shape while all
    data is stored in PostgreSQL under `bf_assistant`.
    """

    def __init__(self, conn: Any):
        self.conn = conn

    def __enter__(self) -> "PgCompatConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def execute(self, sql: str, params: Any | None = None) -> CursorAdapter:
        raw = sql.strip()
        if raw.upper().startswith("PRAGMA"):
            return CursorAdapter(self.conn, rows=[])
        prepared = _normalize_sql(raw)
        cur = self.conn.cursor()
        cur.execute(prepared, params or ())
        lastrowid: int | None = None
        insert_match = re.match(
            r"INSERT\s+INTO\s+(?:(?:[A-Za-z_][A-Za-z0-9_]*)\.)?([A-Za-z_][A-Za-z0-9_]*)",
            raw,
            flags=re.IGNORECASE,
        )
        insert_table = insert_match.group(1).lower() if insert_match else ""
        if insert_table in _SERIAL_ID_TABLES and " RETURNING " not in raw.upper():
            try:
                with self.conn.cursor() as id_cur:
                    id_cur.execute("SELECT lastval() AS id")
                    row = id_cur.fetchone()
                    if row is not None:
                        lastrowid = int(row["id"])
            except Exception:
                lastrowid = None
        return CursorAdapter(self.conn, cursor=cur, lastrowid=lastrowid)

    def executescript(self, script: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(script)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


class RawPgConnectionLease:
    """Connection proxy that returns pooled connections instead of closing them."""

    def __init__(self, conn: Any, pool: Any | None = None):
        self._conn = conn
        self._pool = pool
        self._released = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __enter__(self) -> "RawPgConnectionLease":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
        finally:
            self.close()

    def close(self) -> None:
        if self._released:
            return
        self._released = True
        if self._pool is not None:
            self._pool.putconn(self._conn)
        else:
            self._conn.close()


def pg_params() -> dict[str, Any]:
    user = os.environ.get("GL02_PGUSER", "").strip()
    password = os.environ.get("GL02_PGPASSWORD", "")
    if not user:
        raise RuntimeError("缺少 GL02_PGUSER/GL02_PGPASSWORD，无法使用 PostgreSQL 助手库。")
    return {
        "host": os.environ.get("GL02_PGHOST", "10.30.220.12"),
        "port": int(os.environ.get("GL02_PGPORT", "5432")),
        "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
        "user": user,
        "password": password,
        "connect_timeout": int(os.environ.get("BF_ASSISTANT_PG_CONNECT_TIMEOUT", "8")),
    }


def _new_raw_connection():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("缺少 psycopg，无法连接 PostgreSQL。请先安装 psycopg[binary]。") from exc
    conn = psycopg.connect(**pg_params(), row_factory=dict_row)
    ensure_schema_namespace(conn)
    return conn


def _configure_pool_connection(conn: Any) -> None:
    ensure_schema_namespace(conn)
    conn.commit()


def _get_connection_pool() -> Any | None:
    global _CONNECTION_POOL, _POOL_IMPORT_FAILED
    if os.environ.get("BF_ASSISTANT_PG_POOL_ENABLED", "1").strip().lower() in {"0", "false", "no", "off"}:
        return None
    if _POOL_IMPORT_FAILED:
        return None
    if _CONNECTION_POOL is not None:
        return _CONNECTION_POOL
    with _POOL_LOCK:
        if _CONNECTION_POOL is not None:
            return _CONNECTION_POOL
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError:
            _POOL_IMPORT_FAILED = True
            return None
        params = pg_params()
        min_size = max(1, int(os.environ.get("BF_ASSISTANT_PG_POOL_MIN_SIZE", "1")))
        max_size = max(min_size, int(os.environ.get("BF_ASSISTANT_PG_POOL_MAX_SIZE", "6")))
        timeout = max(1.0, float(os.environ.get("BF_ASSISTANT_PG_POOL_TIMEOUT_SECONDS", "10")))
        conninfo = psycopg.conninfo.make_conninfo(**params)
        _CONNECTION_POOL = ConnectionPool(
            conninfo=conninfo,
            kwargs={"row_factory": dict_row},
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            configure=_configure_pool_connection,
            open=True,
            name="bf-assistant",
        )
        return _CONNECTION_POOL


def close_connection_pool() -> None:
    global _CONNECTION_POOL
    with _POOL_LOCK:
        pool = _CONNECTION_POOL
        _CONNECTION_POOL = None
    if pool is not None:
        pool.close()


atexit.register(close_connection_pool)


def raw_pg_connect() -> RawPgConnectionLease:
    pool = _get_connection_pool()
    if pool is not None:
        return RawPgConnectionLease(pool.getconn(), pool)
    return RawPgConnectionLease(_new_raw_connection())


def db_connect() -> PgCompatConnection:
    global _ASSISTANT_SCHEMA_READY
    conn = raw_pg_connect()
    try:
        if not _ASSISTANT_SCHEMA_READY:
            with _SCHEMA_READY_LOCK:
                if not _ASSISTANT_SCHEMA_READY:
                    ensure_assistant_schema(conn)
                    conn.commit()
                    _ASSISTANT_SCHEMA_READY = True
        return PgCompatConnection(conn)
    except Exception:
        conn.close()
        raise


def _table_name(name: str) -> str:
    return f"{schema_name()}.{_validate_ident(name)}"


def ensure_schema_namespace(conn: Any) -> None:
    schema = schema_name()
    exists = conn.execute(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s LIMIT 1",
        (schema,),
    ).fetchone()
    if not exists:
        try:
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            raise RuntimeError(
                f"PostgreSQL 助手 schema {schema!r} 不存在，当前账号无权限自动创建。"
                "请使用 backend/schema/postgresql_assistant.sql 由管理员或库 owner 初始化，"
                "或将 BF_ASSISTANT_PG_SCHEMA 指向一个当前账号已有 CREATE 权限的 schema。"
            ) from exc
    conn.execute(f"SET search_path TO {schema}, bf_sensor, public")


def ensure_column(conn: PgCompatConnection | Any, table: str, column: str, ddl: str) -> None:
    schema = schema_name()
    table = _validate_ident(table)
    column = _validate_ident(column)
    raw = conn.conn if isinstance(conn, PgCompatConnection) else conn
    row = raw.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = %s
        LIMIT 1
        """,
        (schema, table, column),
    ).fetchone()
    if row:
        return
    pg_ddl = (
        ddl.replace("INTEGER", "bigint")
        .replace("TEXT", "text")
        .replace("NOT NULL DEFAULT 0", "NOT NULL DEFAULT 0")
    )
    raw.execute(f"ALTER TABLE {schema}.{table} ADD COLUMN {column} {pg_ddl}")


def missing_assistant_tables(conn: Any) -> list[str]:
    schema = schema_name()
    rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = ANY(%s)
        """,
        (schema, list(ASSISTANT_REQUIRED_TABLES)),
    ).fetchall()
    existing = {row["table_name"] for row in rows}
    return [table for table in ASSISTANT_REQUIRED_TABLES if table not in existing]


def ensure_assistant_schema(conn: Any) -> None:
    schema = schema_name()
    ensure_schema_namespace(conn)
    try:
        conn.execute(
            f"""
        CREATE TABLE IF NOT EXISTS {schema}.furnace_snapshots (
            id bigserial PRIMARY KEY,
            source_time text NOT NULL,
            created_at text NOT NULL,
            values_json text NOT NULL,
            diagnosis_json text NOT NULL,
            recommendation_json text NOT NULL,
            data_quality_json text NOT NULL,
            payload_json text NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_furnace_snapshots_created
            ON {schema}.furnace_snapshots(created_at DESC);

        CREATE TABLE IF NOT EXISTS {schema}.qa_conversations (
            id text PRIMARY KEY,
            title text NOT NULL,
            created_at text NOT NULL,
            updated_at text NOT NULL,
            last_user_at text,
            project_id bigint,
            status text NOT NULL DEFAULT 'active',
            is_pinned integer NOT NULL DEFAULT 0,
            is_unread integer NOT NULL DEFAULT 0,
            archived_at text
        );
        CREATE INDEX IF NOT EXISTS idx_qa_conversations_updated
            ON {schema}.qa_conversations(updated_at DESC);

        CREATE TABLE IF NOT EXISTS {schema}.qa_messages (
            id bigserial PRIMARY KEY,
            conversation_id text NOT NULL REFERENCES {schema}.qa_conversations(id) ON DELETE CASCADE,
            role text NOT NULL,
            content text NOT NULL,
            created_at text NOT NULL,
            snapshot_id bigint,
            hidden_context_json text
        );
        CREATE INDEX IF NOT EXISTS idx_qa_messages_conversation
            ON {schema}.qa_messages(conversation_id, id);

        CREATE TABLE IF NOT EXISTS {schema}.period_reports (
            id bigserial PRIMARY KEY,
            furnace_id text NOT NULL DEFAULT 'GL02',
            period_kind text NOT NULL CHECK (period_kind IN ('hourly', 'daily', 'weekly', 'monthly')),
            period_start text NOT NULL,
            period_end text NOT NULL,
            timezone text NOT NULL DEFAULT 'Asia/Shanghai',
            title text NOT NULL,
            report_markdown text NOT NULL,
            markdown_path text,
            docx_path text,
            metrics_json text,
            diagnosis_json text,
            recommendation_json text,
            sensor_refs_json text,
            source_snapshot_min_id bigint,
            source_snapshot_max_id bigint,
            created_at text NOT NULL,
            updated_at text NOT NULL,
            UNIQUE (furnace_id, period_kind, period_start, period_end)
        );
        CREATE INDEX IF NOT EXISTS idx_period_reports_range
            ON {schema}.period_reports(furnace_id, period_kind, period_start, period_end);

        CREATE TABLE IF NOT EXISTS {schema}.report_template (
            id bigserial PRIMARY KEY,
            code text NOT NULL UNIQUE,
            name text NOT NULL,
            report_type text NOT NULL CHECK (report_type IN ('hourly', 'daily', 'weekly', 'monthly')),
            description text,
            template_schema text,
            render_type text NOT NULL DEFAULT 'json_card',
            enabled integer NOT NULL DEFAULT 1,
            created_at text NOT NULL,
            updated_at text NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_report_template_type
            ON {schema}.report_template(report_type, enabled, updated_at);

        CREATE TABLE IF NOT EXISTS {schema}.report_instance (
            id bigserial PRIMARY KEY,
            template_id bigint NOT NULL REFERENCES {schema}.report_template(id),
            period_report_id bigint,
            furnace_id text NOT NULL DEFAULT 'GL02',
            report_type text NOT NULL CHECK (report_type IN ('hourly', 'daily', 'weekly', 'monthly')),
            time_start text NOT NULL,
            time_end text NOT NULL,
            title text NOT NULL,
            summary text,
            content_json text,
            content_markdown text NOT NULL,
            preview_html text,
            markdown_path text,
            docx_path text,
            created_by text,
            created_at text NOT NULL,
            updated_at text NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_report_instance_range
            ON {schema}.report_instance(furnace_id, report_type, time_start, time_end, id);

        CREATE TABLE IF NOT EXISTS {schema}.qa_projects (
            id bigserial PRIMARY KEY,
            furnace_id text NOT NULL DEFAULT 'GL02',
            name text NOT NULL,
            folder_path text NOT NULL,
            description text,
            created_by text,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            is_pinned integer NOT NULL DEFAULT 0,
            archived_at text,
            created_at text NOT NULL,
            updated_at text NOT NULL,
            UNIQUE (furnace_id, folder_path)
        );
        CREATE INDEX IF NOT EXISTS idx_qa_projects_status
            ON {schema}.qa_projects(furnace_id, status, updated_at);

        CREATE TABLE IF NOT EXISTS {schema}.project_assets (
            id bigserial PRIMARY KEY,
            project_id bigint NOT NULL REFERENCES {schema}.qa_projects(id) ON DELETE CASCADE,
            asset_type text NOT NULL CHECK (asset_type IN ('period_report', 'markdown_file', 'docx_file', 'folder', 'txt_file', 'pdf_file', 'spreadsheet_file', 'csv_file', 'other')),
            asset_ref_id text NOT NULL DEFAULT '',
            file_path text NOT NULL DEFAULT '',
            display_name text NOT NULL,
            default_include_mode text NOT NULL DEFAULT 'summary' CHECK (default_include_mode IN ('summary', 'full_text', 'selected_sections', 'citation_only')),
            created_at text NOT NULL,
            updated_at text NOT NULL,
            UNIQUE(project_id, asset_type, asset_ref_id, file_path)
        );
        CREATE INDEX IF NOT EXISTS idx_project_assets_project
            ON {schema}.project_assets(project_id, asset_type, updated_at);

        CREATE TABLE IF NOT EXISTS {schema}.qa_message_context_refs (
            id bigserial PRIMARY KEY,
            conversation_id text,
            message_id bigint,
            project_id bigint,
            ref_type text NOT NULL CHECK (ref_type IN ('period_report', 'project_asset', 'project_file', 'manual_text')),
            ref_id text,
            insert_mode text NOT NULL CHECK (insert_mode IN ('summary', 'full_text', 'selected_sections', 'citation_only', 'manual_edited')),
            inserted_title text,
            inserted_text text,
            source_path text,
            created_at text NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_qa_message_context_refs_message
            ON {schema}.qa_message_context_refs(conversation_id, message_id, ref_type);
        """
        )
        ensure_rag_schema(conn)
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        try:
            missing = missing_assistant_tables(conn)
        except Exception:  # noqa: BLE001
            missing = list(ASSISTANT_REQUIRED_TABLES)
        if not missing:
            # The production app account may deliberately have DML privileges
            # only. In that case an owner/admin must initialize the schema once.
            ensure_schema_namespace(conn)
            return
        raise RuntimeError(
            f"无法初始化 PostgreSQL 助手表到 schema {schema!r}。"
            "请确认当前账号对该 schema 具有 CREATE/INSERT/UPDATE/SELECT 权限，"
            "或先由管理员执行 backend/schema/postgresql_assistant.sql。"
            f" 当前缺少表：{', '.join(missing)}。"
        ) from exc


def ensure_rag_schema(conn: Any) -> None:
    schema = schema_name()
    ensure_schema_namespace(conn)
    try:
        conn.execute(
            f"""
        CREATE TABLE IF NOT EXISTS {schema}.rag_document (
            doc_id text PRIMARY KEY,
            title text NOT NULL,
            source_file text NOT NULL,
            knowledge_category text NOT NULL,
            task_scope_json text NOT NULL,
            version text NOT NULL DEFAULT 'v1.0',
            authority_level text NOT NULL DEFAULT 'knowledge_doc',
            full_text text NOT NULL,
            content_hash text NOT NULL,
            created_at text NOT NULL,
            updated_at text NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {schema}.rag_chunk (
            chunk_id text PRIMARY KEY,
            doc_id text NOT NULL REFERENCES {schema}.rag_document(doc_id) ON DELETE CASCADE,
            parent_chunk_id text,
            title text NOT NULL,
            content text NOT NULL,
            enriched_content text NOT NULL,
            summary text,
            keywords_json text NOT NULL,
            entities_json text NOT NULL,
            phenomenon_json text NOT NULL,
            parameter_names_json text NOT NULL,
            chunk_type text NOT NULL,
            token_count integer NOT NULL,
            source_file text NOT NULL,
            knowledge_category text NOT NULL,
            task_scope_json text NOT NULL,
            authority_level text NOT NULL,
            source_priority integer NOT NULL DEFAULT 50,
            content_hash text NOT NULL,
            created_at text NOT NULL,
            search_text text GENERATED ALWAYS AS (
                coalesce(title, '') || ' ' || coalesce(enriched_content, '')
            ) STORED
        );
        CREATE INDEX IF NOT EXISTS idx_rag_chunk_doc
            ON {schema}.rag_chunk(doc_id);
        CREATE INDEX IF NOT EXISTS idx_rag_chunk_category
            ON {schema}.rag_chunk(knowledge_category, source_priority DESC);

        CREATE TABLE IF NOT EXISTS {schema}.rag_query_log (
            query_id text PRIMARY KEY,
            user_query text NOT NULL,
            intent_type text NOT NULL,
            retrieved_chunk_ids_json text NOT NULL,
            created_at text NOT NULL
        );
        """
        )
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise RuntimeError(
            f"无法初始化 PostgreSQL RAG 表到 schema {schema!r}。"
            "请确认当前账号对该 schema 具有 CREATE/INSERT/UPDATE/SELECT 权限，"
            "或先由管理员执行 backend/schema/postgresql_assistant.sql。"
        ) from exc
