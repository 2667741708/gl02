"""Compare pSpace taphole-temperature history with IMES heat/tapping records.

This tool is intentionally read-only.  It uses the one-minute pSpace mirror in
220.12 PostgreSQL for the two taphole temperature tags and the approved IMES
Vastbase relay for official heat numbers and open/close times.

Traceability:
- Q-TAPHOLE-HEAT-INFERENCE-20260719
- docs/铁水硅炉况传感器数据集.md
- docs/question_traceability.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Sequence

import psycopg


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import export_vastbase_local as vastbase  # noqa: E402


TAPHOLE_VARIABLES = ("T_taphole_1", "T_taphole_2")


@dataclass(frozen=True)
class Point:
    variable: str
    ts: datetime
    value: float


@dataclass(frozen=True)
class Transition:
    variable: str
    ts: datetime
    previous: float
    value: float
    delta: float
    direction: str


@dataclass(frozen=True)
class Heat:
    meltno: str
    open_ts: datetime
    close_ts: datetime | None
    tapping_minutes: float | None


def parse_datetime(value: object) -> datetime | None:
    """Parse a database timestamp without inventing a timezone."""

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).strip().replace("T", " "))


def estimate_floor(points: Sequence[Point]) -> float | None:
    """Return the most common 0.1-degree value as the sensor floor."""

    if not points:
        return None
    counts = Counter(round(point.value, 1) for point in points)
    return float(counts.most_common(1)[0][0])


def detect_transitions(
    points: Sequence[Point],
    *,
    minimum_jump: float = 100.0,
    maximum_gap_minutes: float = 2.1,
) -> list[Transition]:
    """Detect large minute-to-minute changes without bridging missing periods."""

    transitions: list[Transition] = []
    for previous, current in zip(points, points[1:]):
        gap_minutes = (current.ts - previous.ts).total_seconds() / 60.0
        delta = current.value - previous.value
        if gap_minutes <= maximum_gap_minutes and abs(delta) >= minimum_jump:
            transitions.append(
                Transition(
                    variable=current.variable,
                    ts=current.ts,
                    previous=previous.value,
                    value=current.value,
                    delta=delta,
                    direction="rise" if delta > 0 else "fall",
                )
            )
    return transitions


def nearest_transition(
    open_ts: datetime,
    transitions: Sequence[Transition],
    *,
    window_minutes: float = 60.0,
) -> tuple[Transition | None, float | None]:
    """Return the closest large sensor transition to an official open time."""

    candidates = [
        (abs((transition.ts - open_ts).total_seconds()) / 60.0, transition)
        for transition in transitions
        if abs((transition.ts - open_ts).total_seconds()) <= window_minutes * 60
    ]
    if not candidates:
        return None, None
    error, transition = min(candidates, key=lambda item: (item[0], item[1].ts))
    return transition, error


def nearest_value(
    points: Sequence[Point],
    target: datetime,
    *,
    window_minutes: float = 5.0,
) -> float | None:
    """Return the closest recorded value inside a small time window."""

    candidates = [
        (abs((point.ts - target).total_seconds()), point.value)
        for point in points
        if abs((point.ts - target).total_seconds()) <= window_minutes * 60
    ]
    return min(candidates, default=(0, None), key=lambda item: item[0])[1]


def median_near(
    points: Sequence[Point],
    target: datetime,
    *,
    window_minutes: float = 10.0,
) -> float | None:
    """Return the median temperature around an event."""

    values = [
        point.value
        for point in points
        if abs((point.ts - target).total_seconds()) <= window_minutes * 60
    ]
    return float(statistics.median(values)) if values else None


def classify_temperature_dominance(
    medians: dict[str, float | None],
    floors: dict[str, float | None],
    *,
    minimum_margin: float = 50.0,
) -> str:
    """Identify only a temperature-dominant tag; this is not a taphole label."""

    excess: list[tuple[float, str]] = []
    for variable in TAPHOLE_VARIABLES:
        value = medians.get(variable)
        floor = floors.get(variable)
        if value is not None and floor is not None:
            excess.append((value - floor, variable))
    if len(excess) != 2:
        return "unknown"
    excess.sort(reverse=True)
    if excess[0][0] - excess[1][0] < minimum_margin:
        return "ambiguous"
    return excess[0][1]


def pg_connection(args: argparse.Namespace) -> psycopg.Connection:
    """Open the approved 220.12 PostgreSQL reader connection."""

    user = os.getenv("GL02_PGUSER", "")
    password = os.getenv("GL02_PGPASSWORD", "")
    if not user or not password:
        raise RuntimeError("GL02_PGUSER/GL02_PGPASSWORD must be set")
    return psycopg.connect(
        host=args.pg_host,
        port=args.pg_port,
        dbname=args.pg_database,
        user=user,
        password=password,
        connect_timeout=args.connect_timeout,
        options=f"-c statement_timeout={args.statement_timeout_ms}",
    )


def read_pspace_mirror(
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
) -> tuple[dict[str, list[Point]], dict[str, dict[str, object]]]:
    """Read the two mapped pSpace tags from bf_sensor in a read-only transaction."""

    with pg_connection(args) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                """
                SELECT variable_name, chinese_name, short_name, tag_long_name,
                       status_usage, is_enabled
                  FROM bf_sensor.sensor_registry
                 WHERE variable_name = ANY(%s)
                 ORDER BY variable_name
                """,
                (list(TAPHOLE_VARIABLES),),
            )
            registry_rows = cursor.fetchall()
            registry = {
                str(row[0]): {
                    "chinese_name": row[1],
                    "short_name": row[2],
                    "tag_long_name": row[3],
                    "status_usage": row[4],
                    "is_enabled": row[5],
                }
                for row in registry_rows
            }
            if set(registry) != set(TAPHOLE_VARIABLES):
                raise RuntimeError(f"missing taphole registry rows: {set(TAPHOLE_VARIABLES) - set(registry)}")
            cursor.execute(
                """
                SELECT r.variable_name, v.ts, v.value
                  FROM bf_sensor.sensor_registry AS r
                  JOIN bf_sensor.one_minute_values AS v
                    ON v.tag_long_name = r.tag_long_name
                 WHERE r.variable_name = ANY(%s)
                   AND v.ts >= %s
                   AND v.ts < %s
                   AND v.value IS NOT NULL
                 ORDER BY r.variable_name, v.ts
                """,
                (list(TAPHOLE_VARIABLES), start, end),
            )
            points = {variable: [] for variable in TAPHOLE_VARIABLES}
            for variable, ts, value in cursor.fetchall():
                points[str(variable)].append(
                    Point(str(variable), parse_datetime(ts) or start, float(value))
                )
    return points, registry


def read_imes_heats(
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
) -> list[Heat]:
    """Read official 2# heat and tapping windows through the local IMES relay."""

    connection_args = SimpleNamespace(
        host=args.imes_host,
        port=args.imes_port,
        database=args.imes_database,
        connect_timeout=args.connect_timeout,
        statement_timeout_ms=args.statement_timeout_ms,
    )
    with psycopg.connect(**vastbase.connection_info(connection_args)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                """
                SELECT meltno, opentime, closetime, tappingtime
                  FROM public.t_ipes_cond
                 WHERE prodcentercode = %s
                   AND workdate >= %s
                   AND workdate < %s
                   AND opentime IS NOT NULL
                 ORDER BY opentime
                """,
                ("2D012", start.date().isoformat(), end.date().isoformat()),
            )
            heats: list[Heat] = []
            for meltno, open_time, close_time, tapping_time in cursor.fetchall():
                open_ts = parse_datetime(open_time)
                if open_ts is None or not (start <= open_ts < end):
                    continue
                heats.append(
                    Heat(
                        meltno=str(meltno or ""),
                        open_ts=open_ts,
                        close_ts=parse_datetime(close_time),
                        tapping_minutes=float(tapping_time) if tapping_time not in (None, "") else None,
                    )
                )
    return heats


