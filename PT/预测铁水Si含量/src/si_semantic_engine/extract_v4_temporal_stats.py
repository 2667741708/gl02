"""Read-only extraction of multi-window sensor statistics for Si V4.

The extractor writes partitioned local Parquet files so a long production
read can resume safely.  PostgreSQL is explicitly placed in read-only mode.
No source table, schema, service or MCP process is modified.

Requirement:
    REQ-SI-TEMPORAL-STATS-V4-20260726
"""

from __future__ import annotations

import argparse
import json
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from .formal_dataset import sha256_file


REQUIREMENT_ID = "REQ-SI-TEMPORAL-STATS-V4-20260726"
WINDOWS_MINUTES = (30, 60, 120, 240)
STATISTICS = ("count", "mean", "std", "min", "max", "slope_per_min")


def _chunks(
    records: Sequence[dict[str, Any]],
    size: int,
) -> list[list[dict[str, Any]]]:
    return [
        list(records[start : start + size])
        for start in range(0, len(records), size)
    ]


def _validate_windows(
    windows_minutes: Sequence[int],
) -> tuple[int, ...]:
    windows = tuple(sorted({int(value) for value in windows_minutes}))
    if not windows or any(value <= 0 for value in windows):
        raise ValueError("时间窗口必须是正整数分钟")
    return windows


def build_statistics_query(
    target_count: int,
    windows_minutes: Sequence[int] = WINDOWS_MINUTES,
) -> str:
    """Build a fixed-window query; only the target VALUES are parameters."""

    if target_count <= 0:
        raise ValueError("target_count必须大于0")
    target_values = ",".join(
        ["(%s::text,%s::timestamp)"] * target_count
    )
    windows = _validate_windows(windows_minutes)
    aggregate_columns: list[str] = []
    for window in windows:
        predicate = (
            f"v.ts >= targets.target_ts - interval '{window} minutes'"
        )
        prefix = f"w{window}"
        aggregate_columns.extend(
            [
                (
                    f"COUNT(v.value) FILTER (WHERE {predicate}) "
                    f"AS {prefix}_count"
                ),
                (
                    f"AVG(v.value::double precision) "
                    f"FILTER (WHERE {predicate}) AS {prefix}_mean"
                ),
                (
                    f"STDDEV_SAMP(v.value::double precision) "
                    f"FILTER (WHERE {predicate}) AS {prefix}_std"
                ),
                (
                    f"MIN(v.value::double precision) "
                    f"FILTER (WHERE {predicate}) AS {prefix}_min"
                ),
                (
                    f"MAX(v.value::double precision) "
                    f"FILTER (WHERE {predicate}) AS {prefix}_max"
                ),
                (
                    "REGR_SLOPE("
                    "v.value::double precision, "
                    "EXTRACT(EPOCH FROM v.ts)::double precision / 60.0"
                    f") FILTER (WHERE {predicate}) "
                    f"AS {prefix}_slope_per_min"
                ),
            ]
        )
    aggregates = ",\n                    ".join(aggregate_columns)
    return f"""
        WITH targets(official_meltno, target_ts) AS (
            VALUES {target_values}
        )
        SELECT
            targets.official_meltno,
            targets.target_ts AS feature_cutoff_ts,
            registry.short_name AS sensor_id,
            registry.variable_name,
            stats.*
        FROM targets
        CROSS JOIN bf_sensor.sensor_registry AS registry
        LEFT JOIN LATERAL (
            SELECT
                    {aggregates}
            FROM bf_sensor.one_minute_values AS v
            WHERE v.tag_long_name = registry.tag_long_name
              AND v.ts < targets.target_ts
              AND v.ts >= targets.target_ts - interval '{max(windows)} minutes'
              AND v.value IS NOT NULL
        ) AS stats ON TRUE
        WHERE registry.is_enabled
          AND NOT registry.is_derived
        ORDER BY targets.target_ts, registry.short_name
    """


def _derive_statistics(
    frame: pd.DataFrame,
    windows_minutes: Sequence[int] = WINDOWS_MINUTES,
) -> pd.DataFrame:
    output = frame.copy()
    for window in _validate_windows(windows_minutes):
        prefix = f"w{window}"
        count = pd.to_numeric(
            output[f"{prefix}_count"], errors="coerce"
        ).fillna(0.0)
        output[f"{prefix}_coverage_ratio"] = (count / float(window)).clip(
            lower=0.0, upper=1.0
        )
        minimum = pd.to_numeric(
            output[f"{prefix}_min"], errors="coerce"
        )
        maximum = pd.to_numeric(
            output[f"{prefix}_max"], errors="coerce"
        )
        output[f"{prefix}_range"] = maximum - minimum
        output[f"{prefix}_cv"] = (
            pd.to_numeric(output[f"{prefix}_std"], errors="coerce")
            / pd.to_numeric(output[f"{prefix}_mean"], errors="coerce").abs()
        ).where(
            pd.to_numeric(
                output[f"{prefix}_mean"], errors="coerce"
            ).abs()
            > 1e-12
        )
    return output


def _connect() -> psycopg.Connection[Any]:
    required = (
        "GL02_PGHOST",
        "GL02_PGPORT",
        "GL02_PGDATABASE",
        "GL02_PGUSER",
        "GL02_PGPASSWORD",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "缺少PostgreSQL环境变量：" + ", ".join(missing)
        )
    return psycopg.connect(
        host=os.environ["GL02_PGHOST"],
        port=int(os.environ["GL02_PGPORT"]),
        dbname=os.environ["GL02_PGDATABASE"],
        user=os.environ["GL02_PGUSER"],
        password=os.environ["GL02_PGPASSWORD"],
        connect_timeout=15,
        options=(
            "-c default_transaction_read_only=on "
            "-c statement_timeout=900000"
        ),
        row_factory=dict_row,
    )


