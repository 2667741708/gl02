"""Install and verify the append-only recommendation audit schema.

Credentials are read only from process/machine environment variables.  The tool
never prints passwords and never stores them in repository files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = ROOT / "自动诊断服务" / "recommendation_audit_schema.sql"


def environment_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    if os.name != "nt":
        return default
    try:
        import winreg

        path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value or default)
    except OSError:
        return default


def role_exists(conn: Any, role: str) -> bool:
    row = conn.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s) AS ok", (role,)).fetchone()
    return bool(row["ok"] if isinstance(row, dict) else row[0])


def grant_runtime_privileges(conn: Any, writer_role: str, reader_role: str) -> dict[str, bool]:
    from psycopg import sql

    installed: dict[str, bool] = {}
    tables = ("recommendation_audit_batches", "recommendation_audit_actions")
    view = "recommendation_audit_action_detail"
    version_table = "recommendation_audit_schema_versions"

    if role_exists(conn, writer_role):
        installed[writer_role] = True
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA bf_assistant TO {}").format(sql.Identifier(writer_role)))
        for table in tables:
            conn.execute(
                sql.SQL("GRANT SELECT, INSERT ON TABLE bf_assistant.{} TO {}").format(
                    sql.Identifier(table), sql.Identifier(writer_role)
                )
            )
            conn.execute(
                sql.SQL(
                    "REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
                    "ON TABLE bf_assistant.{} FROM {}"
                ).format(sql.Identifier(table), sql.Identifier(writer_role))
            )
        conn.execute(
            sql.SQL("GRANT SELECT ON TABLE bf_assistant.{} TO {}").format(
                sql.Identifier(version_table), sql.Identifier(writer_role)
            )
        )
        conn.execute(
            sql.SQL("GRANT SELECT ON TABLE bf_assistant.{} TO {}").format(
                sql.Identifier(view), sql.Identifier(writer_role)
            )
        )
        conn.execute(
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA bf_assistant TO {}").format(
                sql.Identifier(writer_role)
            )
        )
    else:
        installed[writer_role] = False

    if role_exists(conn, reader_role):
        installed[reader_role] = True
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA bf_assistant TO {}").format(sql.Identifier(reader_role)))
        for relation in (*tables, view, version_table):
            conn.execute(
                sql.SQL("GRANT SELECT ON TABLE bf_assistant.{} TO {}").format(
                    sql.Identifier(relation), sql.Identifier(reader_role)
                )
            )
    else:
        installed[reader_role] = False
    return installed


def main() -> int:
    parser = argparse.ArgumentParser(description="Install recommendation audit schema")
    parser.add_argument("--schema-path", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--host", default=environment_value("GL02_PGHOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(environment_value("GL02_PGPORT", "5432")))
    parser.add_argument("--database", default=environment_value("GL02_PGDATABASE", "bf_trend"))
    parser.add_argument("--user", default=environment_value("GL02_PGADMIN_USER", "postgres"))
    parser.add_argument("--password-env", default="GL02_PGADMIN_PASSWORD")
    parser.add_argument("--writer-role", default="gl02_sync")
    parser.add_argument("--reader-role", default="gl02_reader")
    args = parser.parse_args()

    schema_path = args.schema_path.resolve()
    if not schema_path.is_file():
        raise SystemExit(f"schema file is missing: {schema_path}")
    ddl = schema_path.read_text(encoding="utf-8")
    if "REQ-RECOMMENDATION-FULL-AUDIT-20260806" not in ddl:
        raise SystemExit("schema marker is missing")
    password = environment_value(args.password_env)
    if not password:
        raise SystemExit(f"database password environment variable is missing: {args.password_env}")

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=password,
        connect_timeout=15,
        row_factory=dict_row,
    ) as conn:
        with conn.transaction():
            conn.execute(ddl)
            role_status = grant_runtime_privileges(conn, args.writer_role, args.reader_role)

        verification = conn.execute(
            """
            SELECT
                to_regclass('bf_assistant.recommendation_audit_batches')::text AS batch_table,
                to_regclass('bf_assistant.recommendation_audit_actions')::text AS action_table,
                to_regclass('bf_assistant.recommendation_audit_action_detail')::text AS audit_view,
                EXISTS (
                    SELECT 1 FROM bf_assistant.recommendation_audit_schema_versions
                    WHERE version = 'recommendation_audit.v1'
                ) AS version_installed,
                (
                    SELECT count(*) = 2
                    FROM pg_trigger
                    WHERE tgname IN (
                        'trg_recommendation_audit_batches_immutable',
                        'trg_recommendation_audit_actions_immutable'
                    ) AND NOT tgisinternal
                ) AS immutable_triggers_installed
            """
        ).fetchone()
        writer_privileges = None
        if role_status.get(args.writer_role):
            writer_privileges = conn.execute(
                """
                SELECT
                    has_table_privilege(%s, 'bf_assistant.recommendation_audit_batches', 'SELECT,INSERT') AS batch_append,
                    has_table_privilege(%s, 'bf_assistant.recommendation_audit_actions', 'SELECT,INSERT') AS action_append,
                    has_table_privilege(%s, 'bf_assistant.recommendation_audit_batches', 'UPDATE') AS batch_update,
                    has_table_privilege(%s, 'bf_assistant.recommendation_audit_actions', 'DELETE') AS action_delete
                """,
                (args.writer_role, args.writer_role, args.writer_role, args.writer_role),
            ).fetchone()

    writer_safe = bool(
        not role_status.get(args.writer_role)
        or (
            writer_privileges
            and writer_privileges["batch_append"]
            and writer_privileges["action_append"]
            and not writer_privileges["batch_update"]
            and not writer_privileges["action_delete"]
        )
    )

    result = {
        "ok": bool(
            verification
            and verification["batch_table"]
            and verification["action_table"]
            and verification["audit_view"]
            and verification["version_installed"]
            and verification["immutable_triggers_installed"]
            and writer_safe
        ),
        "schema_version": "recommendation_audit.v1",
        "database": args.database,
        "server": f"{args.host}:{args.port}",
        "relations": dict(verification or {}),
        "roles": role_status,
        "writer_privileges": dict(writer_privileges or {}),
        "password_exposed": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
