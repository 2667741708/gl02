"""Patch the active V4 GL02 MCP with the read-only IMES report tool."""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


TOOL = r'''

@mcp.tool()
def query_bf2_operation_log_report(workdate: str = "", limit: int = 200) -> dict[str, Any]:
    """查询 2# 高炉冀南新区高炉作业日志报表的已落库数据。"""
    day = (workdate or datetime.now(LOCAL_TZ).strftime("%Y-%m-%d"))[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("workdate 必须是 YYYY-MM-DD") from exc
    limit = max(1, min(int(limit or 200), 5000))
    profile = get_profile()
    if profile.get("engine") != "bf_sensor_postgresql":
        return {"ok": False, "error": "report_dataset_requires_postgresql", "message": "当前数据库 profile 不是 bf_sensor_postgresql。"}
    psycopg, dict_row = import_psycopg()
    query = """
        SELECT workdate, report_row_number, report_id,
               report_time_raw, report_time_display,
               report_batch_count, report_coal_ratio, report_fuel_ratio,
               material_rate, material_rate_status, material_rate_note,
               report_headers, report_cells, fetched_at, updated_at
        FROM bf_imes.v_bf2_operation_log_report
        WHERE workdate = %s::date
        ORDER BY report_row_number
        LIMIT %s
    """
    try:
        with psycopg.connect(pg_conninfo(profile), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(query, (day, limit))
                rows = [{key: jsonable(value) for key, value in dict(row).items()} for row in cur.fetchall()]
    except Exception as exc:
        return {"ok": False, "workdate": day, "error": type(exc).__name__, "message": "报表视图不可用或数据库连接失败。"}
    return {
        "ok": True,
        "source": "bf_imes.v_bf2_operation_log_report",
        "furnace": "2#高炉",
        "workdate": day,
        "rows_count": len(rows),
        "rows": rows,
        "semantics": {
            "report_fuel_ratio": "Raqsoft 页面 M 列公式重算，不是 IMES 原始字段",
            "report_batch_count": "Raqsoft 页面 D 列批数",
            "material_rate": "语义待现场确认，当前不由批数推断",
        },
    }
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    args = parser.parse_args()
    path = Path(args.path)
    text = path.read_text(encoding="utf-8")
    marker = "\ndef latest_snapshot_value("
    if "def query_bf2_operation_log_report(" in text:
        print("already_present")
        return 0
    if marker not in text:
        raise RuntimeError("MCP insertion marker not found; refusing to modify unknown version")
    backup = path.with_name(path.name + ".bak_report_mcp_20260808")
    shutil.copy2(path, backup)
    path.write_text(text.replace(marker, TOOL + marker, 1), encoding="utf-8")
    print(f"patched={path}")
    print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