def run_extraction(
    *,
    dataset_path: Path,
    output_dir: Path,
    chunk_size: int = 20,
    windows_minutes: Sequence[int] = WINDOWS_MINUTES,
) -> dict[str, Any]:
    if chunk_size <= 0:
        raise ValueError("chunk_size必须大于0")
    windows = _validate_windows(windows_minutes)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = pd.read_csv(
        dataset_path,
        usecols=["official_meltno", "prediction_cutoff_ts"],
        encoding="utf-8-sig",
    )
    dataset["prediction_cutoff_ts"] = pd.to_datetime(
        dataset["prediction_cutoff_ts"], errors="raise"
    )
    dataset = dataset.sort_values(
        ["prediction_cutoff_ts", "official_meltno"], kind="stable"
    )
    if dataset["official_meltno"].duplicated().any():
        raise ValueError("输入数据official_meltno不唯一")
    targets = dataset.rename(
        columns={"prediction_cutoff_ts": "target_ts"}
    ).to_dict("records")
    chunks = _chunks(targets, chunk_size)

    with _connect() as connection:
        identity = connection.execute(
            """
            SELECT
                current_user AS current_user,
                current_setting('transaction_read_only') AS read_only,
                COUNT(*) FILTER (
                    WHERE is_enabled AND NOT is_derived
                ) AS enabled_physical_points
            FROM bf_sensor.sensor_registry
            """
        ).fetchone()
        if str(identity["read_only"]).lower() != "on":
            raise RuntimeError("PostgreSQL连接未进入只读模式")
        for index, chunk in enumerate(chunks, 1):
            part_path = output_dir / f"part-{index:05d}.parquet"
            if part_path.exists():
                existing = pd.read_parquet(
                    part_path,
                    columns=[
                        "official_meltno",
                        "sensor_id",
                    ],
                )
                expected_rows = (
                    len(chunk) * int(identity["enabled_physical_points"])
                )
                if (
                    len(existing) == expected_rows
                    and existing[
                        ["official_meltno", "sensor_id"]
                    ].drop_duplicates().shape[0]
                    == expected_rows
                ):
                    print(
                        json.dumps(
                            {
                                "event": "chunk_skipped",
                                "chunk": index,
                                "chunks": len(chunks),
                                "rows": len(existing),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    continue
                raise RuntimeError(
                    f"已有分片不完整，拒绝覆盖：{part_path}"
                )
            parameters: list[Any] = []
            for target in chunk:
                parameters.extend(
                    [target["official_meltno"], target["target_ts"]]
                )
            rows = connection.execute(
                build_statistics_query(len(chunk), windows),
                parameters,
            ).fetchall()
            part = _derive_statistics(pd.DataFrame(rows), windows)
            expected_rows = (
                len(chunk) * int(identity["enabled_physical_points"])
            )
            if len(part) != expected_rows:
                raise RuntimeError(
                    f"分片{index}行数{len(part)} != 预期{expected_rows}"
                )
            part.to_parquet(part_path, index=False, compression="zstd")
            print(
                json.dumps(
                    {
                        "event": "chunk_written",
                        "chunk": index,
                        "chunks": len(chunks),
                        "heats": len(chunk),
                        "rows": len(part),
                        "path": str(part_path),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    parts = sorted(output_dir.glob("part-*.parquet"))
    if len(parts) != len(chunks):
        raise RuntimeError(
            f"完成分片数{len(parts)} != 预期{len(chunks)}"
        )
    part_records = []
    total_rows = 0
    for path in parts:
        metadata = pd.read_parquet(
            path, columns=["official_meltno", "sensor_id"]
        )
        total_rows += len(metadata)
        part_records.append(
            {
                "name": path.name,
                "rows": int(len(metadata)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "requirement_id": REQUIREMENT_ID,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "immutable_local_readonly_extraction",
        "source": {
            "host": os.environ["GL02_PGHOST"],
            "port": int(os.environ["GL02_PGPORT"]),
            "database": os.environ["GL02_PGDATABASE"],
            "user": os.environ["GL02_PGUSER"],
            "transaction_read_only": True,
            "enabled_physical_points": int(
                identity["enabled_physical_points"]
            ),
        },
        "input": {
            "dataset_path": str(dataset_path.resolve()),
            "dataset_sha256": sha256_file(dataset_path),
            "heat_rows": len(dataset),
        },
        "feature_contract": {
            "cutoff": "strictly before MES opentime",
            "windows_minutes": list(windows),
            "database_statistics": list(STATISTICS),
            "derived_statistics": ["coverage_ratio", "range", "cv"],
            "expected_frequency_minutes": 1,
        },
        "runtime": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "psycopg": psycopg.__version__,
        },
        "parts": part_records,
        "total_rows": total_rows,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="只读提取正式炉次开铁前133点多窗口统计。"
    )
    cli.add_argument("--dataset", type=Path, required=True)
    cli.add_argument("--output-dir", type=Path, required=True)
    cli.add_argument("--chunk-size", type=int, default=20)
    cli.add_argument(
        "--windows-minutes",
        type=int,
        nargs="+",
        default=list(WINDOWS_MINUTES),
        help="统计窗口（分钟），例如 30 60 120 240 480。",
    )
    return cli


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = run_extraction(
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        chunk_size=args.chunk_size,
        windows_minutes=args.windows_minutes,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
