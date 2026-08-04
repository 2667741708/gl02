"""Export one complete real row from every IMES relation readable by two accounts.

The program is intentionally read-only. It discovers relations through
information_schema, verifies SELECT privilege, starts a read-only transaction,
and writes JSON/Markdown evidence without recording database passwords.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "db_dashboard"))
import heat_service  # noqa: E402


def json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"type": "bytes", "hex": value.hex()}
    return str(value)


def display_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=json_default)
    else:
        text = str(json_default(value))
    return text.replace("|", "\\|").replace("\r", "\\r").replace("\n", "\\n")


def readable_relations(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT t.table_schema, t.table_name, t.table_type
        FROM information_schema.tables t
        WHERE t.table_schema = 'public'
          AND has_table_privilege(
                quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),
                'SELECT'
              )
        ORDER BY t.table_name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def relation_columns(
    conn: psycopg.Connection[Any], schema_name: str, relation_name: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ordinal_position, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema_name, relation_name),
    ).fetchall()
    return [dict(row) for row in rows]


def sample_relation(
    conn: psycopg.Connection[Any], schema_name: str, relation_name: str
) -> dict[str, Any]:
    columns = relation_columns(conn, schema_name, relation_name)
    relation = sql.Identifier(schema_name, relation_name)
    if schema_name == "public" and relation_name == "batch_input":
        query = sql.SQL(
            "SELECT * FROM {} "
            "WHERE workdate >= %s AND workdate < %s "
            "LIMIT 1"
        ).format(relation)
        row = conn.execute(
            query,
            (datetime(2026, 7, 26), datetime(2026, 7, 27)),
        ).fetchone()
    elif schema_name == "public" and relation_name == "slag_inspection":
        query = sql.SQL(
            "SELECT * FROM {} WHERE meltno IS NOT NULL LIMIT 1"
        ).format(relation)
        row = conn.execute(query).fetchone()
    else:
        query = sql.SQL("SELECT * FROM {} LIMIT 1").format(relation)
        row = conn.execute(query).fetchone()
    record = dict(row) if row is not None else None
    row_json = (
        json.dumps(record, ensure_ascii=False, sort_keys=True, default=json_default)
        if record is not None
        else ""
    )
    return {
        "columns": columns,
        "column_count": len(columns),
        "has_row": record is not None,
        "record": record,
        "row_sha256": hashlib.sha256(row_json.encode("utf-8")).hexdigest()
        if record is not None
        else None,
    }


def audit_account(
    account_key: str,
    purpose: str,
    params: dict[str, Any],
    statement_timeout_ms: int,
    include_plaintext_credentials: bool,
) -> dict[str, Any]:
    safe_target = {
        "host": params.get("host"),
        "port": params.get("port"),
        "dbname": params.get("dbname"),
    }
    result: dict[str, Any] = {
        "account_key": account_key,
        "purpose": purpose,
        "target": safe_target,
        "credentials": {
            "username": params.get("user"),
            "password": params.get("password")
            if include_plaintext_credentials
            else "<omitted>",
            "plaintext_included": include_plaintext_credentials,
        },
        "identity": {},
        "relations": [],
    }
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        conn.execute("SET default_transaction_read_only = on")
        conn.execute(
            "SELECT set_config('statement_timeout', %s, false)",
            (str(statement_timeout_ms),),
        )
        identity = conn.execute(
            """
            SELECT current_database() AS database,
                   current_user AS db_user,
                   session_user,
                   current_setting('transaction_read_only') AS read_only,
                   current_setting('TimeZone') AS timezone,
                   current_timestamp AS server_time
            """
        ).fetchone()
        result["identity"] = dict(identity)
        for relation in readable_relations(conn):
            entry = dict(relation)
            try:
                entry.update(
                    sample_relation(
                        conn, relation["table_schema"], relation["table_name"]
                    )
                )
                entry["error"] = None
            except Exception as exc:  # keep the remainder of the audit usable
                conn.rollback()
                conn.execute("SET default_transaction_read_only = on")
                conn.execute(
                    "SELECT set_config('statement_timeout', %s, false)",
                    (str(statement_timeout_ms),),
                )
                entry.update(
                    {
                        "columns": [],
                        "column_count": 0,
                        "has_row": False,
                        "record": None,
                        "row_sha256": None,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            result["relations"].append(entry)
    return result


def render_markdown(report: dict[str, Any]) -> str:
    plaintext_included = bool(report.get("plaintext_credentials_included"))
    lines = [
        "# IMES 可读表/视图：逐对象一条完整真实记录",
        "",
        f"- 取样时间：`{report['sampled_at']}`",
        "- 查询方式：Vastbase 只读事务；每个可读对象执行 `SELECT * ... LIMIT 1`。",
        "- 完整性口径：表格按数据库字段顺序列出全部列；`NULL` 表示源记录空值，不代表 0。",
        (
            "- 敏感信息：本报告按用户明确授权包含数据库账号和明文密码；"
            "文件已加入 `.gitignore`，不得提交、截图外发或复制到前端。"
            if plaintext_included
            else "- 安全口径：报告不包含数据库密码、SSH 密码或 Web Cookie。"
        ),
        "",
        "## 汇总",
        "",
        "| 账号用途 | 数据库用户 | 可读对象数 | 成功取到记录 | 空表/失败 |",
        "|---|---|---:|---:|---:|",
    ]
    for account in report["accounts"]:
        ok_count = sum(
            1
            for relation in account["relations"]
            if relation["has_row"] and not relation["error"]
        )
        failed_count = len(account["relations"]) - ok_count
        lines.append(
            f"| {account['account_key']} | `{account['identity'].get('db_user')}` | "
            f"{len(account['relations'])} | {ok_count} | {failed_count} |"
        )
    for account in report["accounts"]:
        lines.extend(
            [
                "",
                f"## 账号：{account['account_key']} "
                f"(`{account['identity'].get('db_user')}`)",
                "",
                f"- 数据库：`{account['identity'].get('database')}`",
                f"- 账号用途：{account['purpose']}",
                f"- 登录账号：`{account['credentials'].get('username')}`",
                f"- 明文密码：`{account['credentials'].get('password')}`",
                f"- 只读状态：`{account['identity'].get('read_only')}`",
                f"- 数据库服务器时间：`{account['identity'].get('server_time')}`",
            ]
        )
        for index, relation in enumerate(account["relations"], start=1):
            relation_id = (
                f"{relation['table_schema']}.{relation['table_name']}"
            )
            lines.extend(
                [
                    "",
                    f"### {index}. `{relation_id}`",
                    "",
                    f"- 对象类型：`{relation['table_type']}`",
                    f"- 完整列数：`{relation['column_count']}`",
                    f"- 记录哈希：`{relation['row_sha256'] or '无'}`",
                ]
            )
            if relation["error"]:
                lines.append(f"- 查询错误：`{relation['error']}`")
                continue
            if not relation["has_row"]:
                lines.append("- 该对象当前未取到记录。")
                continue
            lines.extend(
                [
                    "",
                    "| 序号 | 字段名 | 数据类型 | 真实值 |",
                    "|---:|---|---|---|",
                ]
            )
            record = relation["record"]
            for column in relation["columns"]:
                name = column["column_name"]
                lines.append(
                    f"| {column['ordinal_position']} | `{name}` | "
                    f"`{column['data_type']}` | {display_value(record.get(name))} |"
                )
    lines.extend(
        [
            "",
            "## 通过 MCP 按变量和时间范围访问",
            "",
            "MCP 服务入口：",
            "`高炉前端数据/智能助手/mcp/imes_relay_mcp_server.py`。",
            "所有查询都在数据库只读事务中执行。时间范围采用",
            "`[start_time, end_time)`，即开始时间包含、结束时间不包含。",
            "",
            "### 1. 查看两个账号和可读对象",
            "",
            "```json",
            '{"tool":"list_imes_database_profiles","arguments":{}}',
            "```",
            "",
            "```json",
            '{"tool":"list_imes_business_objects","arguments":{"account_profile":"operations"}}',
            "```",
            "",
            "```json",
            '{"tool":"list_imes_business_objects","arguments":{"account_profile":"laboratory"}}',
            "```",
            "",
            "### 2. 按变量和时间范围查询生产实绩",
            "",
            "```json",
            "{",
            '  "tool": "query_imes_variables",',
            '  "arguments": {',
            '    "account_profile": "operations",',
            '    "object_name": "public.t_ipes_out_put",',
            '    "variables": ["workdate", "meltno", "ironquan", "workshift"],',
            '    "time_column": "workdate",',
            '    "start_time": "2026-07-25 00:00:00",',
            '    "end_time": "2026-07-27 00:00:00",',
            '    "exact_filters": {"prodcentercode": "2D012"},',
            '    "order_by": "workdate",',
            '    "descending": true,',
            '    "row_limit": 200',
            "  }",
            "}",
            "```",
            "",
            "### 3. 按变量和时间范围查询烧结矿化验",
            "",
            "```json",
            "{",
            '  "tool": "query_imes_variables",',
            '  "arguments": {',
            '    "account_profile": "laboratory",',
            '    "object_name": "public.v_qpes_sinter_machine_sample_insp_final",',
            '    "variables": ["试样单号", "业务日期", "加工中心编码", "tfevalue", "caovalue", "sio2value"],',
            '    "time_column": "业务日期",',
            '    "start_time": "2026-07-01",',
            '    "end_time": "2026-07-28",',
            '    "exact_filters": {"加工中心编码": "JS2"},',
            '    "order_by": "业务日期",',
            '    "descending": true,',
            '    "row_limit": 100',
            "  }",
            "}",
            "```",
            "",
            "### 4. 执行任意单条只读 SQL",
            "",
            "SQL 可使用 `%s` 参数占位符；只允许一条",
            "`SELECT/WITH/SHOW/EXPLAIN/VALUES/TABLE` 查询，写入、DDL、",
            "事务控制和多语句会被拒绝。",
            "",
            "```json",
            "{",
            '  "tool": "query_imes_readonly_sql",',
            '  "arguments": {',
            '    "account_profile": "operations",',
            '    "sql": "SELECT workdate,meltno,ironquan FROM public.t_ipes_out_put WHERE workdate >= %s AND workdate < %s AND prodcentercode = %s ORDER BY workdate DESC",',
            '    "parameters": ["2026-07-25", "2026-07-27", "2D012"],',
            '    "row_limit": 500',
            "  }",
            "}",
            "```",
            "",
            "调用第二个账号时，只需把 `account_profile` 改为",
            "`laboratory`；不得把账号或密码作为 MCP 参数传入。",
        ]
    )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从两个 IMES Vastbase 只读账号的每个可读表/视图抽取一条完整记录。"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "logs" / "imes_complete_row_samples_20260727",
    )
    parser.add_argument("--statement-timeout-ms", type=int, default=60000)
    parser.add_argument(
        "--include-plaintext-credentials",
        action="store_true",
        help="按用户明确授权在本机报告中写入数据库账号和明文密码。",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "audit_id": "Q-IMES-COMPLETE-ROW-SAMPLES-20260727",
        "sampled_at": datetime.now().astimezone(),
        "policy": "read_only_select_limit_1",
        "plaintext_credentials_included": args.include_plaintext_credentials,
        "accounts": [
            audit_account(
                "operations",
                "炉次作业、生产实绩、批次投料、铁水旧化验和炉渣旧检验",
                heat_service.imes_ops_params(),
                args.statement_timeout_ms,
                args.include_plaintext_credentials,
            ),
            audit_account(
                "laboratory",
                "铁水、原料/烧结矿、炉渣和炼钢最终化验视图",
                heat_service.imes_lab_params(),
                args.statement_timeout_ms,
                args.include_plaintext_credentials,
            ),
        ],
    }
    json_path = args.output_dir / "imes_complete_row_samples.json"
    markdown_path = args.output_dir / "imes_complete_row_samples.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    summary = {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "accounts": [
            {
                "account_key": account["account_key"],
                "db_user": account["identity"].get("db_user"),
                "read_only": account["identity"].get("read_only"),
                "readable_relations": len(account["relations"]),
                "rows_exported": sum(
                    1 for relation in account["relations"] if relation["has_row"]
                ),
                "errors": [
                    {
                        "relation": relation["table_name"],
                        "error": relation["error"],
                    }
                    for relation in account["relations"]
                    if relation["error"]
                ],
            }
            for account in report["accounts"]
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
