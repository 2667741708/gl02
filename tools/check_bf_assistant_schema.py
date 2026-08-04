from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any


def read_user_env(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except OSError:
        return ""


def get_password(name: str, default: str = "", *, prefer_user_env: bool = False) -> str:
    user_value = read_user_env(name)
    process_value = os.environ.get(name, "")
    if prefer_user_env:
        return user_value or process_value or default
    return process_value or user_value or default


def targets() -> dict[str, dict[str, Any]]:
    return {
        "local": {
            "host": "127.0.0.1",
            "port": 15432,
            "dbname": "bf_trend",
            "user": "gl02_sync",
            "password": "gl02_local_sync",
        },
        "22012": {
            "host": "10.30.220.12",
            "port": 5432,
            "dbname": "bf_trend",
            "user": "gl02_reader",
            "password": get_password("GL02_PGPASSWORD", prefer_user_env=True),
        },
    }


def check_target(name: str, cfg: dict[str, Any], schema: str, timeout: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "host": cfg["host"],
        "port": cfg["port"],
        "database": cfg["dbname"],
        "user": cfg["user"],
    }
    if not cfg.get("password"):
        item.update({"connected": False, "error": "missing password environment"})
        return item

    try:
        import psycopg
    except Exception as exc:
        item.update({"connected": False, "error": f"import psycopg failed: {exc}"})
        return item

    try:
        with psycopg.connect(
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
            connect_timeout=timeout,
            options=f"-c statement_timeout={timeout * 1000}",
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("select current_database(), current_user")
                database, current_user = cur.fetchone()
                cur.execute("select exists(select 1 from pg_namespace where nspname=%s)", (schema,))
                exists_in_pg_namespace = bool(cur.fetchone()[0])
                cur.execute(
                    "select exists(select 1 from information_schema.schemata where schema_name=%s)",
                    (schema,),
                )
                visible_in_information_schema = bool(cur.fetchone()[0])

                has_usage = False
                has_create = False
                if exists_in_pg_namespace:
                    cur.execute("select has_schema_privilege(current_user, %s, 'USAGE')", (schema,))
                    has_usage = bool(cur.fetchone()[0])
                    cur.execute("select has_schema_privilege(current_user, %s, 'CREATE')", (schema,))
                    has_create = bool(cur.fetchone()[0])

                visible_tables: list[str] = []
                if has_usage:
                    cur.execute(
                        """
                        select table_name
                        from information_schema.tables
                        where table_schema=%s
                          and table_type='BASE TABLE'
                        order by table_name
                        """,
                        (schema,),
                    )
                    visible_tables = [row[0] for row in cur.fetchall()]

                item.update(
                    {
                        "connected": True,
                        "current_database": database,
                        "current_user": current_user,
                        "schema": schema,
                        "exists_in_pg_namespace": exists_in_pg_namespace,
                        "visible_in_information_schema": visible_in_information_schema,
                        "current_user_has_usage": has_usage,
                        "current_user_has_create": has_create,
                        "visible_table_count": len(visible_tables),
                        "visible_tables": visible_tables,
                    }
                )
    except Exception as exc:
        item.update({"connected": False, "error": str(exc)})
    return item


def print_text(payload: dict[str, Any]) -> None:
    print(f"checked_at: {payload['checked_at']}")
    for item in payload["results"]:
        print()
        print(f"[{item['name']}] {item['user']}@{item['host']}:{item['port']}/{item['database']}")
        print(f"connected: {item.get('connected')}")
        if not item.get("connected"):
            print(f"error: {item.get('error')}")
            continue
        print(f"schema_exists: {item['exists_in_pg_namespace']}")
        print(f"schema_visible: {item['visible_in_information_schema']}")
        print(f"has_usage: {item['current_user_has_usage']}")
        print(f"has_create: {item['current_user_has_create']}")
        print(f"visible_table_count: {item['visible_table_count']}")
        if item["visible_tables"]:
            print("visible_tables: " + ", ".join(item["visible_tables"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check bf_assistant schema visibility on local and 220.12 PostgreSQL.")
    parser.add_argument("--targets", default="local,22012", help="Comma-separated target names: local,22012")
    parser.add_argument("--schema", default="bf_assistant")
    parser.add_argument("--timeout-seconds", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    all_targets = targets()
    selected = [part.strip() for part in args.targets.split(",") if part.strip()]
    unknown = [name for name in selected if name not in all_targets]
    if unknown:
        print(f"Unknown target(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    payload = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "results": [
            check_target(name, all_targets[name], args.schema, args.timeout_seconds)
            for name in selected
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