def build_alignment(
    heats: Sequence[Heat],
    points: dict[str, list[Point]],
    transitions: Sequence[Transition],
    floors: dict[str, float | None],
) -> list[dict[str, object]]:
    """Join official heats to nearest temperature changes and opening values."""

    rows: list[dict[str, object]] = []
    for heat in heats:
        transition, error = nearest_transition(heat.open_ts, transitions)
        medians = {
            variable: median_near(points[variable], heat.open_ts)
            for variable in TAPHOLE_VARIABLES
        }
        row: dict[str, object] = {
            "meltno": heat.meltno,
            "open_ts": heat.open_ts.isoformat(sep=" "),
            "close_ts": heat.close_ts.isoformat(sep=" ") if heat.close_ts else "",
            "tapping_minutes": heat.tapping_minutes,
            "nearest_transition_ts": transition.ts.isoformat(sep=" ") if transition else "",
            "nearest_transition_variable": transition.variable if transition else "",
            "nearest_transition_direction": transition.direction if transition else "",
            "nearest_transition_delta_c": round(transition.delta, 3) if transition else "",
            "transition_error_minutes": round(error, 3) if error is not None else "",
        }
        for variable in TAPHOLE_VARIABLES:
            row[f"{variable}_at_open"] = nearest_value(points[variable], heat.open_ts)
            row[f"{variable}_median_10m"] = medians[variable]
        row["temperature_dominant_tag"] = classify_temperature_dominance(medians, floors)
        rows.append(row)
    return rows


def coverage(rows: Sequence[dict[str, object]], minutes: float) -> int:
    """Count official openings with a large transition inside the tolerance."""

    return sum(
        1
        for row in rows
        if row["transition_error_minutes"] != ""
        and float(row["transition_error_minutes"]) <= minutes
    )


