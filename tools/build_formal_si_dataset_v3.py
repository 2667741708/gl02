"""Build the formal-meltno Si V3 dataset from read-only production sources.

The program joins:

* MES official heat/sample relations;
* MES heat opening/closing times;
* the lab view's tank number by exact ``batchno``;
* PostgreSQL sensor observations strictly before each official heat open time.

It writes local artifacts only.  It never derives a heat number from a sample
number and never replaces ``takesampletime`` with judgement/result time.

Requirements:
    REQ-SI-FORMAL-LABEL-CONTRACT-V3-20260726
    REQ-SI-FORMAL-DATASET-V3-20260726
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT / "PT" / "预测铁水Si含量"
MODULE_SRC = MODULE_ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(MODULE_SRC) not in sys.path:
    sys.path.insert(0, str(MODULE_SRC))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import build_hot_metal_si_dataset as legacy_reader
from db_dashboard.heat_service import (
    _vastbase_connect,
    imes_lab_params,
    imes_ops_params,
)
from si_semantic_engine.formal_dataset import (
    assemble_formal_dataset,
    write_dataset_artifacts,
)
from si_semantic_engine.formal_labels import build_label_contract


REQUIREMENT_ID = "REQ-SI-FORMAL-DATASET-V3-20260726"
DEFAULT_OUTPUT = MODULE_ROOT / "data" / "processed" / "formal_v3_20260726"


def emit(event: str, **payload: Any) -> None:
    print(
        json.dumps(
            {"event": event, **payload},
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def fetch_formal_samples(
    min_cutoff: datetime,
    max_cutoff: datetime,
) -> pd.DataFrame:
    """Read official heat/sample chemistry through the operations account."""

    with _vastbase_connect(imes_ops_params()) as connection:
        rows = connection.execute(
            """
            SELECT
                CAST(s.id AS text) AS sample_record_id,
                CAST(s.batchno AS text) AS batchno,
                CAST(s.heatno AS text) AS official_meltno,
                COALESCE(b.judgetime, s.judgetime) AS result_ts,
                COALESCE(s.takesampletime, b.takesampletime) AS sample_ts,
                h.opentime AS open_ts,
                h.closetime AS close_ts,
                b.value_01 AS c_pct,
                b.value_02 AS si_pct,
                b.value_03 AS mn_pct,
                b.value_04 AS p_pct,
                b.value_05 AS s_pct,
                s.takesampleclass AS sample_class,
                s.inspphyclass AS physical_class
            FROM public.t_qpes_inner_batch AS s
            JOIN public.inner_batch_insp_bb AS b
              ON b.batchno = s.batchno
            JOIN public.t_ipes_cond AS h
              ON h.meltno = s.heatno
            WHERE s.heatno LIKE '2#%%'
              AND s.batchno IS NOT NULL
              AND h.opentime >= %s
              AND h.opentime <= %s
            ORDER BY h.opentime, s.heatno, result_ts, s.batchno
            """,
            (
                min_cutoff.strftime("%Y-%m-%d %H:%M:%S"),
                max_cutoff.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        ).fetchall()
    frame = pd.DataFrame([dict(row) for row in rows])
    if frame.empty:
        raise RuntimeError("MES正式炉次与传感器时间范围没有交集")
    return frame


def fetch_tank_map() -> dict[str, str]:
    """Read tank numbers and index them by exact laboratory batch number."""

    with _vastbase_connect(imes_lab_params()) as connection:
        rows = connection.execute(
            """
            SELECT CAST(batchno AS text) AS batchno,
                   CAST(thankno AS text) AS tank_no
            FROM public.v_qpes_mat_final
            WHERE batchno IS NOT NULL
              AND thankno IS NOT NULL
            """
        ).fetchall()
    result: dict[str, str] = {}
    conflicts: set[str] = set()
    for row in rows:
        batchno = str(row["batchno"] or "").strip()
        tank_no = str(row["tank_no"] or "").strip()
        if not batchno or not tank_no:
            continue
        previous = result.get(batchno)
        if previous is not None and previous != tank_no:
            conflicts.add(batchno)
            continue
        result[batchno] = tank_no
    for batchno in conflicts:
        result.pop(batchno, None)
    emit(
        "tank_map_ready",
        exact_batch_rows=len(result),
        conflicting_batch_rows=len(conflicts),
    )
    return result


def attach_source_fields(
    formal_samples: pd.DataFrame,
    tank_map: dict[str, str],
) -> pd.DataFrame:
    frame = formal_samples.copy()
    frame["tank_no"] = frame["batchno"].astype(str).str.strip().map(tank_map)
    # The audited MES permission surface exposes no reliable taphole identifier.
    frame["taphole_id"] = None
    return frame


def fetch_registry(
    connection: psycopg.Connection[Any],
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT short_name, tag_long_name, variable_name, chinese_name
        FROM bf_sensor.sensor_registry
        WHERE is_enabled
          AND NOT is_derived
        ORDER BY short_name, tag_long_name
        """
    ).fetchall()
    result = [dict(row) for row in rows]
    names = [str(row["short_name"]) for row in result]
    if len(names) != len(set(names)):
        raise RuntimeError("sensor_registry中启用物理点short_name不唯一")
    return result


