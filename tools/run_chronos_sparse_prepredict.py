from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = ROOT / "自动诊断服务"
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

from local_pg_ws_bridge import (  # noqa: E402
    DISPLAY_NAMES,
    build_chronos_job,
    clean_feature_series,
    fetch_chronos_feature_frame,
)
from backtest_chronos2_from_pg import post_json  # noqa: E402


SPARSE_COVARIATES: dict[str, list[str]] = {
    "P_top": [
        "P_top_gas_A",
        "P_top_gas_B",
        "P_top_gas_C",
        "P_top_gas_D",
        "P_blast",
        "DP_total",
        "Q_blast",
    ],
    "P_top_gas_A": ["P_top", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D", "DP_total", "T_top_A"],
    "P_top_gas_B": ["P_top", "P_top_gas_A", "P_top_gas_C", "P_top_gas_D", "DP_total", "T_top_B"],
    "P_top_gas_C": ["P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_D", "DP_total", "T_top_C"],
    "P_top_gas_D": ["P_top", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "DP_total", "T_top_D"],
    "Q_blast": ["P_blast_cold", "P_blast", "DP_total", "PI"],
    "P_blast_cold": ["Q_blast", "P_blast", "DP_total", "P_top"],
    "P_blast": ["P_blast_cold", "Q_blast", "P_top", "DP_total"],
    "T_blast": ["P_blast", "Q_blast", "PCI_rate", "O2_rate"],
    "T_top": ["T_top_A", "T_top_B", "T_top_C", "T_top_D", "P_top", "GasUtil"],
    "T_top_A": ["T_top", "T_top_B", "T_top_C", "T_top_D", "P_top", "GasUtil"],
    "T_top_B": ["T_top", "T_top_A", "T_top_C", "T_top_D", "P_top", "GasUtil"],
    "T_top_C": ["T_top", "T_top_A", "T_top_B", "T_top_D", "P_top", "GasUtil"],
    "T_top_D": ["T_top", "T_top_A", "T_top_B", "T_top_C", "P_top", "GasUtil"],
    "PI": ["DP_total", "Q_blast", "P_top", "P_blast", "DP_upper", "DP_lower"],
    "DP_total": ["DP_upper", "DP_lower", "P_blast", "P_top", "Q_blast", "PI"],
    "DP_upper": ["DP_total", "DP_lower", "P_top", "P_blast", "PI"],
    "DP_lower": ["DP_total", "DP_upper", "P_blast", "Q_blast", "PI"],
    "GasUtil": ["T_top", "T_top_A", "T_top_B", "T_top_C", "T_top_D", "P_top", "Q_blast"],
}


def finite_stats(values: list[Any]) -> dict[str, Any]:
    finite = []
    for value in values:
        if value is None:
            continue
        number = float(value)
        if math.isfinite(number):
            finite.append(number)
    return {
        "points": len(values),
        "finite_count": len(finite),
        "nonzero_count": sum(abs(value) > 1e-9 for value in finite),
        "min": min(finite) if finite else None,
        "max": max(finite) if finite else None,
        "last": finite[-1] if finite else None,
    }


def build_variant_payload(
    frame: pd.DataFrame,
    targets: list[str],
    variant: str,
    context_minutes: int,
    prediction_minutes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    jobs = []
    manifest: dict[str, Any] = {}
    context = frame.tail(context_minutes)
    cutoff = context.index[-1]

    for target_id in targets:
        job = build_chronos_job(frame, target_id, prediction_minutes, context_minutes)
        selected = [] if variant == "target_only" else SPARSE_COVARIATES[target_id]
        selected = [item for item in selected if item in context.columns and item != target_id]
        covariates = []
        input_summary = {target_id: finite_stats(job["target"]["values"])}
        for covariate_id in selected:
            values = clean_feature_series(context[covariate_id], context_minutes)
            covariates.append(
                {
                    "id": covariate_id,
                    "name": DISPLAY_NAMES.get(covariate_id, covariate_id),
                    "values": values,
                    "nonnull_count": sum(value is not None for value in values),
                }
            )
            input_summary[covariate_id] = finite_stats(values)

        job["covariates"] = covariates
        job["covariate_ids"] = selected
        job["feature_type"] = f"prepredict_{variant}"
        job["feature_engine"] = "BUG-TREND-19-SPARSE-PREPREDICT-20260808"
        jobs.append(job)
        manifest[target_id] = {
            "target_id": target_id,
            "context_minutes": len(job["target"]["values"]),
            "covariate_ids": selected,
            "inputs": input_summary,
        }

    payload = {
        "jobs": jobs,
        "feature_source": {
            "type": "postgresql_sparse_prepredict",
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "time_start": frame.index.min().isoformat(sep=" "),
            "time_end": frame.index.max().isoformat(sep=" "),
        },
        "request": {
            "variant": variant,
            "target_ids": targets,
            "context_minutes": context_minutes,
            "prediction_minutes": prediction_minutes,
            "cutoff_time": cutoff.isoformat(sep=" "),
            "data_source": "22012_postgresql_read_only",
        },
    }
    return payload, manifest


def prediction_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = {}
    for item in result.get("predictions") or []:
        values = item.get("p50") or []
        stats = finite_stats(values)
        stats["covariate_count"] = item.get("covariate_count")
        stats["status"] = item.get("status", "success")
        summary[str(item.get("target_id"))] = stats
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare target-only and sparse-covariate Chronos pre-predictions.")
    parser.add_argument("--db-host", default="10.30.220.12")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="bf_trend")
    parser.add_argument("--db-user", default="gl02_reader")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--chronos-url", default="http://10.30.220.12:8777")
    parser.add_argument("--context-minutes", type=int, default=480)
    parser.add_argument("--prediction-minutes", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=float, default=1200)
    parser.add_argument("--variants", default="target_only,sparse")
    parser.add_argument("--output-dir", default=str(ROOT / "logs" / "chronos_sparse_prepredict" / "comparison"))
    args = parser.parse_args()

    password = os.environ.get(args.db_password_env, "")
    if not password:
        raise SystemExit(f"missing database password environment variable: {args.db_password_env}")

    with psycopg.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=password,
        connect_timeout=12,
        row_factory=dict_row,
    ) as conn:
        frame = fetch_chronos_feature_frame(conn, datetime.now() - timedelta(days=2))
    if frame.empty:
        raise SystemExit("no PostgreSQL feature data was loaded")

    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    targets = list(SPARSE_COVARIATES)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined: dict[str, Any] = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "chronos_url": args.chronos_url,
        "targets": targets,
        "variants": {},
    }

    variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    invalid_variants = [item for item in variants if item not in {"target_only", "sparse"}]
    if invalid_variants:
        raise SystemExit(f"unsupported variants: {invalid_variants}")
    for variant in variants:
        payload, manifest = build_variant_payload(
            frame,
            targets,
            variant,
            args.context_minutes,
            args.prediction_minutes,
        )
        print(f"REQUEST variant={variant} jobs={len(payload['jobs'])}", flush=True)
        result = post_json(args.chronos_url, payload, args.timeout_seconds)
        summary = prediction_summary(result)
        combined["variants"][variant] = {
            "request": payload["request"],
            "input_manifest": manifest,
            "response_status": result.get("status"),
            "response_error": result.get("error") or result.get("message"),
            "prediction_summary": summary,
            "raw_response": result,
        }
        for target_id in targets:
            item = summary.get(target_id, {})
            print(
                "PRED",
                variant,
                target_id,
                "cov",
                item.get("covariate_count"),
                "points",
                item.get("points"),
                "nonzero",
                item.get("nonzero_count"),
                "first_last",
                [item.get("min"), item.get("max"), item.get("last")],
                flush=True,
            )

    output_path = output_dir / f"chronos_sparse_prepredict_{stamp}.json"
    output_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT", output_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
