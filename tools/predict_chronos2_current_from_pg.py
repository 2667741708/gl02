from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from backtest_chronos2_from_pg import (
    CHRONOS_TARGET_IDS,
    ROOT,
    build_payload_for_cutoff,
    db_params,
    post_json,
)
from local_pg_ws_bridge import fetch_chronos_feature_frame


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate current Chronos2 forecasts from PostgreSQL data.")
    parser.add_argument("--db-profile", choices=["local", "22012", "custom"], default="local")
    parser.add_argument("--db-host", default="")
    parser.add_argument("--db-port", default="")
    parser.add_argument("--db-name", default="")
    parser.add_argument("--db-user", default="")
    parser.add_argument("--db-password", default="")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--chronos-url", default="http://127.0.0.1:8777")
    parser.add_argument("--targets", default=",".join(CHRONOS_TARGET_IDS))
    parser.add_argument("--context-minutes", type=int, default=480)
    parser.add_argument("--prediction-minutes", type=int, default=120)
    parser.add_argument("--lookback-days", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=1200)
    parser.add_argument("--output-dir", default=str(ROOT / "chronos外推预测" / "results" / "pg_current_forecast"))
    args = parser.parse_args()

    targets = list(CHRONOS_TARGET_IDS) if args.targets.strip().lower() == "all" else [
        item.strip() for item in args.targets.split(",") if item.strip()
    ]
    params = db_params(args)
    safe_params = {key: ("***" if key == "password" and value else value) for key, value in params.items()}
    print("DB", safe_params, flush=True)
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        frame = fetch_chronos_feature_frame(conn, datetime.now() - timedelta(days=args.lookback_days))
    if frame.empty:
        raise SystemExit("no feature data loaded from PostgreSQL")
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    cutoff = frame.index.max().floor("min")
    payload, skipped = build_payload_for_cutoff(frame, targets, cutoff, args.context_minutes, args.prediction_minutes)
    print(
        f"REQUEST current_cutoff={cutoff} jobs={len(payload['jobs'])} skipped={len(skipped)} "
        f"chronos={args.chronos_url}",
        flush=True,
    )
    result = post_json(args.chronos_url, payload, args.timeout_seconds)
    result["source_cutoff_time"] = cutoff.isoformat(sep=" ")
    result["feature_source"] = payload["feature_source"]
    result["request"] = payload["request"]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"chronos2_current_forecast_{stamp}.json"
    csv_path = output_dir / f"chronos2_current_forecast_{stamp}.csv"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for prediction in result.get("predictions") or []:
        timestamps = prediction.get("future_timestamps") or []
        for idx, ts in enumerate(timestamps):
            rows.append(
                {
                    "target_id": prediction.get("target_id"),
                    "target_name": prediction.get("target_name"),
                    "cutoff_time": prediction.get("cutoff_time") or cutoff.isoformat(sep=" "),
                    "forecast_time": ts,
                    "p10": (prediction.get("p10") or [None] * len(timestamps))[idx],
                    "p50": (prediction.get("p50") or [None] * len(timestamps))[idx],
                    "p90": (prediction.get("p90") or [None] * len(timestamps))[idx],
                    "covariate_count": prediction.get("covariate_count"),
                    "feature_type": prediction.get("feature_type"),
                    "feature_engine": prediction.get("feature_engine"),
                }
            )
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print("FORECAST_JSON", json_path, flush=True)
    print("FORECAST_CSV", csv_path, flush=True)
    for prediction in result.get("predictions") or []:
        p50 = prediction.get("p50") or []
        print(
            "PRED",
            prediction.get("target_id"),
            "cov",
            prediction.get("covariate_count"),
            "points",
            len(p50),
            "first_p50",
            p50[:3],
            "last_p50",
            p50[-3:],
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