def _chunks(values: Sequence[dict[str, Any]], size: int):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_temporal_sensor_features(
    connection: psycopg.Connection[Any],
    heat_targets: pd.DataFrame,
    registry: Sequence[dict[str, Any]],
    *,
    max_lag_minutes: int,
    chunk_size: int,
) -> pd.DataFrame:
    """Read last/60-minute/120-minute observations before each cutoff."""

    targets = (
        heat_targets[
            ["official_meltno", "prediction_cutoff_ts"]
        ]
        .dropna()
        .sort_values(["prediction_cutoff_ts", "official_meltno"])
        .to_dict("records")
    )
    wide_rows: dict[str, dict[str, Any]] = {
        str(item["official_meltno"]): {
            "official_meltno": str(item["official_meltno"]),
            "feature_cutoff_ts": item["prediction_cutoff_ts"],
            "sensor__available_last_count": 0,
            "sensor__available_60m_count": 0,
            "sensor__available_120m_count": 0,
        }
        for item in targets
    }
    target_chunks = list(_chunks(targets, chunk_size))
    for chunk_no, chunk in enumerate(target_chunks, 1):
        values_sql = ",".join(
            ["(%s::text,%s::timestamp)"] * len(chunk)
        )
        parameters: list[Any] = []
        for item in chunk:
            parameters.extend(
                [item["official_meltno"], item["prediction_cutoff_ts"]]
            )
        parameters.extend(
            [max_lag_minutes, max_lag_minutes, max_lag_minutes]
        )
        rows = connection.execute(
            f"""
            WITH targets(official_meltno, target_ts) AS (
                VALUES {values_sql}
            )
            SELECT
                targets.official_meltno,
                targets.target_ts,
                r.short_name,
                latest.ts AS latest_ts,
                latest.value AS latest_value,
                prior60.ts AS prior60_ts,
                prior60.value AS prior60_value,
                prior120.ts AS prior120_ts,
                prior120.value AS prior120_value
            FROM targets
            CROSS JOIN bf_sensor.sensor_registry AS r
            LEFT JOIN LATERAL (
                SELECT v.ts, v.value
                FROM bf_sensor.one_minute_values AS v
                WHERE v.tag_long_name = r.tag_long_name
                  AND v.ts < targets.target_ts
                  AND v.ts >= targets.target_ts
                      - (%s * interval '1 minute')
                ORDER BY v.ts DESC
                LIMIT 1
            ) AS latest ON TRUE
            LEFT JOIN LATERAL (
                SELECT v.ts, v.value
                FROM bf_sensor.one_minute_values AS v
                WHERE v.tag_long_name = r.tag_long_name
                  AND v.ts < targets.target_ts - interval '60 minutes'
                  AND v.ts >= targets.target_ts
                      - ((60 + %s) * interval '1 minute')
                ORDER BY v.ts DESC
                LIMIT 1
            ) AS prior60 ON TRUE
            LEFT JOIN LATERAL (
                SELECT v.ts, v.value
                FROM bf_sensor.one_minute_values AS v
                WHERE v.tag_long_name = r.tag_long_name
                  AND v.ts < targets.target_ts - interval '120 minutes'
                  AND v.ts >= targets.target_ts
                      - ((120 + %s) * interval '1 minute')
                ORDER BY v.ts DESC
                LIMIT 1
            ) AS prior120 ON TRUE
            WHERE r.is_enabled
              AND NOT r.is_derived
            ORDER BY targets.target_ts, r.short_name
            """,
            parameters,
        ).fetchall()
        for raw in rows:
            row = dict(raw)
            meltno = str(row["official_meltno"])
            name = str(row["short_name"])
            output = wide_rows[meltno]
            current = row.get("latest_value")
            value60 = row.get("prior60_value")
            value120 = row.get("prior120_value")
            current_number = (
                float(current)
                if current is not None and math.isfinite(float(current))
                else None
            )
            number60 = (
                float(value60)
                if value60 is not None and math.isfinite(float(value60))
                else None
            )
            number120 = (
                float(value120)
                if value120 is not None and math.isfinite(float(value120))
                else None
            )
            output[f"sensor__{name}__last"] = current_number
            output[f"sensor__{name}__delta_60m"] = (
                current_number - number60
                if current_number is not None and number60 is not None
                else None
            )
            output[f"sensor__{name}__slope_60m_per_min"] = (
                (current_number - number60) / 60.0
                if current_number is not None and number60 is not None
                else None
            )
            output[f"sensor__{name}__delta_120m"] = (
                current_number - number120
                if current_number is not None and number120 is not None
                else None
            )
            output[f"sensor__{name}__slope_120m_per_min"] = (
                (current_number - number120) / 120.0
                if current_number is not None and number120 is not None
                else None
            )
            if current_number is not None:
                output["sensor__available_last_count"] += 1
            if number60 is not None:
                output["sensor__available_60m_count"] += 1
            if number120 is not None:
                output["sensor__available_120m_count"] += 1
        emit(
            "sensor_feature_progress",
            chunk=chunk_no,
            chunks=len(target_chunks),
            heats_processed=min(chunk_no * chunk_size, len(targets)),
        )
    frame = pd.DataFrame(wide_rows.values())
    expected_feature_columns = len(registry) * 5
    emit(
        "sensor_features_ready",
        heat_rows=len(frame),
        physical_points=len(registry),
        temporal_feature_columns=expected_feature_columns,
    )
    return frame


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="构建MES正式meltno和开铁前传感器特征的Si V3数据集。"
    )
    cli.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    cli.add_argument("--min-sensor-last-values", type=int, default=100)
    cli.add_argument("--max-sensor-lag-minutes", type=int, default=10)
    cli.add_argument("--sensor-chunk-size", type=int, default=60)
    cli.add_argument("--train-ratio", type=float, default=0.70)
    cli.add_argument("--validation-ratio", type=float, default=0.15)
    cli.add_argument("--statement-timeout-ms", type=int, default=300000)
    cli.add_argument("--ssh-host", default="10.30.220.12")
    cli.add_argument("--ssh-user", default="administrator")
    cli.add_argument("--remote-pg-host", default="127.0.0.1")
    cli.add_argument("--remote-pg-port", type=int, default=5432)
    cli.add_argument("--local-tunnel-port", type=int, default=15435)
    cli.add_argument("--remote-pg-user", default="gl02_sync")
    cli.add_argument("--remote-pg-db", default="bf_trend")
    cli.add_argument("--connect-timeout", type=int, default=20)
    return cli


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir = args.output_dir.resolve()
    legacy_args = argparse.Namespace(
        ssh_host=args.ssh_host,
        ssh_user=args.ssh_user,
        remote_pg_host=args.remote_pg_host,
        remote_pg_port=args.remote_pg_port,
        local_tunnel_port=args.local_tunnel_port,
        remote_pg_user=args.remote_pg_user,
        remote_pg_db=args.remote_pg_db,
        connect_timeout=args.connect_timeout,
    )
    emit("start", requirement_id=REQUIREMENT_ID, output_dir=args.output_dir)
    with legacy_reader.sensor_ssh_tunnel(legacy_args) as (
        sensor_port,
        ssh_client,
    ):
        sensor_info = legacy_reader.remote_sensor_params(
            legacy_args,
            sensor_port,
            ssh_client,
        )
        sensor_info["options"] = (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={args.statement_timeout_ms}"
        )
        with psycopg.connect(
            **sensor_info,
            row_factory=dict_row,
        ) as sensor_connection:
            sensor_connection.execute("SET default_transaction_read_only = on")
            sensor_bounds = legacy_reader.sensor_bounds(sensor_connection)
            min_ts = sensor_bounds.get("min_ts")
            max_ts = sensor_bounds.get("max_ts")
            if not isinstance(min_ts, datetime) or not isinstance(
                max_ts, datetime
            ):
                raise RuntimeError("PostgreSQL传感器历史为空")
            registry = fetch_registry(sensor_connection)
            emit(
                "sources_ready",
                sensor_min_ts=min_ts,
                sensor_max_ts=max_ts,
                physical_points=len(registry),
            )
            raw_samples = fetch_formal_samples(min_ts, max_ts)
            tank_map = fetch_tank_map()
            raw_samples = attach_source_fields(raw_samples, tank_map)
            labels = build_label_contract(raw_samples)
            emit("label_contract_ready", **labels.audit)
            sensor_features = fetch_temporal_sensor_features(
                sensor_connection,
                labels.heat_targets,
                registry,
                max_lag_minutes=args.max_sensor_lag_minutes,
                chunk_size=args.sensor_chunk_size,
            )
    dataset = assemble_formal_dataset(
        labels.heat_targets,
        sensor_features,
        min_sensor_last_values=args.min_sensor_last_values,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
    )
    manifest = write_dataset_artifacts(
        samples=labels.samples,
        heat_targets=labels.heat_targets,
        next_sample_targets=labels.next_sample_targets,
        sensor_features=sensor_features,
        dataset=dataset,
        audit=labels.audit,
        output_dir=args.output_dir,
        source_metadata={
            "mes_heat_identity": (
                "public.t_qpes_inner_batch.heatno exact join "
                "public.t_ipes_cond.meltno"
            ),
            "mes_chemistry": (
                "public.inner_batch_insp_bb exact join on batchno"
            ),
            "mes_tank": (
                "public.v_qpes_mat_final.thankno exact join on batchno"
            ),
            "sensor_history": {
                "min_ts": min_ts,
                "max_ts": max_ts,
                "enabled_physical_points": len(registry),
            },
        },
    )
    emit(
        "complete",
        training_heats=manifest["shape"]["training_heat_rows"],
        output_dir=args.output_dir,
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
