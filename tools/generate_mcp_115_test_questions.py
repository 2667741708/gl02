from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "docs" / "MCP_115变量诊断指标测试问题集.md"


@dataclass(frozen=True)
class Sensor:
    variable_name: str
    tag_long_name: str
    description: str


def import_psycopg() -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("缺少 psycopg，需使用项目 .venv 或已安装 psycopg 的 Python 运行。") from exc
    return psycopg, dict_row


def conninfo(args: argparse.Namespace) -> str:
    return (
        f"host={args.host} port={args.port} dbname={args.database} "
        f"user={args.user} password={args.password} connect_timeout=10"
    )


def fetch_physical_sensors(args: argparse.Namespace) -> list[Sensor]:
    psycopg, dict_row = import_psycopg()
    sql = """
        SELECT variable_name, tag_long_name, description
        FROM bf_sensor.sensor_registry
        WHERE is_enabled
          AND tag_long_name <> 'T_top_A-D avg'
        ORDER BY
          CASE
            WHEN variable_name LIKE 'T_body_%' THEN 20
            WHEN variable_name LIKE 'T_throat_%' THEN 21
            ELSE 10
          END,
          variable_name
    """
    with psycopg.connect(conninfo(args), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [
        Sensor(
            variable_name=str(row["variable_name"]),
            tag_long_name=str(row["tag_long_name"]),
            description=str(row["description"] or ""),
        )
        for row in rows
    ]


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def command_for(variable: str, start: str, end: str) -> str:
    return (
        'python "高炉前端数据/智能助手/mcp/gl02_mcp_python_sdk_query.py" '
        f'features --variable "{variable}" --start "{start}" --end "{end}" --max-points 5000'
    )


def natural_fuzzy_cases(start: str, end: str) -> list[tuple[str, str, str, str]]:
    return [
        (
            "过去 1h 的炉顶温度怎么变？",
            "`T_top`（综合顶温，T_top_A-D 平均）",
            "先用 `find_gl02_variables(\"炉顶温度\")` 确认解析到综合顶温，再调用 `query_gl02_feature_statistics(variable=\"炉顶温度\", start_time, end_time)`。",
            command_for("炉顶温度", start, end),
        ),
        (
            "过去 1h 的炉顶压力有没有上升？",
            "`P_top`（综合顶压/顶压平均）",
            "用别名“炉顶压力/顶压/综合顶压”解析到 `P_top`，重点看 `features.range.slope_per_min`、`delta`、`trend`、`z60`。",
            command_for("炉顶压力", start, end),
        ),
        (
            "过去 1h 的炉喉压力变化如何？",
            "`P_top_gas_A-D`（当前口径：4 个上升管煤气压力；没有单独炉喉压力平均点）",
            "当前应拆成 A/B/C/D 四次查询，或让调用方并行调用 MCP；分别看四点 `trend/stddev/z60` 后再比较差异。",
            "<br>".join(command_for(v, start, end) for v in ["炉喉压力A", "炉喉压力B", "炉喉压力C", "炉喉压力D"]),
        ),
        (
            "过去 1h 的透气性指数变化怎样？",
            "`PI`（透气性指数）",
            "用“透气性指数/透气指数/透气性”解析到 `PI`，重点看 `delta/trend/slope_per_min/z60/z15`。",
            command_for("透气性指数", start, end),
        ),
        (
            "过去 1h 的煤气利用率变化怎样？",
            "`GasUtil`（煤气利用率，数据库为原始小数）",
            "用“煤气利用率/煤气利用”解析到 `GasUtil`；MCP 返回原始小数，前端展示时再转百分数。",
            command_for("煤气利用率", start, end),
        ),
        (
            "最近 1h 炉顶温度、顶压、透气性、煤气利用率一起看，哪个变化最大？",
            "`T_top/P_top/PI/GasUtil`",
            "对四个变量分别调用 `query_gl02_feature_statistics()`，按 `abs(delta)`、`abs(z60)` 或 `trend` 汇总排序。",
            "<br>".join(command_for(v, start, end) for v in ["炉顶温度", "炉顶压力", "透气性指数", "煤气利用率"]),
        ),
        (
            "过去 1h 上升管四点顶温是否偏散？",
            "`T_top_A-D`",
            "分别查 A/B/C/D 四点，比较 `avg/max/min/stddev/z60`；综合温度则查 `T_top`。",
            "<br>".join(command_for(v, start, end) for v in ["顶温A", "顶温B", "顶温C", "顶温D"]),
        ),
    ]


def build_markdown(sensors: list[Sensor], args: argparse.Namespace) -> str:
    end_dt = datetime.fromisoformat(args.end.replace("+08:00", ""))
    windows = [
        ("15 分钟", end_dt - timedelta(minutes=15), end_dt),
        ("60 分钟", end_dt - timedelta(minutes=60), end_dt),
        ("2 小时", end_dt - timedelta(hours=2), end_dt),
        ("24 小时", end_dt - timedelta(hours=24), end_dt),
    ]
    default_start = iso(end_dt - timedelta(hours=2))
    default_end = iso(end_dt)
    lines = [
        "# MCP 115 变量诊断指标测试问题集",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 用途",
        "",
        "本文件用于逐个验证 MCP 对 115 个物理诊断变量的增强统计能力：`avg/min/max/stddev/slope/trend/z60/z15/zstd/baseline_30d`。",
        "",
        "对应实现：",
        "",
        "- [增强统计 MCP 工具 bf_data_mcp_server.py:L1653-L1716](../高炉前端数据/智能助手/mcp/bf_data_mcp_server.py#L1653-L1716)",
        "- [本测试集生成脚本 generate_mcp_115_test_questions.py:L37-L236](../tools/generate_mcp_115_test_questions.py#L37-L236)",
        "",
        "## 2. 时间窗测试矩阵",
        "",
        "| 测试窗 | 目标 | CLI 示例 |",
        "|---|---|---|",
    ]
    for label, start_dt, stop_dt in windows:
        start = iso(start_dt)
        stop = iso(stop_dt)
        lines.append(
            f"| {label} | 验证不同历史范围的均值、极值、标准差、斜率、趋势和 Z 指标 | `{command_for('P_blast', start, stop)}` |"
        )
    lines.extend(
        [
            "",
            "## 3. 中文模糊自然问法测试集",
            "",
            "这部分用于验证真实问法是否能被 MCP/调用方解析到正确变量。推荐调用顺序：先 `find_gl02_variables()` 看候选，再把确认后的中文名或变量名传给 `query_gl02_feature_statistics()`。",
            "",
            "| 自然问法 | 应解析到 | MCP 做法 | CLI 示例 |",
            "|---|---|---|---|",
        ]
    )
    one_hour_start = iso(end_dt - timedelta(hours=1))
    one_hour_end = iso(end_dt)
    for question, resolved, method, command in natural_fuzzy_cases(one_hour_start, one_hour_end):
        lines.append(f"| {question} | {resolved} | {method} | `{command}` |")
    lines.extend(
        [
            "",
            "注意：当前项目没有单独的“炉喉压力平均”物理点；自然问法“炉喉压力”在测试中按 4 个上升管煤气压力 `P_top_gas_A-D` 处理。如后续新增独立炉喉压力点，需要先补充映射和 aliases。",
            "",
            "## 4. 逐变量示例问题",
            "",
            f"默认示例时间窗：`{default_start}` 到 `{default_end}`。需要测试其他范围时，替换问题中的时间或 CLI 的 `--start/--end`。",
            "",
            f"变量数量：{len(sensors)}",
            "",
            "| # | 变量 | 说明 | 示例问题 | CLI |",
            "|---:|---|---|---|---|",
        ]
    )
    for idx, sensor in enumerate(sensors, 1):
        desc = sensor.description.replace("|", "/")
        question = (
            f"请用 MCP 查询 {sensor.variable_name}（{desc}）在 {default_start} 到 {default_end} 的 "
            "均值、最大值、最小值、标准差、斜率、趋势、z60、z15、zstd 和 30天历史基线。"
        )
        lines.append(
            f"| {idx} | `{sensor.variable_name}` | {desc} | {question} | `{command_for(sensor.variable_name, default_start, default_end)}` |"
        )
    lines.extend(
        [
            "",
            "## 5. 炉喉 4 点专项问题",
            "",
            "- 请用中文模糊词“炉喉A”检索点位，并返回变量名、点 ID 和描述。",
            "- 请比较 `T_throat_A/T_throat_B/T_throat_C/T_throat_D` 最近 60 分钟的均值、最大最小、标准差和趋势。",
            "- 请分别查询 4 个炉喉温度点最近 60 分钟的 z60/z15/zstd 和 30 天历史基线。",
            "",
            "## 6. 验收信号",
            "",
            "- 每个变量的 `features.range` 至少包含 `avg/min/max/stddev/slope_per_min/trend`。",
            "- 每个变量的 `features.z` 至少包含 `z60/z15/zstd`；若 `baseline_30d` 为空，需要检查 `bf_sensor.daily_baselines` 是否覆盖该变量。",
            "- 炉喉 4 点应能通过中文“炉喉A-D”、英文 `T_throat_A-D` 和点 ID `SIO_GL02_BT_T0235..T0238` 检索。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate MCP 115-variable diagnostic metric test questions.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="15432")
    parser.add_argument("--database", default="bf_trend")
    parser.add_argument("--user", default="gl02_sync")
    parser.add_argument("--password", default="gl02_local_sync")
    parser.add_argument("--end", default="2026-05-16T10:00:00+08:00")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    sensors = fetch_physical_sensors(args)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_markdown(sensors, args), encoding="utf-8")
    print(f"wrote {output} with {len(sensors)} variables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