def write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    """Write a UTF-8 CSV with a stable header."""

    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render_report(summary: dict[str, object], rows: Sequence[dict[str, object]]) -> str:
    """Render the concise audit report."""

    heat_count = int(summary["official_heat_count"])
    return "\n".join(
        [
            "# 1/2 号出铁口温度与炉次/出铁时间对齐核查",
            "",
            f"窗口：`{summary['start']}` 至 `{summary['end']}`。",
            "",
            "## 结论",
            "",
            "- pSpace 两点是 `1#出铁口温度`、`2#出铁口温度`，不是开铁口/堵口数字事件。",
            "- 温度曲线可产生候选热态区间和大幅跳变，但仅凭这两点不能可靠恢复正式炉次号。",
            "- 正式炉次号、开口时间、堵口时间应以 IMES `t_ipes_cond` 为锚点；温度曲线用于交叉验证和缺失补推。",
            f"- 本窗口官方 2# 炉次 `{heat_count}` 个；大幅温度跳变在 ±15/±30/±60 分钟内覆盖 "
            f"`{summary['coverage_15m']}/{summary['coverage_30m']}/{summary['coverage_60m']}` 个。",
            f"- 两点估计底值分别为 `{summary['sensor_floors_c']}` ℃。长时间底值、热惯性和两点同时高温会造成边界歧义。",
            "",
            "## 数据边界",
            "",
            f"- pSpace 镜像行数：`{summary['sensor_rows']}`。",
            f"- 检出的 ≥100℃ 分钟跳变：`{summary['transition_count']}`。",
            "- `temperature_dominant_tag` 只表示开口附近哪条温度信号更高，不等于现场确认的实际使用铁口。",
            "- 若需形成生产标签，必须增加开口机/泥炮动作、铁口选择状态或现场日志之一，并用 IMES 炉次校准。",
            "",
            "## 最近对齐样例",
            "",
            "| 炉次 | IMES 开口 | IMES 堵口 | 最近温度跳变 | 误差/min | 信号 |",
            "|---|---|---|---|---:|---|",
            *[
                "| {meltno} | {open_ts} | {close_ts} | {nearest_transition_ts} | "
                "{transition_error_minutes} | {nearest_transition_variable} {nearest_transition_direction} |".format(
                    **row
                )
                for row in rows[-12:]
            ],
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="只读对齐 pSpace 1/2 号铁口温度与 IMES 正式炉次/开堵口时间。"
    )
    parser.add_argument("--start", required=True, help="开始时间，ISO 格式。")
    parser.add_argument("--end", required=True, help="结束时间，ISO 格式，不包含。")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--pg-host", default="10.30.220.12")
    parser.add_argument("--pg-port", type=int, default=5432)
    parser.add_argument("--pg-database", default="bf_trend")
    parser.add_argument("--imes-host", default="127.0.0.1")
    parser.add_argument("--imes-port", type=int, default=15433)
    parser.add_argument("--imes-database", default="vastbase")
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--statement-timeout-ms", type=int, default=60000)
    parser.add_argument("--minimum-jump", type=float, default=100.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    start = parse_datetime(args.start)
    end = parse_datetime(args.end)
    if start is None or end is None or end <= start:
        raise SystemExit("--end must be later than --start")

    points, registry = read_pspace_mirror(args, start, end)
    heats = read_imes_heats(args, start, end)
    floors = {variable: estimate_floor(points[variable]) for variable in TAPHOLE_VARIABLES}
    transitions = sorted(
        [
            transition
            for variable in TAPHOLE_VARIABLES
            for transition in detect_transitions(
                points[variable],
                minimum_jump=args.minimum_jump,
            )
        ],
        key=lambda item: (item.ts, item.variable),
    )
    rows = build_alignment(heats, points, transitions, floors)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    transition_rows = [
        {
            **asdict(transition),
            "ts": transition.ts.isoformat(sep=" "),
        }
        for transition in transitions
    ]
    summary: dict[str, object] = {
        "generated_at": datetime.now().isoformat(),
        "start": start.isoformat(sep=" "),
        "end": end.isoformat(sep=" "),
        "read_policy": "readonly",
        "pspace_source": f"{args.pg_host}:{args.pg_port}/{args.pg_database}/bf_sensor.one_minute_values",
        "imes_source": f"{args.imes_host}:{args.imes_port}/{args.imes_database}/public.t_ipes_cond",
        "registry": registry,
        "sensor_rows": {variable: len(points[variable]) for variable in TAPHOLE_VARIABLES},
        "sensor_floors_c": floors,
        "official_heat_count": len(heats),
        "transition_count": len(transitions),
        "coverage_15m": coverage(rows, 15),
        "coverage_30m": coverage(rows, 30),
        "coverage_60m": coverage(rows, 60),
        "can_infer_official_heat_number_from_temperatures_alone": False,
        "recommended_role": "candidate_window_detection_and_imes_cross_validation",
    }
    write_csv(args.out_dir / "heat_alignment.csv", rows)
    write_csv(args.out_dir / "sensor_transitions.csv", transition_rows)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (args.out_dir / "report.md").write_text(
        render_report(summary, rows),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
